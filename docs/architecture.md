# Architecture

## Request flow

```
                    ┌──────────────────────────────────────────────┐
  Browser           │  FastAPI                                     │
  (Next.js)         │                                              │
      │  POST       │   ┌────────────┐   hit                       │
      │  /api/query │   │   cache    ├──────────────► response     │
      ├────────────►├──►│  (SQLite)  │                             │
      │             │   └─────┬──────┘                             │
      │             │         │ miss                               │
      │             │   ┌─────▼──────┐  over budget                │
      │             │   │ rate limit ├──────────────► 429           │
      │             │   └─────┬──────┘                             │
      │             │         │                                    │
      │             │   ┌─────▼───────────────────────────┐        │
      │             │   │  thread pool (never the loop)   │        │
      │             │   │                                 │        │
      │             │   │   question ──► LLM ──► SQL      │        │
      │             │   │                  ▲      │       │        │
      │             │   │                  │      ▼       │        │
      │             │   │                  │  SQL guard   │        │
      │             │   │         error    │      │       │        │
      │             │   │         feedback │      ▼       │        │
      │             │   │                  └── DuckDB     │        │
      │             │   │                         │       │        │
      │             │   │                         ▼       │        │
      │             │   │                  rows ──► LLM ──┼──► explanation
      │             │   └─────────────────────────────────┘        │
      │             │         │                                    │
      │◄────────────┤    cache + history write                     │
                    └──────────────────────────────────────────────┘
                                      │
                              ┌───────▼────────┐
                              │ 12 Parquet     │
                              │ files, 41M rows│
                              │ scanned lazily │
                              └────────────────┘
```

## Design decisions

### DuckDB over Postgres

41M rows across 12 Parquet files, read-only, single analyst at a time. Postgres
would mean an ETL step, a server to run, and a schema to maintain — for data
that is already columnar and already on disk. DuckDB reads Parquet natively and
runs in-process, so there is no network hop between the query engine and the
API, and the whole thing deploys as one container.

The tradeoff: no concurrent writers and no horizontal scaling. Neither matters
for an analytical read-only workload.

### A view, not a table

```sql
CREATE VIEW taxi AS SELECT * FROM read_parquet('yellow_tripdata_2024-*.parquet')
WHERE tpep_pickup_datetime >= '2024-01-01' AND tpep_pickup_datetime < '2025-01-01'
```

`CREATE TABLE AS` would copy 41M rows into memory at boot — several GB and a
slow start. A view keeps the data on disk and lets DuckDB push filters and
projections down into the Parquet scan, so `SELECT AVG(fare_amount)` touches one
column instead of nineteen. Startup is under a second and aggregates still
return in well under a second.

The date predicate is not cosmetic: the raw TLC files contain a handful of rows
with timestamps in 2002 and 2098, which otherwise show up in every time series.

### Zone names are denormalised, not joined

`PULocationID = 132` is JFK. Nobody knows that, so the raw schema makes the
most natural questions — "average fare from JFK to Midtown" — impossible to
ask. The TLC publishes a 265-row lookup mapping location IDs to borough and
zone name. Two ways to use it:

**A. Denormalise** — `LEFT JOIN` it into the `taxi` view so `pickup_zone` and
`pickup_borough` are just columns.
**B. Expose a `zones` table** and let the model write the joins.

A is not free. Measured on the full 41M rows:

| Query | Plain view | With both joins |
|---|---|---|
| `COUNT(*)` | 116 ms | 313 ms |
| `AVG(fare_amount)` | 148 ms | 340 ms |
| `GROUP BY payment_type` | 133 ms | 342 ms |

About **200 ms, paid by every query** — including the ones that never mention a
zone. DuckDB will not eliminate the unused joins even with a `PRIMARY KEY` on
`LocationID`, because it still has to read both location-ID columns to satisfy
them, which defeats projection pushdown on the Parquet scan.

A won anyway. A response costs 1–7 s, almost all of it two LLM round trips, so
200 ms is 3–10% of wall clock — while writing a correct multi-table join is the
single thing an 8B model fails at most reliably. This trades compute I have
plenty of for accuracy I am short of.

The eval backs the choice rather than just asserting it: all 6 new zone
questions were correct on the first attempt, and the original 36 scored exactly
as they had before the change (28/36). If those numbers had gone the other way,
option B was the fallback.

The join is `LEFT`, not `INNER`: about 4M rows carry location IDs with no
lookup entry, and an inner join would have silently dropped them from every
query in the application — quietly changing the answer to "how many trips were
there?".

### The SQL guard

The model is untrusted input — and so is the SQL editor, where a person types
straight into a box wired to the database. Both go through the same four
layers (`backend/sql_guard.py`):

1. **Statement type**, via DuckDB's own parser. Exactly one statement, and it
   must be a SELECT. This is the same parser that will execute the query, so
   there is no dialect gap — and it settles comment tricks and stacked
   statements (`SELECT 1; DROP TABLE taxi`) for free.
2. **Leading keyword**, because DuckDB reports `PRAGMA ...` as
   `StatementType.SELECT`. The parser alone would let it through.
3. **Identifier denylist**, because `read_csv('/etc/passwd')` is a perfectly
   ordinary SELECT as far as the parser is concerned — and so are
   `duckdb_secrets()`, `duckdb_tables()`, `sqlite_master` and
   `current_setting()`. Checked as bare identifiers rather than function calls,
   since `sqlite_master` needs no parentheses. Whole families are blocked by
   prefix (`duckdb_`, `pragma_`, `sqlite_`, `read_`, …) so a DuckDB upgrade
   that adds a new introspection function is covered without an edit.
   `duckdb_secrets()` is the sharpest of these: it returns nothing today, but
   would hand over storage credentials the moment any are configured.
4. **A row cap pushed into the SQL**, so the database stops producing rows at
   the limit instead of the API truncating 41M rows after the fact.

The connection itself is hardened before any generated SQL reaches it:
extension auto-install and auto-load are disabled, which closes the widest hole
(a SELECT that loads native code).

Data generators (`range`, `generate_series`) are blocked too. They give a
public endpoint unbounded CPU on data that isn't the dataset, and there is
nothing to practise with in them.

The previous implementation was a keyword denylist over `re.findall`. It missed
`COPY ... TO` (writes files), `ATTACH` (mounts other databases), `INSTALL`/`LOAD`,
and any filesystem read from inside a SELECT — and it rejected the harmless
string literal `'drop table'`.

### Self-correction

An 8B model gets DuckDB dialect and column names wrong often enough to matter.
Rather than surfacing `Binder Error: Referenced column "borough" not found`, the
pipeline feeds that error back as a correction turn and lets the model try
again (`MAX_SQL_RETRIES`, default 2).

Its value depends on how good the prompt already is. Against the baseline
prompt it rescued 11 of 36 questions and pushed the valid-SQL rate to 100%.
Once few-shot exemplars fixed most first attempts, only 3 questions still
failed — and those are hard enough that the model repeats the same mistake
given the error, so they now exhaust their retries instead. Self-correction
is a safety net for a mediocre prompt, not a substitute for a good one.

### Caching before rate limiting

Generation runs at temperature 0, so the same question deterministically
produces the same SQL, which makes the whole response safe to memoize. The
cache is checked *before* the rate limiter on purpose: the limit exists to bound
LLM spend, and a cache hit costs nothing, so a throttled visitor can still
explore every question that has already been asked.

### Threadpool offload

`run_pipeline` is fully synchronous — an HTTPS call to Groq plus a DuckDB scan.
Calling it directly from an `async def` handler blocks the event loop and
serialises every concurrent request behind it. It runs in a worker thread
instead, and each request gets its own DuckDB cursor, since a connection is not
safe to use concurrently.

### In-process rate limiting

A sliding window per IP plus a daily global ceiling, held in memory. Correct for
the single-instance free-tier deployment this targets; a multi-instance
deployment would need Redis. That limitation is deliberate and documented rather
than hidden.

## Evaluation

`backend/eval/` measures **execution accuracy**: a generated query is correct
when its result set matches hand-written reference SQL. Text comparison would
call `COUNT(*)` and `SUM(1)` different; result comparison does not.

Rows are compared as an order-insensitive multiset, floats are rounded to 2
decimals, and column names and column order are ignored while column *count* is
not — so aliasing `avg_fare` as `average_fare` passes and so does selecting the
group key second, while volunteering an extra column fails. Columns are
canonicalised by their own values rather than sorted per row, so a result with
the right values but the wrong row pairings is still caught.

CI runs `python -m eval.run --check`, which executes every reference query
without calling the LLM. It costs nothing, needs no API key, and catches the
golden set drifting out of sync with the schema.

`--rescore` re-scores a finished run against corrected reference SQL by
re-executing the stored model output. Generation is the expensive,
non-deterministic half of an evaluation; scoring is neither. When adding the
zone columns made one reference query stale — "how many distinct pickup
zones?" had counted location IDs, because before the join there was nothing
else to count — this recomputed the score exactly, without paying to
regenerate and without letting run-to-run variance masquerade as the effect of
the fix.

## What I would change with more time

- **Streaming explanations over SSE.** The explanation is generated token by
  token but delivered all at once; the perceived latency is worse than the real
  latency.
- **Redis for cache and rate limiting**, if this ever ran on more than one
  instance.
- **A larger eval set.** Repeated runs vary by about 3 points at temperature 0,
  so 36 cases is enough to compare two prompts and not enough to detect a small
  regression. Several hundred cases, and reporting a mean over repeated runs,
  would fix that.
- **The three questions that still fail.** All three are multi-step
  aggregations where the model puts a bare column in the SELECT alongside an
  aggregate. A stricter correction prompt that names the offending column, or a
  larger model for questions the guard flags as complex, would likely close them.
- **Reclaiming the join cost.** The zone columns tax every query ~200 ms even
  when unused. Splitting the view in two and picking one based on whether the
  question mentions a place would recover it, at the cost of a routing decision
  that can itself be wrong.

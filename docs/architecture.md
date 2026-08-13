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

### The SQL guard

The model is untrusted input, so its output is validated in four layers
(`backend/sql_guard.py`):

1. **Statement type**, via DuckDB's own parser. Exactly one statement, and it
   must be a SELECT. This is the same parser that will execute the query, so
   there is no dialect gap — and it settles comment tricks and stacked
   statements (`SELECT 1; DROP TABLE taxi`) for free.
2. **Leading keyword**, because DuckDB reports `PRAGMA ...` as
   `StatementType.SELECT`. The parser alone would let it through.
3. **Function denylist**, because `read_csv('/etc/passwd')` is a perfectly
   ordinary SELECT as far as the parser is concerned.
4. **A row cap pushed into the SQL**, so the database stops producing rows at
   the limit instead of the API truncating 41M rows after the fact.

The connection itself is hardened before any generated SQL reaches it:
extension auto-install and auto-load are disabled, which closes the widest hole
(a SELECT that loads native code).

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
- **Zone names.** `PULocationID` is an opaque integer; joining the TLC zone
  lookup would let people ask about neighbourhoods instead of IDs, which is
  what they actually want.

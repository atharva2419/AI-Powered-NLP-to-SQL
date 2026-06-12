# AI-Powered NL→SQL over NYC Taxi Data

Ask plain-English questions about **3 million NYC taxi trips** and get back the SQL, the results, and a plain-English explanation — powered by **LLaMA 3.1** (Groq) and **DuckDB**.

<!-- Add a screenshot here — drag & drop an image into this file on GitHub -->

---

## Features

- **Natural language → SQL** — type a question, get a DuckDB query back in under 2 seconds
- **Instant results** — DuckDB queries run in-process against a local Parquet file (~3M rows)
- **Plain-English explanation** — the LLM reads the result and writes 1–2 sentences summarising what it means
- **Auto-charts** — results are automatically visualised: a stat card for single values, a bar chart for category breakdowns, a line chart for time series
- **Query history** — every successful query is saved to SQLite; click any past query to instantly restore it
- **Schema explorer** — collapsible panel showing all 19 columns with their types
- **SQL safety** — blocks DROP / DELETE / INSERT / UPDATE / CREATE / ALTER at the server level
- **Fully tested** — 49 backend tests (pytest) + 41 frontend tests (Jest + RTL), CI via GitHub Actions
- **Docker-ready** — one command brings up the full stack

---

## How it works

```
User question
     │
     ▼
LLaMA 3.1 (Groq)  ──► SQL query
                              │
                              ▼
                        DuckDB (in-process)  ──► Result rows
                                                      │
                                                      ▼
                                              LLaMA 3.1 (Groq)  ──► Explanation
```

1. Your question is sent to the FastAPI backend
2. LLaMA 3.1 translates it into a DuckDB SQL query over a `taxi` table
3. DuckDB executes the query against a local Parquet file (no database server needed)
4. LLaMA 3.1 reads the result and writes a short explanation
5. The response (SQL + rows + explanation + latency) is returned to the browser
6. The query is persisted to SQLite for history

---

## Quick start with Docker (recommended)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop).

```bash
# 1. Clone
git clone https://github.com/atharva2419/AI-Powered-NLP-to-SQL.git
cd AI-Powered-NLP-to-SQL

# 2. Add your Groq API key (free at console.groq.com)
echo "GROQ_API_KEY=your_key_here" > .env

# 3. Download the data (~50 MB Parquet file)
python backend/data/download_data.py

# 4. Start
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). The frontend waits for the backend health check before starting, so the app is fully ready on first load.

```bash
# Stop
docker compose down
```

> **Tip:** Re-run `docker compose up --build` after adding Python/npm packages. For code-only changes, `docker compose up` (no `--build`) is faster.

---

## Manual setup (no Docker)

**Prerequisites:** Python 3.10+, Node.js 18+, a free [Groq API key](https://console.groq.com)

```bash
# Clone and configure
git clone https://github.com/atharva2419/AI-Powered-NLP-to-SQL.git
cd AI-Powered-NLP-to-SQL
echo "GROQ_API_KEY=your_key_here" > .env

# Backend
cd backend
pip install -r requirements.txt
python data/download_data.py
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Running tests

```bash
# Backend (49 tests)
pytest backend/tests/ -v

# Frontend (41 tests)
cd frontend && npm test
```

Tests run automatically on every push via GitHub Actions (two parallel jobs: backend pytest + frontend tsc + jest).

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/query` | Translate a question to SQL and run it |
| `GET` | `/api/examples` | Six example questions |
| `GET` | `/api/schema` | All 19 taxi table columns with types |
| `GET` | `/api/history` | Last 20 successful queries (SQLite) |

**POST /api/query — request body:**
```json
{ "question": "What is the average fare amount?" }
```

**POST /api/query — response:**
```json
{
  "sql": "SELECT AVG(fare_amount) FROM taxi",
  "result": { "columns": ["avg(fare_amount)"], "rows": [[14.23]], "row_count": 1 },
  "explanation": "The average fare across all 3M trips is $14.23.",
  "latency_ms": 1840
}
```

---

## Example questions

| Question | Generated SQL |
|----------|---------------|
| How many trips were taken in total? | `SELECT COUNT(*) FROM taxi` |
| What is the average fare amount? | `SELECT AVG(fare_amount) FROM taxi` |
| What hour of the day has the most pickups? | `SELECT HOUR(tpep_pickup_datetime) AS hour, COUNT(*) AS trips FROM taxi GROUP BY hour ORDER BY trips DESC LIMIT 1` |
| What percentage of trips are paid by credit card? | `SELECT ROUND(100.0 * SUM(CASE WHEN payment_type = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct FROM taxi` |
| What is the average trip distance by payment type? | `SELECT payment_type, AVG(trip_distance) AS avg_distance FROM taxi GROUP BY payment_type ORDER BY payment_type` |

---

## Project structure

```
NL-SQL/
├── backend/
│   ├── Dockerfile
│   ├── main.py              # FastAPI app — 4 endpoints + CORS + validation
│   ├── query_engine.py      # LLM → SQL → DuckDB pipeline + safety validation
│   ├── history.py           # SQLite query history (init, save, get)
│   ├── requirements.txt
│   ├── tests/
│   │   ├── conftest.py      # isolated test parquet + temp SQLite DB
│   │   ├── test_main.py     # API endpoint tests (27 tests)
│   │   ├── test_query_engine.py  # pipeline unit tests (13 tests)
│   │   └── test_history.py  # SQLite history tests (9 tests)
│   └── data/
│       ├── taxi.parquet     # not in git — run download_data.py
│       └── history.db       # not in git — auto-created on first run
├── frontend/
│   ├── Dockerfile
│   ├── app/
│   │   └── page.tsx         # Main UI — search, results, chart, history, schema
│   ├── components/
│   │   └── ResultChart.tsx  # Recharts stat card / bar / line renderer
│   ├── lib/
│   │   ├── api.ts           # Typed fetch functions + interfaces
│   │   └── chart.ts         # Result-shape detection (which chart fits?)
│   └── __tests__/
│       ├── api.test.ts      # fetch function tests (12 tests)
│       ├── chart.test.ts    # chart detection tests (10 tests)
│       └── page.test.tsx    # UI component tests (19 tests)
├── .github/workflows/ci.yml # parallel backend + frontend CI
├── docker-compose.yml
├── .env                     # GROQ_API_KEY — not in git
└── .env.example
```

---

## Tech stack

| Layer | Technology |
|-------|------------|
| LLM | LLaMA 3.1 8B via [Groq](https://console.groq.com) |
| Query engine | [DuckDB](https://duckdb.org) (in-process, no server) |
| Data | NYC TLC Yellow Taxi Parquet (~3M rows, ~50 MB) |
| Backend | Python · FastAPI · Pydantic |
| History | SQLite (Python stdlib `sqlite3`) |
| Frontend | Next.js 16 · React · Tailwind CSS v4 |
| Charts | [Recharts](https://recharts.org) |
| Tests | pytest · Jest · React Testing Library |
| CI | GitHub Actions |
| Containers | Docker · docker-compose |

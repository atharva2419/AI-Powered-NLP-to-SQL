# AI-Powered NL→SQL over NYC Taxi Data

Ask plain-English questions about **41 million NYC taxi trips** (full year 2024) and get back the SQL, the results, an auto-generated chart, and a plain-English explanation — powered by **LLaMA 3.1** (Groq) and **DuckDB**.

<!-- Add a screenshot here — drag & drop an image into this file on GitHub -->

---

## Features

- **Natural language → SQL** — type a question, get a DuckDB query back in under 2 seconds
- **Instant results** — DuckDB queries 41M rows lazily via a view over 12 monthly Parquet files; aggregates return in under half a second with nothing loaded into memory at startup
- **Plain-English explanation** — the LLM reads the result and writes 1–2 sentences summarising what it means
- **Auto-charts** — results are automatically visualised: a stat card for single values, a bar chart for category breakdowns, a line chart for time series
- **Query history** — every successful query is saved to SQLite; click any past query to instantly restore it
- **Column glossary** — collapsible panel describing all 19 columns in plain English (including what coded values like `payment_type = 1` mean), so users know what they can ask
- **SQL safety** — blocks DROP / DELETE / INSERT / UPDATE / CREATE / ALTER at the server level
- **Fully tested** — 49 backend tests (pytest) + 46 frontend tests (Jest + RTL), CI via GitHub Actions
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
2. LLaMA 3.1 translates it into a DuckDB SQL query over a `taxi` view
3. DuckDB executes the query lazily against 12 monthly Parquet files (41M rows, no database server, nothing pre-loaded into memory — the view also filters out records with corrupt timestamps)
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

# 3. Download the data (12 monthly Parquet files, ~700 MB total — resumable)
python backend/data/download_data.py

# 4. Start
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). The frontend waits for the backend health check before starting, so the app is fully ready on first load.

```bash
# Stop
docker compose down
```

> **Note:** Source code is baked into the images at build time (only `backend/data/` is volume-mounted), so re-run `docker compose up --build` after **any** code change. Plain `docker compose up` is only enough when nothing but the data changed.

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

# Frontend (46 tests)
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
| Which month had the most trips? | `SELECT MONTH(tpep_pickup_datetime) AS month, COUNT(*) AS trips FROM taxi GROUP BY month ORDER BY trips DESC LIMIT 1` |

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
│       ├── yellow_tripdata_2024-*.parquet  # 12 files, not in git — run download_data.py
│       └── history.db       # not in git — auto-created on first run
├── frontend/
│   ├── Dockerfile
│   ├── app/
│   │   └── page.tsx         # Main UI — search, results, chart, history, schema
│   ├── components/
│   │   └── ResultChart.tsx  # Recharts stat card / bar / line renderer
│   ├── lib/
│   │   ├── api.ts           # Typed fetch functions + interfaces
│   │   ├── chart.ts         # Result-shape detection (which chart fits?)
│   │   └── glossary.ts      # Plain-English column descriptions (TLC data dictionary)
│   └── __tests__/
│       ├── api.test.ts      # fetch function tests (12 tests)
│       ├── chart.test.ts    # chart detection tests (10 tests)
│       ├── glossary.test.ts # glossary coverage tests (4 tests)
│       └── page.test.tsx    # UI component tests (20 tests)
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
| Data | NYC TLC Yellow Taxi Parquet (41M rows, full year 2024, ~700 MB) |
| Backend | Python · FastAPI · Pydantic |
| History | SQLite (Python stdlib `sqlite3`) |
| Frontend | Next.js 16 · React · Tailwind CSS v4 |
| Charts | [Recharts](https://recharts.org) |
| Tests | pytest · Jest · React Testing Library |
| CI | GitHub Actions |
| Containers | Docker · docker-compose |

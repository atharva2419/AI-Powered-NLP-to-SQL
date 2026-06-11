# NL-SQL — Natural Language to SQL over NYC Taxi Data

Ask plain-English questions about 3 million NYC taxi trips and get back the SQL, the results, and a human-readable explanation — powered by LLaMA 3.1 (via Groq) and DuckDB.

<!-- screenshot placeholder: add a screenshot of the UI here -->

---

## How it works

1. **Question** — You type a question in plain English (e.g. *"What hour has the most pickups?"*)
2. **LLM** — LLaMA 3.1 (via Groq) translates it into a DuckDB SQL query against the `taxi` table
3. **DuckDB** — The query runs in-process against a local Parquet file (~3M rows, instant results)
4. **Explanation** — The LLM reads the result and writes 1–2 plain-English sentences summarising what it means

---

## Running with Docker (recommended)

The easiest way to run the full stack. Requires [Docker Desktop](https://www.docker.com/products/docker-desktop).

### 1. Clone and configure

```bash
git clone <repo-url>
cd NL-SQL
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

### 2. Download the data

```bash
python backend/data/download_data.py
```

### 3. Start everything

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000).

The frontend waits for the backend to pass its health check before starting, so the app is fully ready on first load.

To stop:

```bash
docker compose down
```

> **Note:** Re-run `docker compose up --build` after installing new Python or npm packages. For code-only changes, `docker compose up` (no `--build`) is faster.

---

## Running locally (manual setup)

### Prerequisites

- Python 3.10+
- Node.js 18+
- A free [Groq API key](https://console.groq.com)

### 1. Clone

```bash
git clone <repo-url>
cd NL-SQL
```

### 2. Configure

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
python data/download_data.py
uvicorn main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Running tests

### Backend

```bash
pytest backend/tests/ -v
```

### Frontend

```bash
cd frontend
npm test
```

---

## Example questions

| Question | Generated SQL |
|---|---|
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
│   ├── main.py              # FastAPI app (3 endpoints)
│   ├── query_engine.py      # LLM → SQL → DuckDB pipeline
│   ├── requirements.txt
│   ├── tests/
│   │   ├── conftest.py      # test parquet fixture
│   │   ├── test_main.py     # API endpoint tests
│   │   └── test_query_engine.py
│   └── data/
│       └── taxi.parquet     # not in git — run download_data.py
├── frontend/
│   ├── Dockerfile
│   ├── app/
│   │   └── page.tsx         # Main UI
│   ├── lib/
│   │   └── api.ts           # Typed fetch functions
│   └── __tests__/
│       ├── api.test.ts
│       └── page.test.tsx
├── docker-compose.yml
├── .env                     # GROQ_API_KEY (not in git)
└── .env.example
```

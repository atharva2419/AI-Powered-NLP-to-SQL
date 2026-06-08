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

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- A free [Groq API key](https://console.groq.com)

### 1. Clone

```bash
git clone <repo-url>
cd NL-SQL
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

Download the data:

```bash
python data/download_data.py
```

Start the API server:

```bash
uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

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
│   ├── main.py           # FastAPI app (3 endpoints)
│   ├── query_engine.py   # LLM → SQL → DuckDB pipeline
│   ├── requirements.txt
│   └── data/
│       └── taxi.parquet
├── frontend/
│   ├── app/
│   │   └── page.tsx      # Main UI
│   └── lib/
│       └── api.ts        # Typed fetch functions
└── .env                  # GROQ_API_KEY
```

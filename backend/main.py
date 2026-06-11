import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import history
import query_engine  # noqa: F401 — loads DuckDB table at import time
from query_engine import _con, run_pipeline

EXAMPLES = [
    "How many trips were taken in total?",
    "What hour of the day has the most pickups?",
    "What is the average fare amount?",
    "Which day of the week is busiest?",
    "What percentage of trips are paid by credit card?",
    "What is the average trip distance by payment type?",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    history.init_db()
    print("DuckDB ready — taxi table pre-loaded")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    msg = exc.errors()[0]["msg"] if exc.errors() else "Invalid request"
    return JSONResponse(status_code=400, content={"error": msg})


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


@app.post("/api/query")
async def post_query(req: QueryRequest):
    try:
        t0 = time.perf_counter()
        out = run_pipeline(req.question)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if "error" in out.get("result", {}):
            return JSONResponse(status_code=400, content={"error": out["result"]["error"]})
        try:
            history.save_query(
                req.question, out["sql"], out["result"], out["explanation"], latency_ms
            )
        except Exception:
            pass  # never let history writes break the response
        return {
            "sql": out["sql"],
            "result": out["result"],
            "explanation": out["explanation"],
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/api/examples")
async def get_examples():
    return {"examples": EXAMPLES}


@app.get("/api/schema")
async def get_schema():
    rows = _con.execute(
        "SELECT column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_name = 'taxi' "
        "ORDER BY ordinal_position"
    ).fetchall()
    return {"columns": [{"name": col, "type": dtype} for col, dtype in rows]}


@app.get("/api/history")
async def get_query_history():
    return {"history": history.get_history(limit=20)}

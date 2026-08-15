import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import cache
import config
import history
import metrics
import ratelimit
import sql_guard
from query_engine import _SCHEMA, ROW_COUNT, _con, run_pipeline, run_query
from sql_guard import SQLGuardError

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
log = logging.getLogger("nlsql.api")

EXAMPLES = [
    "How many trips were taken in total?",
    "What hour of the day has the most pickups?",
    "What is the average fare from JFK Airport?",
    "How many trips started in each borough?",
    "What percentage of trips are paid by credit card?",
    "What is the average trip distance by payment type?",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    history.init_db()
    cache.init_db()
    log.info(
        "ready - model=%s cache=%s rate_limit=%s",
        config.MODEL_NAME,
        config.CACHE_ENABLED,
        config.RATE_LIMIT_ENABLED,
    )
    yield


app = FastAPI(
    title="NYC Taxi NL→SQL API",
    description="Natural-language questions over 41M NYC taxi trips, answered with DuckDB.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Tag every request with an id and log its outcome and duration."""
    request_id = uuid.uuid4().hex[:8]
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    log.info(
        "%s %s %s %dms id=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    msg = exc.errors()[0]["msg"] if exc.errors() else "Invalid request"
    return JSONResponse(status_code=400, content={"error": msg})


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


def _client_ip(request: Request) -> str:
    # Behind a platform proxy (Fly/Render/Vercel) the peer address is the
    # proxy, so prefer the first hop in X-Forwarded-For when present.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.post("/api/query")
async def post_query(req: QueryRequest, request: Request):
    metrics.incr("queries_total")
    t0 = time.perf_counter()

    # Cache before rate limit, deliberately: the limit exists to bound LLM
    # spend, and a cache hit costs nothing. A throttled visitor can still
    # explore every example question instead of hitting a wall.
    cached = cache.get(req.question)
    if cached is not None:
        metrics.incr("cache_hits")
        latency_ms = int((time.perf_counter() - t0) * 1000)
        metrics.observe_latency(latency_ms)
        return {**cached, "latency_ms": latency_ms, "cached": True}

    try:
        ratelimit.check(_client_ip(request))
    except ratelimit.RateLimitExceeded as exc:
        metrics.incr("rate_limited")
        return JSONResponse(
            status_code=429,
            content={"error": exc.message},
            headers={"Retry-After": str(exc.retry_after)},
        )

    try:
        # run_pipeline is fully synchronous (HTTP to Groq + DuckDB scans).
        # Calling it directly would block the event loop and serialise every
        # concurrent request behind this one.
        out = await run_in_threadpool(run_pipeline, req.question)
    except SQLGuardError as exc:
        metrics.incr("errors")
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        metrics.incr("errors")
        log.exception("pipeline failed")
        return JSONResponse(
            status_code=502,
            content={"error": f"The query service failed: {exc}"},
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)
    metrics.observe_latency(latency_ms)

    if "error" in out.get("result", {}):
        metrics.incr("errors")
        return JSONResponse(status_code=400, content={"error": out["result"]["error"]})

    payload = {
        "sql": out["sql"],
        "result": out["result"],
        "explanation": out["explanation"],
        "attempts": out.get("attempts", 1),
    }
    cache.put(req.question, payload)

    try:
        history.save_query(
            req.question, out["sql"], out["result"], out["explanation"], latency_ms
        )
    except Exception:
        log.warning("history write failed", exc_info=True)

    return {**payload, "latency_ms": latency_ms, "cached": False}


class ExecuteRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=5000)


@app.post("/api/execute")
async def post_execute(req: ExecuteRequest, request: Request):
    """Run SQL the user typed or edited themselves.

    This is what makes the SQL box a learning tool rather than a read-only
    display: tweak the query, run it, see what changes. No LLM is involved, so
    it is fast, free, and charged against a separate allowance.

    Hand-written SQL is exactly as untrusted as model-written SQL, so it goes
    through the same guard — one SELECT, no filesystem access, row cap pushed
    into the query, wall-clock timeout. The guard was never LLM-specific; it
    validates SQL, whoever wrote it.
    """
    metrics.incr("executions_total")
    t0 = time.perf_counter()

    try:
        ratelimit.check(_client_ip(request), bucket="sql")
    except ratelimit.RateLimitExceeded as exc:
        metrics.incr("rate_limited")
        return JSONResponse(
            status_code=429,
            content={"error": exc.message},
            headers={"Retry-After": str(exc.retry_after)},
        )

    try:
        sql = sql_guard.validate(req.sql)
    except SQLGuardError as exc:
        metrics.incr("execute_rejected")
        return JSONResponse(status_code=400, content={"error": str(exc)})

    result = await run_in_threadpool(run_query, sql)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if "error" in result:
        metrics.incr("execute_errors")
        return JSONResponse(status_code=400, content={"error": result["error"]})

    return {"sql": sql, "result": result, "latency_ms": latency_ms}


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
    # row_count rides along with the schema rather than getting its own
    # endpoint: the frontend already fetches this on load, and the dataset
    # size is part of describing what you can ask about.
    return {
        "columns": [{"name": col, "type": dtype} for col, dtype in rows],
        "row_count": ROW_COUNT,
    }


@app.get("/api/history")
async def get_query_history():
    return {"history": history.get_history(limit=20)}


@app.get("/api/metrics")
async def get_metrics():
    """Operational counters: throughput, cache hit rate, latency spread."""
    return {
        **metrics.snapshot(),
        "cache": cache.stats(),
        "rate_limit": ratelimit.snapshot(),
    }


@app.get("/health")
async def health():
    """Liveness probe — confirms the DuckDB view is queryable, not just that
    the process is up. Used by the Docker healthcheck and the host platform."""
    try:
        _con.execute("SELECT 1 FROM taxi LIMIT 1").fetchall()
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "detail": str(exc)})
    return {"status": "ok", "model": config.MODEL_NAME, "columns": len(_SCHEMA.split(","))}

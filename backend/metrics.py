"""In-process metrics.

Deliberately dependency-free: a hosted demo on a free tier has no Prometheus
to scrape it, and the numbers that matter here (cache hit rate, how often the
model needs a second attempt, latency spread) are few enough to keep in
memory. Latencies are kept in a bounded deque so memory stays flat.
"""

import threading
from collections import deque

_MAX_SAMPLES = 1000

_lock = threading.Lock()
_counters: dict[str, int] = {}
_latencies: deque[int] = deque(maxlen=_MAX_SAMPLES)


def incr(name: str, amount: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + amount


def observe_latency(ms: int) -> None:
    with _lock:
        _latencies.append(ms)


def reset() -> None:
    with _lock:
        _counters.clear()
        _latencies.clear()


def _percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    # Nearest-rank percentile: simple, and exact for the small sample sizes here.
    idx = min(len(sorted_values) - 1, int(round(pct / 100 * len(sorted_values) + 0.5)) - 1)
    return sorted_values[max(idx, 0)]


def snapshot() -> dict:
    with _lock:
        counters = dict(_counters)
        samples = sorted(_latencies)

    total = counters.get("queries_total", 0)
    hits = counters.get("cache_hits", 0)
    return {
        "counters": counters,
        "cache_hit_rate": round(hits / total, 3) if total else 0.0,
        "latency_ms": {
            "count": len(samples),
            "p50": _percentile(samples, 50),
            "p95": _percentile(samples, 95),
            "max": samples[-1] if samples else 0,
        },
    }

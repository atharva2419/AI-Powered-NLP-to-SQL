"""Per-IP and global rate limiting for the hosted demo.

Each question costs two LLM calls against a personal API key, so an
unthrottled public endpoint is a way to hand a stranger the bill. Two limits
apply together: a sliding window per client IP (stops one visitor hammering
it) and a daily global ceiling (bounds total spend no matter how many
visitors show up).

In-process and dependency-free — correct for the single-instance free-tier
deployment this targets. A multi-instance deployment would need Redis; that
tradeoff is deliberate and documented rather than hidden.
"""

import threading
import time
from collections import defaultdict, deque

import config

_HOUR = 3600
_DAY = 86400

_lock = threading.Lock()
# Keyed by (bucket, client ip). Buckets exist because the two endpoints cost
# very different things: an NL question spends real money on two LLM calls,
# while re-running edited SQL costs only local CPU. Charging both against one
# allowance would mean a few minutes of learning in the SQL editor locks you
# out of asking questions.
_per_ip: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_global: deque[float] = deque()


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


def _prune(window: deque[float], horizon: float, now: float) -> None:
    while window and now - window[0] > horizon:
        window.popleft()


def _retry_after(window: deque[float], horizon: float, now: float) -> int:
    """Seconds until the oldest request in the window ages out.

    An empty window means the limit is configured at zero — nothing will ever
    age out, so quote the full horizon rather than indexing into it.
    """
    if not window:
        return int(horizon)
    return max(1, int(horizon - (now - window[0])))


def check(client_ip: str, bucket: str = "llm") -> None:
    """Record a request for ``client_ip``, or raise :class:`RateLimitExceeded`.

    ``bucket`` selects which allowance to charge. Only the "llm" bucket counts
    against the global daily budget, because only it spends money; "sql" covers
    re-running edited SQL, which is local CPU and gets a far looser ceiling.
    """
    if not config.RATE_LIMIT_ENABLED:
        return

    is_llm = bucket == "llm"
    hourly_limit = (
        config.RATE_LIMIT_PER_HOUR if is_llm else config.EXECUTE_RATE_LIMIT_PER_HOUR
    )

    now = time.time()
    with _lock:
        if is_llm:
            _prune(_global, _DAY, now)
            if len(_global) >= config.RATE_LIMIT_GLOBAL_PER_DAY:
                raise RateLimitExceeded(
                    "The demo has hit its daily query budget. Try again tomorrow, "
                    "or run it locally with your own Groq key.",
                    retry_after=_retry_after(_global, _DAY, now),
                )

        window = _per_ip[(bucket, client_ip)]
        _prune(window, _HOUR, now)
        if len(window) >= hourly_limit:
            noun = "questions" if is_llm else "query runs"
            raise RateLimitExceeded(
                f"Rate limit reached ({hourly_limit} {noun} per hour). "
                + ("Cached questions still work — try an example." if is_llm
                   else "Give it a few minutes."),
                retry_after=_retry_after(window, _HOUR, now),
            )

        window.append(now)
        if is_llm:
            _global.append(now)


def reset() -> None:
    with _lock:
        _per_ip.clear()
        _global.clear()


def snapshot() -> dict:
    now = time.time()
    with _lock:
        _prune(_global, _DAY, now)
        return {
            "enabled": config.RATE_LIMIT_ENABLED,
            "queries_last_24h": len(_global),
            "daily_budget": config.RATE_LIMIT_GLOBAL_PER_DAY,
            "tracked_clients": len(_per_ip),
        }

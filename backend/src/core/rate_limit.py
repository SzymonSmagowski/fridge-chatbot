"""slowapi limiter singleton + 429 response handler.

Backed by Redis so multiple uvicorn workers share one counter. Per §5.10 the
JSON body always includes `retry_after_sec` so the FE can show a countdown.
"""
from __future__ import annotations

import math
from functools import lru_cache

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.core.settings import Settings


@lru_cache
def get_limiter(settings: Settings | None = None) -> Limiter:
    """Process-wide Limiter; uses Redis storage so workers share counters."""
    s = settings or Settings()
    return Limiter(
        key_func=get_remote_address,
        storage_uri=s.REDIS_URL,
        strategy="fixed-window",
    )


def rate_limit_exceeded_handler(
    request: Request,  # noqa: ARG001 — FastAPI signature
    exc: RateLimitExceeded,
) -> JSONResponse:
    """Translate slowapi's exception to the §5.10 envelope."""
    # slowapi exposes the limit string ("5/minute") and remaining window seconds
    # via exc.detail / exc.limit. Window length is parsed from the limit string.
    retry_after = _extract_retry_after_sec(exc)
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        content={
            "code": "auth.rate_limited",
            "detail": (
                f"Too many requests. Try again in {retry_after}s."
            ),
            "retry_after_sec": retry_after,
        },
    )


_PERIOD_SECONDS: dict[str, int] = {
    "second": 1, "seconds": 1,
    "minute": 60, "minutes": 60,
    "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
}


def _extract_retry_after_sec(exc: RateLimitExceeded) -> int:
    """Best-effort retry estimate from a slowapi RateLimitExceeded.

    Falls back to ceiling of the limit window when slowapi doesn't expose a
    fresher remaining-time hint.
    """
    detail = str(getattr(exc, "detail", "") or "")
    # detail looks like "5 per 1 minute" — parse the trailing period word.
    parts = detail.lower().split()
    for i, token in enumerate(parts):
        if token in _PERIOD_SECONDS and i > 0:
            try:
                amount = int(parts[i - 1])
            except ValueError:
                amount = 1
            return max(1, math.ceil(amount * _PERIOD_SECONDS[token]))
    return 60

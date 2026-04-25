"""Async Redis client singleton.

Used by:
- core/cache.py (cache-aside reads + writes)
- core/pubsub.py / services/chat_streaming.py (pub/sub channels)
- core/rate_limit.py (slowapi storage URI)
- services/google_token_service.py (access-token cache)
"""
from __future__ import annotations

from redis.asyncio import Redis

from src.core.settings import Settings

_client: Redis | None = None


def get_redis_client(settings: Settings) -> Redis:
    """Return the process-wide async Redis client, creating it lazily."""
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis_client() -> None:
    """Close the process-wide client (called from FastAPI lifespan shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None

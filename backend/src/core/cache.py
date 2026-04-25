"""Cache-aside helper with single-flight (SETNX) protection and pattern invalidation.

Discipline lives in the caller: every write endpoint must invalidate the keys it
mutated per the §7.6 invalidation map. The helper itself is intentionally tight.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Awaitable, Callable, TypeVar

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.services.logger import get_logger

logger = get_logger("cache")

T = TypeVar("T")

LOCK_WAIT_MAX_SECONDS = 2.0
LOCK_TTL_SECONDS = 5
SCAN_BATCH = 200


def sha1_short(payload: dict[str, Any]) -> str:
    """Stable short hash for cache keys derived from filter dicts."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


async def cache_aside(
    redis: Redis,
    key: str,
    ttl_seconds: int,
    fetcher: Callable[[], Awaitable[T]],
    serializer: Callable[[T], str] = json.dumps,
    deserializer: Callable[[str], T] = json.loads,
) -> T:
    """Read-through cache with SETNX single-flight stampede protection.

    On any RedisError we fall through to the fetcher — Redis outages must not
    take the API down.
    """
    try:
        cached = await redis.get(key)
    except RedisError as exc:
        logger.warning("cache get failed for %s: %s", key, exc)
        return await fetcher()

    if cached is not None:
        return deserializer(cached)

    lock_key = f"lock:{key}"
    try:
        got_lock = await redis.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS)
    except RedisError as exc:
        logger.warning("cache lock failed for %s: %s", key, exc)
        return await fetcher()

    if not got_lock:
        # Someone else is fetching; brief wait then read again.
        deadline_steps = int(LOCK_WAIT_MAX_SECONDS * 10)
        for _ in range(deadline_steps):
            await asyncio.sleep(0.1)
            try:
                cached = await redis.get(key)
            except RedisError:
                break
            if cached is not None:
                return deserializer(cached)
        # Give up waiting; fetch ourselves anyway.

    try:
        value = await fetcher()
        try:
            await redis.set(key, serializer(value), ex=ttl_seconds)
        except RedisError as exc:
            logger.warning("cache set failed for %s: %s", key, exc)
        return value
    finally:
        try:
            await redis.delete(lock_key)
        except RedisError:
            pass


async def invalidate(redis: Redis, *patterns: str) -> None:
    """Delete the given keys. Patterns containing '*' are expanded via SCAN.

    No-op on Redis errors — invalidation failure is logged but never raised so
    that writes still complete; stale data drains via TTL within minutes.
    """
    try:
        for pattern in patterns:
            if "*" in pattern:
                cursor: int = 0
                while True:
                    cursor, keys = await redis.scan(
                        cursor=cursor, match=pattern, count=SCAN_BATCH
                    )
                    if keys:
                        await redis.delete(*keys)
                    if cursor == 0:
                        break
            else:
                await redis.delete(pattern)
    except RedisError as exc:
        logger.warning("cache invalidate failed for %s: %s", patterns, exc)


def family_key(family_id: Any, *parts: str) -> str:
    """Build the family-scoped cache key prefix used throughout the API."""
    return ":".join(["family", str(family_id), *parts])

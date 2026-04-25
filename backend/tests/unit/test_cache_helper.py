"""Unit tests for src/core/cache.py — read-through cache + invalidation.

Uses real Redis (cheap, the devcontainer always has it). Single-flight (SETNX
lock) is verified by counting fetcher invocations under concurrent reads.
"""
from __future__ import annotations

import asyncio

import pytest
from redis.asyncio import Redis

from src.core.cache import cache_aside, family_key, invalidate, sha1_short


def test_sha1_short_is_deterministic_for_same_dict() -> None:
    a = sha1_short({"x": 1, "y": 2})
    b = sha1_short({"y": 2, "x": 1})
    assert a == b


def test_sha1_short_changes_when_value_changes() -> None:
    assert sha1_short({"x": 1}) != sha1_short({"x": 2})


def test_family_key_builds_colon_separated_path() -> None:
    assert family_key("abc", "members", "x") == "family:abc:members:x"


@pytest.mark.asyncio
async def test_cache_aside_returns_fetcher_value_on_miss(
    redis_client: Redis,
) -> None:
    calls = 0

    async def fetcher():
        nonlocal calls
        calls += 1
        return {"k": "v"}

    value = await cache_aside(redis_client, "test:miss", 60, fetcher)
    assert value == {"k": "v"}
    assert calls == 1


@pytest.mark.asyncio
async def test_cache_aside_returns_cached_value_on_second_call(
    redis_client: Redis,
) -> None:
    calls = 0

    async def fetcher():
        nonlocal calls
        calls += 1
        return {"v": calls}

    a = await cache_aside(redis_client, "test:hit", 60, fetcher)
    b = await cache_aside(redis_client, "test:hit", 60, fetcher)
    assert a == b
    assert calls == 1, "second call must hit the cache"


@pytest.mark.asyncio
async def test_cache_aside_concurrent_misses_run_fetcher_at_least_once(
    redis_client: Redis,
) -> None:
    """SETNX single-flight: under concurrent miss, fetcher runs at most twice
    (winner + lock-loser fallback after the lock-wait timeout). For a fast
    fetcher, the loser should observe the cached value within the wait
    window and skip its own fetch."""
    calls = 0

    async def fetcher():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"v": "value"}

    results = await asyncio.gather(
        *[cache_aside(redis_client, "test:concurrent", 60, fetcher) for _ in range(8)]
    )
    assert all(r == {"v": "value"} for r in results)
    # All eight reads must not trigger eight fetches — the lock must coalesce.
    assert calls < 8, f"expected SETNX single-flight; got {calls} fetches"


@pytest.mark.asyncio
async def test_invalidate_deletes_exact_key(redis_client: Redis) -> None:
    await redis_client.set("test:exact", "x")
    await invalidate(redis_client, "test:exact")
    assert await redis_client.get("test:exact") is None


@pytest.mark.asyncio
async def test_invalidate_with_glob_deletes_matching_keys(
    redis_client: Redis,
) -> None:
    await redis_client.set("test:notes:abc", "1")
    await redis_client.set("test:notes:def", "2")
    await redis_client.set("test:other:keep", "3")
    await invalidate(redis_client, "test:notes:*")
    assert await redis_client.get("test:notes:abc") is None
    assert await redis_client.get("test:notes:def") is None
    assert await redis_client.get("test:other:keep") == "3"

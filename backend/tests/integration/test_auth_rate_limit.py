"""Integration tests for §5.10 — legacy /auth/* rate-limited via slowapi.

Per Architect:
- POST /auth/login → 5/min/IP
- POST /auth/register → 3/min/IP
- POST /auth/refresh → 10/min/IP
- 429 envelope: {"code": "auth.rate_limited", "detail": "Too many requests. Try again in 60s.", "retry_after_sec": 60}
- Retry-After HTTP header set to the same value.

The slowapi limiter holds counters in Redis — tests pre-flush so counts start clean.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
async def reset_rate_limits(redis_client) -> None:
    """slowapi keys live under `LIMITER/...` — wipe between tests."""
    await redis_client.flushdb()


def _login(client: TestClient, username: str = "nobody") -> int:
    resp = client.post(
        "/auth/login",
        json={"username": username, "password": "wrong"},
    )
    return resp.status_code


def test_login_returns_429_with_envelope_after_5_attempts(
    client: TestClient,
) -> None:
    # 5 misses are 401 (invalid creds); the 6th is 429.
    for _ in range(5):
        assert _login(client) == 401
    resp = client.post(
        "/auth/login",
        json={"username": "nobody", "password": "wrong"},
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body == {
        "code": "auth.rate_limited",
        "detail": "Too many requests. Try again in 60s.",
        "retry_after_sec": 60,
    }
    assert resp.headers.get("Retry-After") == "60"


def test_register_returns_429_after_3_attempts(client: TestClient) -> None:
    # /auth/register limit is 3/min. 3 OK-ish (409 since same username), 4th is 429.
    for _ in range(3):
        client.post(
            "/auth/register",
            json={"username": "u", "password": "x", "email": None},
        )
    resp = client.post(
        "/auth/register",
        json={"username": "u", "password": "x", "email": None},
    )
    assert resp.status_code == 429
    assert resp.json()["code"] == "auth.rate_limited"

"""Integration tests for slowapi rate-limit decorators on REST endpoints.

What's covered:
- `POST /api/pairing/start` — 10/minute per IP. 11th request → 429 with
  the §5.10 envelope (`code`, `detail`, `retry_after_sec`). Tier A/8.
- `POST /api/feedback` — 10/minute per device. 11th request → 429.
  Tier A/9.
- `POST /api/calendar/sync/pull` — 5/minute keyed by JWT subject (NOT
  IP), so two different devices on the same client IP each get their own
  budget. Tier B/12.

slowapi storage is Redis-backed (REDIS_URL → DB 0 by default). The
`reset_rate_limit_storage` fixture wipes that storage before each test so
buckets from a prior test don't poison this one.

Quality bar: NO `time.sleep` for window expiry. We always reset before
asserting; the limit-window math doesn't need to advance.
"""
from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Slowapi storage cleaner — must run BEFORE each test that uses the limiter,
# otherwise leftover counts from a previous test can cause false 429s.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_rate_limit_storage() -> Iterator[None]:
    """Wipe slowapi's Redis-backed storage before AND after each test.

    Both endpoints share one Limiter (it's an `lru_cache`d singleton), and
    its storage lives in the same Redis instance the rest of the app uses.
    `storage.reset()` deletes every key with the slowapi prefix.
    """
    from src.core.rate_limit import get_limiter

    limiter = get_limiter()
    try:
        limiter.limiter.storage.reset()
    except Exception:
        # storage.reset() needs at least one key to scan; on a clean DB
        # the underlying scan returns 0 deletions. Swallow.
        pass
    yield
    try:
        limiter.limiter.storage.reset()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Stub OAuth so /pairing/start doesn't error on the missing client.
# ---------------------------------------------------------------------------


@pytest.fixture
def oauth_stub(app):
    from src.core import dependencies as deps

    class _Stub:
        def build_authorize_url(self, state: str) -> tuple[str, str]:
            return (
                f"https://accounts.google.com/o/oauth2/v2/auth?state={state}",
                "stub-cv",
            )

    app.dependency_overrides[deps.get_google_oauth_service] = lambda: _Stub()
    yield


# ---------------------------------------------------------------------------
# Tier A/8 — pairing rate limit
# ---------------------------------------------------------------------------


def test_pairing_start_rate_limit_blocks_eleventh_call_with_429(
    client: TestClient, oauth_stub
) -> None:
    """10/minute per remote IP. The 11th burst call must return 429 with
    the §5.10 envelope (`code`, `detail`, `retry_after_sec`).
    """
    payload = {"device_label": "Kitchen"}
    for i in range(10):
        r = client.post("/api/pairing/start", json=payload)
        assert r.status_code == 200, f"call {i + 1} should succeed, got {r.status_code} {r.text}"

    blocked = client.post("/api/pairing/start", json=payload)
    assert blocked.status_code == 429, blocked.text
    body = blocked.json()
    # §5.10 envelope.
    assert body.get("code") == "auth.rate_limited"
    assert "Try again" in body.get("detail", "")
    assert isinstance(body.get("retry_after_sec"), int)
    assert body["retry_after_sec"] > 0
    # Retry-After header is set so a transparent FE polling loop works.
    assert blocked.headers.get("Retry-After")


def test_pairing_start_rate_limit_first_ten_calls_succeed(
    client: TestClient, oauth_stub
) -> None:
    """Boundary: exactly 10 requests in window must all succeed."""
    for i in range(10):
        r = client.post("/api/pairing/start", json={"device_label": f"k{i}"})
        assert r.status_code == 200, (
            f"call {i + 1} should succeed within budget, got {r.status_code}"
        )


# ---------------------------------------------------------------------------
# Tier A/9 — feedback rate limit (per-device)
# ---------------------------------------------------------------------------


def test_post_feedback_rate_limit_blocks_eleventh_call_with_429(
    client: TestClient, family
) -> None:
    """10/minute per device JWT subject."""
    _family_id, _device_id, token = family
    headers = {"Authorization": f"Bearer {token}"}
    body = {"category": "bug", "message": "lots of feedback"}
    for i in range(10):
        r = client.post("/api/feedback", headers=headers, json=body)
        assert r.status_code == 201, f"call {i + 1} got {r.status_code}: {r.text}"

    blocked = client.post("/api/feedback", headers=headers, json=body)
    assert blocked.status_code == 429
    payload = blocked.json()
    assert payload.get("code") == "auth.rate_limited"
    assert isinstance(payload.get("retry_after_sec"), int)


def test_post_feedback_rate_limit_separate_devices_have_separate_budgets(
    client: TestClient, make_family
) -> None:
    """Per-device key: device A burning its 10/min budget must not affect
    device B's budget. Verifies the slowapi key_func reads the JWT sub.
    """
    _, _, token_a = make_family(family_name="Alpha")
    _, _, token_b = make_family(family_name="Bravo")
    body = {"category": "bug", "message": "x"}

    for i in range(10):
        r = client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {token_a}"},
            json=body,
        )
        assert r.status_code == 201, f"A call {i + 1} got {r.status_code}: {r.text}"

    # A is now exhausted. B's first call MUST still succeed.
    r_b = client.post(
        "/api/feedback",
        headers={"Authorization": f"Bearer {token_b}"},
        json=body,
    )
    assert r_b.status_code == 201, (
        "Device B's first call shouldn't be blocked by Device A's "
        f"exhaustion: got {r_b.status_code} {r_b.text}"
    )


# ---------------------------------------------------------------------------
# Tier B/12 — calendar pull rate limit (per-device, NOT per-IP)
# ---------------------------------------------------------------------------


def test_calendar_pull_rate_limit_keyed_by_device_not_ip(
    client: TestClient, db, make_family
) -> None:
    """Two devices on the same TestClient IP each get their own 5/min budget.

    Implementation note: /api/calendar/sync/pull returns 404 on the very
    first call here (member_id is unknown), but slowapi runs BEFORE the
    auth dep + handler body — it counts the request against the per-device
    bucket regardless. So we burn 5 calls on device A, then verify device
    B's first call STILL returns 404 (not 429).
    """
    from uuid import uuid4

    family_a_id, _device_a_id, token_a = make_family(family_name="A")
    family_b_id, _device_b_id, token_b = make_family(family_name="B")
    member_id = uuid4()  # unknown — handler will 404, but the limiter still counts

    # Burn device A's 5/min budget.
    for i in range(5):
        r = client.post(
            f"/api/calendar/sync/pull?member_id={member_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        # Either 404 (member not found) or 409 (no token). Anything other
        # than 429 means we're below A's budget cap.
        assert r.status_code != 429, (
            f"A call {i + 1} unexpectedly 429'd: {r.text}"
        )

    # Device A's 6th call MUST now 429 — its budget is exhausted.
    r_a_blocked = client.post(
        f"/api/calendar/sync/pull?member_id={member_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_a_blocked.status_code == 429, (
        f"Device A 6th call should be rate-limited, got {r_a_blocked.status_code}: {r_a_blocked.text}"
    )

    # Device B's FIRST call must NOT be rate-limited — different JWT sub
    # → different bucket. (It can return 404/409, just not 429.)
    r_b = client.post(
        f"/api/calendar/sync/pull?member_id={member_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r_b.status_code != 429, (
        "Device B's first call shouldn't share a bucket with Device A: "
        f"got {r_b.status_code} {r_b.text}"
    )

"""Integration tests for cursor pagination on the threads chat-history surface.

What's covered:
- `GET /threads/{id}` returns the new envelope shape (thread meta + first
  page of messages) — Tier C/regression.
- `GET /threads/{id}/messages?before=&limit=` paginates correctly across
  multiple pages, with no gaps and no duplicates — Tier A/1.
- Edge cases: empty thread, exactly-one-page thread, malformed cursor,
  cross-thread cursor leak, limit clamping — Tier A/1, Tier A/2.
- Auth + ownership: 401 unauth, 403 cross-user — Tier A/3.

These hit the real dev_test Postgres via the conftest harness; they do NOT
touch the chat WS or the LLM — pagination is a pure REST concern.

Naming: behavior-first per the BackendTester rules. Each name reads like a
spec line; no `_endpoint_works`-style names.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.database import Message, Thread, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thread_with_messages(
    db: Session,
    *,
    family,
    n_messages: int,
    base_time: datetime | None = None,
) -> tuple[Thread, list[Message]]:
    """Seed a thread owned by the family's shadow user with N controlled-time
    messages. Returns the thread and its messages in INSERTION ORDER (oldest
    first); the API will return them DESC by created_at.

    Each message is spaced 1 second apart so the order is deterministic and
    `created_at` ties (which would otherwise force the message_id tiebreaker)
    are avoided. A separate test exercises the tiebreaker explicitly.
    """
    family_id, device_id, _token = family
    # Look up the shadow user via the device.
    from src.models import Device

    device = db.query(Device).filter(Device.id == device_id).first()
    assert device is not None
    user = db.query(User).filter(User.id == device.shadow_user_id).first()
    assert user is not None

    thread = Thread(user_id=user.id, title="Pagination Test Thread")
    db.add(thread)
    db.flush()

    base = base_time or datetime(2026, 5, 1, 12, 0, 0)
    msgs: list[Message] = []
    for i in range(n_messages):
        m = Message(
            thread_id=thread.thread_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"message {i}",
            type="message",
            created_at=base + timedelta(seconds=i),
        )
        db.add(m)
        msgs.append(m)
    db.commit()
    db.refresh(thread)
    for m in msgs:
        db.refresh(m)
    return thread, msgs


def _auth_for(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tier A/1 — pagination correctness
# ---------------------------------------------------------------------------


def test_messages_pagination_returns_consecutive_pages_without_gaps(
    client: TestClient, db, family
) -> None:
    """75 messages → 30 + 30 + 15, no overlaps, no missing rows."""
    _family_id, _device_id, token = family
    thread, seeded = _make_thread_with_messages(db, family=family, n_messages=75)

    # Page 1 — initial /threads/{id} envelope.
    r1 = client.get(f"/threads/{thread.id}", headers=_auth_for(token))
    assert r1.status_code == 200
    page1 = r1.json()
    assert page1["has_more"] is True
    assert page1["next_cursor"] is not None
    assert len(page1["messages"]) == 30

    # Page 2 — explicit /messages with cursor.
    r2 = client.get(
        f"/threads/{thread.id}/messages",
        params={"before": page1["next_cursor"], "limit": 30},
        headers=_auth_for(token),
    )
    assert r2.status_code == 200
    page2 = r2.json()
    assert page2["has_more"] is True
    assert page2["next_cursor"] is not None
    assert len(page2["messages"]) == 30

    # Page 3 — last 15.
    r3 = client.get(
        f"/threads/{thread.id}/messages",
        params={"before": page2["next_cursor"], "limit": 30},
        headers=_auth_for(token),
    )
    assert r3.status_code == 200
    page3 = r3.json()
    assert page3["has_more"] is False
    assert page3["next_cursor"] is None
    assert len(page3["messages"]) == 15

    # Concatenate; assert it's exactly the seeded list reversed (newest first),
    # by content. No dupes, no gaps.
    streamed = (
        page1["messages"] + page2["messages"] + page3["messages"]
    )
    assert len(streamed) == 75
    expected_reverse = list(reversed([m.content for m in seeded]))
    assert [m["content"] for m in streamed] == expected_reverse

    # No duplicate IDs across pages.
    ids = [m["id"] for m in streamed]
    assert len(set(ids)) == 75


def test_messages_pagination_thread_with_exactly_one_page_returns_has_more_false(
    client: TestClient, db, family
) -> None:
    """Off-by-one guard for the peek-one-extra logic.

    Seed exactly DEFAULT_PAGE_LIMIT (30) messages: page must contain all 30
    and `has_more` must be False (because there is no 31st row to find).
    """
    _family_id, _device_id, token = family
    thread, _msgs = _make_thread_with_messages(db, family=family, n_messages=30)

    r = client.get(f"/threads/{thread.id}", headers=_auth_for(token))
    assert r.status_code == 200
    body = r.json()
    assert len(body["messages"]) == 30
    assert body["has_more"] is False
    assert body["next_cursor"] is None


def test_messages_pagination_empty_thread_returns_empty_page(
    client: TestClient, db, family
) -> None:
    _family_id, _device_id, token = family
    thread, _ = _make_thread_with_messages(db, family=family, n_messages=0)

    # Initial envelope.
    r = client.get(f"/threads/{thread.id}", headers=_auth_for(token))
    assert r.status_code == 200
    body = r.json()
    assert body["messages"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None

    # Dedicated endpoint with no cursor — same shape.
    r2 = client.get(
        f"/threads/{thread.id}/messages", headers=_auth_for(token)
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2 == {"messages": [], "has_more": False, "next_cursor": None}


# ---------------------------------------------------------------------------
# Tier A/2 — cursor tamper / malformed
# ---------------------------------------------------------------------------


def test_messages_pagination_malformed_cursor_returns_400(
    client: TestClient, db, family
) -> None:
    _family_id, _device_id, token = family
    thread, _ = _make_thread_with_messages(db, family=family, n_messages=5)

    r = client.get(
        f"/threads/{thread.id}/messages",
        params={"before": "garbage-not-base64"},
        headers=_auth_for(token),
    )
    assert r.status_code == 400
    assert "Invalid cursor" in r.json().get("detail", "")


def test_messages_pagination_cursor_pointing_to_other_thread_does_not_leak_messages(
    client: TestClient, db, family, make_family
) -> None:
    """Cursor opacity contract.

    The cursor only encodes (created_at, message_id) — no thread_id. The
    pagination handler always filters by the path's thread_id, so a cursor
    crafted from another thread's row is safe: it just shifts the WHERE
    bound, but rows from the foreign thread are never returned.

    Concretely: if user-A passes a cursor referencing user-A's other thread
    when paginating user-A's first thread, we MUST only see rows from the
    first thread.
    """
    _family_id, _device_id, token = family
    # Thread A under same user, base time T0.
    thread_a, _msgs_a = _make_thread_with_messages(
        db, family=family, n_messages=5,
        base_time=datetime(2026, 5, 1, 9, 0, 0),
    )
    # Thread B under same user, base time later (T0 + 1h). All B messages
    # have created_at > all A messages.
    thread_b, msgs_b = _make_thread_with_messages(
        db, family=family, n_messages=5,
        base_time=datetime(2026, 5, 1, 10, 0, 0),
    )
    # Build a cursor from B's NEWEST message and use it to paginate A.
    b_newest = msgs_b[-1]
    raw = json.dumps(
        {"created_at": b_newest.created_at.isoformat(), "id": str(b_newest.message_id)},
        separators=(",", ":"),
    )
    cross_cursor = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    r = client.get(
        f"/threads/{thread_a.id}/messages",
        params={"before": cross_cursor, "limit": 30},
        headers=_auth_for(token),
    )
    assert r.status_code == 200
    body = r.json()
    # All A's rows have created_at < B's newest, so the cursor doesn't
    # exclude any of them; the returned set should be exactly A's 5 rows.
    assert len(body["messages"]) == 5
    contents = {m["content"] for m in body["messages"]}
    assert contents == {f"message {i}" for i in range(5)}


def test_messages_pagination_limit_above_max_returns_422(
    client: TestClient, db, family
) -> None:
    """Contract pin: limit > 100 → 422 with explicit error detail.

    The route raises `HTTPException(422, ...)` with a clear message rather
    than silently clamping. Pinning the contract here so a future "let's
    just clamp" refactor doesn't silently change client behavior.
    """
    _family_id, _device_id, token = family
    thread, _ = _make_thread_with_messages(db, family=family, n_messages=5)

    r = client.get(
        f"/threads/{thread.id}/messages",
        params={"limit": 200},
        headers=_auth_for(token),
    )
    assert r.status_code == 422
    assert "limit must be between 1 and 100" in r.json().get("detail", "")


def test_messages_pagination_limit_below_one_returns_422(
    client: TestClient, db, family
) -> None:
    _family_id, _device_id, token = family
    thread, _ = _make_thread_with_messages(db, family=family, n_messages=5)

    r = client.get(
        f"/threads/{thread.id}/messages",
        params={"limit": 0},
        headers=_auth_for(token),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Tier A/3 — auth on the new endpoint
# ---------------------------------------------------------------------------


def test_messages_endpoint_without_auth_returns_401(
    client: TestClient, db, family
) -> None:
    _, _, _ = family
    thread, _ = _make_thread_with_messages(db, family=family, n_messages=2)
    r = client.get(f"/threads/{thread.id}/messages")
    assert r.status_code == 401


def test_messages_endpoint_with_other_users_token_returns_403(
    client: TestClient, db, family, make_family
) -> None:
    """Thread is owned by family-A's shadow user; family-B's token must be
    rejected. Matches the existing /threads/{id} ownership check (403)."""
    thread, _ = _make_thread_with_messages(db, family=family, n_messages=3)
    # Another family's device JWT — same JWT signing key, different sub/family.
    _other_family_id, _other_device_id, other_token = make_family(
        family_name="Other Family"
    )

    r = client.get(
        f"/threads/{thread.id}/messages",
        headers=_auth_for(other_token),
    )
    assert r.status_code == 403


def test_messages_endpoint_unknown_thread_returns_404(
    client: TestClient, family
) -> None:
    _family_id, _device_id, token = family
    r = client.get(
        "/threads/9999999/messages",
        headers=_auth_for(token),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tier C/13 — response shape regression for /threads/{id}
# ---------------------------------------------------------------------------


def test_get_thread_returns_envelope_with_thread_meta_and_messages_page(
    client: TestClient, db, family
) -> None:
    """Pin the new envelope shape so a backend regression here would FE-break
    the chat history feature.
    """
    _family_id, _device_id, token = family
    thread, _ = _make_thread_with_messages(db, family=family, n_messages=2)
    r = client.get(f"/threads/{thread.id}", headers=_auth_for(token))
    assert r.status_code == 200
    body = r.json()
    # Thread metadata fields.
    assert body["id"] == thread.id
    assert body["thread_id"] == str(thread.thread_id)
    assert body["title"] == "Pagination Test Thread"
    assert "created_at" in body and "updated_at" in body
    # Page envelope merged in.
    assert "messages" in body and isinstance(body["messages"], list)
    assert "has_more" in body and body["has_more"] is False
    assert "next_cursor" in body
    # Message shape.
    msg = body["messages"][0]
    for k in ("id", "role", "content", "type", "created_at"):
        assert k in msg, f"missing field {k!r} in message item"

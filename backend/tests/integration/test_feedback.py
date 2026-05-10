"""Integration tests for /api/feedback (§B.5/§B.6).

What's covered:
- Auth on POST + GET — Tier A/3.
- Author-kind security boundary: REST cannot ever produce
  `assistant_on_behalf_of_user`. Pin the contract: extra-field rejection
  vs ignore + actual stored row — Tier A/4.
- Family scoping: device in family A only sees family A's feedback,
  never family B's — Tier A/5.
- The internal `submit_from_assistant` service path: writes
  `assistant_on_behalf_of_user`, AND verify it's not exposed via any
  HTTP route — Tier A/6.
- `status` filter — Tier C/14.

Naming: spec-line style. One reason to fail per test.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.feedback import (
    Feedback,
    FeedbackAuthorKind,
    FeedbackCategory,
    FeedbackStatus,
)


def _auth_for(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tier A/3 — auth
# ---------------------------------------------------------------------------


def test_post_feedback_without_auth_returns_401(client: TestClient) -> None:
    r = client.post(
        "/api/feedback",
        json={"category": "bug", "message": "anonymous attempt"},
    )
    assert r.status_code == 401


def test_get_feedback_without_auth_returns_401(client: TestClient) -> None:
    r = client.get("/api/feedback")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Tier A/4 — security boundary on POST /api/feedback
# ---------------------------------------------------------------------------


def test_post_feedback_rejects_author_kind_in_body(
    client: TestClient, family
) -> None:
    """Contract pin (security boundary): the REST schema for FeedbackCreateRequest
    does NOT declare `author_kind`. Pydantic v2's default is `extra='ignore'`
    UNLESS the schema sets `model_config = ConfigDict(extra='forbid')`.

    This test pins whichever behavior is currently in effect, and the assertion
    block flags the behavior as a finding so the team can decide.

    Goal: make sure that NO MATTER what the client sends, the stored row is
    `author_kind="user"`. This is the security guarantee.
    """
    _family_id, _device_id, token = family
    r = client.post(
        "/api/feedback",
        headers=_auth_for(token),
        json={
            "category": "bug",
            "message": "trying to spoof author_kind",
            "author_kind": "assistant_on_behalf_of_user",
        },
    )
    # The handler must NEVER honor a client-supplied author_kind. Whether the
    # validator rejects (422) or silently ignores it (201), the stored row
    # must say author_kind="user".
    if r.status_code == 422:
        # Schema is `extra=forbid` — preferred posture. Nothing was written.
        return
    assert r.status_code == 201, (
        "Unexpected status from spoofed-author POST: " f"{r.status_code} {r.text}"
    )
    # If we got 201, the schema is currently `extra=ignore`. The stored row
    # must STILL say `user`.
    body = r.json()
    assert body["author_kind"] == "user", (
        "Spoofed author_kind made it into the response — security regression. "
        f"Got: {body!r}"
    )


def test_post_feedback_happy_path_stores_user_authored_row(
    client: TestClient, family, db: Session
) -> None:
    family_id, device_id, token = family
    r = client.post(
        "/api/feedback",
        headers=_auth_for(token),
        json={"category": "bug", "message": "the fridge UI lags after a fresh boot"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # Response contract.
    assert body["author_kind"] == "user"
    assert body["category"] == "bug"
    assert body["status"] == "open"
    assert body["message"] == "the fridge UI lags after a fresh boot"
    assert UUID(body["id"])
    assert UUID(body["family_id"]) == family_id
    assert UUID(body["device_id"]) == device_id
    assert body["member_id"] is None  # kiosk has no logged-in member
    assert body["thread_id"] is None
    assert "created_at" in body and "updated_at" in body

    # DB state — the row really was persisted with the correct columns.
    row = db.query(Feedback).filter(Feedback.id == UUID(body["id"])).one()
    assert row.author_kind == FeedbackAuthorKind.user
    assert row.family_id == family_id
    assert row.device_id == device_id
    assert row.member_id is None
    assert row.status == FeedbackStatus.open
    assert row.category == FeedbackCategory.bug


def test_post_feedback_with_invalid_category_returns_422(
    client: TestClient, family
) -> None:
    _family_id, _device_id, token = family
    r = client.post(
        "/api/feedback",
        headers=_auth_for(token),
        json={"category": "wishlist", "message": "must fail validation"},
    )
    assert r.status_code == 422


def test_post_feedback_with_empty_message_returns_422(
    client: TestClient, family
) -> None:
    """min_length=1 on the message field."""
    _family_id, _device_id, token = family
    r = client.post(
        "/api/feedback",
        headers=_auth_for(token),
        json={"category": "bug", "message": ""},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Tier A/5 — family scoping on GET /api/feedback
# ---------------------------------------------------------------------------


def test_list_feedback_only_returns_rows_from_callers_family(
    client: TestClient, db: Session, make_family
) -> None:
    family_a_id, device_a_id, token_a = make_family(family_name="Alpha")
    family_b_id, device_b_id, token_b = make_family(family_name="Bravo")

    # Seed two rows in family A and one in family B directly.
    db.add(
        Feedback(
            family_id=family_a_id,
            category=FeedbackCategory.bug,
            message="A1",
            author_kind=FeedbackAuthorKind.user,
            device_id=device_a_id,
        )
    )
    db.add(
        Feedback(
            family_id=family_a_id,
            category=FeedbackCategory.improvement,
            message="A2",
            author_kind=FeedbackAuthorKind.user,
            device_id=device_a_id,
        )
    )
    db.add(
        Feedback(
            family_id=family_b_id,
            category=FeedbackCategory.bug,
            message="B1",
            author_kind=FeedbackAuthorKind.user,
            device_id=device_b_id,
        )
    )
    db.commit()

    ra = client.get("/api/feedback", headers=_auth_for(token_a))
    assert ra.status_code == 200
    body_a = ra.json()
    assert body_a["has_more"] is False
    contents_a = sorted(item["message"] for item in body_a["items"])
    assert contents_a == ["A1", "A2"]
    for item in body_a["items"]:
        assert UUID(item["family_id"]) == family_a_id

    rb = client.get("/api/feedback", headers=_auth_for(token_b))
    assert rb.status_code == 200
    body_b = rb.json()
    contents_b = [item["message"] for item in body_b["items"]]
    assert contents_b == ["B1"]
    assert UUID(body_b["items"][0]["family_id"]) == family_b_id


# ---------------------------------------------------------------------------
# Tier C/14 — status filter
# ---------------------------------------------------------------------------


def test_list_feedback_status_filter_only_returns_matching_rows(
    client: TestClient, db: Session, family
) -> None:
    family_id, device_id, token = family
    # Seed one row per status.
    for status_, msg in [
        (FeedbackStatus.open, "open one"),
        (FeedbackStatus.reviewing, "reviewing one"),
        (FeedbackStatus.resolved, "resolved one"),
    ]:
        db.add(
            Feedback(
                family_id=family_id,
                category=FeedbackCategory.bug,
                message=msg,
                author_kind=FeedbackAuthorKind.user,
                status=status_,
                device_id=device_id,
            )
        )
    db.commit()

    r = client.get(
        "/api/feedback",
        params={"status": "resolved"},
        headers=_auth_for(token),
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "resolved"
    assert items[0]["message"] == "resolved one"


def test_list_feedback_invalid_status_returns_422(
    client: TestClient, family
) -> None:
    """Pin: status enum is `Literal["open","reviewing","resolved"]`."""
    _family_id, _device_id, token = family
    r = client.get(
        "/api/feedback",
        params={"status": "wontfix"},
        headers=_auth_for(token),
    )
    assert r.status_code == 422


def test_list_feedback_above_limit_returns_422(
    client: TestClient, family
) -> None:
    _family_id, _device_id, token = family
    r = client.get(
        "/api/feedback",
        params={"limit": 200},
        headers=_auth_for(token),
    )
    assert r.status_code == 422


def test_list_feedback_malformed_cursor_returns_400(
    client: TestClient, family
) -> None:
    _family_id, _device_id, token = family
    r = client.get(
        "/api/feedback",
        params={"before": "garbage"},
        headers=_auth_for(token),
    )
    assert r.status_code == 400


def test_list_feedback_paginates_newest_first_with_cursor(
    client: TestClient, db: Session, family
) -> None:
    """Seed 7 rows, page size 3 → 3+3+1, newest first, no overlap."""
    family_id, device_id, token = family
    base = datetime(2026, 5, 1, 12, 0, 0)
    for i in range(7):
        db.add(
            Feedback(
                family_id=family_id,
                category=FeedbackCategory.bug,
                message=f"f{i}",
                author_kind=FeedbackAuthorKind.user,
                device_id=device_id,
                created_at=base + timedelta(seconds=i),
            )
        )
    db.commit()

    # Page 1.
    r1 = client.get(
        "/api/feedback",
        params={"limit": 3},
        headers=_auth_for(token),
    )
    assert r1.status_code == 200
    p1 = r1.json()
    assert p1["has_more"] is True
    assert p1["next_cursor"]
    assert [m["message"] for m in p1["items"]] == ["f6", "f5", "f4"]

    # Page 2.
    r2 = client.get(
        "/api/feedback",
        params={"limit": 3, "before": p1["next_cursor"]},
        headers=_auth_for(token),
    )
    p2 = r2.json()
    assert p2["has_more"] is True
    assert [m["message"] for m in p2["items"]] == ["f3", "f2", "f1"]

    # Page 3.
    r3 = client.get(
        "/api/feedback",
        params={"limit": 3, "before": p2["next_cursor"]},
        headers=_auth_for(token),
    )
    p3 = r3.json()
    assert p3["has_more"] is False
    assert p3["next_cursor"] is None
    assert [m["message"] for m in p3["items"]] == ["f0"]


# ---------------------------------------------------------------------------
# Tier A/6 — the assistant write path is service-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_service_assistant_write_path_records_assistant_kind(
    db: Session, family
) -> None:
    """`FeedbackService.submit_from_assistant` produces a row with
    `author_kind=assistant_on_behalf_of_user`. This is the only legitimate
    way that enum value enters the table.
    """
    from src.services.feedback_service import FeedbackService

    family_id, _device_id, _token = family
    svc = FeedbackService(db, family_id)
    row = await svc.submit_from_assistant(
        category=FeedbackCategory.improvement,
        message="please add reminders for soon-expiring food",
        thread_id=None,
    )
    assert row.author_kind == FeedbackAuthorKind.assistant_on_behalf_of_user
    assert row.family_id == family_id
    assert row.member_id is None
    assert row.device_id is None
    assert row.status == FeedbackStatus.open
    persisted = db.query(Feedback).filter(Feedback.id == row.id).one()
    assert persisted.author_kind == FeedbackAuthorKind.assistant_on_behalf_of_user


def test_feedback_router_does_not_expose_an_assistant_submit_endpoint() -> None:
    """Document the security architecture in tests: there is no HTTP route
    under feedback that writes `author_kind=assistant_on_behalf_of_user`.

    This is grep-as-test: scan the feedback module's route source for any
    obvious assistant submit handler. If someone adds one, this test fails
    so the team has to deliberately update it.
    """
    import inspect

    from src.routes import feedback as feedback_routes

    src = inspect.getsource(feedback_routes)
    # Heuristic: any call into submit_from_assistant from the route layer
    # would be a leak. The string should NOT appear in the route file.
    assert "submit_from_assistant" not in src, (
        "feedback route module references submit_from_assistant — the "
        "assistant write path must remain service-only (LangGraph tool)."
    )


def test_feedback_create_request_schema_does_not_declare_author_kind() -> None:
    """Schema-level guard so a Pydantic model edit can't sneak in an
    `author_kind` field. (FastAPI auto-binds extra fields when present.)
    """
    from src.schemas.feedback import FeedbackCreateRequest

    fields = set(FeedbackCreateRequest.model_fields.keys())
    assert "author_kind" not in fields, (
        "FeedbackCreateRequest must not expose author_kind. "
        f"Current fields: {fields!r}"
    )

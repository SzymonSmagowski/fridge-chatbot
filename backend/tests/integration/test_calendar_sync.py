"""Integration tests for /calendar/sync-state and /calendar/sync/pull (§5.9)."""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from src.models import GoogleToken, GoogleTokenStatus, Member, MemberStatus
from src.schemas.calendar_sync import SyncStateResponse


def _add_member(db, family_id, **kw) -> Member:
    m = Member(
        family_id=family_id,
        name=kw.get("name", "M"),
        color=kw.get("color", "sage"),
        status=kw.get("status", MemberStatus.active),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def test_get_sync_state_returns_per_member_row(
    client: TestClient, auth_headers, db, family
) -> None:
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom", color="rose")
    db.add(
        GoogleToken(
            member_id=mom.id,
            refresh_token_encrypted=b"x",
            google_sub="g-1",
            google_email="mom@example.com",
            scope="x",
            status=GoogleTokenStatus.connected,
        )
    )
    db.commit()
    resp = client.get("/calendar/sync-state", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["member_id"] == str(mom.id)
    assert rows[0]["google_status"] == "connected"
    assert rows[0]["consecutive_failures"] == 0
    SyncStateResponse.model_validate(rows[0])


def test_get_sync_state_for_member_without_google_returns_not_connected(
    client: TestClient, auth_headers, db, family
) -> None:
    family_id, _, _ = family
    _add_member(db, family_id, name="Dad", color="amber")
    rows = client.get("/calendar/sync-state", headers=auth_headers).json()
    assert rows[0]["google_status"] == "not_connected"


def test_force_pull_for_unknown_member_returns_404(
    client: TestClient, auth_headers
) -> None:
    resp = client.post(
        f"/calendar/sync/pull?member_id={uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "members.not_found"


def test_force_pull_for_member_without_google_returns_409(
    client: TestClient, auth_headers, db, family
) -> None:
    family_id, _, _ = family
    dad = _add_member(db, family_id, name="Dad", color="amber")
    resp = client.post(
        f"/calendar/sync/pull?member_id={dad.id}", headers=auth_headers
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "calendar.not_connected"

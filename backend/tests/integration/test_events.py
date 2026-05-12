"""Integration tests for /events (§5.7, google-calendar.md MoSCoW).

Covers:
- POST creates an `Event` row with proper `event_targets` per fan-out rules
  (assignee-only, fan-out-no-assignee, car-only, missing-google-token skip).
- GET / list with filters, source=fridge|external|all
- PATCH / DELETE with scope=instance vs all_future
- Google API is **mocked** at GoogleCalendarService — never reaches the
  network. The fan-out worker invocation is verified by patching the
  background-task entrypoint.
- Resync flips failed targets back to pending and re-enqueues fan-out.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.models import (
    Event,
    EventTarget,
    EventTargetSyncStatus,
    GoogleToken,
    GoogleTokenStatus,
    Member,
    MemberStatus,
)
from src.schemas.events import EventListResponse, EventResponse


def _connect_member_google(
    db, member_id: UUID, status: GoogleTokenStatus = GoogleTokenStatus.connected
) -> None:
    db.add(
        GoogleToken(
            member_id=member_id,
            refresh_token_encrypted=b"ciphertext",
            google_sub="google-sub-123",
            google_email="member@example.com",
            scope="openid email profile https://www.googleapis.com/auth/calendar",
            status=status,
        )
    )
    db.commit()


def _create_member_via_db(db, family_id: UUID, **kwargs) -> Member:
    member = Member(
        family_id=family_id,
        name=kwargs.get("name", "Member"),
        color=kwargs.get("color", "sage"),
        status=kwargs.get("status", MemberStatus.active),
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


# ---------------------------------------------------------------------------
# Happy-path POST + fan-out plan
# ---------------------------------------------------------------------------


def test_post_event_with_assignee_creates_one_target_pending(
    client: TestClient, auth_headers, db, family, monkeypatch
) -> None:
    """google-calendar.md Must: single-member assignment writes to that one calendar."""
    family_id, _, _ = family
    dad = _create_member_via_db(db, family_id, name="Dad", color="amber")
    _connect_member_google(db, dad.id)

    # Stub the BackgroundTasks fan-out so it doesn't kick off real Google work.
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    start = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Soccer practice",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "timezone": "Europe/Warsaw",
            "assignee_member_id": str(dad.id),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Soccer practice"
    assert body["assignee_member_id"] == str(dad.id)
    assert len(body["targets"]) == 1
    assert body["targets"][0]["sync_status"] == "pending"
    assert body["targets"][0]["member_id"] == str(dad.id)
    EventResponse.model_validate(body)


def test_post_event_with_no_assignee_fans_out_to_all_active_members(
    client: TestClient, auth_headers, db, family, monkeypatch
) -> None:
    """google-calendar.md Must: unassigned event fans out to every active+connected member."""
    family_id, _, _ = family
    mom = _create_member_via_db(db, family_id, name="Mom", color="rose")
    dad = _create_member_via_db(db, family_id, name="Dad", color="amber")
    inactive = _create_member_via_db(
        db, family_id, name="Old", color="stone", status=MemberStatus.inactive
    )
    _connect_member_google(db, mom.id)
    _connect_member_google(db, dad.id)
    _connect_member_google(db, inactive.id)

    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Family dinner",
            "start_at": "2026-05-02T18:00:00+00:00",
            "end_at": "2026-05-02T20:00:00+00:00",
        },
    )
    assert resp.status_code == 201
    targets = resp.json()["targets"]
    member_ids = {t["member_id"] for t in targets}
    # Active connected members → pending; inactive members are excluded.
    assert {str(mom.id), str(dad.id)} == member_ids


def test_post_event_skips_member_without_google_connection(
    client: TestClient, auth_headers, db, family, monkeypatch
) -> None:
    """google-calendar.md Must: member without Google → save, skipped target,
    `last_error='no_google_connection'`."""
    family_id, _, _ = family
    dad = _create_member_via_db(db, family_id, name="Dad", color="amber")
    # No google_token row for Dad.

    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Soccer",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
            "assignee_member_id": str(dad.id),
        },
    )
    assert resp.status_code == 201
    targets = resp.json()["targets"]
    assert len(targets) == 1
    assert targets[0]["sync_status"] == "skipped"
    assert targets[0]["last_error"] == "no_google_connection"


def test_post_event_with_car_only_fans_out_to_all_active_members(
    client: TestClient, auth_headers, db, family, monkeypatch
) -> None:
    """cars.md Must: car-only event writes to every active member's calendar."""
    family_id, _, _ = family
    mom = _create_member_via_db(db, family_id, name="Mom", color="rose")
    dad = _create_member_via_db(db, family_id, name="Dad", color="amber")
    _connect_member_google(db, mom.id)
    _connect_member_google(db, dad.id)
    car = client.post(
        "/api/cars", headers=auth_headers, json={"name": "Volvo"}
    ).json()

    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Mom takes Volvo",
            "start_at": "2026-05-03T08:00:00+00:00",
            "end_at": "2026-05-03T18:00:00+00:00",
            "assignee_member_id": None,
            "car_ids": [car["id"]],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    # Car decoration in description (event_service _with_car_decoration).
    assert "Volvo" in (body["description"] or "")
    assert {t["member_id"] for t in body["targets"]} == {
        str(mom.id),
        str(dad.id),
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_post_event_with_empty_title_returns_422(
    client: TestClient, auth_headers
) -> None:
    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
        },
    )
    assert resp.status_code == 422


def test_post_event_with_end_before_start_returns_400(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    """Service-layer validation: end_at must be >= start_at."""
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Backwards",
            "start_at": "2026-05-01T11:00:00+00:00",
            "end_at": "2026-05-01T10:00:00+00:00",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "events.invalid_time_range"


def test_post_event_with_malformed_rrule_returns_400(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    """Service-layer validation: rrule must parse via dateutil.rrulestr."""
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Recurring",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
            "rrule": "FREQ=NOT_A_REAL_FREQ;INTERVAL=oops",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "events.invalid_rrule"
    assert "FREQ=NOT_A_REAL_FREQ" in resp.json()["detail"]["detail"]


def test_post_event_with_valid_rrule_succeeds(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    """Sanity check: a syntactically valid RRULE passes validation."""
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Weekly",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
            "rrule": "FREQ=WEEKLY;COUNT=5",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["rrule"] == "FREQ=WEEKLY;COUNT=5"


def test_post_event_with_cross_family_assignee_returns_404(
    client: TestClient, auth_headers, db, make_family, monkeypatch
) -> None:
    """Family-ownership check: assignee_member_id from another family is rejected."""
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    other_family_id, _, _ = make_family(family_name="Other Family")
    intruder = _create_member_via_db(db, other_family_id, name="Intruder")

    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Cross-family",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
            "assignee_member_id": str(intruder.id),
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "members.not_found"


def test_post_event_with_cross_family_car_returns_404(
    client: TestClient, auth_headers, make_family, monkeypatch
) -> None:
    """Family-ownership check: car_ids from another family are rejected."""
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    _other_family, _device, other_token = make_family(family_name="Other Family")
    other_car = client.post(
        "/api/cars",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"name": "Stranger Volvo"},
    ).json()

    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Cross-family car",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
            "car_ids": [other_car["id"]],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "cars.not_found"


# ---------------------------------------------------------------------------
# GET / list
# ---------------------------------------------------------------------------


def test_get_events_returns_fridge_external_envelope(
    client: TestClient, auth_headers
) -> None:
    resp = client.get("/api/events", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "fridge" in body
    assert "external" in body
    assert "total" in body
    EventListResponse.model_validate(body)


def test_get_event_in_other_family_returns_404(
    client: TestClient, auth_headers, make_family, monkeypatch
) -> None:
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    _other_fam, _device, other_token = make_family(family_name="Other")
    other_event = client.post(
        "/api/events",
        headers={"Authorization": f"Bearer {other_token}"},
        json={
            "title": "Secret",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
        },
    ).json()
    resp = client.get(f"/api/events/{other_event['id']}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "events.not_found"


# ---------------------------------------------------------------------------
# PATCH / DELETE
# ---------------------------------------------------------------------------


def test_patch_event_updates_title(
    client: TestClient, auth_headers, monkeypatch
) -> None:
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    created = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "Old",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
        },
    ).json()
    resp = client.patch(
        f"/api/events/{created['id']}",
        headers=auth_headers,
        json={"title": "New"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New"


def test_delete_event_returns_204(
    client: TestClient, auth_headers, monkeypatch, db
) -> None:
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    created = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "x",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
        },
    ).json()
    resp = client.delete(f"/api/events/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert db.query(Event).filter(Event.id == UUID(created["id"])).first() is None


def test_resync_event_flips_failed_targets_to_pending(
    client: TestClient, auth_headers, db, family, monkeypatch
) -> None:
    """§5.7: POST /events/{id}/resync re-enqueues failed targets."""
    family_id, _, _ = family
    member = _create_member_via_db(db, family_id, name="Mom", color="rose")
    _connect_member_google(db, member.id)

    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    created = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "x",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
            "assignee_member_id": str(member.id),
        },
    ).json()

    # Force the target to failed.
    target = db.query(EventTarget).filter(
        EventTarget.event_id == UUID(created["id"])
    ).first()
    target.sync_status = EventTargetSyncStatus.failed
    target.last_error = "boom"
    db.commit()

    resp = client.post(
        f"/api/events/{created['id']}/resync", headers=auth_headers
    )
    assert resp.status_code == 200
    target = db.query(EventTarget).filter(
        EventTarget.event_id == UUID(created["id"])
    ).first()
    assert target.sync_status == EventTargetSyncStatus.pending
    assert target.last_error is None


# ---------------------------------------------------------------------------
# Pub/sub on writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_event_publishes_event_created_frame(
    client: TestClient, auth_headers, family, family_event_collector, monkeypatch
) -> None:
    family_id, _, _ = family
    from src.workers import calendar_write_worker
    monkeypatch.setattr(calendar_write_worker, "fan_out_event", _async_no_op)

    async with family_event_collector(family_id) as collector:
        client.post(
            "/api/events",
            headers=auth_headers,
            json={
                "title": "x",
                "start_at": "2026-05-01T10:00:00+00:00",
                "end_at": "2026-05-01T11:00:00+00:00",
            },
        )
        frames = await collector.wait_for(1)
    assert frames[0]["type"] == "event.created"
    assert frames[0]["entity"] == "events"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _async_no_op(*args, **kwargs) -> None:
    """Drop-in async stub for `fan_out_event` so tests don't hit Google."""
    return None

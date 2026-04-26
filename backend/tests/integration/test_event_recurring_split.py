"""§5.7 / §6.7 — `EventService._split_recurring_series` ("this and following").

Covers the 8 edge cases BackendDeveloper recommended after the A5 implementation:
1. Happy path single target — series caps original RRULE with UNTIL, inserts
   new master Event row with original (uncapped) RRULE, parallel `event_targets`
   on the new row, original targets untouched.
2. Falls through on non-recurring events (no RRULE → returns original).
3. Existing UNTIL on original RRULE is stripped before re-cap.
4. Existing COUNT on original RRULE is stripped before re-cap.
5. Idempotent on retry — second call returns existing sibling, no second
   Google call, no third Event row.
6. Google insert fails after master patch — DB rollback, raises 502
   `events.recurring_split_partial`, original RRULE survives unchanged.
7. Token missing for one target — that target is skipped silently, the other
   target still produces a new EventTarget row.

Google Calendar API is mocked at the service-injection seam — we substitute
fakes for `GoogleCalendarService` and `GoogleTokenService` so no network IO.
The DB is the real test Postgres (per the project test discipline — never
mock the DB).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from src.models import (
    Event,
    EventTarget,
    EventTargetSyncStatus,
    GoogleToken,
    GoogleTokenStatus,
    Member,
    MemberStatus,
)
from src.schemas.events import EventUpdateRequest
from src.services.chat_streaming import ChatStreamer
from src.services.event_service import (
    EventService,
    _cap_rrule_with_until,
    _format_until,
)
from src.services.event_target_resolver import EventTargetResolver


# ---------------------------------------------------------------------------
# Fakes for the two external collaborators
# ---------------------------------------------------------------------------


class _FakeCalendar:
    """Drop-in for GoogleCalendarService — records calls, returns canned ids."""

    def __init__(
        self,
        *,
        insert_ids: list[str] | None = None,
        insert_raises: Exception | None = None,
    ) -> None:
        self._insert_ids = list(insert_ids or [])
        self._insert_raises = insert_raises
        self.update_calls: list[tuple[str, str, dict]] = []
        self.insert_calls: list[tuple[str, dict]] = []

    async def update(self, access_token: str, google_event_id: str, body: dict):
        self.update_calls.append((access_token, google_event_id, body))
        return {"id": google_event_id}

    async def insert_raw(self, access_token: str, body: dict):
        self.insert_calls.append((access_token, body))
        if self._insert_raises is not None:
            raise self._insert_raises
        if not self._insert_ids:
            new_id = f"new-google-{len(self.insert_calls)}"
        else:
            new_id = self._insert_ids.pop(0)
        return {"id": new_id, "summary": body.get("summary")}


class _FakeTokenService:
    def __init__(self, tokens_by_member: dict[UUID, str | None]) -> None:
        self.tokens = tokens_by_member

    async def get_access_token(self, member_id: UUID) -> str | None:
        return self.tokens.get(member_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_member(
    db: Session, family_id: UUID, name: str, color: str = "sage"
) -> Member:
    member = Member(
        family_id=family_id, name=name, color=color, status=MemberStatus.active
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _connect_member(db: Session, member_id: UUID) -> None:
    db.add(
        GoogleToken(
            member_id=member_id,
            refresh_token_encrypted=b"ciphertext",
            google_sub=f"google-sub-{member_id.hex[:6]}",
            google_email=f"{member_id.hex[:6]}@example.com",
            scope="openid email profile https://www.googleapis.com/auth/calendar",
            status=GoogleTokenStatus.connected,
        )
    )
    db.commit()


def _create_recurring_event(
    db: Session,
    family_id: UUID,
    *,
    rrule: str,
    title: str = "Soccer practice",
    member_targets: list[tuple[UUID, str]] | None = None,
) -> Event:
    """Build a recurring Event with `event_targets` already in synced state.

    `member_targets` is a list of (member_id, google_event_id) pairs.
    """
    start = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 4, 11, 0, tzinfo=timezone.utc)
    ev = Event(
        family_id=family_id,
        title=title,
        description="weekly",
        start_at=start,
        end_at=end,
        timezone="Europe/Warsaw",
        rrule=rrule,
    )
    db.add(ev)
    db.flush()
    for member_id, google_id in member_targets or []:
        ev.targets.append(
            EventTarget(
                event_id=ev.id,
                member_id=member_id,
                google_event_id=google_id,
                sync_status=EventTargetSyncStatus.synced,
                synced_at=datetime.now(tz=timezone.utc),
            )
        )
    db.commit()
    db.refresh(ev)
    return ev


def _build_event_service(
    db: Session,
    redis: Redis,
    family_id: UUID,
    *,
    calendar: _FakeCalendar,
    token_service: _FakeTokenService,
) -> EventService:
    resolver = EventTargetResolver(db, family_id)
    streamer = ChatStreamer(redis)
    return EventService(
        db,
        family_id,
        resolver,
        streamer,
        calendar=calendar,
        token_service=token_service,
    )


# ---------------------------------------------------------------------------
# 1. Happy path — single target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_recurring_series_happy_path_caps_original_and_inserts_new_master(
    db: Session, redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom", color="rose")
    _connect_member(db, mom.id)
    dad = _add_member(db, family_id, name="Dad", color="amber")
    _connect_member(db, dad.id)

    # Original recurring event with two fanned-out targets, both synced.
    original = _create_recurring_event(
        db,
        family_id,
        rrule="FREQ=WEEKLY;BYDAY=MO",
        title="Soccer practice",
        member_targets=[(mom.id, "g-mom-orig"), (dad.id, "g-dad-orig")],
    )
    original_targets_snapshot = {
        t.member_id: (t.google_event_id, t.sync_status) for t in original.targets
    }

    instance_start = original.start_at + timedelta(days=14)  # the third occurrence
    calendar = _FakeCalendar(insert_ids=["g-mom-new", "g-dad-new"])
    tokens = _FakeTokenService({mom.id: "at-mom", dad.id: "at-dad"})
    service = _build_event_service(
        db, redis_client, family_id, calendar=calendar, token_service=tokens
    )

    new_ev = await service._split_recurring_series(
        event_id=original.id,
        instance_start_time=instance_start,
        patch_body={"title": "Soccer Mon (renamed)"},
    )

    db.refresh(original)
    expected_until = _format_until(instance_start)

    # 1) Original local RRULE is now capped with UNTIL.
    assert original.rrule.endswith(f"UNTIL={expected_until}")
    # 2) New local Event row exists with the ORIGINAL (uncapped) RRULE.
    assert new_ev.id != original.id
    assert new_ev.rrule == "FREQ=WEEKLY;BYDAY=MO"
    assert new_ev.title == "Soccer Mon (renamed)"
    assert new_ev.start_at == instance_start
    # 3) Two new EventTarget rows on the new event with sync_status=synced.
    assert len(new_ev.targets) == 2
    new_member_ids = {t.member_id for t in new_ev.targets}
    assert new_member_ids == {mom.id, dad.id}
    for t in new_ev.targets:
        assert t.sync_status == EventTargetSyncStatus.synced
        assert t.google_event_id in {"g-mom-new", "g-dad-new"}
    # 4) Original targets untouched.
    db_orig = db.query(Event).filter(Event.id == original.id).one()
    db_orig_targets = {
        t.member_id: (t.google_event_id, t.sync_status) for t in db_orig.targets
    }
    assert db_orig_targets == original_targets_snapshot
    # 5) Google calls: one PATCH + one INSERT per target = 2 + 2.
    assert len(calendar.update_calls) == 2
    assert len(calendar.insert_calls) == 2


# ---------------------------------------------------------------------------
# 2. No RRULE → falls through (no-op return)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_recurring_series_falls_through_when_no_rrule(
    db: Session, redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom")
    _connect_member(db, mom.id)

    # Non-recurring event.
    ev = Event(
        family_id=family_id,
        title="One-off",
        start_at=datetime(2026, 5, 1, 10, tzinfo=timezone.utc),
        end_at=datetime(2026, 5, 1, 11, tzinfo=timezone.utc),
        timezone="Europe/Warsaw",
        rrule=None,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    calendar = _FakeCalendar()
    tokens = _FakeTokenService({mom.id: "at-mom"})
    service = _build_event_service(
        db, redis_client, family_id, calendar=calendar, token_service=tokens
    )

    returned = await service._split_recurring_series(
        event_id=ev.id,
        instance_start_time=ev.start_at,
        patch_body={"title": "Renamed"},
    )

    # Defensive no-op — caller should not have invoked us. Returns the original
    # row, makes zero Google calls, creates no new Event row.
    assert returned.id == ev.id
    assert calendar.update_calls == []
    assert calendar.insert_calls == []
    second_event_count = (
        db.query(Event).filter(Event.family_id == family_id).count()
    )
    assert second_event_count == 1


# ---------------------------------------------------------------------------
# 3. Existing UNTIL stripped before re-cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_recurring_series_strips_existing_until(
    db: Session, redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom")
    _connect_member(db, mom.id)

    original = _create_recurring_event(
        db,
        family_id,
        rrule="FREQ=WEEKLY;UNTIL=20271231T000000Z;BYDAY=MO",
        member_targets=[(mom.id, "g-mom-orig")],
    )
    instance_start = original.start_at + timedelta(days=7)

    calendar = _FakeCalendar(insert_ids=["g-mom-new"])
    tokens = _FakeTokenService({mom.id: "at-mom"})
    service = _build_event_service(
        db, redis_client, family_id, calendar=calendar, token_service=tokens
    )

    new_ev = await service._split_recurring_series(
        event_id=original.id,
        instance_start_time=instance_start,
        patch_body={},
    )

    db.refresh(original)
    expected_until = _format_until(instance_start)
    # Capped RRULE has the NEW UNTIL, not 20271231T000000Z.
    assert f"UNTIL={expected_until}" in original.rrule
    assert "UNTIL=20271231T000000Z" not in original.rrule
    # New master keeps original BYDAY=MO without UNTIL.
    assert new_ev.rrule == "FREQ=WEEKLY;UNTIL=20271231T000000Z;BYDAY=MO"


# ---------------------------------------------------------------------------
# 4. Existing COUNT stripped before re-cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_recurring_series_strips_existing_count(
    db: Session, redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom")
    _connect_member(db, mom.id)

    original = _create_recurring_event(
        db,
        family_id,
        rrule="FREQ=WEEKLY;COUNT=10;BYDAY=MO",
        member_targets=[(mom.id, "g-mom-orig")],
    )
    instance_start = original.start_at + timedelta(days=7)

    calendar = _FakeCalendar(insert_ids=["g-mom-new"])
    tokens = _FakeTokenService({mom.id: "at-mom"})
    service = _build_event_service(
        db, redis_client, family_id, calendar=calendar, token_service=tokens
    )

    await service._split_recurring_series(
        event_id=original.id,
        instance_start_time=instance_start,
        patch_body={},
    )

    db.refresh(original)
    expected_until = _format_until(instance_start)
    assert f"UNTIL={expected_until}" in original.rrule
    # COUNT is stripped — no longer present anywhere in the capped RRULE.
    assert "COUNT=" not in original.rrule


# ---------------------------------------------------------------------------
# 5. Idempotency on retry — second call returns existing sibling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_recurring_series_is_idempotent_on_retry_when_title_unchanged(
    db: Session, redis_client: Redis, family
) -> None:
    """Happy-case idempotency: when the patch_body does NOT rename the title,
    a retry with the same instance_start_time short-circuits via
    `_find_split_sibling` and returns the existing sibling Event row."""
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom")
    _connect_member(db, mom.id)

    original = _create_recurring_event(
        db,
        family_id,
        rrule="FREQ=WEEKLY;BYDAY=MO",
        member_targets=[(mom.id, "g-mom-orig")],
    )
    instance_start = original.start_at + timedelta(days=14)

    calendar = _FakeCalendar(insert_ids=["g-mom-new"])
    tokens = _FakeTokenService({mom.id: "at-mom"})
    service = _build_event_service(
        db, redis_client, family_id, calendar=calendar, token_service=tokens
    )

    # First call — no title change in the patch.
    first = await service._split_recurring_series(
        event_id=original.id,
        instance_start_time=instance_start,
        patch_body={"location": "New Field"},
    )
    first_id = first.id
    update_count_after_first = len(calendar.update_calls)
    insert_count_after_first = len(calendar.insert_calls)
    event_count_after_first = (
        db.query(Event).filter(Event.family_id == family_id).count()
    )
    assert event_count_after_first == 2

    # Second call with the same instance_start — should short-circuit because
    # the new event's title still matches the (now-capped) original.
    second = await service._split_recurring_series(
        event_id=original.id,
        instance_start_time=instance_start,
        patch_body={"location": "New Field"},
    )
    assert second.id == first_id
    # No further Google API calls.
    assert len(calendar.update_calls) == update_count_after_first
    assert len(calendar.insert_calls) == insert_count_after_first
    # No third Event row created.
    event_count_after_second = (
        db.query(Event).filter(Event.family_id == family_id).count()
    )
    assert event_count_after_second == 2


@pytest.mark.asyncio
async def test_split_recurring_series_idempotent_when_title_renamed(
    db: Session, redis_client: Redis, family
) -> None:
    """Idempotent retry even when the first split renamed the event.

    Regression test for the original `_find_split_sibling` title-match bug:
    sibling lookup now keys on `(family_id, parent_event_id, start_at)` per
    the 0002_event_parent_id migration, so retries find the existing split
    regardless of what fields were patched on the first call."""
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom")
    _connect_member(db, mom.id)

    original = _create_recurring_event(
        db,
        family_id,
        rrule="FREQ=WEEKLY;BYDAY=MO",
        member_targets=[(mom.id, "g-mom-orig")],
    )
    instance_start = original.start_at + timedelta(days=14)

    calendar = _FakeCalendar(insert_ids=["g-mom-new", "g-mom-new-2"])
    tokens = _FakeTokenService({mom.id: "at-mom"})
    service = _build_event_service(
        db, redis_client, family_id, calendar=calendar, token_service=tokens
    )

    first = await service._split_recurring_series(
        event_id=original.id,
        instance_start_time=instance_start,
        patch_body={"title": "Soccer Mon (renamed)"},
    )
    second = await service._split_recurring_series(
        event_id=original.id,
        instance_start_time=instance_start,
        patch_body={"title": "Soccer Mon (renamed)"},
    )

    # Idempotency invariant — currently violated.
    assert second.id == first.id
    assert len(calendar.insert_calls) == 1
    rows = db.query(Event).filter(Event.family_id == family_id).count()
    assert rows == 2


# ---------------------------------------------------------------------------
# 6. Google insert fails after master patch — rollback + 502
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_recurring_series_rolls_back_when_google_insert_raises(
    db: Session, redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom")
    _connect_member(db, mom.id)

    original = _create_recurring_event(
        db,
        family_id,
        rrule="FREQ=WEEKLY;BYDAY=MO",
        member_targets=[(mom.id, "g-mom-orig")],
    )
    original_rrule = original.rrule
    instance_start = original.start_at + timedelta(days=7)

    calendar = _FakeCalendar(insert_raises=RuntimeError("Google 503"))
    tokens = _FakeTokenService({mom.id: "at-mom"})
    service = _build_event_service(
        db, redis_client, family_id, calendar=calendar, token_service=tokens
    )

    with pytest.raises(HTTPException) as exc:
        await service._split_recurring_series(
            event_id=original.id,
            instance_start_time=instance_start,
            patch_body={"title": "Renamed"},
        )

    assert exc.value.status_code == 502
    assert exc.value.detail["code"] == "events.recurring_split_partial"

    # After rollback the original RRULE survives unchanged on next read.
    db.expire_all()
    refreshed = db.query(Event).filter(Event.id == original.id).one()
    assert refreshed.rrule == original_rrule
    # And no second Event row was inserted.
    rows = db.query(Event).filter(Event.family_id == family_id).count()
    assert rows == 1


# ---------------------------------------------------------------------------
# 7. Token missing for one target — that target is skipped silently
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_recurring_series_skips_target_without_access_token(
    db: Session, redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom", color="rose")
    _connect_member(db, mom.id)
    dad = _add_member(db, family_id, name="Dad", color="amber")
    _connect_member(db, dad.id)

    original = _create_recurring_event(
        db,
        family_id,
        rrule="FREQ=WEEKLY;BYDAY=MO",
        member_targets=[(mom.id, "g-mom-orig"), (dad.id, "g-dad-orig")],
    )
    instance_start = original.start_at + timedelta(days=14)

    calendar = _FakeCalendar(insert_ids=["g-mom-new"])
    # Dad's token is None → his target is skipped.
    tokens = _FakeTokenService({mom.id: "at-mom", dad.id: None})
    service = _build_event_service(
        db, redis_client, family_id, calendar=calendar, token_service=tokens
    )

    new_ev = await service._split_recurring_series(
        event_id=original.id,
        instance_start_time=instance_start,
        patch_body={},
    )

    # Only Mom got her Google calls + her new EventTarget row.
    assert len(calendar.update_calls) == 1
    assert len(calendar.insert_calls) == 1
    assert len(new_ev.targets) == 1
    assert new_ev.targets[0].member_id == mom.id
    assert new_ev.targets[0].google_event_id == "g-mom-new"


# ---------------------------------------------------------------------------
# Module-level helpers — quick unit coverage for the RRULE math.
# ---------------------------------------------------------------------------


def test_format_until_returns_one_second_before_instance_in_utc_basic_format() -> None:
    """`_format_until` must return RFC 5545 UTC basic format, one second before
    the instance start. The new master begins exactly at the instance, so the
    capped series ends one second earlier."""
    instance = datetime(2026, 5, 13, 8, 0, 0, tzinfo=timezone.utc)
    assert _format_until(instance) == "20260513T075959Z"


def test_cap_rrule_with_until_strips_existing_until_and_count() -> None:
    instance = datetime(2026, 5, 13, 8, 0, 0, tzinfo=timezone.utc)
    capped = _cap_rrule_with_until(
        "FREQ=WEEKLY;UNTIL=20991231T000000Z;COUNT=99;BYDAY=MO", instance
    )
    parts = capped.split(";")
    # FREQ + BYDAY survive; UNTIL is the new value; COUNT and old UNTIL are gone.
    assert "FREQ=WEEKLY" in parts
    assert "BYDAY=MO" in parts
    assert "UNTIL=20260513T075959Z" in parts
    assert not any(p.startswith("COUNT=") for p in parts)
    until_count = sum(1 for p in parts if p.startswith("UNTIL="))
    assert until_count == 1


# ---------------------------------------------------------------------------
# 503 guard — service refuses to split when Google integration not configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_recurring_series_returns_503_when_calendar_not_configured(
    db: Session, redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    mom = _add_member(db, family_id, name="Mom")
    _connect_member(db, mom.id)

    original = _create_recurring_event(
        db,
        family_id,
        rrule="FREQ=WEEKLY;BYDAY=MO",
        member_targets=[(mom.id, "g-mom-orig")],
    )
    instance_start = original.start_at + timedelta(days=7)

    resolver = EventTargetResolver(db, family_id)
    streamer = ChatStreamer(redis_client)
    service = EventService(
        db, family_id, resolver, streamer, calendar=None, token_service=None
    )

    with pytest.raises(HTTPException) as exc:
        await service._split_recurring_series(
            event_id=original.id,
            instance_start_time=instance_start,
            patch_body={},
        )
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "events.recurring_split_unavailable"


# Suppress unused-import warning for uuid4 — kept for downstream helpers.
_ = (EventUpdateRequest, uuid4)

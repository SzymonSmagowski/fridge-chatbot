"""EventService — local CRUD for fridge events + Google fan-out enqueue.

Fan-out used to be the route handler's responsibility (FastAPI BackgroundTasks),
which silently dropped writes coming from the chat/voice tool path. Ownership
now sits in the service so every caller — REST, LLM tool, future cron — gets
the Google Calendar push for free. Implementation: `asyncio.create_task` on
the shared event loop after commit. Same fire-and-forget shape as
BackgroundTasks, but no FastAPI dependency.

Recurring scope semantics (D8) for PATCH/DELETE land here as light branches —
the heavy "this and following" mechanic short-circuits to a TODO branch in v1
because the FE doesn't drive it yet (calendar feature spec is Must on the
basics; recurring all_future is a Should we leave to a follow-up rather than
silently misbehave).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from dateutil.rrule import rrulestr
from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from src.core.context import current_actor
from src.core.family_events import family_event_payload
from src.models import (
    Car,
    Event,
    EventCar,
    EventTarget,
    EventTargetSyncStatus,
    ExternalEventCacheRow,
    Family,
    Member,
)
from src.schemas.events import (
    EventCreateRequest,
    EventListResponse,
    EventResponse,
    EventTargetView,
    EventUpdateRequest,
    ExternalEventResponse,
)
from src.services.chat_streaming import ChatStreamer
from src.services.event_target_resolver import EventTargetPlan, EventTargetResolver
from src.services.google_calendar_service import GoogleCalendarService
from src.services.google_token_service import GoogleTokenService
from src.services.logger import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from src.core.settings import Settings

logger = get_logger("event_service")

EventScope = Literal["instance", "all_future"]
EventSourceFilter = Literal["fridge", "external", "all"]


@dataclass
class EventListFilters:
    from_dt: datetime | None
    to_dt: datetime | None
    member_id: UUID | None
    car_id: UUID | None
    source: EventSourceFilter


class EventService:
    def __init__(
        self,
        db: Session,
        family_id: UUID,
        target_resolver: EventTargetResolver,
        streamer: ChatStreamer,
        calendar: GoogleCalendarService | None = None,
        token_service: GoogleTokenService | None = None,
        settings: "Settings | None" = None,
        session_factory: sessionmaker | None = None,
        redis: "Redis | None" = None,
    ) -> None:
        self.db = db
        self.family_id = family_id
        self.targets = target_resolver
        self.streamer = streamer
        self.calendar = calendar
        self.token_service = token_service
        # Fan-out deps. All-or-nothing: when any is None the service still
        # works for local CRUD but skips the Google push (with a warning).
        # Tests that don't exercise sync can keep their existing 4-arg
        # construction.
        self._settings = settings
        self._session_factory = session_factory
        self._redis = redis

    async def _publish(self, *, type: str, event_id: UUID) -> None:
        await self.streamer.publish_family_event(
            self.family_id,
            family_event_payload(
                type=type,
                entity="events",
                id=event_id,
                actor=current_actor.get(),
            ),
        )

    def _enqueue_fanout(self, event: Event) -> None:
        """Spawn an asyncio task that pushes each `pending` target to Google.

        Idempotent across overlapping enqueues: `sync_target` takes a Redis
        SETNX lock per (event_id, member_id) and bails when another worker
        holds it. Safe to call from both routes and the chat-tool path.
        """
        target_ids = [
            t.id
            for t in event.targets
            if t.sync_status == EventTargetSyncStatus.pending
        ]
        if not target_ids:
            return
        if (
            self._settings is None
            or self._session_factory is None
            or self._redis is None
        ):
            logger.warning(
                "fan-out skipped for event %s: EventService missing settings/session_factory/redis. "
                "Pass them in the EventService constructor to enable Google Calendar push.",
                event.id,
            )
            return
        # Late import to avoid worker→service cycle.
        from src.workers.calendar_write_worker import fan_out_event

        asyncio.create_task(
            fan_out_event(
                event_id=event.id,
                target_ids=target_ids,
                settings=self._settings,
                session_factory=self._session_factory,
                redis=self._redis,
            )
        )

    # ---- reads -------------------------------------------------------------
    def list(self, filters: EventListFilters) -> EventListResponse:
        fridge_items: list[EventResponse] = []
        external_items: list[ExternalEventResponse] = []

        if filters.source in ("fridge", "all"):
            q = self.db.query(Event).filter(Event.family_id == self.family_id)
            if filters.from_dt is not None:
                q = q.filter(Event.end_at >= filters.from_dt)
            if filters.to_dt is not None:
                q = q.filter(Event.start_at <= filters.to_dt)
            if filters.member_id is not None:
                q = q.filter(Event.assignee_member_id == filters.member_id)
            if filters.car_id is not None:
                q = q.join(EventCar, EventCar.event_id == Event.id).filter(
                    EventCar.car_id == filters.car_id
                )
            for ev in q.order_by(Event.start_at.asc()).all():
                fridge_items.append(self.to_response(ev))

        if filters.source in ("external", "all"):
            q = (
                self.db.query(ExternalEventCacheRow)
                .filter(
                    ExternalEventCacheRow.family_id == self.family_id,
                    ExternalEventCacheRow.created_by_fridge.is_(False),
                )
            )
            if filters.from_dt is not None:
                q = q.filter(ExternalEventCacheRow.end_at >= filters.from_dt)
            if filters.to_dt is not None:
                q = q.filter(ExternalEventCacheRow.start_at <= filters.to_dt)
            if filters.member_id is not None:
                q = q.filter(ExternalEventCacheRow.member_id == filters.member_id)
            for row in q.order_by(ExternalEventCacheRow.start_at.asc()).all():
                external_items.append(
                    ExternalEventResponse(
                        id=row.id,
                        family_id=row.family_id,
                        member_id=row.member_id,
                        google_event_id=row.google_event_id,
                        title=row.title,
                        description=row.description,
                        start_at=row.start_at,
                        end_at=row.end_at,
                        location=row.location,
                        is_all_day=row.is_all_day,
                        rrule=row.rrule,
                    )
                )

        return EventListResponse(
            fridge=fridge_items,
            external=external_items,
            total=len(fridge_items) + len(external_items),
        )

    def get(self, event_id: UUID) -> Event:
        ev = (
            self.db.query(Event)
            .filter(Event.id == event_id, Event.family_id == self.family_id)
            .first()
        )
        if not ev:
            raise HTTPException(
                status_code=404,
                detail={"code": "events.not_found", "detail": "Event not found"},
            )
        return ev

    # ---- writes ------------------------------------------------------------
    async def create(self, data: EventCreateRequest) -> tuple[Event, list[EventTargetPlan]]:
        self._validate_create(data)

        family = self.db.query(Family).filter(Family.id == self.family_id).first()
        fallback_tz = family.timezone if family else "UTC"

        ev = Event(
            family_id=self.family_id,
            title=data.title,
            description=self._with_car_decoration(
                data.description, data.car_ids
            ),
            start_at=data.start_at,
            end_at=data.end_at,
            timezone=data.timezone or fallback_tz,
            location=data.location,
            assignee_member_id=data.assignee_member_id,
            rrule=data.rrule,
        )
        self.db.add(ev)
        self.db.flush()

        for car_id in data.car_ids:
            ev.car_links.append(EventCar(event_id=ev.id, car_id=car_id))

        plans = self.targets.resolve_targets(
            assignee_member_id=data.assignee_member_id, car_ids=data.car_ids
        )
        for plan in plans:
            ev.targets.append(
                EventTarget(
                    event_id=ev.id,
                    member_id=plan.member_id,
                    sync_status=EventTargetSyncStatus.skipped
                    if plan.skipped_reason
                    else EventTargetSyncStatus.pending,
                    last_error=plan.skipped_reason,
                )
            )

        self.db.commit()
        self.db.refresh(ev)
        await self._publish(type="event.created", event_id=ev.id)
        self._enqueue_fanout(ev)
        return ev, plans

    async def update(
        self, event_id: UUID, data: EventUpdateRequest, scope: EventScope = "instance"
    ) -> Event:
        ev = self.get(event_id)

        # Recurring "this and following" mechanic — split the series in two.
        # See §5.7 step list and §6.7 algorithm.
        if scope == "all_future" and ev.rrule:
            new_ev = await self._split_recurring_series(
                event_id=event_id,
                instance_start_time=ev.start_at,
                patch_body=data.model_dump(exclude_unset=True),
            )
            await self._publish(type="event.updated", event_id=event_id)
            return new_ev

        updates = data.model_dump(exclude_unset=True)
        car_ids = updates.pop("car_ids", None)

        for field in (
            "title",
            "description",
            "start_at",
            "end_at",
            "timezone",
            "location",
            "assignee_member_id",
            "rrule",
        ):
            if field in updates:
                setattr(ev, field, updates[field])

        if car_ids is not None:
            ev.car_links.clear()
            for car_id in car_ids:
                ev.car_links.append(EventCar(event_id=ev.id, car_id=car_id))

        self.db.commit()
        self.db.refresh(ev)
        await self._publish(type="event.updated", event_id=ev.id)
        self._enqueue_fanout(ev)
        return ev

    async def delete(self, event_id: UUID, scope: EventScope = "instance") -> None:
        ev = self.get(event_id)
        deleted_id = ev.id
        self.db.delete(ev)
        self.db.commit()
        await self._publish(type="event.deleted", event_id=deleted_id)

    def mark_target(
        self,
        target_id: UUID,
        *,
        google_event_id: str | None,
        sync_status: EventTargetSyncStatus,
        last_error: str | None = None,
    ) -> None:
        target = (
            self.db.query(EventTarget)
            .filter(EventTarget.id == target_id)
            .first()
        )
        if not target:
            return
        target.google_event_id = google_event_id or target.google_event_id
        target.sync_status = sync_status
        target.last_error = last_error
        if sync_status == EventTargetSyncStatus.synced:
            target.synced_at = datetime.now(tz=timezone.utc)
        elif sync_status == EventTargetSyncStatus.failed:
            target.retry_count += 1
        self.db.commit()

    async def resync(self, event_id: UUID) -> Event:
        """Reset failed targets to pending and re-enqueue the fan-out.

        Also picks up stale `pending` targets — historically those came from
        the chat-tool path which never enqueued fan-out (fixed 2026-05-12),
        so re-running this on an old event drains the orphan backlog.
        `sync_target` is single-flight on Redis so this is safe to call even
        if a write is already in flight.
        """
        ev = self.get(event_id)
        for target in ev.targets:
            if target.sync_status == EventTargetSyncStatus.failed:
                target.sync_status = EventTargetSyncStatus.pending
                target.last_error = None
        self.db.commit()
        self.db.refresh(ev)
        await self._publish(type="event.resync", event_id=ev.id)
        self._enqueue_fanout(ev)
        return ev

    # ---- response builder --------------------------------------------------
    def to_response(self, ev: Event) -> EventResponse:
        return EventResponse(
            id=ev.id,
            family_id=ev.family_id,
            title=ev.title,
            description=ev.description,
            start_at=ev.start_at,
            end_at=ev.end_at,
            timezone=ev.timezone,
            location=ev.location,
            assignee_member_id=ev.assignee_member_id,
            car_ids=[link.car_id for link in ev.car_links],
            rrule=ev.rrule,
            targets=[
                EventTargetView(
                    id=t.id,
                    member_id=t.member_id,
                    google_event_id=t.google_event_id,
                    sync_status=t.sync_status.value,
                    retry_count=t.retry_count,
                    last_error=t.last_error,
                    synced_at=t.synced_at,
                )
                for t in ev.targets
            ],
            source="fridge",
            created_at=ev.created_at,
            updated_at=ev.updated_at,
        )

    # ---- validation --------------------------------------------------------
    def _validate_create(self, data: EventCreateRequest) -> None:
        """Server-side validation for chat-tool / API event creation.

        Pydantic enforces field types + title length; this layer enforces
        cross-field invariants (start/end ordering), RRULE syntax, and
        family-ownership for FKs the request supplies.
        """
        if data.end_at < data.start_at:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "events.invalid_time_range",
                    "detail": "end_at must be on or after start_at",
                },
            )

        if data.rrule:
            try:
                rrulestr(data.rrule, dtstart=data.start_at)
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "events.invalid_rrule",
                        "detail": f"Malformed RRULE {data.rrule!r}: {exc}",
                    },
                ) from exc

        if data.assignee_member_id is not None:
            in_family = (
                self.db.query(Member.id)
                .filter(
                    Member.id == data.assignee_member_id,
                    Member.family_id == self.family_id,
                )
                .first()
            )
            if in_family is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "members.not_found",
                        "detail": "Assignee member not found",
                    },
                )

        if data.car_ids:
            owned = {
                row[0]
                for row in self.db.query(Car.id)
                .filter(
                    Car.family_id == self.family_id,
                    Car.id.in_(data.car_ids),
                )
                .all()
            }
            missing = [c for c in data.car_ids if c not in owned]
            if missing:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "cars.not_found",
                        "detail": "One or more car_ids not found in this family",
                    },
                )

    def _with_car_decoration(
        self, description: str | None, car_ids: list[UUID]
    ) -> str | None:
        if not car_ids:
            return description
        cars = (
            self.db.query(Car)
            .filter(Car.family_id == self.family_id, Car.id.in_(car_ids))
            .all()
        )
        if not cars:
            return description
        car_line = " ".join(f"🚗 {c.name}" for c in cars)
        if description:
            return f"{car_line}\n{description}"
        return car_line

    # ---- recurring-series split (§5.7 / §6.7) -----------------------------
    async def _split_recurring_series(
        self,
        *,
        event_id: UUID,
        instance_start_time: datetime,
        patch_body: dict,
    ) -> Event:
        """Implements the §5.7 5-step "this and following" mechanic.

        Caps the original Google master with `UNTIL=<instance - 1s>`, inserts
        a new Google master with the patched fields and the original (uncapped)
        RRULE, then mirrors the split locally: the original local row's rrule
        becomes the capped form, and a new local row + parallel event_targets
        are inserted with `sync_status=synced` (Google already returned the
        new ids).

        Edge cases:
        - No RRULE on the local event: caller should not invoke this; we
          return the original event unchanged as a defensive no-op.
        - Existing UNTIL/COUNT on the original RRULE: stripped before the
          new UNTIL is appended.
        - Idempotency: if the local event's RRULE is already capped with
          a matching UNTIL boundary, return the existing sibling (no
          double-split).
        - Google insert failure after master patch: rolls back the local
          DB transaction and raises 502; the operator can recover via
          POST /api/events/{id}/resync.
        """
        if self.calendar is None or self.token_service is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "events.recurring_split_unavailable",
                    "detail": (
                        "Google integration not configured; cannot split recurring series"
                    ),
                },
            )

        ev = self.get(event_id)
        if not ev.rrule:
            # Edge case: caller invoked us on a non-recurring event. Treat as
            # a no-op so the caller's `update(scope="all_future")` falls
            # through to the single-instance code path on the next call.
            return ev

        # Idempotency: detect already-capped RRULE that matches this instance.
        until_token = _format_until(instance_start_time)
        if f"UNTIL={until_token}" in ev.rrule:
            sibling = self._find_split_sibling(ev, instance_start_time)
            if sibling is not None:
                return sibling

        new_rrule = _cap_rrule_with_until(ev.rrule, instance_start_time)

        # Build the new master's body fields by merging the patch over the
        # current master's surviving fields.
        merged = {
            "title": patch_body.get("title", ev.title),
            "description": patch_body.get("description", ev.description),
            "start_at": patch_body.get("start_at", instance_start_time),
            "end_at": patch_body.get("end_at", _shift_end(ev, instance_start_time)),
            "timezone": patch_body.get("timezone", ev.timezone),
            "location": patch_body.get("location", ev.location),
            "assignee_member_id": patch_body.get(
                "assignee_member_id", ev.assignee_member_id
            ),
            "rrule": ev.rrule,  # the new master keeps the ORIGINAL uncapped rrule
        }

        # Step 1-4: cap the Google master + insert the new Google master per
        # existing target (one Google round-trip pair per fanned-out member).
        target_results: list[tuple[EventTarget, str]] = []
        for target in ev.targets:
            if not target.google_event_id:
                continue
            access_token = await self.token_service.get_access_token(
                target.member_id
            )
            if not access_token:
                # Skip this target; it'll be picked up on next resync.
                continue

            try:
                # Cap the original Google master.
                await self.calendar.update(
                    access_token,
                    target.google_event_id,
                    {"recurrence": [_with_rrule_prefix(new_rrule)]},
                )
                # Insert the new Google master.
                inserted = await self.calendar.insert_raw(
                    access_token,
                    _build_google_event_body(merged),
                )
                new_google_id = inserted["id"]
                target_results.append((target, new_google_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "_split_recurring_series google call failed for target %s: %s",
                    target.id,
                    exc,
                )
                self.db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "events.recurring_split_partial",
                        "detail": (
                            "Google API error mid-split; original master may be "
                            "capped but new master missing. Use /events/{id}/resync."
                        ),
                    },
                ) from exc

        # Step 5: mirror the split in the local DB. Cap the original local
        # rrule, then insert the new master with the ORIGINAL uncapped rrule.
        ev.rrule = new_rrule

        new_local = Event(
            family_id=self.family_id,
            title=merged["title"],
            description=merged["description"],
            start_at=merged["start_at"],
            end_at=merged["end_at"],
            timezone=merged["timezone"],
            location=merged["location"],
            assignee_member_id=merged["assignee_member_id"],
            rrule=merged["rrule"],
            parent_event_id=ev.id,
        )

        # Carry car links onto the new local event.
        for link in ev.car_links:
            new_local.car_links.append(EventCar(car_id=link.car_id))

        self.db.add(new_local)
        self.db.flush()  # populate new_local.id

        # Parallel event_targets on the new local event — Google already
        # returned ids so sync_status=synced.
        now = datetime.now(tz=timezone.utc)
        for target, new_google_id in target_results:
            new_local.targets.append(
                EventTarget(
                    member_id=target.member_id,
                    google_event_id=new_google_id,
                    sync_status=EventTargetSyncStatus.synced,
                    synced_at=now,
                )
            )

        self.db.commit()
        self.db.refresh(new_local)
        return new_local

    def _find_split_sibling(
        self, original: Event, instance_start_time: datetime
    ) -> Event | None:
        """Idempotency helper — find a previously-created sibling event row.

        Matches on `(family_id, parent_event_id, start_at)` — a stable
        composite key that does NOT depend on patched fields like `title`.
        Filtering by title broke idempotency when the patch renamed the
        event (the new sibling carries the patched title, so a retry
        couldn't find it and inserted a duplicate row + duplicate Google
        master).
        """
        return (
            self.db.query(Event)
            .filter(
                Event.family_id == self.family_id,
                Event.parent_event_id == original.id,
                Event.start_at == instance_start_time,
            )
            .first()
        )


# ---- module-level helpers (no-state, easy to unit test) ----------------
def _format_until(instance_start_time: datetime) -> str:
    """RFC 5545 UTC basic format, e.g. 20260513T080000Z, one second BEFORE
    the new master's start so the original series ends right before it."""
    boundary = instance_start_time - timedelta(seconds=1)
    if boundary.tzinfo is None:
        boundary = boundary.replace(tzinfo=timezone.utc)
    boundary_utc = boundary.astimezone(timezone.utc)
    return boundary_utc.strftime("%Y%m%dT%H%M%SZ")


def _cap_rrule_with_until(original_rrule: str, instance_start_time: datetime) -> str:
    """Strip any existing UNTIL/COUNT from the RRULE, then append a new UNTIL."""
    parts = [p for p in original_rrule.split(";") if p]
    cleaned = [
        p for p in parts if not p.startswith("UNTIL=") and not p.startswith("COUNT=")
    ]
    cleaned.append(f"UNTIL={_format_until(instance_start_time)}")
    return ";".join(cleaned)


def _with_rrule_prefix(rrule: str) -> str:
    """Google's recurrence array entries must start with `RRULE:`."""
    return rrule if rrule.startswith("RRULE:") else f"RRULE:{rrule}"


def _shift_end(original: Event, new_start: datetime) -> datetime:
    """Preserve the original duration when only `start_at` is patched."""
    duration = original.end_at - original.start_at
    return new_start + duration


def _build_google_event_body(merged: dict) -> dict:
    """Build the Google Events.insert body from a merged-fields dict."""
    body: dict = {
        "summary": merged["title"],
        "start": {
            "dateTime": merged["start_at"].isoformat(),
            "timeZone": merged["timezone"],
        },
        "end": {
            "dateTime": merged["end_at"].isoformat(),
            "timeZone": merged["timezone"],
        },
    }
    if merged.get("description") is not None:
        body["description"] = merged["description"]
    if merged.get("location") is not None:
        body["location"] = merged["location"]
    if merged.get("rrule"):
        body["recurrence"] = [_with_rrule_prefix(merged["rrule"])]
    return body

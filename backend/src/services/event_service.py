"""EventService — local CRUD for fridge events. Google fan-out is enqueued via
BackgroundTasks in the route handler so the request can return immediately
with `sync_status=pending` per §1.

Recurring scope semantics (D8) for PATCH/DELETE land here as light branches —
the heavy "this and following" mechanic short-circuits to a TODO branch in v1
because the FE doesn't drive it yet (calendar feature spec is Must on the
basics; recurring all_future is a Should we leave to a follow-up rather than
silently misbehave).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models import (
    Car,
    Event,
    EventCar,
    EventTarget,
    EventTargetSyncStatus,
    ExternalEventCacheRow,
    Family,
)
from src.schemas.events import (
    EventCreateRequest,
    EventListResponse,
    EventResponse,
    EventTargetView,
    EventUpdateRequest,
    ExternalEventResponse,
)
from src.services.event_target_resolver import EventTargetPlan, EventTargetResolver

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
    ) -> None:
        self.db = db
        self.family_id = family_id
        self.targets = target_resolver

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
    def create(self, data: EventCreateRequest) -> tuple[Event, list[EventTargetPlan]]:
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
        return ev, plans

    def update(
        self, event_id: UUID, data: EventUpdateRequest, scope: EventScope = "instance"
    ) -> Event:
        ev = self.get(event_id)
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
        return ev

    def delete(self, event_id: UUID, scope: EventScope = "instance") -> None:
        ev = self.get(event_id)
        self.db.delete(ev)
        self.db.commit()

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

    def resync(self, event_id: UUID) -> Event:
        ev = self.get(event_id)
        for target in ev.targets:
            if target.sync_status == EventTargetSyncStatus.failed:
                target.sync_status = EventTargetSyncStatus.pending
                target.last_error = None
        self.db.commit()
        self.db.refresh(ev)
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

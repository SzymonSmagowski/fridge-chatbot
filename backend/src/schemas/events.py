"""Event request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EventTargetSyncStatusName = Literal["pending", "synced", "failed", "skipped"]
EventScope = Literal["instance", "all_future"]
EventSourceFilter = Literal["fridge", "external", "all"]


class EventTargetView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    member_id: UUID
    google_event_id: str | None = None
    sync_status: EventTargetSyncStatusName
    retry_count: int
    last_error: str | None = None
    synced_at: datetime | None = None


class EventCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    start_at: datetime
    end_at: datetime
    timezone: str | None = None
    location: str | None = None
    assignee_member_id: UUID | None = None
    car_ids: list[UUID] = Field(default_factory=list)
    rrule: str | None = None


class EventUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    location: str | None = None
    assignee_member_id: UUID | None = None
    car_ids: list[UUID] | None = None
    rrule: str | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime
    timezone: str
    location: str | None = None
    assignee_member_id: UUID | None = None
    car_ids: list[UUID]
    rrule: str | None = None
    targets: list[EventTargetView]
    source: Literal["fridge", "external"] = "fridge"
    created_at: datetime
    updated_at: datetime


class ExternalEventResponse(BaseModel):
    """External (read-only) event from a member's Google Calendar.

    Mirrors the shape of EventResponse where it makes sense so the FE can
    render fridge + external events with the same component.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    member_id: UUID
    google_event_id: str
    title: str | None = None
    description: str | None = None
    start_at: datetime
    end_at: datetime
    location: str | None = None
    is_all_day: bool
    rrule: str | None = None
    source: Literal["external"] = "external"


class EventListResponse(BaseModel):
    fridge: list[EventResponse]
    external: list[ExternalEventResponse]
    total: int

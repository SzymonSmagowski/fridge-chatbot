"""Note request/response models."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NoteLabelView(BaseModel):
    slug: str
    display_name: str


class NoteCreateRequest(BaseModel):
    content: str = ""
    icon: str | None = None
    label_slugs: list[str] = Field(default_factory=list)
    pinned: bool = False
    assignee_member_id: UUID | None = None
    car_ids: list[UUID] = Field(default_factory=list)
    linked_event_id: UUID | None = None


class NoteUpdateRequest(BaseModel):
    content: str | None = None
    icon: str | None = None
    label_slugs: list[str] | None = None
    pinned: bool | None = None
    assignee_member_id: UUID | None = None
    car_ids: list[UUID] | None = None
    linked_event_id: UUID | None = None


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    content: str
    icon: str | None = None
    labels: list[NoteLabelView]
    pinned: bool
    assignee_member_id: UUID | None = None
    car_ids: list[UUID]
    linked_event_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class NoteListResponse(BaseModel):
    items: list[NoteResponse]
    total: int


class ShoppingListAppendRequest(BaseModel):
    line: str = Field(min_length=1)

"""Car request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CarCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    year: int | None = None
    color_label: str | None = None
    color: str = "stone"
    notes: str | None = None


class CarUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    year: int | None = None
    color_label: str | None = None
    color: str | None = None
    notes: str | None = None


class CarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    name: str
    year: int | None = None
    color_label: str | None = None
    color: str
    notes: str | None = None
    status: Literal["active", "inactive"]
    created_at: datetime

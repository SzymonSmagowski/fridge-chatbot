"""Label request/response models."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LabelCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)


class LabelUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class LabelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str
    is_reserved: bool
    note_count: int

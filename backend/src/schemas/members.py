"""Member request/response models including the joined Google state."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

GoogleStateName = Literal[
    "connected", "reconnect_needed", "revoked", "not_connected"
]


class GoogleState(BaseModel):
    status: GoogleStateName
    email: str | None = None
    connected_at: datetime | None = None


class MemberCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    nickname: str | None = None
    color: str = Field(min_length=1, max_length=32)


class MemberUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    nickname: str | None = None
    color: str | None = Field(default=None, min_length=1, max_length=32)


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    name: str
    nickname: str | None = None
    color: str
    status: Literal["active", "inactive"]
    is_setup_owner: bool
    google: GoogleState
    created_at: datetime

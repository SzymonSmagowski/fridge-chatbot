"""Calendar-sync ops endpoint response models."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SyncStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    member_id: UUID
    member_name: str
    last_pull_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    consecutive_failures: int
    google_status: str  # connected | reconnect_needed | revoked | not_connected

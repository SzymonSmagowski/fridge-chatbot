"""OAuth + pairing request/response models."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class PairingStartRequest(BaseModel):
    device_label: str | None = None


class PairingStartResponse(BaseModel):
    pairing_id: str
    authorize_url: str


class AuthorizeUrlResponse(BaseModel):
    authorize_url: str


class GoogleConnectStartResponse(BaseModel):
    authorize_url: str
    member_id: UUID

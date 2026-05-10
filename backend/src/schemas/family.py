"""Family + FamilyPreferences request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# `auto` = detect per turn from user input; `en` / `pl` = seed default
# language. Used by `detect_language` graph node and the voice greeting.
VoiceLocale = Literal["auto", "en", "pl"]


class FamilyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    timezone: str
    created_at: datetime


class FamilyUpdate(BaseModel):
    name: str | None = None
    timezone: str | None = None


class FamilyPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    family_id: UUID
    sync_interval_sec: int
    fanout_enabled: bool
    voice_wake_enabled: bool
    always_on: bool
    auto_create_shopping_list: bool
    voice_locale: VoiceLocale
    updated_at: datetime


class FamilyPreferencesPatch(BaseModel):
    sync_interval_sec: int | None = None
    fanout_enabled: bool | None = None
    voice_wake_enabled: bool | None = None
    always_on: bool | None = None
    auto_create_shopping_list: bool | None = None
    voice_locale: VoiceLocale | None = None

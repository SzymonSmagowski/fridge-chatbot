"""Get + patch the family preferences row."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.context import current_actor
from src.core.family_events import family_event_payload
from src.models import FamilyPreferences
from src.schemas.family import FamilyPreferencesPatch
from src.services.chat_streaming import ChatStreamer


class FamilyPreferencesService:
    def __init__(
        self, db: Session, family_id: UUID, streamer: ChatStreamer
    ) -> None:
        self.db = db
        self.family_id = family_id
        self.streamer = streamer

    def get(self) -> FamilyPreferences:
        prefs = (
            self.db.query(FamilyPreferences)
            .filter(FamilyPreferences.family_id == self.family_id)
            .first()
        )
        if not prefs:
            raise HTTPException(status_code=404, detail="Family preferences not found")
        return prefs

    async def patch(self, data: FamilyPreferencesPatch) -> FamilyPreferences:
        prefs = self.get()
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(prefs, field, value)
        self.db.commit()
        self.db.refresh(prefs)
        await self.streamer.publish_family_event(
            self.family_id,
            family_event_payload(
                type="family_preferences.updated",
                entity="family_preferences",
                id=self.family_id,
                actor=current_actor.get(),
            ),
        )
        return prefs

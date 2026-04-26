"""Read + patch the family row itself (name, timezone)."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.context import current_actor
from src.core.family_events import family_event_payload
from src.models import Family
from src.services.chat_streaming import ChatStreamer


class FamilyService:
    def __init__(
        self, db: Session, family_id: UUID, streamer: ChatStreamer
    ) -> None:
        self.db = db
        self.family_id = family_id
        self.streamer = streamer

    def get(self) -> Family:
        family = self.db.query(Family).filter(Family.id == self.family_id).first()
        if not family:
            raise HTTPException(status_code=404, detail="Family not found")
        return family

    async def update(self, *, name: str | None, timezone: str | None) -> Family:
        family = self.get()
        if name is not None:
            family.name = name
        if timezone is not None:
            family.timezone = timezone
        self.db.commit()
        self.db.refresh(family)
        await self.streamer.publish_family_event(
            self.family_id,
            family_event_payload(
                type="family.updated",
                entity="family",
                id=self.family_id,
                actor=current_actor.get(),
            ),
        )
        return family

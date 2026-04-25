"""Read + patch the family row itself (name, timezone)."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models import Family


class FamilyService:
    def __init__(self, db: Session, family_id: UUID) -> None:
        self.db = db
        self.family_id = family_id

    def get(self) -> Family:
        family = self.db.query(Family).filter(Family.id == self.family_id).first()
        if not family:
            raise HTTPException(status_code=404, detail="Family not found")
        return family

    def update(self, *, name: str | None, timezone: str | None) -> Family:
        family = self.get()
        if name is not None:
            family.name = name
        if timezone is not None:
            family.timezone = timezone
        self.db.commit()
        self.db.refresh(family)
        return family

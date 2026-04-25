"""LabelService — list/CRUD plus the upsert_for_slugs helper that NoteService
calls on create/update so unknown slugs auto-materialize.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.labels import (
    RESERVED_DISPLAY_NAMES,
    RESERVED_SLUGS,
    display_name_for_slug,
    is_reserved,
    normalize_slug,
)
from src.models import Label, NoteLabel
from src.schemas.labels import LabelResponse


class LabelReservedError(Exception):
    pass


class LabelService:
    def __init__(self, db: Session, family_id: UUID) -> None:
        self.db = db
        self.family_id = family_id

    def list(self) -> list[Label]:
        return (
            self.db.query(Label)
            .filter(Label.family_id == self.family_id)
            .order_by(Label.display_name.asc())
            .all()
        )

    def get(self, slug: str) -> Label:
        label = (
            self.db.query(Label)
            .filter(Label.family_id == self.family_id, Label.slug == slug)
            .first()
        )
        if not label:
            raise HTTPException(
                status_code=404,
                detail={"code": "labels.not_found", "detail": "Label not found"},
            )
        return label

    def create(self, slug: str, display_name: str) -> Label:
        slug = normalize_slug(slug)
        if not slug:
            raise HTTPException(
                status_code=422,
                detail={"code": "labels.invalid_slug", "detail": "slug is empty"},
            )
        existing = (
            self.db.query(Label)
            .filter(Label.family_id == self.family_id, Label.slug == slug)
            .first()
        )
        if existing:
            return existing
        label = Label(
            family_id=self.family_id, slug=slug, display_name=display_name.strip()
        )
        self.db.add(label)
        self.db.commit()
        self.db.refresh(label)
        return label

    def update(self, slug: str, display_name: str) -> Label:
        label = self.get(slug)
        label.display_name = display_name.strip()
        self.db.commit()
        self.db.refresh(label)
        return label

    def delete(self, slug: str) -> None:
        if is_reserved(slug):
            raise LabelReservedError(slug)
        label = self.get(slug)
        self.db.delete(label)
        self.db.commit()

    def upsert_for_slugs(self, raw_slugs: list[str]) -> list[Label]:
        """Normalize input slugs, ensure every one exists in `labels`, return them.

        Reserved slugs are rendered with their curated display name; everything
        else is title-cased.
        """
        normalized: list[str] = []
        for raw in raw_slugs:
            slug = normalize_slug(raw)
            if slug and slug not in normalized:
                normalized.append(slug)
        if not normalized:
            return []

        existing = (
            self.db.query(Label)
            .filter(Label.family_id == self.family_id, Label.slug.in_(normalized))
            .all()
        )
        existing_slugs = {label.slug for label in existing}

        for slug in normalized:
            if slug in existing_slugs:
                continue
            label = Label(
                family_id=self.family_id,
                slug=slug,
                display_name=display_name_for_slug(slug),
            )
            self.db.add(label)
            existing.append(label)
        self.db.flush()
        return [label for label in existing if label.slug in set(normalized)]

    def to_response(self, label: Label) -> LabelResponse:
        note_count = (
            self.db.query(NoteLabel)
            .filter(
                NoteLabel.family_id == self.family_id,
                NoteLabel.label_slug == label.slug,
            )
            .count()
        )
        return LabelResponse(
            slug=label.slug,
            display_name=label.display_name,
            is_reserved=is_reserved(label.slug),
            note_count=note_count,
        )

    @staticmethod
    def reserved_display_name(slug: str) -> str:
        return RESERVED_DISPLAY_NAMES.get(slug, display_name_for_slug(slug))

    @staticmethod
    def reserved_slugs() -> frozenset[str]:
        return RESERVED_SLUGS

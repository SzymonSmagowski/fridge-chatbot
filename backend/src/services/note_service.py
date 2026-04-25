"""NoteService — list/get/create/update/delete + shopping-list append.

Auto-materializes label slugs via LabelService.upsert_for_slugs so the chat
assistant's `add_note(label_slugs=["shopping-list"])` is always safe.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models import FamilyPreferences, Note, NoteCar, NoteLabel
from src.schemas.notes import (
    NoteCreateRequest,
    NoteLabelView,
    NoteResponse,
    NoteUpdateRequest,
)
from src.services.label_service import LabelService

SHOPPING_LIST_SLUG = "shopping-list"


@dataclass
class NoteListFilters:
    pinned: str = "all"  # "true" | "false" | "all"
    label: str | None = None
    assignee_member_id: UUID | None = None
    limit: int = 200
    offset: int = 0


class NoteService:
    def __init__(
        self, db: Session, family_id: UUID, label_service: LabelService
    ) -> None:
        self.db = db
        self.family_id = family_id
        self.labels = label_service

    # ---- reads -------------------------------------------------------------
    def list(self, filters: NoteListFilters) -> tuple[list[Note], int]:
        q = self.db.query(Note).filter(Note.family_id == self.family_id)

        if filters.pinned == "true":
            q = q.filter(Note.pinned.is_(True))
        elif filters.pinned == "false":
            q = q.filter(Note.pinned.is_(False))
        if filters.assignee_member_id is not None:
            q = q.filter(Note.assignee_member_id == filters.assignee_member_id)
        if filters.label:
            q = q.join(NoteLabel, NoteLabel.note_id == Note.id).filter(
                NoteLabel.family_id == self.family_id,
                NoteLabel.label_slug == filters.label,
            )

        total = q.count()
        items = (
            q.order_by(Note.pinned.desc(), Note.updated_at.desc())
            .offset(filters.offset)
            .limit(filters.limit)
            .all()
        )
        return items, total

    def get(self, note_id: UUID) -> Note:
        note = (
            self.db.query(Note)
            .filter(Note.id == note_id, Note.family_id == self.family_id)
            .first()
        )
        if not note:
            raise HTTPException(
                status_code=404,
                detail={"code": "notes.not_found", "detail": "Note not found"},
            )
        return note

    # ---- writes ------------------------------------------------------------
    def create(self, data: NoteCreateRequest) -> Note:
        note = Note(
            family_id=self.family_id,
            content=data.content or "",
            icon=data.icon,
            pinned=data.pinned,
            assignee_member_id=data.assignee_member_id,
            linked_event_id=data.linked_event_id,
        )
        self.db.add(note)
        self.db.flush()  # populate note.id

        self._set_labels(note, data.label_slugs)
        self._set_cars(note, data.car_ids)
        self.db.commit()
        self.db.refresh(note)
        return note

    def update(self, note_id: UUID, data: NoteUpdateRequest) -> Note:
        note = self.get(note_id)
        updates = data.model_dump(exclude_unset=True)

        for field in ("content", "icon", "pinned", "assignee_member_id", "linked_event_id"):
            if field in updates:
                setattr(note, field, updates[field])

        if "label_slugs" in updates:
            self._set_labels(note, updates["label_slugs"] or [])
        if "car_ids" in updates:
            self._set_cars(note, updates["car_ids"] or [])

        self.db.commit()
        self.db.refresh(note)
        return note

    def delete(self, note_id: UUID) -> None:
        note = self.get(note_id)
        self.db.delete(note)
        self.db.commit()

    def append_shopping_list(
        self, line: str, *, auto_create_default: bool
    ) -> Note:
        line = line.strip()
        if not line:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "notes.shopping_list_empty",
                    "detail": "Shopping-list line cannot be empty",
                },
            )

        existing = self._find_latest_with_label(SHOPPING_LIST_SLUG)
        if existing:
            current_lines = existing.content.splitlines()
            if not current_lines or current_lines[-1].strip() != line:
                existing.content = (
                    f"{existing.content}\n{line}" if existing.content else line
                )
            self.db.commit()
            self.db.refresh(existing)
            return existing

        prefs = (
            self.db.query(FamilyPreferences)
            .filter(FamilyPreferences.family_id == self.family_id)
            .first()
        )
        auto_create = (
            prefs.auto_create_shopping_list if prefs else auto_create_default
        )
        if not auto_create:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "notes.shopping_list_missing",
                    "detail": "No shopping-list note exists and auto-create is disabled",
                },
            )

        return self.create(
            NoteCreateRequest(
                content=line,
                pinned=True,
                label_slugs=[SHOPPING_LIST_SLUG],
            )
        )

    # ---- helpers -----------------------------------------------------------
    def _set_labels(self, note: Note, slugs: list[str]) -> None:
        # Replace label set wholesale; cascade-delete handles removal.
        note.label_links.clear()
        if not slugs:
            self.db.flush()
            return
        labels = self.labels.upsert_for_slugs(slugs)
        for label in labels:
            note.label_links.append(
                NoteLabel(
                    note_id=note.id,
                    family_id=self.family_id,
                    label_slug=label.slug,
                )
            )
        self.db.flush()

    def _set_cars(self, note: Note, car_ids: list[UUID]) -> None:
        note.car_links.clear()
        for car_id in car_ids:
            note.car_links.append(NoteCar(note_id=note.id, car_id=car_id))
        self.db.flush()

    def _find_latest_with_label(self, slug: str) -> Note | None:
        return (
            self.db.query(Note)
            .join(NoteLabel, NoteLabel.note_id == Note.id)
            .filter(
                Note.family_id == self.family_id,
                NoteLabel.family_id == self.family_id,
                NoteLabel.label_slug == slug,
            )
            .order_by(Note.updated_at.desc())
            .first()
        )

    # ---- response builder --------------------------------------------------
    def to_response(self, note: Note) -> NoteResponse:
        label_views: list[NoteLabelView] = []
        for link in note.label_links:
            display = (
                link.label.display_name
                if link.label
                else LabelService.reserved_display_name(link.label_slug)
            )
            label_views.append(
                NoteLabelView(slug=link.label_slug, display_name=display)
            )
        car_ids = [link.car_id for link in note.car_links]

        return NoteResponse(
            id=note.id,
            family_id=note.family_id,
            content=note.content,
            icon=note.icon,
            labels=label_views,
            pinned=note.pinned,
            assignee_member_id=note.assignee_member_id,
            car_ids=car_ids,
            linked_event_id=note.linked_event_id,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

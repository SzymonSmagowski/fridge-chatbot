"""Note + NoteCar junction."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.db.postgres import Base


class Note(Base):
    __tablename__ = "notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignee_member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    content = Column(Text, nullable=False, default="")
    icon = Column(String(64), nullable=True)
    pinned = Column(Boolean, nullable=False, default=False)
    linked_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    family = relationship("Family", back_populates="notes")
    label_links = relationship(
        "NoteLabel", back_populates="note", cascade="all, delete-orphan"
    )
    car_links = relationship(
        "NoteCar", back_populates="note", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_notes_family_pinned_updated",
            "family_id",
            "pinned",
            "updated_at",
        ),
        Index("ix_notes_family_assignee", "family_id", "assignee_member_id"),
    )


class NoteCar(Base):
    __tablename__ = "note_cars"

    note_id = Column(UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"))
    car_id = Column(UUID(as_uuid=True), ForeignKey("cars.id", ondelete="CASCADE"))

    note = relationship("Note", back_populates="car_links")
    car = relationship("Car")

    __table_args__ = (
        PrimaryKeyConstraint("note_id", "car_id", name="pk_note_cars"),
    )

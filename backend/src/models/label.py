"""Label + NoteLabel junction. Replaces the old `notes.labels: text[]` column."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.db.postgres import Base


class Label(Base):
    __tablename__ = "labels"

    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug = Column(String(64), nullable=False)
    display_name = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("Family", back_populates="labels")
    note_links = relationship(
        "NoteLabel",
        back_populates="label",
        cascade="all, delete-orphan",
        primaryjoin="and_(Label.family_id==NoteLabel.family_id, "
                    "Label.slug==NoteLabel.label_slug)",
    )

    __table_args__ = (
        PrimaryKeyConstraint("family_id", "slug", name="pk_labels"),
        Index("ix_labels_family", "family_id"),
    )


class NoteLabel(Base):
    __tablename__ = "note_labels"

    note_id = Column(
        UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    family_id = Column(UUID(as_uuid=True), nullable=False)
    label_slug = Column(String(64), nullable=False)

    note = relationship("Note", back_populates="label_links")
    label = relationship(
        "Label",
        back_populates="note_links",
        primaryjoin="and_(NoteLabel.family_id==Label.family_id, "
                    "NoteLabel.label_slug==Label.slug)",
        foreign_keys=[family_id, label_slug],
    )

    __table_args__ = (
        PrimaryKeyConstraint("note_id", "label_slug", name="pk_note_labels"),
        ForeignKeyConstraint(
            ["family_id", "label_slug"],
            ["labels.family_id", "labels.slug"],
            ondelete="CASCADE",
            name="fk_note_labels_label",
        ),
        Index("ix_note_labels_family_slug", "family_id", "label_slug"),
    )

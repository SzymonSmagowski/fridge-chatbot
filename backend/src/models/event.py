"""Event, EventTarget, EventCar, ExternalEventCacheRow."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.db.postgres import Base


class EventTargetSyncStatus(str, enum.Enum):
    pending = "pending"
    synced = "synced"
    failed = "failed"
    skipped = "skipped"


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    timezone = Column(String(64), nullable=False)
    location = Column(String(400), nullable=True)
    assignee_member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    rrule = Column(Text, nullable=True)
    parent_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    family = relationship("Family", back_populates="events")
    targets = relationship(
        "EventTarget", back_populates="event", cascade="all, delete-orphan"
    )
    car_links = relationship(
        "EventCar", back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_events_family_start", "family_id", "start_at"),
        Index("ix_events_family_assignee", "family_id", "assignee_member_id"),
        Index(
            "ix_events_family_parent_start",
            "family_id",
            "parent_event_id",
            "start_at",
        ),
    )


class EventTarget(Base):
    __tablename__ = "event_targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
    )
    google_event_id = Column(String(256), nullable=True)
    sync_status = Column(
        Enum(EventTargetSyncStatus, name="event_target_sync_status"),
        nullable=False,
        default=EventTargetSyncStatus.pending,
    )
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    synced_at = Column(DateTime, nullable=True)

    event = relationship("Event", back_populates="targets")
    member = relationship("Member")

    __table_args__ = (
        UniqueConstraint("event_id", "member_id", name="uq_event_targets_event_member"),
        Index("ix_event_targets_status_retry", "sync_status", "retry_count"),
    )


class EventCar(Base):
    __tablename__ = "event_cars"

    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    car_id = Column(UUID(as_uuid=True), ForeignKey("cars.id", ondelete="CASCADE"))

    event = relationship("Event", back_populates="car_links")
    car = relationship("Car")

    __table_args__ = (
        PrimaryKeyConstraint("event_id", "car_id", name="pk_event_cars"),
    )


class ExternalEventCacheRow(Base):
    __tablename__ = "external_events_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
    )
    google_event_id = Column(String(256), nullable=False)
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    location = Column(String(400), nullable=True)
    is_all_day = Column(Boolean, nullable=False, default=False)
    rrule = Column(Text, nullable=True)
    created_by_fridge = Column(Boolean, nullable=False, default=False)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    member = relationship("Member")

    __table_args__ = (
        UniqueConstraint(
            "member_id", "google_event_id", name="uq_external_events_member_geid"
        ),
        Index("ix_external_events_family_start", "family_id", "start_at"),
        Index(
            "ix_external_events_family_member_start",
            "family_id",
            "member_id",
            "start_at",
        ),
    )

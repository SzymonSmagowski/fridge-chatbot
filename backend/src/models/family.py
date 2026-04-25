"""Family / FamilyPreferences / Device — scope root for everything per-family."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.db.postgres import Base


class Family(Base):
    __tablename__ = "families"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    timezone = Column(String(64), nullable=False, default="Europe/Warsaw")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    preferences = relationship(
        "FamilyPreferences",
        uselist=False,
        back_populates="family",
        cascade="all, delete-orphan",
    )
    devices = relationship("Device", back_populates="family", cascade="all, delete-orphan")
    members = relationship("Member", back_populates="family", cascade="all, delete-orphan")
    cars = relationship("Car", back_populates="family", cascade="all, delete-orphan")
    labels = relationship("Label", back_populates="family", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="family", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="family", cascade="all, delete-orphan")


class FamilyPreferences(Base):
    __tablename__ = "family_preferences"

    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sync_interval_sec = Column(Integer, nullable=False, default=300)
    fanout_enabled = Column(Boolean, nullable=False, default=True)
    voice_wake_enabled = Column(Boolean, nullable=False, default=False)
    always_on = Column(Boolean, nullable=False, default=True)
    auto_create_shopping_list = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    family = relationship("Family", back_populates="preferences")


class Device(Base):
    __tablename__ = "devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(120), nullable=True)
    paired_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    # Shadow user FK so existing /threads endpoints (which take user FK) keep
    # working without rewrite. One shadow user per device, created at pairing.
    shadow_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    family = relationship("Family", back_populates="devices")

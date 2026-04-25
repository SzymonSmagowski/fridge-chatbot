"""Member, GoogleToken (encrypted refresh token), CalendarSyncState."""
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
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.db.postgres import Base


class MemberStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class GoogleTokenStatus(str, enum.Enum):
    connected = "connected"
    reconnect_needed = "reconnect_needed"
    revoked = "revoked"


class Member(Base):
    __tablename__ = "members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(120), nullable=False)
    nickname = Column(String(120), nullable=True)
    color = Column(String(32), nullable=False)
    status = Column(
        Enum(MemberStatus, name="member_status"),
        nullable=False,
        default=MemberStatus.active,
    )
    is_setup_owner = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("Family", back_populates="members")
    google_token = relationship(
        "GoogleToken",
        uselist=False,
        back_populates="member",
        cascade="all, delete-orphan",
    )
    sync_state = relationship(
        "CalendarSyncState",
        uselist=False,
        back_populates="member",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_members_family_status", "family_id", "status"),
    )


class GoogleToken(Base):
    __tablename__ = "google_tokens"

    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        primary_key=True,
    )
    refresh_token_encrypted = Column(LargeBinary, nullable=False)
    google_sub = Column(String(64), nullable=False)
    google_email = Column(String(200), nullable=False)
    scope = Column(String(400), nullable=False)
    status = Column(
        Enum(GoogleTokenStatus, name="google_token_status"),
        nullable=False,
        default=GoogleTokenStatus.connected,
    )
    connected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_refreshed_at = Column(DateTime, nullable=True)

    member = relationship("Member", back_populates="google_token")


class CalendarSyncState(Base):
    __tablename__ = "calendar_sync_state"

    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_pull_at = Column(DateTime, nullable=True)
    last_pull_sync_token = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)

    member = relationship("Member", back_populates="sync_state")

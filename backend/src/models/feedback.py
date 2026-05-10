"""Feedback — household-to-developer reports (bugs, ideas, questions).

Family-scoped. Both UI submissions (`POST /api/feedback`) and assistant-
mediated submissions (`submit_feedback` LangGraph tool) write here.
`author_kind` distinguishes the two. The REST schema deliberately doesn't
expose `author_kind` — the route hardcodes `user`; the tool path is the only
way `assistant_on_behalf_of_user` ever lands in the table.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID

from src.db.postgres import Base


class FeedbackCategory(str, enum.Enum):
    bug = "bug"
    improvement = "improvement"
    question = "question"
    other = "other"


class FeedbackAuthorKind(str, enum.Enum):
    user = "user"
    assistant_on_behalf_of_user = "assistant_on_behalf_of_user"


class FeedbackStatus(str, enum.Enum):
    open = "open"
    reviewing = "reviewing"
    resolved = "resolved"


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("threads.thread_id", ondelete="SET NULL"),
        nullable=True,
    )
    category = Column(
        SAEnum(FeedbackCategory, name="feedback_category", create_type=False),
        nullable=False,
    )
    message = Column(Text, nullable=False)
    author_kind = Column(
        SAEnum(FeedbackAuthorKind, name="feedback_author_kind", create_type=False),
        nullable=False,
    )
    status = Column(
        SAEnum(FeedbackStatus, name="feedback_status", create_type=False),
        nullable=False,
        default=FeedbackStatus.open,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_feedback_family_created", "family_id", "created_at"),
        Index("ix_feedback_family_status", "family_id", "status"),
    )

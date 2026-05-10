"""FeedbackService — family-scoped CRUD for the feedback channel.

Two write paths:
- `submit_from_user` — called from `POST /api/feedback`. Records the device
  and (optionally) the chat thread the feedback was sent from. Always writes
  `author_kind=user`.
- `submit_from_assistant` — called from the LangGraph `submit_feedback` tool.
  Always writes `author_kind=assistant_on_behalf_of_user`. The tool can only
  be reached after the user explicitly confirmed in chat (see the system
  prompt addition in shared/prompts.py).

The split exists so the HTTP boundary cannot ever produce
`assistant_on_behalf_of_user` — that's a security boundary, not a stylistic
preference.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.models.feedback import (
    Feedback,
    FeedbackAuthorKind,
    FeedbackCategory,
    FeedbackStatus,
)


@dataclass
class FeedbackListFilters:
    status: Optional[FeedbackStatus] = None
    limit: int = 30
    before: Optional[tuple[datetime, UUID]] = None


class FeedbackService:
    def __init__(self, db: Session, family_id: UUID) -> None:
        self.db = db
        self.family_id = family_id

    async def submit_from_user(
        self,
        *,
        category: FeedbackCategory,
        message: str,
        thread_id: Optional[UUID],
        member_id: Optional[UUID],
        device_id: Optional[UUID],
    ) -> Feedback:
        return self._insert(
            category=category,
            message=message,
            thread_id=thread_id,
            member_id=member_id,
            device_id=device_id,
            author_kind=FeedbackAuthorKind.user,
        )

    async def submit_from_assistant(
        self,
        *,
        category: FeedbackCategory,
        message: str,
        thread_id: Optional[UUID],
    ) -> Feedback:
        # No member_id / device_id from the assistant path — the LangGraph
        # tool only knows family_id. Resolving device_id from the WS context
        # could be added later but doesn't add operational value yet.
        return self._insert(
            category=category,
            message=message,
            thread_id=thread_id,
            member_id=None,
            device_id=None,
            author_kind=FeedbackAuthorKind.assistant_on_behalf_of_user,
        )

    def list_page(
        self, filters: FeedbackListFilters
    ) -> tuple[list[Feedback], bool]:
        """Cursor-paginated, newest-first. Returns (items, has_more).

        Same emulated tuple-comparison as `list_thread_messages_page` so two
        feedback rows with equal `created_at` (rare, but possible under fast
        bursts) are still totally ordered.
        """
        q = self.db.query(Feedback).filter(Feedback.family_id == self.family_id)
        if filters.status is not None:
            q = q.filter(Feedback.status == filters.status)
        if filters.before is not None:
            ts, fid = filters.before
            q = q.filter(
                or_(
                    Feedback.created_at < ts,
                    and_(Feedback.created_at == ts, Feedback.id < fid),
                )
            )
        rows = (
            q.order_by(Feedback.created_at.desc(), Feedback.id.desc())
            .limit(filters.limit + 1)
            .all()
        )
        has_more = len(rows) > filters.limit
        return rows[: filters.limit], has_more

    def _insert(
        self,
        *,
        category: FeedbackCategory,
        message: str,
        thread_id: Optional[UUID],
        member_id: Optional[UUID],
        device_id: Optional[UUID],
        author_kind: FeedbackAuthorKind,
    ) -> Feedback:
        row = Feedback(
            family_id=self.family_id,
            category=category,
            message=message,
            thread_id=thread_id,
            member_id=member_id,
            device_id=device_id,
            author_kind=author_kind,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

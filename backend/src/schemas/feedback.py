"""Feedback request/response models (§B.5)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FeedbackCategoryLiteral = Literal["bug", "improvement", "question", "other"]
FeedbackAuthorKindLiteral = Literal["user", "assistant_on_behalf_of_user"]
FeedbackStatusLiteral = Literal["open", "reviewing", "resolved"]


class FeedbackCreateRequest(BaseModel):
    """Body for `POST /api/feedback`.

    `author_kind` is intentionally absent — the REST handler always writes
    `user`. The assistant path writes `assistant_on_behalf_of_user` via
    `FeedbackService.submit_from_assistant`, which is unreachable from HTTP.
    """

    category: FeedbackCategoryLiteral
    message: str = Field(min_length=1, max_length=4000)
    thread_id: Optional[UUID] = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    member_id: Optional[UUID] = None
    device_id: Optional[UUID] = None
    thread_id: Optional[UUID] = None
    category: FeedbackCategoryLiteral
    message: str
    author_kind: FeedbackAuthorKindLiteral
    status: FeedbackStatusLiteral
    created_at: datetime
    updated_at: datetime


class FeedbackListResponse(BaseModel):
    """Cursor-paginated, newest-first list page.

    Same envelope as the messages page so the FE has one shape to remember.
    `next_cursor` references the OLDEST feedback in the page.
    """

    items: list[FeedbackResponse]
    has_more: bool
    next_cursor: Optional[str] = None

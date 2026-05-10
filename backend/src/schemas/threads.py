from typing import List, Optional

from pydantic import BaseModel


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    type: str = "message"
    created_at: Optional[str] = None
    score: Optional[str] = None
    comment: Optional[str] = None

    class Config:
        from_attributes = True


class ThreadResponse(BaseModel):
    id: int
    thread_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MessagesPageResponse(BaseModel):
    """Cursor-paginated chat history page envelope.

    Used by both `GET /threads/{id}/messages` and the messages-bearing portion
    of `GET /threads/{id}` (via composition into ThreadMessagesResponse).
    Wire order is newest-first; `next_cursor` points at the OLDEST message in
    the page (the last array element). FE re-uses next_cursor as `before` to
    fetch the next-older page.
    """

    messages: List[MessageResponse]
    has_more: bool
    next_cursor: Optional[str] = None


class ThreadMessagesResponse(ThreadResponse):
    """Initial thread-open response: thread metadata + the latest 30 messages."""

    messages: List[MessageResponse]
    has_more: bool
    next_cursor: Optional[str] = None


class ThreadCreate(BaseModel):
    first_user_message: str


class ThreadUpdate(BaseModel):
    title: str


class MessageFeedback(BaseModel):
    feedback: str  # 'like' | 'dislike'
    comment: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: Optional[int] = None

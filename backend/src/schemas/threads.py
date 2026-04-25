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


class ThreadMessagesResponse(ThreadResponse):
    messages: List[MessageResponse]


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

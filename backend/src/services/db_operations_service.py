from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.core.settings import Settings
from src.models.database import Message, Thread, User
from src.services.logger import get_logger

logger = get_logger("db_operations")


class DatabaseOperationsService:
    """Thin wrapper around common DB operations for threads / messages / feedback."""

    def __init__(self, settings: Settings, db: Session):
        self.settings = settings
        self.db = db

    # --- User ---
    async def get_user_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    # --- Threads ---
    async def create_thread(self, user_id: int, title: str) -> Thread:
        thread = Thread(user_id=user_id, title=title)
        self.db.add(thread)
        self.db.commit()
        self.db.refresh(thread)
        return thread

    async def get_thread(self, thread_id: int) -> Optional[Thread]:
        return self.db.query(Thread).filter(Thread.id == thread_id).first()

    async def get_thread_by_uuid(self, thread_uuid: UUID) -> Optional[Thread]:
        return self.db.query(Thread).filter(Thread.thread_id == thread_uuid).first()

    async def get_user_threads(self, user_id: int) -> List[Thread]:
        return (
            self.db.query(Thread)
            .filter(Thread.user_id == user_id)
            .order_by(Thread.updated_at.desc())
            .all()
        )

    async def update_thread_title(self, thread_id: int, title: str) -> Optional[Thread]:
        thread = await self.get_thread(thread_id)
        if not thread:
            return None
        thread.title = title
        self.db.commit()
        self.db.refresh(thread)
        return thread

    async def update_thread_timestamp(self, thread_id: int) -> None:
        thread = await self.get_thread(thread_id)
        if thread:
            from datetime import datetime
            thread.updated_at = datetime.utcnow()
            self.db.commit()

    async def delete_thread(self, thread_id: int) -> bool:
        thread = await self.get_thread(thread_id)
        if not thread:
            return False
        self.db.delete(thread)
        self.db.commit()
        return True

    # --- Messages ---
    async def save_message(
        self,
        thread_uuid: UUID,
        role: str,
        content: str,
        type_: str = "message",
    ) -> Message:
        msg = Message(thread_id=thread_uuid, role=role, content=content, type=type_)
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    async def list_thread_messages_page(
        self,
        thread_uuid: UUID,
        *,
        before: Optional[tuple[datetime, UUID]],
        limit: int,
    ) -> tuple[List[Message], bool]:
        """Cursor-paginated, newest-first message page.

        `before` is a (created_at, message_id) tuple — emulated tuple
        comparison so two messages with equal `created_at` are still totally
        ordered by `message_id`. Fetches `limit + 1` rows so we can compute
        `has_more` cheaply without a COUNT.
        """
        q = self.db.query(Message).filter(Message.thread_id == thread_uuid)
        if before is not None:
            ts, mid = before
            q = q.filter(
                or_(
                    Message.created_at < ts,
                    and_(Message.created_at == ts, Message.message_id < mid),
                )
            )
        rows = (
            q.order_by(Message.created_at.desc(), Message.message_id.desc())
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        return rows[:limit], has_more

    async def get_message_by_uuid(self, message_uuid: UUID) -> Optional[Message]:
        return self.db.query(Message).filter(Message.message_id == message_uuid).first()

    async def update_message_feedback_by_uuid(
        self,
        message_uuid: UUID,
        feedback: Optional[str],
        comment: Optional[str],
    ) -> Optional[Message]:
        msg = await self.get_message_by_uuid(message_uuid)
        if not msg:
            return None
        msg.score = feedback
        msg.comment = comment
        self.db.commit()
        self.db.refresh(msg)
        return msg

"""Parent router.

Thin orchestrator that picks a subgraph and streams its response back to the
caller. Today there is only one subgraph (FridgeAssistant); add more and route
on `use_case` or a classifier when needed.

When the WebSocket handler hands us a device-JWT-resolved family_id, we
construct a per-call FridgeAssistant bound with that family's tool surface so
the LLM can call into the family-scoped service layer (§6.4).
"""
from typing import AsyncIterator, Awaitable, Callable
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import sessionmaker

from src.core.settings import Settings
from src.db.shared_engine import get_session_factory
from src.llm_graphs.subgraphs.fridge_assistant.fridge_assistant import FridgeAssistant
from src.services.chat_streaming import ChatStreamer
from src.services.db_operations_service import DatabaseOperationsService
from src.services.logger import get_logger

logger = get_logger("parent_router")


class ParentRouter:
    def __init__(self, settings: Settings, db_operations_service: DatabaseOperationsService):
        self.settings = settings
        self.db_ops = db_operations_service
        self.session_factory: sessionmaker = get_session_factory(settings)
        # Default tool-less assistant for chat without a device context.
        self.fridge_assistant = FridgeAssistant(settings)

    async def astream_response(
        self,
        message_content: str,
        thread_uuid: str,
        websocket_callback: Callable[[dict], Awaitable[None]],
        *,
        family_id: UUID | None = None,
        chat_streamer: ChatStreamer | None = None,
    ) -> AsyncIterator[dict]:
        """Persist the user message, stream the assistant reply, then persist it."""
        from uuid import UUID as _UUID

        thread_uuid_obj = _UUID(thread_uuid)
        await self.db_ops.save_message(
            thread_uuid_obj, role="user", content=message_content
        )

        history = await self._load_history(thread_uuid_obj)

        if family_id is not None:
            assistant = FridgeAssistant(
                self.settings,
                family_id=family_id,
                session_factory=self.session_factory,
            )
        else:
            assistant = self.fridge_assistant

        accumulated = []
        async for token in assistant.astream(
            message_content,
            history=history,
            chat_streamer=chat_streamer,
            thread_id=thread_uuid,
        ):
            accumulated.append(token)
            chunk = {"type": "message", "content": token}
            await websocket_callback(chunk)
            yield chunk

        full_reply = "".join(accumulated)
        if full_reply:
            await self.db_ops.save_message(
                thread_uuid_obj, role="assistant", content=full_reply
            )

    async def _load_history(self, thread_uuid):
        rows = await self.db_ops.get_formatted_thread_messages(thread_uuid)
        history = []
        for r in rows[:-1]:  # exclude the message we just saved
            if r["role"] == "user":
                history.append(HumanMessage(content=r["content"]))
            elif r["role"] == "assistant":
                history.append(AIMessage(content=r["content"]))
        return history

    async def cleanup(self) -> None:
        return

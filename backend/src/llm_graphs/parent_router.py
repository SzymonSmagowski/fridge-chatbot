"""Parent router.

Thin orchestrator that picks a per-channel graph and streams its response back
to the caller. Two channels exist: `chat` (this entrypoint, via the chat WS)
and `voice` (separate `voice_worker` process, not routed through here). Both
graphs live under `llm_graphs/graphs/` and share tools + services via
`llm_graphs/shared/`.

When the WebSocket handler hands us a device-JWT-resolved family_id, we
construct a per-call ChatGraph bound with that family's tool surface so the
LLM can call into the family-scoped service layer (§6.4).
"""
import asyncio
from typing import AsyncIterator, Awaitable, Callable
from uuid import UUID

from sqlalchemy.orm import sessionmaker

from src.core.settings import Settings
from src.db.shared_engine import get_session_factory
from src.llm_graphs.graphs.chat_graph import ChatGraph
from src.services.chat_streaming import ChatStreamer
from src.services.db_operations_service import DatabaseOperationsService
from src.services.logger import get_logger
from src.services.thread_summary_service import (
    load_compacted_history,
    maybe_summarize_thread,
)

logger = get_logger("parent_router")


class ParentRouter:
    def __init__(self, settings: Settings, db_operations_service: DatabaseOperationsService):
        self.settings = settings
        self.db_ops = db_operations_service
        self.session_factory: sessionmaker = get_session_factory(settings)
        # Default tool-less chat graph for sessions without a device context.
        self.default_chat_graph = ChatGraph(settings)

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
            voice_locale = self._load_voice_locale(family_id)
            assistant = ChatGraph(
                self.settings,
                family_id=family_id,
                session_factory=self.session_factory,
                voice_locale=voice_locale,
                thread_uuid=thread_uuid_obj,
            )
        else:
            assistant = self.default_chat_graph

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
            # Trigger periodic summary regeneration in the background — the
            # user already got their reply, no need to make them wait. Errors
            # here are non-fatal (the thread keeps working with the older
            # summary or with no summary at all).
            asyncio.create_task(self._maybe_summarize(thread_uuid_obj))

    async def _maybe_summarize(self, thread_uuid: UUID) -> None:
        """Background task: regenerate the thread's running summary if enough
        new messages have accumulated. Opens its own session to avoid sharing
        the request-scoped one already used by the streaming reply."""
        try:
            with self.session_factory() as db:
                await maybe_summarize_thread(db, thread_uuid, self.settings)
        except Exception as exc:  # noqa: BLE001
            # Summary regeneration is best-effort; never break chat over it.
            logger.warning(
                "thread summary regeneration failed for %s: %s", thread_uuid, exc
            )

    def _load_voice_locale(self, family_id: UUID) -> str:
        """Read the household's voice_locale preference. Cheap (single row
        lookup) but per-call so a settings change takes effect on the next
        message without process restart. Falls back to 'auto' if no row.
        """
        from src.models.family import FamilyPreferences

        try:
            with self.session_factory() as db:
                prefs = (
                    db.query(FamilyPreferences)
                    .filter(FamilyPreferences.family_id == family_id)
                    .first()
                )
                return prefs.voice_locale if prefs else "auto"
        except Exception as exc:  # noqa: BLE001
            # Best-effort — the chat path must keep working even if prefs
            # lookup fails (corrupted row, transient DB issue).
            logger.warning(
                "voice_locale lookup failed for family %s: %s; defaulting to auto",
                family_id,
                exc,
            )
            return "auto"

    async def _load_history(self, thread_uuid: UUID):
        """Compact history: prior summary (if any) + last WINDOW messages.

        Replaces the previous "replay every message" behavior, which was
        cheap up to ~30 messages but quadratic afterwards. See
        `services/thread_summary_service.py` for the rolling-summary scheme.
        """
        with self.session_factory() as db:
            return load_compacted_history(db, thread_uuid, exclude_last=True)

    async def cleanup(self) -> None:
        return

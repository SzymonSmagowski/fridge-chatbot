"""LangChain tool wrappers around the family-scoped service layer.

Tools are bound to the LLM with a `family_id` injected from graph state so the
model never has to (and never should) be trusted to scope its own queries.

The tools call the same services the REST API uses — one source of truth.

Mutating tools set `current_actor.set("chat-tool")` (§6.6) so the service-layer
publish stamps the broadcast frame with `actor: "chat-tool"`. ContextVars are
async-safe — each `asyncio.Task` inherits a copy of the context, so concurrent
tool invocations don't bleed actor values.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy.orm import sessionmaker

from src.core.context import current_actor
from src.core.settings import Settings
from src.models import MemberStatus
from src.schemas.notes import NoteCreateRequest
from src.services.chat_streaming import ChatStreamer
from src.services.event_service import EventListFilters, EventService
from src.services.event_target_resolver import EventTargetResolver
from src.services.label_service import LabelService
from src.services.member_service import MemberService
from src.services.note_service import NoteListFilters, NoteService
from src.services.redis_service import get_redis_client


def _run(coro):
    """Run an async coroutine from a (possibly sync) tool wrapper.

    LangChain calls @tool functions synchronously; our service mutation
    methods are async (they await Redis publishes). Use a fresh event loop
    when none is running, or schedule on the existing loop and wait.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # If we're inside a running loop (LangGraph driving us), schedule and
    # wait via run_coroutine_threadsafe-style fallback. The expected path
    # is the no-loop branch above; LangGraph tool nodes are sync.
    return asyncio.get_event_loop().run_until_complete(coro)


def build_tools(
    *, family_id: UUID, session_factory: sessionmaker, settings: Settings
) -> list[Any]:
    """Return a list of @tool functions, all closed over `family_id`."""
    redis = get_redis_client(settings)
    streamer = ChatStreamer(redis)

    @tool
    def list_notes(label_slug: str | None = None) -> list[dict]:
        """List notes for this family. Optional label_slug filter."""
        with session_factory() as db:
            labels = LabelService(db, family_id, streamer)
            notes = NoteService(db, family_id, labels, streamer)
            items, _total = notes.list(NoteListFilters(label=label_slug))
            return [notes.to_response(n).model_dump(mode="json") for n in items]

    @tool
    def add_note(
        content: str,
        label_slugs: list[str] | None = None,
        pinned: bool = False,
        assignee_member_id: str | None = None,
        icon: str | None = None,
    ) -> dict:
        """Create a note for this family."""
        current_actor.set("chat-tool")
        with session_factory() as db:
            labels = LabelService(db, family_id, streamer)
            notes = NoteService(db, family_id, labels, streamer)
            note = _run(
                notes.create(
                    NoteCreateRequest(
                        content=content,
                        label_slugs=label_slugs or [],
                        pinned=pinned,
                        assignee_member_id=UUID(assignee_member_id)
                        if assignee_member_id
                        else None,
                        icon=icon,
                    )
                )
            )
            return notes.to_response(note).model_dump(mode="json")

    @tool
    def add_to_shopping_list(line: str) -> dict:
        """Append a line to this family's shopping-list note."""
        current_actor.set("chat-tool")
        with session_factory() as db:
            labels = LabelService(db, family_id, streamer)
            notes = NoteService(db, family_id, labels, streamer)
            note = _run(
                notes.append_shopping_list(
                    line,
                    auto_create_default=settings.AUTO_CREATE_SHOPPING_LIST_DEFAULT,
                )
            )
            return notes.to_response(note).model_dump(mode="json")

    @tool
    def add_event(
        title: str,
        start_at: str,
        end_at: str,
        timezone: str | None = None,
        location: str | None = None,
        assignee_member_id: str | None = None,
        car_ids: list[str] | None = None,
        rrule: str | None = None,
    ) -> dict:
        """Create a calendar event. Times are ISO 8601."""
        from src.schemas.events import EventCreateRequest

        current_actor.set("chat-tool")
        with session_factory() as db:
            resolver = EventTargetResolver(db, family_id)
            events = EventService(db, family_id, resolver, streamer)
            ev, _ = _run(
                events.create(
                    EventCreateRequest(
                        title=title,
                        start_at=datetime.fromisoformat(
                            start_at.replace("Z", "+00:00")
                        ),
                        end_at=datetime.fromisoformat(end_at.replace("Z", "+00:00")),
                        timezone=timezone,
                        location=location,
                        assignee_member_id=UUID(assignee_member_id)
                        if assignee_member_id
                        else None,
                        car_ids=[UUID(c) for c in (car_ids or [])],
                        rrule=rrule,
                    )
                )
            )
            return events.to_response(ev).model_dump(mode="json")

    @tool
    def read_calendar_window(
        from_iso: str, to_iso: str, member_id: str | None = None
    ) -> dict:
        """List events in a time window. Returns merged fridge + external rows."""
        with session_factory() as db:
            resolver = EventTargetResolver(db, family_id)
            events = EventService(db, family_id, resolver, streamer)
            result = events.list(
                EventListFilters(
                    from_dt=datetime.fromisoformat(from_iso.replace("Z", "+00:00")),
                    to_dt=datetime.fromisoformat(to_iso.replace("Z", "+00:00")),
                    member_id=UUID(member_id) if member_id else None,
                    car_id=None,
                    source="all",
                )
            )
            return result.model_dump(mode="json")

    @tool
    def set_member_inactive(member_id: str) -> dict:
        """Set a family member to inactive status."""
        current_actor.set("chat-tool")
        with session_factory() as db:
            members = MemberService(db, family_id, streamer)
            member = _run(
                members.set_status(UUID(member_id), MemberStatus.inactive)
            )
            return members.to_response(member).model_dump(mode="json")

    return [
        list_notes,
        add_note,
        add_to_shopping_list,
        add_event,
        read_calendar_window,
        set_member_inactive,
    ]

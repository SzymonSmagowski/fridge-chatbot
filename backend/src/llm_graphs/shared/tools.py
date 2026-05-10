"""LangChain tool wrappers around the family-scoped service layer.

Tools are bound to the LLM with a `family_id` injected from graph state so the
model never has to (and never should) be trusted to scope its own queries.

The tools call the same services the REST API uses — one source of truth.

Mutating tools set `current_actor.set("chat-tool")` (§6.6) so the service-layer
publish stamps the broadcast frame with `actor: "chat-tool"`. ContextVars are
async-safe — each `asyncio.Task` inherits a copy of the context, so concurrent
tool invocations don't bleed actor values.

Async vs sync split: read-only tools stay sync (faster — no event-loop juggling
for a list query). Mutating tools are async because the service-layer
publish (`ChatStreamer.publish_family_event`) is async and must run on the
same event loop as the process-wide Redis client. Earlier this layer wrapped
async services with a sync `_run` bridge; that bridge crossed event loops and
caused "Event loop is closed" failures whenever a chat-tool write tried to
publish — see docs/features/chat-graph-bugfix-async-bridge.md for the full
postmortem.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy.orm import sessionmaker

from src.core.cache import family_key, invalidate
from src.core.context import current_actor
from src.core.settings import Settings
from src.models import Car, Member, MemberStatus
from src.schemas.cars import CarCreateRequest
from src.schemas.notes import NoteCreateRequest
from src.services.car_service import CarService
from src.services.chat_streaming import ChatStreamer
from src.services.event_service import EventListFilters, EventService
from src.services.event_target_resolver import EventTargetResolver
from src.services.label_service import LabelService
from src.services.member_service import MemberService
from src.services.note_service import NoteListFilters, NoteService
from src.services.redis_service import get_redis_client

# Tool-layer caps so the LLM never receives an arbitrarily large payload that
# could blow its context window. REST clients still get the full list via the
# normal `?limit=` query — these caps live on the tool wrapper only.
LIST_NOTES_TOOL_CAP = 50
CALENDAR_WINDOW_TOOL_CAP = 50


def _member_name(db, member_id) -> str | None:
    """Resolve a member UUID (or stringified UUID) to the member's display
    name. Returns None on missing or invalid id. Used to swap technical
    `assignee_member_id` fields for human names in tool returns so the
    voice agent never has to read UUIDs aloud."""
    if not member_id:
        return None
    try:
        uid = member_id if isinstance(member_id, UUID) else UUID(str(member_id))
    except (TypeError, ValueError):
        return None
    m = db.query(Member).filter(Member.id == uid).first()
    return m.name if m else None


def _car_names(db, car_ids) -> list[str]:
    """Resolve car UUIDs to display names. Same purpose as `_member_name`."""
    if not car_ids:
        return []
    uids: list[UUID] = []
    for cid in car_ids:
        try:
            uids.append(cid if isinstance(cid, UUID) else UUID(str(cid)))
        except (TypeError, ValueError):
            continue
    if not uids:
        return []
    rows = db.query(Car).filter(Car.id.in_(uids)).all()
    return [c.name for c in rows]


def build_tools(
    *,
    family_id: UUID,
    session_factory: sessionmaker,
    settings: Settings,
    end_session_signal: Any | None = None,
) -> list[Any]:
    """Return a list of @tool functions, all closed over `family_id`.

    `end_session_signal` is an optional `asyncio.Event` (or anything with a
    `.set()` method). When provided, the `end_session` tool is registered;
    the LLM uses it to signal "the user said they're done" and the voice
    worker's watcher coroutine reacts by closing the LiveKit session after
    the goodbye TTS finishes. Pass `None` for chat — chat sessions don't
    have a session to close.
    """
    redis = get_redis_client(settings)
    streamer = ChatStreamer(redis)

    async def _invalidate_list_cache(*entity_namespaces: str) -> None:
        """Drop the family's cached list responses for the given REST cache
        namespaces (`"notes"`, `"events"`, `"cars"`, `"members"`).

        Architectural note: this duplicates what the REST routes do in their
        per-route `_invalidate` helpers. The right long-term home for this
        is inside the service layer (so any caller — REST, tool, worker —
        invalidates correctly). For now we mirror the route patterns
        directly so the chat tool's mutations stop leaving stale cached
        list responses behind. Without this, a `GET /notes` after a chat-
        tool `add_note` returns the pre-tool list until the cache TTL
        expires — which is what was making freshly-created notes invisible
        in the Notes tab until app restart.
        """
        keys = [family_key(family_id, f"{ns}:*") for ns in entity_namespaces]
        await invalidate(redis, *keys)

    @tool
    def list_notes(label_slug: str | None = None) -> dict:
        """List notes for this family. Optional label_slug filter.

        Capped at the 50 most recent notes to protect the LLM's context.
        Returns terse summaries — no UUIDs, timestamps, or other technical
        fields the assistant might accidentally read aloud. There is no
        edit-by-id tool, so the LLM doesn't need note IDs anyway.
        """
        with session_factory() as db:
            labels = LabelService(db, family_id, streamer)
            notes = NoteService(db, family_id, labels, streamer)
            items, total = notes.list(
                NoteListFilters(label=label_slug, limit=LIST_NOTES_TOOL_CAP)
            )
            summaries = [
                {
                    "content": n.content,
                    "labels": [link.label.slug for link in (n.label_links or [])],
                    "pinned": bool(n.pinned),
                    "assigned_to": _member_name(db, n.assignee_member_id),
                }
                for n in items
            ]
            return {
                "notes": summaries,
                "total_count": total,
                "truncated": total > len(items),
            }

    @tool
    async def add_note(
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
            note = await notes.create(
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
            await _invalidate_list_cache("notes")
            # Terse confirmation only — no UUIDs, timestamps, FKs. The
            # assistant has nothing technical to read aloud.
            return {
                "ok": True,
                "what": "note",
                "content": note.content,
                "labels": label_slugs or [],
                "pinned": bool(note.pinned),
                "assigned_to": _member_name(db, note.assignee_member_id),
            }

    @tool
    async def add_to_shopping_list(line: str) -> dict:
        """Append a line to this family's shopping-list note."""
        current_actor.set("chat-tool")
        with session_factory() as db:
            labels = LabelService(db, family_id, streamer)
            notes = NoteService(db, family_id, labels, streamer)
            await notes.append_shopping_list(
                line,
                auto_create_default=settings.AUTO_CREATE_SHOPPING_LIST_DEFAULT,
            )
            await _invalidate_list_cache("notes")
            return {
                "ok": True,
                "what": "shopping_list_item",
                "added": line,
            }

    @tool
    async def add_event(
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
            ev, _ = await events.create(
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
            await _invalidate_list_cache("events")
            # Keep ISO timestamps so the assistant can convert to a spoken
            # form ("Saturday at three") — that conversion belongs to the
            # LLM, not the tool. Drop everything else technical (UUIDs,
            # created_at, fan-out target rows).
            return {
                "ok": True,
                "what": "event",
                "title": ev.title,
                "starts_at": ev.start_at.isoformat() if ev.start_at else None,
                "ends_at": ev.end_at.isoformat() if ev.end_at else None,
                "timezone": ev.timezone,
                "location": ev.location,
                "assigned_to": _member_name(db, ev.assignee_member_id),
                "cars": _car_names(db, [c.car_id for c in (ev.car_links or [])]),
                "recurring": bool(rrule),
            }

    @tool
    def read_calendar_window(
        from_iso: str, to_iso: str, member_id: str | None = None
    ) -> dict:
        """List events in a time window. Returns merged fridge + external rows.

        Capped at 50 events combined (fridge + external) to protect the LLM's
        context. Returns terse summaries — title, ISO times, location, who
        it's assigned to. No event UUIDs, no per-target sync state, no
        timestamps. The LLM converts ISO times to spoken form.
        """
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
            payload = result.model_dump(mode="json")
            total = payload["total"]
            fridge = payload["fridge"]
            external = payload["external"]
            remaining = CALENDAR_WINDOW_TOOL_CAP
            capped_fridge = fridge[:remaining]
            remaining -= len(capped_fridge)
            capped_external = external[:max(remaining, 0)]

            def _summarize(row: dict) -> dict:
                return {
                    "title": row.get("title"),
                    "starts_at": row.get("start_at"),
                    "ends_at": row.get("end_at"),
                    "location": row.get("location"),
                    "assigned_to": _member_name(db, row.get("assignee_member_id")),
                }

            return {
                "fridge": [_summarize(r) for r in capped_fridge],
                "external": [_summarize(r) for r in capped_external],
                "total_count": total,
                "truncated": (len(capped_fridge) + len(capped_external)) < total,
            }

    @tool
    async def set_member_inactive(member_id: str) -> dict:
        """Set a family member to inactive status."""
        current_actor.set("chat-tool")
        with session_factory() as db:
            members = MemberService(db, family_id, streamer)
            member = await members.set_status(UUID(member_id), MemberStatus.inactive)
            await _invalidate_list_cache("members")
            return {"ok": True, "what": "member", "name": member.name, "active": False}

    @tool
    async def set_member_active(member_id: str) -> dict:
        """Set a family member to active status."""
        current_actor.set("chat-tool")
        with session_factory() as db:
            members = MemberService(db, family_id, streamer)
            member = await members.set_status(UUID(member_id), MemberStatus.active)
            await _invalidate_list_cache("members")
            return {"ok": True, "what": "member", "name": member.name, "active": True}

    @tool
    def list_members() -> list[dict]:
        """List the active members of this family with their names + colors.

        Each row keeps `id` because `add_note` / `add_event` /
        `set_member_*` take a member UUID. The LLM uses these IDs for
        chained tool calls only — the prompt forbids reading them aloud.
        Other technical fields (created_at, family_id, status enum,
        nickname) are stripped.
        """
        with session_factory() as db:
            members = MemberService(db, family_id, streamer)
            items = members.list(status_filter="active")
            return [
                {"id": str(m.id), "name": m.name, "color": m.color}
                for m in items
            ]

    @tool
    def list_cars() -> list[dict]:
        """List the active cars in this family.

        Keeps `id` because `add_event` takes a list of car UUIDs. Strips
        every other technical field (status, family_id, timestamps).
        """
        with session_factory() as db:
            cars = CarService(db, family_id, streamer)
            items = cars.list(status_filter="active")
            return [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "color": c.color_label,
                }
                for c in items
            ]

    @tool
    async def add_car(
        name: str,
        year: int | None = None,
        color_label: str | None = None,
        notes: str | None = None,
    ) -> dict:
        """Add a car to this family. `color_label` is the spoken color (e.g. 'Red', 'White')."""
        current_actor.set("chat-tool")
        with session_factory() as db:
            cars = CarService(db, family_id, streamer)
            car = await cars.create(
                CarCreateRequest(
                    name=name,
                    year=year,
                    color_label=color_label,
                    notes=notes,
                )
            )
            await _invalidate_list_cache("cars")
            return {
                "ok": True,
                "what": "car",
                "name": car.name,
                "year": car.year,
                "color": car.color_label,
            }

    tools_list: list[Any] = [
        list_notes,
        add_note,
        add_to_shopping_list,
        add_event,
        read_calendar_window,
        set_member_inactive,
        set_member_active,
        list_members,
        list_cars,
        add_car,
    ]

    # Voice-only: gives the LLM an explicit way to signal "the user said
    # they're done". The chat channel has no equivalent — the user just
    # closes the tab. We register the tool only when the worker passes
    # in an Event to receive the signal, so chat-graph doesn't see it.
    if end_session_signal is not None:

        @tool
        def end_session() -> dict:
            """Signal that the user is done with the voice session.

            Use this ONLY when the user clearly indicates they're finished,
            in any language. Examples that should trigger this: "to tyle",
            "dziękuję, koniec", "okej, wystarczy", "that's it", "thanks,
            we're done", "stop". Don't call it just because there's a
            pause in conversation — wait for an explicit goodbye.

            After calling this tool, your final spoken reply should be a
            brief polite goodbye ("Do widzenia." / "Bye, talk soon.").
            The session will close shortly after that reply finishes
            playing — no manual disconnection needed by the user.
            """
            end_session_signal.set()
            return {"ok": True, "what": "end_session"}

        tools_list.append(end_session)

    return tools_list

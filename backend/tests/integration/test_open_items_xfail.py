"""§13 Open items #8 and #9 — formerly xfail, now passing after the worker +
chat-tool publish refactor (architecture §6.6 + ChatStreamer.publish_family_event).

#8 — calendar_write_worker.fan_out_event publishes a unified §5.11 frame via
    ChatStreamer.publish_family_event(actor="sync-worker") on completion.
#9 — chat tools (NoteService, EventService, MemberService) publish through the
    same ChatStreamer; tool wrappers stamp `current_actor.set("chat-tool")`
    before invoking the service so the broadcast carries the right actor.

Filename retained for git-blame continuity; markers removed.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.orm import sessionmaker


@pytest.mark.asyncio
async def test_calendar_write_worker_publishes_unified_event_synced_frame(
    redis_client: Redis,
    family,
    family_event_collector,
    test_settings,
    session_factory: sessionmaker,
    db,
) -> None:
    """§13 Open #8 (resolved): when fan_out_event finishes, it publishes a
    `family:{id}:events` frame with the §5.11 envelope (entity, actor, ts).

    We invoke the worker directly with empty target_ids — no Google calls
    happen, but the post-fan-out publish still fires and we assert its shape.
    """
    from src.workers.calendar_write_worker import fan_out_event
    from src.models import Event

    family_id, _, _ = family

    # Need a real Event row so _family_id_for_event resolves a non-empty string.
    ev = Event(
        family_id=family_id,
        title="Probe",
        start_at=datetime(2026, 5, 1, 10, tzinfo=timezone.utc),
        end_at=datetime(2026, 5, 1, 11, tzinfo=timezone.utc),
        timezone="Europe/Warsaw",
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    async with family_event_collector(family_id) as collector:
        await fan_out_event(
            event_id=ev.id,
            target_ids=[],  # no per-target work, but the post-publish still fires
            settings=test_settings,
            session_factory=session_factory,
            redis=redis_client,
        )
        frames = await collector.wait_for(1)

    assert len(frames) >= 1, "calendar_write_worker did not publish family event"
    frame = frames[0]
    assert frame["type"] == "event.synced"
    assert frame["entity"] == "events"
    assert frame["actor"] == "sync-worker"
    assert frame["id"] == str(ev.id)
    assert "ts" in frame


@pytest.mark.asyncio
async def test_chat_tool_add_note_publishes_family_event_with_actor_chat_tool(
    client: TestClient,
    auth_headers,
    family,
    family_event_collector,
    test_settings,
    session_factory: sessionmaker,
    redis_client: Redis,
) -> None:
    """§13 Open #9 (resolved): when the FridgeAssistant `add_note` tool
    creates a note, the broadcast frame on `family:{id}:events` carries
    `actor: 'chat-tool'`.

    We exercise the tool's exact path: stamp `current_actor.set("chat-tool")`
    then invoke `NoteService.create` with the production constructor signature
    (now: db, family_id, label_service, streamer).
    """
    from src.core.context import current_actor
    from src.schemas.notes import NoteCreateRequest
    from src.services.chat_streaming import ChatStreamer
    from src.services.label_service import LabelService
    from src.services.note_service import NoteService

    family_id, _, _ = family

    streamer = ChatStreamer(redis_client)

    async with family_event_collector(family_id) as collector:
        with session_factory() as db_session:
            labels = LabelService(db_session, family_id, streamer)
            service = NoteService(db_session, family_id, labels, streamer)
            current_actor.set("chat-tool")
            await service.create(NoteCreateRequest(content="from chat"))
        frames = await collector.wait_for(1)

    assert len(frames) >= 1, "chat-tool write did NOT publish family event"
    frame = frames[0]
    assert frame["type"] == "note.created"
    assert frame["entity"] == "notes"
    assert frame["actor"] == "chat-tool"
    assert "ts" in frame
    assert "id" in frame


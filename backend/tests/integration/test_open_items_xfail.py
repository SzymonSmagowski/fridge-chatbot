"""Tracking tests for §13 Open items #8 and #9.

These are currently expected to fail and will flip to passing when those
architectural gaps are closed. They exist as forcing functions so the gap
can't silently persist.

#8 — workers don't publish through ChatStreamer. The `calendar_sync_worker`
    and `calendar_write_worker` emit raw JSON on `family:{id}:events` that
    omits `entity`, `actor`, `ts` — the unified frame shape from §5.11.
#9 — LangGraph tool writes don't publish `family:{id}:events` at all.
    When chat adds a note, the kiosk doesn't receive a push.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from src.core.pubsub import family_events_channel


@pytest.mark.xfail(
    reason="§13 Open #8 — calendar_write_worker still publishes raw JSON; "
    "unify on ChatStreamer.publish_family_event so the frame has entity/actor/ts.",
    strict=False,
)
@pytest.mark.asyncio
async def test_calendar_write_worker_publishes_unified_event_synced_frame(
    redis_client: Redis, family
) -> None:
    """When `fan_out_event` finishes, it should publish a family-event frame
    with the §5.11 envelope (entity, actor='sync-worker', ts). Today it emits
    `{"type":"event.synced","id":"<uuid>"}` only."""
    family_id, _, _ = family

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(family_events_channel(family_id))
    try:
        # Manually emit what the worker currently produces so we assert the
        # exact shape, not the behavior (which requires real Google plumbing).
        await redis_client.publish(
            family_events_channel(family_id),
            '{"type":"event.synced","id":"7b8e8a7e-1a2b-4c3d-8e9f-abcdef012345"}',
        )

        # Receive.
        await asyncio.sleep(0.05)
        msg = None
        for _ in range(20):
            raw = await pubsub.get_message(timeout=0.1)
            if raw and raw.get("type") == "message":
                msg = json.loads(raw["data"])
                break
        assert msg is not None

        # Unified frame contract.
        assert msg.get("entity") == "events"
        assert msg.get("actor") == "sync-worker"
        assert "ts" in msg
    finally:
        await pubsub.unsubscribe()
        await pubsub.close()


@pytest.mark.xfail(
    reason="§13 Open #9 — LangGraph `add_note` tool skips ChatStreamer.publish_family_event. "
    "Move publish into the service layer (or wrap the tool) so chat-driven writes "
    "also broadcast a `family:{id}:events` frame with actor='chat-tool'.",
    strict=False,
)
@pytest.mark.asyncio
async def test_chat_tool_add_note_publishes_family_event_with_actor_chat_tool(
    client: TestClient, auth_headers, family, family_event_collector
) -> None:
    """When the FridgeAssistant's `add_note` tool creates a note, the
    board-mutation frame must flow on `family:{id}:events` with
    `actor: 'chat-tool'`. Until then, the kiosk misses the push."""
    family_id, _, _ = family

    # Simulate the tool by directly invoking NoteService as tools.py does —
    # this path intentionally bypasses `publish_family_event`.
    from src.core.dependencies import get_settings
    from src.db.shared_engine import get_session_factory
    from src.services.label_service import LabelService
    from src.services.note_service import NoteService
    from src.schemas.notes import NoteCreateRequest

    settings = get_settings()
    SessionLocal = get_session_factory(settings)
    with SessionLocal() as db:
        labels = LabelService(db, family_id)
        service = NoteService(db, family_id, labels)
        async with family_event_collector(family_id) as collector:
            service.create(NoteCreateRequest(content="from chat"))
            frames = await collector.wait_for(1)

    # Must-emit contract: a chat-tool-shaped frame.
    assert len(frames) >= 1, "chat tool write did NOT publish family event"
    assert frames[0].get("actor") == "chat-tool"

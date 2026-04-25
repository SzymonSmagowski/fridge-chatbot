"""Consistent payload shape for `family:{family_id}:events` broadcasts.

One helper used by every write endpoint so subscribers on the other side of the
WebSocket (the kiosk, future companion devices) see a uniform envelope.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

Entity = Literal[
    "notes",
    "members",
    "cars",
    "events",
    "labels",
    "family",
    "family_preferences",
]

Actor = Literal["rest", "chat-tool", "sync-worker"]


def family_event_payload(
    *,
    type: str,
    entity: Entity,
    id: Any,
    actor: Actor = "rest",
) -> dict:
    return {
        "type": type,
        "entity": entity,
        "id": str(id),
        "actor": actor,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

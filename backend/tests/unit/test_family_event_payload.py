"""Unit tests for src/core/family_events.py — broadcast payload contract."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from src.core.family_events import family_event_payload


def test_family_event_payload_has_all_required_fields() -> None:
    note_id = uuid4()
    payload = family_event_payload(
        type="note.created", entity="notes", id=note_id
    )
    assert payload["type"] == "note.created"
    assert payload["entity"] == "notes"
    assert payload["id"] == str(note_id)
    assert payload["actor"] == "rest"
    # ts is ISO8601 — parse it.
    datetime.fromisoformat(payload["ts"])


def test_family_event_payload_actor_default_rest() -> None:
    payload = family_event_payload(
        type="note.created", entity="notes", id="x"
    )
    assert payload["actor"] == "rest"


def test_family_event_payload_actor_can_be_overridden() -> None:
    payload = family_event_payload(
        type="event.synced", entity="events", id="x", actor="sync-worker"
    )
    assert payload["actor"] == "sync-worker"


def test_family_event_payload_id_coerced_to_string() -> None:
    payload = family_event_payload(
        type="note.created", entity="notes", id=uuid4()
    )
    assert isinstance(payload["id"], str)

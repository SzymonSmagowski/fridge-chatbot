"""Integration tests for WS /ws/family/{family_id}/events (§5.11).

Close codes per Architect:
- 4003 missing_token, invalid_token, family_mismatch
- 1011 redis_unavailable

Heartbeat: 25 s — verified by patching the constant down to <1 s for the
heartbeat test only (keeps the suite fast).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


CLOSE_POLICY_VIOLATION = 4003


def _expect_close_with_code(ws, expected_code: int) -> None:
    """Server sent its close frame after accept(). Read the next message and
    assert WebSocketDisconnect with the right code."""
    with pytest.raises(WebSocketDisconnect) as exc:
        ws.receive_text()
    assert exc.value.code == expected_code


def test_ws_family_events_without_token_closes_4003(client: TestClient, family) -> None:
    family_id, _, _ = family
    with client.websocket_connect(f"/ws/family/{family_id}/events") as ws:
        _expect_close_with_code(ws, CLOSE_POLICY_VIOLATION)


def test_ws_family_events_with_garbage_token_closes_4003(
    client: TestClient, family
) -> None:
    family_id, _, _ = family
    with client.websocket_connect(
        f"/ws/family/{family_id}/events?token=garbage"
    ) as ws:
        _expect_close_with_code(ws, CLOSE_POLICY_VIOLATION)


def test_ws_family_events_with_user_jwt_closes_4003(
    client: TestClient, family, make_jwt
) -> None:
    """typ != device → invalid_token close."""
    family_id, _, _ = family
    user_jwt = make_jwt(typ="access", family_id=family_id)
    with client.websocket_connect(
        f"/ws/family/{family_id}/events?token={user_jwt}"
    ) as ws:
        _expect_close_with_code(ws, CLOSE_POLICY_VIOLATION)


def test_ws_family_events_with_mismatched_family_closes_4003(
    client: TestClient, family, make_jwt
) -> None:
    """JWT family_id != path family_id → family_mismatch close."""
    family_id, _, _ = family
    other_token = make_jwt(typ="device", family_id=uuid4())
    with client.websocket_connect(
        f"/ws/family/{family_id}/events?token={other_token}"
    ) as ws:
        _expect_close_with_code(ws, CLOSE_POLICY_VIOLATION)


def test_ws_family_events_forwards_published_frame_to_client(
    client: TestClient, auth_headers, family
) -> None:
    """Happy path: connect, trigger a write through HTTP, receive the frame."""
    family_id, _, token = family
    with client.websocket_connect(
        f"/ws/family/{family_id}/events?token={token}"
    ) as ws:
        # Drive a REST write — this publishes to family:{id}:events.
        client.post(
            "/api/notes", headers=auth_headers, json={"content": "ws test"}
        )
        frame = ws.receive_json(mode="text")
        # In rare cases a heartbeat could land first; loop past it.
        while frame.get("type") == "ping":
            frame = ws.receive_json(mode="text")
        assert frame["type"] == "note.created"
        assert frame["entity"] == "notes"
        assert frame["actor"] == "rest"
        assert "id" in frame and "ts" in frame


def test_ws_family_events_heartbeat_sends_ping_frame(
    client: TestClient, family, monkeypatch
) -> None:
    """Heartbeat should send {'type':'ping'} on schedule. We shorten the
    interval so the test stays fast.
    """
    from src.routes import family_events_ws as ws_module
    monkeypatch.setattr(ws_module, "HEARTBEAT_INTERVAL_SECONDS", 0.2)

    family_id, _, token = family
    with client.websocket_connect(
        f"/ws/family/{family_id}/events?token={token}"
    ) as ws:
        # Should get at least one ping within ~1 s.
        frame = ws.receive_json(mode="text")
        assert frame == {"type": "ping"}

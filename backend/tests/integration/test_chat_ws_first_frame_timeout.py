"""Integration tests for the chat WS first-frame timeout (H1).

Slowloris-style attackers can `accept()` a WS and never send a frame, holding
a connection forever. The route now wraps the first `receive_json()` in
`asyncio.wait_for(timeout=5.0)` and closes with code 4001 on expiry.

These tests validate:
- A connection that never sends a first frame is closed with code 4001
  within ~5 s. We patch the timeout down so the suite stays fast.
- A connection that sends a valid first frame within the deadline is NOT
  prematurely closed by the timeout (proves the wait_for is wired correctly).

We do NOT exercise the LLM path here — that's covered by the behavioral
suite. Instead we send a token that fails auth, which makes the handler
respond with `{"error": "Invalid token"}` and close the socket cleanly.
That confirms the first-frame timeout did NOT fire prematurely.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


WS_FIRST_FRAME_CLOSE_CODE = 4001


@pytest.fixture
def stubbed_parent_router(app):
    """Inject a do-nothing ParentRouter so the WS dep resolves.

    The first-frame-timeout path doesn't call astream_response — the
    timeout fires before any business logic. We just need the dep to not
    raise `ParentRouter not initialized`.
    """
    from src.core import dependencies as deps

    class _NoopRouter:
        async def astream_response(self, *args, **kwargs):
            yield {}

        async def cleanup(self):
            pass

    async def _override():
        return _NoopRouter()

    app.dependency_overrides[deps.get_parent_router] = _override
    yield


def _expect_close_with_code(ws, expected_code: int) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        # Reading any frame after a server-initiated close raises the
        # disconnect with the close code attached.
        ws.receive_text()
    assert exc.value.code == expected_code, (
        f"Expected close code {expected_code}, got {exc.value.code}"
    )


def test_chat_ws_closes_with_4001_when_first_frame_not_received_in_time(
    client: TestClient, db, family, monkeypatch, stubbed_parent_router
) -> None:
    """Patch the timeout to a tiny value so the test runs fast. The
    behavior under test is: open WS, send NO frames, server closes after
    the deadline with code 4001.
    """
    from src.routes import threads as threads_module

    # 0.2 s is enough to demonstrate the close path while keeping the test
    # well under 1 s. Production timeout is 5.0 s; that constant exists in
    # the route module.
    monkeypatch.setattr(
        threads_module, "WS_FIRST_FRAME_TIMEOUT_SECONDS", 0.2
    )

    # Seed a thread so the URL has a real id; the timeout fires before the
    # thread is even consulted, but using a real id matches production.
    from src.models.database import Thread, User
    from src.models import Device

    family_id, device_id, _token = family
    device = db.query(Device).filter(Device.id == device_id).first()
    user = db.query(User).filter(User.id == device.shadow_user_id).first()
    thread = Thread(user_id=user.id, title="ws-timeout-test")
    db.add(thread)
    db.commit()
    db.refresh(thread)

    with client.websocket_connect(f"/ws/threads/{thread.id}") as ws:
        # Don't send anything — the server should close after ~0.2 s.
        _expect_close_with_code(ws, WS_FIRST_FRAME_CLOSE_CODE)


def test_chat_ws_does_not_close_with_4001_when_first_frame_arrives_in_time(
    client: TestClient, db, family, monkeypatch, stubbed_parent_router
) -> None:
    """Negative: if the client DOES send a first frame within the deadline,
    the timeout must NOT fire. We send a frame with an obviously-bad token
    so the handler replies with `{"error": "Invalid token"}` and closes
    normally — proving the timeout path was bypassed.
    """
    from src.routes import threads as threads_module

    monkeypatch.setattr(
        threads_module, "WS_FIRST_FRAME_TIMEOUT_SECONDS", 0.2
    )

    # Need a real thread.
    from src.models.database import Thread, User
    from src.models import Device

    family_id, device_id, _token = family
    device = db.query(Device).filter(Device.id == device_id).first()
    user = db.query(User).filter(User.id == device.shadow_user_id).first()
    thread = Thread(user_id=user.id, title="ws-fast-frame")
    db.add(thread)
    db.commit()
    db.refresh(thread)

    with client.websocket_connect(f"/ws/threads/{thread.id}") as ws:
        ws.send_json({"content": "hello", "token": "obviously-not-a-jwt"})
        # The handler responds with error frame, then closes. Read frames
        # until we see the auth error, then expect a normal close.
        frame = ws.receive_json()
        assert frame == {"error": "Invalid token"}, (
            "Expected auth error after a fast first frame, got: " f"{frame!r}"
        )
        # The route then `return`s, hitting the `finally: websocket.close()`
        # path which closes with default code 1000.
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        # 4001 would mean the timeout fired regardless — that's the bug.
        assert exc.value.code != WS_FIRST_FRAME_CLOSE_CODE, (
            "First frame WAS sent, but server closed with the timeout code "
            "4001 anyway — the wait_for branch must not have been bypassed."
        )

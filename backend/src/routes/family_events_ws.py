"""Long-lived `family:{family_id}:events` WebSocket subscriber (§7.7).

Clients open one WS per device; the server subscribes to the Redis pub/sub
channel for the device's family and forwards every message as a JSON text
frame. Reduces the kiosk's board polling to push-on-change.

Auth: device JWT via `?token=` query param (matches the subscriber pattern
used by long-lived event streams; the chat WS uses a first-message handshake
because it carries user content — irrelevant here).
"""
from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError

from src.core.dependencies import get_auth_service, get_chat_streamer
from src.services.auth_service import AuthService
from src.services.chat_streaming import ChatStreamer
from src.services.logger import get_logger

router = APIRouter(tags=["family-events"])
logger = get_logger("family_events_ws")

# Close codes (RFC 6455 + application range).
CLOSE_POLICY_VIOLATION = 4003  # custom: family_mismatch
CLOSE_INTERNAL_ERROR = 1011

# Heartbeat cadence. Chat WS has no ping loop, but this socket is long-lived
# and may sit idle through a proxy's idle timeout — send a ping every 25s.
HEARTBEAT_INTERVAL_SECONDS = 25


@router.websocket("/ws/family/{family_id}/events")
async def family_events_ws(
    websocket: WebSocket,
    family_id: UUID,
    auth_service: AuthService = Depends(get_auth_service),
    streamer: ChatStreamer = Depends(get_chat_streamer),
) -> None:
    # Accept the handshake first so we can send a real close frame with our
    # custom application close code (4003). Rejecting pre-accept produces an
    # HTTP 403 handshake failure instead, which obscures the reason from the
    # client.
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=CLOSE_POLICY_VIOLATION, reason="missing_token")
        return

    try:
        claims = auth_service.decode_token(token)
    except Exception:
        await websocket.close(code=CLOSE_POLICY_VIOLATION, reason="invalid_token")
        return

    if claims.get("typ") != "device":
        await websocket.close(code=CLOSE_POLICY_VIOLATION, reason="invalid_token")
        return

    claim_family = claims.get("family_id")
    if not claim_family or str(claim_family) != str(family_id):
        await websocket.close(
            code=CLOSE_POLICY_VIOLATION, reason="family_mismatch"
        )
        return

    heartbeat_task: asyncio.Task | None = None
    try:
        async with streamer.subscribe_family(family_id) as channel:
            heartbeat_task = asyncio.create_task(_heartbeat(websocket))
            forward_task = asyncio.create_task(
                _forward_messages(websocket, channel)
            )
            receive_task = asyncio.create_task(_drain_client(websocket))

            done, pending = await asyncio.wait(
                {forward_task, receive_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, (WebSocketDisconnect, RedisError)):
                    raise exc
                if isinstance(exc, RedisError):
                    logger.warning(
                        "redis error on family_events ws for %s: %s",
                        family_id,
                        exc,
                    )
                    await _safe_close(
                        websocket,
                        code=CLOSE_INTERNAL_ERROR,
                        reason="redis_unavailable",
                    )
                    return
    except RedisError as exc:
        logger.warning(
            "redis subscribe failed for family %s: %s", family_id, exc
        )
        await _safe_close(
            websocket, code=CLOSE_INTERNAL_ERROR, reason="redis_unavailable"
        )
        return
    except WebSocketDisconnect:
        pass
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await _safe_close(websocket)
        logger.info("family_events ws closed for family %s", family_id)


async def _forward_messages(websocket: WebSocket, channel) -> None:
    async for payload in channel.listen():
        await websocket.send_json(payload)


async def _drain_client(websocket: WebSocket) -> None:
    """Consume client frames so we notice disconnects promptly.

    The subscriber protocol is one-way (server → client). Anything the client
    sends is ignored, but we must keep draining so `WebSocketDisconnect` is
    raised on close.

    H1 note — the chat WS adds a 5s timeout on the first receive because it
    requires the client to send a content+token frame to begin. The family
    events WS doesn't: auth is already done at handshake (?token=), and
    healthy clients are passive subscribers. The 25s heartbeat (see
    HEARTBEAT_INTERVAL_SECONDS) is the liveness mechanism here, not a
    receive timeout — adding one would close every well-behaved subscriber.
    """
    while True:
        await websocket.receive_text()


async def _heartbeat(websocket: WebSocket) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        try:
            await websocket.send_json({"type": "ping"})
        except Exception:  # noqa: BLE001
            return


async def _safe_close(
    websocket: WebSocket, *, code: int = 1000, reason: str = ""
) -> None:
    """Best-effort close. Swallows every exception by design.

    Cleanup paths reach this function from `finally` blocks where the socket
    might already be torn down, in which case calling close() raises:
      - `RuntimeError` if starlette already saw a disconnect
      - `AttributeError: 'WebSocketProtocol' object has no attribute
        'transfer_data_task'` when uvicorn's legacy `websockets_impl` adapter
        races a close against a connection that was never fully wired
        (mismatch between uvicorn's adapter and `websockets >= 13` internals).
    Either way, the socket is gone — re-raising would just spam logs.
    """
    from starlette.websockets import WebSocketState

    if websocket.application_state == WebSocketState.DISCONNECTED:
        return
    try:
        await websocket.close(code=code, reason=reason)
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        logger.debug("ignored error while closing family-events ws: %s", exc)

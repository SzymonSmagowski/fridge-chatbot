import asyncio
import base64
import binascii
import json
from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.core.dependencies import (
    get_auth_service,
    get_db,
    get_db_operations_service,
    get_llm_utils,
    get_parent_router,
)
from src.services.chat_streaming import ChatStreamer
from src.services.redis_service import get_redis_client
from src.core.dependencies import get_settings
from src.schemas.threads import (
    MessageFeedback,
    MessagesPageResponse,
    ThreadCreate,
    ThreadMessagesResponse,
    ThreadResponse,
    ThreadUpdate,
)
from src.services.logger import get_logger

router = APIRouter(tags=["threads"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/pairing/start")
logger = get_logger("threads_route")

# How long the chat WS will wait for the auth+content first frame before
# closing with code 4001. H1 — without this, an attacker can `accept()` and
# hold the socket open forever.
WS_FIRST_FRAME_TIMEOUT_SECONDS = 5.0

# Per-IP rate limit on the chat WS connect path. slowapi's @limiter.limit
# decorator is unreliable on WebSocket endpoints in some FastAPI versions, so
# we implement a manual Redis INCR + TTL gate at the top of the handler.
WS_RATE_LIMIT_MAX = 10
WS_RATE_LIMIT_WINDOW_SECONDS = 60
WS_RATE_LIMIT_CLOSE_CODE = 4429


def _encode_cursor(created_at: datetime, message_id: UUID) -> str:
    """Opaque cursor over (created_at, message_id) for stable pagination.

    Both fields are needed: created_at gives chronological order; message_id
    breaks ties when two rows share a timestamp (microsecond collisions
    happen in fixtures and under heavy ingest).
    """
    raw = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(message_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Inverse of _encode_cursor. Raises HTTPException(400) on malformed input."""
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + pad).encode()).decode()
        data = json.loads(raw)
        return datetime.fromisoformat(data["created_at"]), UUID(data["id"])
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc


def _thread_to_response(thread) -> dict:
    return {
        "id": thread.id,
        "thread_id": str(thread.thread_id),
        "title": thread.title,
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
    }


@router.get("/threads", response_model=List[ThreadResponse])
async def list_threads(
    token: str = Depends(oauth2_scheme),
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
    db_ops=Depends(get_db_operations_service),
):
    user = await auth_service.get_current_user(token, db)
    threads = await db_ops.get_user_threads(user.id)
    return [_thread_to_response(t) for t in threads]


@router.post("/threads", response_model=ThreadResponse)
async def create_thread(
    payload: ThreadCreate,
    token: str = Depends(oauth2_scheme),
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
    db_ops=Depends(get_db_operations_service),
    llm_utils=Depends(get_llm_utils),
):
    user = await auth_service.get_current_user(token, db)
    title = await llm_utils.generate_thread_title(payload.first_user_message)
    thread = await db_ops.create_thread(user.id, title)
    return _thread_to_response(thread)


DEFAULT_PAGE_LIMIT = 30
MAX_PAGE_LIMIT = 100


def _format_messages_page(items, has_more: bool) -> dict:
    """Shared envelope for {messages, has_more, next_cursor} pagination.

    `next_cursor` points at the OLDEST message in this page (the last array
    element since we serve newest-first). FE re-uses it as `before` for the
    next page. Null when has_more is False.
    """
    next_cursor = (
        _encode_cursor(items[-1].created_at, items[-1].message_id)
        if items and has_more
        else None
    )
    return {
        "messages": [
            {
                "id": str(m.message_id),
                "role": m.role,
                "content": m.content,
                "type": m.type,
                "created_at": m.created_at.isoformat(),
                "score": m.score,
                "comment": m.comment,
            }
            for m in items
        ],
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


# TODO(threads-family-scoping): The /threads/* surface still uses the legacy
# `get_current_user` (shadow-user) auth path. Migrating to `get_device_context`
# requires adding family_id to threads + a backfill — explicitly out of scope
# for the pagination + feedback build (Architect's design A.4).
@router.get("/threads/{thread_id}", response_model=ThreadMessagesResponse)
async def get_thread(
    thread_id: int,
    token: str = Depends(oauth2_scheme),
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
    db_ops=Depends(get_db_operations_service),
):
    user = await auth_service.get_current_user(token, db)
    thread = await db_ops.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this thread")

    items, has_more = await db_ops.list_thread_messages_page(
        thread.thread_id, before=None, limit=DEFAULT_PAGE_LIMIT
    )
    page = _format_messages_page(items, has_more)
    return {**_thread_to_response(thread), **page}


@router.get(
    "/threads/{thread_id}/messages",
    response_model=MessagesPageResponse,
)
async def list_thread_messages(
    thread_id: int,
    before: str | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    token: str = Depends(oauth2_scheme),
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
    db_ops=Depends(get_db_operations_service),
):
    if limit < 1 or limit > MAX_PAGE_LIMIT:
        raise HTTPException(
            status_code=422,
            detail=f"limit must be between 1 and {MAX_PAGE_LIMIT}",
        )

    user = await auth_service.get_current_user(token, db)
    thread = await db_ops.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to access this thread"
        )

    cursor = _decode_cursor(before) if before else None
    items, has_more = await db_ops.list_thread_messages_page(
        thread.thread_id, before=cursor, limit=limit
    )
    return _format_messages_page(items, has_more)


@router.patch("/threads/{thread_id}", response_model=ThreadResponse)
async def rename_thread(
    thread_id: int,
    payload: ThreadUpdate,
    token: str = Depends(oauth2_scheme),
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
    db_ops=Depends(get_db_operations_service),
):
    user = await auth_service.get_current_user(token, db)
    thread = await db_ops.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this thread")

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    updated = await db_ops.update_thread_title(thread_id, title)
    return _thread_to_response(updated)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: int,
    token: str = Depends(oauth2_scheme),
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
    db_ops=Depends(get_db_operations_service),
):
    user = await auth_service.get_current_user(token, db)
    thread = await db_ops.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this thread")

    await db_ops.delete_thread(thread_id)
    return {"id": thread_id, "success": True}


@router.post("/threads/messages/{message_id}/feedback")
async def message_feedback(
    message_id: str,
    payload: MessageFeedback,
    token: str = Depends(oauth2_scheme),
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
    db_ops=Depends(get_db_operations_service),
):
    user = await auth_service.get_current_user(token, db)
    try:
        message_uuid = UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID (must be UUID)")

    message = await db_ops.get_message_by_uuid(message_uuid)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    thread = await db_ops.get_thread_by_uuid(message.thread_id)
    if not thread or thread.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    feedback = payload.feedback.lower()
    if feedback not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="feedback must be 'like' or 'dislike'")

    updated = await db_ops.update_message_feedback_by_uuid(message_uuid, feedback, payload.comment)
    return {"message_id": str(updated.message_id), "feedback": feedback, "success": True}


async def _check_ws_rate_limit(websocket: WebSocket) -> bool:
    """Manual Redis INCR/TTL rate limit for the chat WS connect path (H2).

    slowapi's @limiter.limit decorator is unreliable on WebSocket endpoints
    in current FastAPI/slowapi versions, so we gate manually using the same
    Redis storage the limiter would have used. Returns True on allow, False
    on deny (in which case the caller closes the WS with code 4429).

    On Redis error we fail open — a working chat is more important than a
    rate-limit guarantee, and the limit is a defense-in-depth signal, not a
    primary auth gate.
    """
    settings = get_settings()
    redis = get_redis_client(settings)
    client_host = websocket.client.host if websocket.client else "unknown"
    bucket_key = f"ratelimit:ws:chat:{client_host}"
    try:
        count = await redis.incr(bucket_key)
        if count == 1:
            await redis.expire(bucket_key, WS_RATE_LIMIT_WINDOW_SECONDS)
        return count <= WS_RATE_LIMIT_MAX
    except Exception as exc:  # noqa: BLE001 — fail open
        logger.warning("ws rate-limit check failed; allowing: %s", exc)
        return True


@router.websocket("/ws/threads/{thread_id}")
async def chat_websocket(
    websocket: WebSocket,
    thread_id: int,
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
    db_ops=Depends(get_db_operations_service),
    parent_router=Depends(get_parent_router),
):
    ws_connected = True

    async def safe_send(data: dict) -> None:
        nonlocal ws_connected
        if not ws_connected:
            return
        try:
            await websocket.send_json(data)
        except Exception:
            ws_connected = False

    if not await _check_ws_rate_limit(websocket):
        await websocket.close(
            code=WS_RATE_LIMIT_CLOSE_CODE, reason="rate_limited"
        )
        return

    await websocket.accept()
    try:
        try:
            payload = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=WS_FIRST_FRAME_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            await websocket.close(code=4001, reason="auth handshake timeout")
            return
        content = payload.get("content")
        token = payload.get("token")

        if not content:
            await safe_send({"error": "Please provide a message content"})
            return
        if not token:
            await safe_send({"error": "Authentication error"})
            return

        # Extract family_id from a device JWT so the FridgeAssistant can bind
        # tools scoped to this family. User-JWTs continue to work (family_id
        # remains None and the assistant runs without tools).
        family_id = None
        try:
            decoded = auth_service.decode_token(token)
            if decoded.get("typ") == "device":
                fam = decoded.get("family_id")
                if fam:
                    from uuid import UUID as _UUID
                    family_id = _UUID(fam)
        except HTTPException:
            await safe_send({"error": "Invalid token"})
            return

        try:
            user = await auth_service.get_current_user(token, db)
        except HTTPException:
            await safe_send({"error": "Invalid token"})
            return

        thread = await db_ops.get_thread(thread_id)
        if not thread:
            await safe_send({"error": "Thread not found"})
            return
        if thread.user_id != user.id:
            await safe_send({"error": "Not authorized to access this thread"})
            return

        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            await safe_send({
                "type": "error_notification",
                "message": "OPENAI_API_KEY not configured on the backend.",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return

        await safe_send({"status": "processing"})

        # Build a ChatStreamer for the publish-side of §7.7. Subscriber-side
        # WS multiplexing remains a future addition; protocol unchanged today.
        chat_streamer = ChatStreamer(get_redis_client(settings))

        async def on_chunk(data: dict) -> None:
            pass

        try:
            async for _chunk in parent_router.astream_response(
                content,
                str(thread.thread_id),
                on_chunk,
                family_id=family_id,
                chat_streamer=chat_streamer,
            ):
                await safe_send(_chunk)
        except Exception as e:
            logger.error("Error while streaming: %s", e, exc_info=True)
            await safe_send({
                "type": "error_notification",
                "message": "Something went wrong while processing your message.",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return

        await db_ops.update_thread_timestamp(thread.id)

    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass

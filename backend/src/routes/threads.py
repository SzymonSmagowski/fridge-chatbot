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
    ThreadCreate,
    ThreadMessagesResponse,
    ThreadResponse,
    ThreadUpdate,
)
from src.services.logger import get_logger

router = APIRouter(tags=["threads"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
logger = get_logger("threads_route")


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

    messages = await db_ops.get_formatted_thread_messages(thread.thread_id)
    return {**_thread_to_response(thread), "messages": messages}


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

    await websocket.accept()
    try:
        payload = await websocket.receive_json()
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

        await safe_send({"status": "processing"})

        # Build a ChatStreamer for the publish-side of §7.7. Subscriber-side
        # WS multiplexing remains a future addition; protocol unchanged today.
        settings = get_settings()
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

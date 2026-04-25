"""Notes endpoints (§5.5)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis

from src.core.cache import cache_aside, family_key, invalidate, sha1_short
from src.core.dependencies import (
    DeviceContext,
    get_chat_streamer,
    get_device_context,
    get_note_service,
    get_redis,
    get_settings,
)
from src.core.family_events import family_event_payload
from src.core.settings import Settings
from src.schemas.notes import (
    NoteCreateRequest,
    NoteListResponse,
    NoteResponse,
    NoteUpdateRequest,
    ShoppingListAppendRequest,
)
from src.services.chat_streaming import ChatStreamer
from src.services.note_service import NoteListFilters, NoteService

router = APIRouter(prefix="/notes", tags=["notes"])

NOTES_TTL = 300


def _list_key(family_id, filters: dict) -> str:
    return family_key(family_id, "notes", sha1_short(filters))


def _detail_key(family_id, note_id) -> str:
    return family_key(family_id, "note", str(note_id))


async def _invalidate(redis: Redis, family_id, note_id=None) -> None:
    keys = [family_key(family_id, "notes:*")]
    if note_id is not None:
        keys.append(_detail_key(family_id, note_id))
    await invalidate(redis, *keys)


@router.get("", response_model=NoteListResponse)
async def list_notes(
    pinned: Literal["true", "false", "all"] = "all",
    label: str | None = None,
    assignee_member_id: UUID | None = None,
    limit: int = 200,
    offset: int = 0,
    ctx: DeviceContext = Depends(get_device_context),
    notes: NoteService = Depends(get_note_service),
    redis: Redis = Depends(get_redis),
):
    filters_dict = {
        "pinned": pinned,
        "label": label,
        "assignee_member_id": str(assignee_member_id) if assignee_member_id else None,
        "limit": limit,
        "offset": offset,
    }
    key = _list_key(ctx.family_id, filters_dict)

    async def fetch():
        items, total = notes.list(
            NoteListFilters(
                pinned=pinned,
                label=label,
                assignee_member_id=assignee_member_id,
                limit=limit,
                offset=offset,
            )
        )
        return NoteListResponse(
            items=[notes.to_response(n) for n in items],
            total=total,
        ).model_dump(mode="json")

    payload = await cache_aside(redis, key, NOTES_TTL, fetch)
    return NoteListResponse.model_validate(payload)


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteCreateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    notes: NoteService = Depends(get_note_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    note = notes.create(body)
    await _invalidate(redis, ctx.family_id, note.id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="note.created", entity="notes", id=note.id),
    )
    return notes.to_response(note)


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    notes: NoteService = Depends(get_note_service),
    redis: Redis = Depends(get_redis),
):
    key = _detail_key(ctx.family_id, note_id)

    async def fetch():
        note = notes.get(note_id)
        return notes.to_response(note).model_dump(mode="json")

    payload = await cache_aside(redis, key, NOTES_TTL, fetch)
    return NoteResponse.model_validate(payload)


@router.patch("/{note_id}", response_model=NoteResponse)
async def patch_note(
    note_id: UUID,
    body: NoteUpdateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    notes: NoteService = Depends(get_note_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    note = notes.update(note_id, body)
    await _invalidate(redis, ctx.family_id, note_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="note.updated", entity="notes", id=note_id),
    )
    return notes.to_response(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    notes: NoteService = Depends(get_note_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    notes.delete(note_id)
    await _invalidate(redis, ctx.family_id, note_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="note.deleted", entity="notes", id=note_id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/shopping-list/append", response_model=NoteResponse)
async def append_shopping_list(
    body: ShoppingListAppendRequest,
    ctx: DeviceContext = Depends(get_device_context),
    notes: NoteService = Depends(get_note_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
    settings: Settings = Depends(get_settings),
):
    note = notes.append_shopping_list(
        body.line, auto_create_default=settings.AUTO_CREATE_SHOPPING_LIST_DEFAULT
    )
    await _invalidate(redis, ctx.family_id, note.id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(
            type="note.shopping_list.appended", entity="notes", id=note.id
        ),
    )
    return notes.to_response(note)

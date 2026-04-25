"""Labels CRUD (§5.6)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from redis.asyncio import Redis

from src.core.cache import cache_aside, family_key, invalidate
from src.core.dependencies import (
    DeviceContext,
    get_chat_streamer,
    get_device_context,
    get_label_service,
    get_redis,
)
from src.core.family_events import family_event_payload
from src.schemas.labels import (
    LabelCreateRequest,
    LabelResponse,
    LabelUpdateRequest,
)
from src.services.chat_streaming import ChatStreamer
from src.services.label_service import LabelReservedError, LabelService

router = APIRouter(prefix="/labels", tags=["labels"])

LABELS_TTL = 900


def _list_key(family_id) -> str:
    return family_key(family_id, "labels")


async def _invalidate(redis: Redis, family_id) -> None:
    await invalidate(
        redis, _list_key(family_id), family_key(family_id, "notes:*")
    )


@router.get("", response_model=list[LabelResponse])
async def list_labels(
    ctx: DeviceContext = Depends(get_device_context),
    labels_service: LabelService = Depends(get_label_service),
    redis: Redis = Depends(get_redis),
):
    key = _list_key(ctx.family_id)

    async def fetch():
        return [
            labels_service.to_response(label).model_dump(mode="json")
            for label in labels_service.list()
        ]

    payload = await cache_aside(redis, key, LABELS_TTL, fetch)
    return [LabelResponse.model_validate(p) for p in payload]


@router.post("", response_model=LabelResponse, status_code=status.HTTP_201_CREATED)
async def create_label(
    body: LabelCreateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    labels_service: LabelService = Depends(get_label_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    label = labels_service.create(body.slug, body.display_name)
    await _invalidate(redis, ctx.family_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="label.created", entity="labels", id=label.slug),
    )
    return labels_service.to_response(label)


@router.patch("/{slug}", response_model=LabelResponse)
async def patch_label(
    slug: str,
    body: LabelUpdateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    labels_service: LabelService = Depends(get_label_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    label = labels_service.update(slug, body.display_name)
    await _invalidate(redis, ctx.family_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="label.updated", entity="labels", id=label.slug),
    )
    return labels_service.to_response(label)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(
    slug: str,
    ctx: DeviceContext = Depends(get_device_context),
    labels_service: LabelService = Depends(get_label_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    try:
        labels_service.delete(slug)
    except LabelReservedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "labels.reserved",
                "detail": f"Label '{exc}' is reserved and cannot be deleted",
            },
        ) from exc
    await _invalidate(redis, ctx.family_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="label.deleted", entity="labels", id=slug),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

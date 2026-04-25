"""Events endpoints (§5.7) — fridge events + external cache reads.

Background calendar fan-out is enqueued via FastAPI BackgroundTasks per D3.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy.orm import sessionmaker

from src.core.cache import cache_aside, family_key, invalidate, sha1_short
from src.core.dependencies import (
    DeviceContext,
    get_chat_streamer,
    get_device_context,
    get_event_service,
    get_redis,
    get_session_factory_dep,
    get_settings,
)
from src.core.family_events import family_event_payload
from src.core.settings import Settings
from src.models import EventTargetSyncStatus
from src.schemas.events import (
    EventCreateRequest,
    EventListResponse,
    EventResponse,
    EventUpdateRequest,
)
from src.services.chat_streaming import ChatStreamer
from src.services.event_service import EventListFilters, EventService
from src.workers.calendar_write_worker import fan_out_event

router = APIRouter(prefix="/events", tags=["events"])

EVENTS_TTL = 300


def _list_key(family_id, filters: dict) -> str:
    return family_key(family_id, "events", sha1_short(filters))


def _detail_key(family_id, event_id) -> str:
    return family_key(family_id, "event", str(event_id))


async def _invalidate(redis: Redis, family_id, event_id=None) -> None:
    keys = [family_key(family_id, "events:*")]
    if event_id is not None:
        keys.append(_detail_key(family_id, event_id))
    await invalidate(redis, *keys)


@router.get("", response_model=EventListResponse)
async def list_events(
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    member_id: UUID | None = None,
    car_id: UUID | None = None,
    source: Literal["fridge", "external", "all"] = "all",
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
):
    filters_dict = {
        "from_dt": from_dt.isoformat() if from_dt else None,
        "to_dt": to_dt.isoformat() if to_dt else None,
        "member_id": str(member_id) if member_id else None,
        "car_id": str(car_id) if car_id else None,
        "source": source,
    }
    key = _list_key(ctx.family_id, filters_dict)

    async def fetch():
        result = events_service.list(
            EventListFilters(
                from_dt=from_dt,
                to_dt=to_dt,
                member_id=member_id,
                car_id=car_id,
                source=source,
            )
        )
        return result.model_dump(mode="json")

    payload = await cache_aside(redis, key, EVENTS_TTL, fetch)
    return EventListResponse.model_validate(payload)


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: EventCreateRequest,
    background_tasks: BackgroundTasks,
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
    session_factory: sessionmaker = Depends(get_session_factory_dep),
    settings: Settings = Depends(get_settings),
):
    event, _plans = events_service.create(body)
    target_ids = [
        t.id for t in event.targets if t.sync_status == EventTargetSyncStatus.pending
    ]

    await _invalidate(redis, ctx.family_id, event.id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="event.created", entity="events", id=event.id),
    )

    if target_ids:
        background_tasks.add_task(
            fan_out_event,
            event_id=event.id,
            target_ids=target_ids,
            settings=settings,
            session_factory=session_factory,
            redis=redis,
        )
    return events_service.to_response(event)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
):
    key = _detail_key(ctx.family_id, event_id)

    async def fetch():
        ev = events_service.get(event_id)
        return events_service.to_response(ev).model_dump(mode="json")

    payload = await cache_aside(redis, key, EVENTS_TTL, fetch)
    return EventResponse.model_validate(payload)


@router.patch("/{event_id}", response_model=EventResponse)
async def patch_event(
    event_id: UUID,
    body: EventUpdateRequest,
    scope: Literal["instance", "all_future"] = "instance",
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    event = events_service.update(event_id, body, scope=scope)
    await _invalidate(redis, ctx.family_id, event_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="event.updated", entity="events", id=event_id),
    )
    return events_service.to_response(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: UUID,
    scope: Literal["instance", "all_future"] = "instance",
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    events_service.delete(event_id, scope=scope)
    await _invalidate(redis, ctx.family_id, event_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="event.deleted", entity="events", id=event_id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{event_id}/resync", response_model=EventResponse)
async def resync_event(
    event_id: UUID,
    background_tasks: BackgroundTasks,
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
    session_factory: sessionmaker = Depends(get_session_factory_dep),
    settings: Settings = Depends(get_settings),
):
    event = events_service.resync(event_id)
    target_ids = [
        t.id for t in event.targets if t.sync_status == EventTargetSyncStatus.pending
    ]
    await _invalidate(redis, ctx.family_id, event_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="event.resynced", entity="events", id=event_id),
    )
    if target_ids:
        background_tasks.add_task(
            fan_out_event,
            event_id=event.id,
            target_ids=target_ids,
            settings=settings,
            session_factory=session_factory,
            redis=redis,
        )
    return events_service.to_response(event)

"""Events endpoints (§5.7) — fridge events + external cache reads.

Google Calendar fan-out is enqueued inside `EventService` itself (so the
chat-tool path gets it too — see services/event_service.py). The route just
calls the service and returns.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis

from src.core.cache import cache_aside, family_key, invalidate, sha1_short
from src.core.dependencies import (
    DeviceContext,
    get_device_context,
    get_event_service,
    get_redis,
)
from src.schemas.events import (
    EventCreateRequest,
    EventListResponse,
    EventResponse,
    EventUpdateRequest,
)
from src.services.event_service import EventListFilters, EventService

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
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
):
    event, _plans = await events_service.create(body)
    await _invalidate(redis, ctx.family_id, event.id)
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
):
    event = await events_service.update(event_id, body, scope=scope)
    await _invalidate(redis, ctx.family_id, event_id)
    return events_service.to_response(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: UUID,
    scope: Literal["instance", "all_future"] = "instance",
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
):
    await events_service.delete(event_id, scope=scope)
    await _invalidate(redis, ctx.family_id, event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{event_id}/resync", response_model=EventResponse)
async def resync_event(
    event_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    events_service: EventService = Depends(get_event_service),
    redis: Redis = Depends(get_redis),
):
    event = await events_service.resync(event_id)
    await _invalidate(redis, ctx.family_id, event_id)
    return events_service.to_response(event)

"""Cars CRUD (§5.4)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis

from src.core.cache import cache_aside, family_key, invalidate, sha1_short
from src.core.dependencies import (
    DeviceContext,
    get_car_service,
    get_chat_streamer,
    get_device_context,
    get_redis,
)
from src.core.family_events import family_event_payload
from src.models import CarStatus
from src.schemas.cars import CarCreateRequest, CarResponse, CarUpdateRequest
from src.services.car_service import CarService
from src.services.chat_streaming import ChatStreamer

router = APIRouter(prefix="/cars", tags=["cars"])

CARS_TTL = 300


def _list_key(family_id, status_filter: str) -> str:
    return family_key(family_id, "cars", sha1_short({"status": status_filter}))


def _detail_key(family_id, car_id) -> str:
    return family_key(family_id, "car", str(car_id))


async def _invalidate(
    redis: Redis, family_id, car_id=None, also_notes_events: bool = False
) -> None:
    keys = [family_key(family_id, "cars:*")]
    if car_id is not None:
        keys.append(_detail_key(family_id, car_id))
    if also_notes_events:
        keys.append(family_key(family_id, "notes:*"))
        keys.append(family_key(family_id, "events:*"))
    await invalidate(redis, *keys)


@router.get("", response_model=list[CarResponse])
async def list_cars(
    status: Literal["active", "inactive", "all"] = "active",
    ctx: DeviceContext = Depends(get_device_context),
    cars_service: CarService = Depends(get_car_service),
    redis: Redis = Depends(get_redis),
):
    key = _list_key(ctx.family_id, status)

    async def fetch():
        return [
            CarResponse.model_validate(c).model_dump(mode="json")
            for c in cars_service.list(status)
        ]

    payload = await cache_aside(redis, key, CARS_TTL, fetch)
    return [CarResponse.model_validate(p) for p in payload]


@router.post("", response_model=CarResponse, status_code=status.HTTP_201_CREATED)
async def create_car(
    body: CarCreateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    cars_service: CarService = Depends(get_car_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    car = cars_service.create(body)
    await _invalidate(redis, ctx.family_id, car.id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="car.created", entity="cars", id=car.id),
    )
    return CarResponse.model_validate(car)


@router.patch("/{car_id}", response_model=CarResponse)
async def patch_car(
    car_id: UUID,
    body: CarUpdateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    cars_service: CarService = Depends(get_car_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    car = cars_service.update(car_id, body)
    await _invalidate(redis, ctx.family_id, car_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="car.updated", entity="cars", id=car_id),
    )
    return CarResponse.model_validate(car)


@router.post("/{car_id}/set-inactive", response_model=CarResponse)
async def set_inactive(
    car_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    cars_service: CarService = Depends(get_car_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    car = cars_service.set_status(car_id, CarStatus.inactive)
    await _invalidate(redis, ctx.family_id, car_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="car.updated", entity="cars", id=car_id),
    )
    return CarResponse.model_validate(car)


@router.post("/{car_id}/set-active", response_model=CarResponse)
async def set_active(
    car_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    cars_service: CarService = Depends(get_car_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    car = cars_service.set_status(car_id, CarStatus.active)
    await _invalidate(redis, ctx.family_id, car_id)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="car.updated", entity="cars", id=car_id),
    )
    return CarResponse.model_validate(car)


@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_car(
    car_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    cars_service: CarService = Depends(get_car_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    cars_service.hard_delete(car_id)
    await _invalidate(redis, ctx.family_id, car_id, also_notes_events=True)
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(type="car.deleted", entity="cars", id=car_id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

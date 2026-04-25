"""Family + Family preferences endpoints (§5.2, §5.8)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from src.core.cache import cache_aside, family_key, invalidate
from src.core.dependencies import (
    DeviceContext,
    get_chat_streamer,
    get_device_context,
    get_family_preferences_service,
    get_family_service,
    get_redis,
)
from src.core.family_events import family_event_payload
from src.schemas.family import (
    FamilyPreferencesPatch,
    FamilyPreferencesResponse,
    FamilyResponse,
    FamilyUpdate,
)
from src.services.chat_streaming import ChatStreamer
from src.services.family_preferences_service import FamilyPreferencesService
from src.services.family_service import FamilyService

router = APIRouter(prefix="/family", tags=["family"])

FAMILY_TTL = 900
PREFERENCES_TTL = 900


@router.get("", response_model=FamilyResponse)
async def get_family(
    ctx: DeviceContext = Depends(get_device_context),
    family_service: FamilyService = Depends(get_family_service),
    redis: Redis = Depends(get_redis),
):
    key = family_key(ctx.family_id, "family")

    async def fetch():
        family = family_service.get()
        return FamilyResponse.model_validate(family).model_dump(mode="json")

    payload = await cache_aside(redis, key, FAMILY_TTL, fetch)
    return FamilyResponse.model_validate(payload)


@router.patch("", response_model=FamilyResponse)
async def patch_family(
    body: FamilyUpdate,
    ctx: DeviceContext = Depends(get_device_context),
    family_service: FamilyService = Depends(get_family_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    family = family_service.update(name=body.name, timezone=body.timezone)
    await invalidate(redis, family_key(ctx.family_id, "family"))
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(
            type="family.updated", entity="family", id=ctx.family_id
        ),
    )
    return FamilyResponse.model_validate(family)


@router.get("/preferences", response_model=FamilyPreferencesResponse)
async def get_preferences(
    ctx: DeviceContext = Depends(get_device_context),
    prefs_service: FamilyPreferencesService = Depends(get_family_preferences_service),
    redis: Redis = Depends(get_redis),
):
    key = family_key(ctx.family_id, "family_preferences")

    async def fetch():
        prefs = prefs_service.get()
        return FamilyPreferencesResponse.model_validate(prefs).model_dump(mode="json")

    payload = await cache_aside(redis, key, PREFERENCES_TTL, fetch)
    return FamilyPreferencesResponse.model_validate(payload)


@router.patch("/preferences", response_model=FamilyPreferencesResponse)
async def patch_preferences(
    body: FamilyPreferencesPatch,
    ctx: DeviceContext = Depends(get_device_context),
    prefs_service: FamilyPreferencesService = Depends(get_family_preferences_service),
    redis: Redis = Depends(get_redis),
    streamer: ChatStreamer = Depends(get_chat_streamer),
):
    prefs = prefs_service.patch(body)
    await invalidate(redis, family_key(ctx.family_id, "family_preferences"))
    await streamer.publish_family_event(
        ctx.family_id,
        family_event_payload(
            type="family_preferences.updated",
            entity="family_preferences",
            id=ctx.family_id,
        ),
    )
    return FamilyPreferencesResponse.model_validate(prefs)

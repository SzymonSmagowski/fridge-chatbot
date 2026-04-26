"""Members CRUD (§5.3)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis

from src.core.cache import cache_aside, family_key, invalidate, sha1_short
from src.core.dependencies import (
    DeviceContext,
    get_device_context,
    get_member_service,
    get_redis,
)
from src.models import MemberStatus
from src.schemas.members import (
    MemberCreateRequest,
    MemberResponse,
    MemberUpdateRequest,
)
from src.services.member_service import MemberService

router = APIRouter(prefix="/members", tags=["members"])

MEMBERS_TTL = 900


def _filter_hash(status_filter: str) -> str:
    return sha1_short({"status": status_filter})


def _list_key(family_id, status_filter: str) -> str:
    return family_key(family_id, "members", _filter_hash(status_filter))


def _detail_key(family_id, member_id) -> str:
    return family_key(family_id, "member", str(member_id))


async def _invalidate(redis: Redis, family_id, member_id=None) -> None:
    keys = [family_key(family_id, "members:*")]
    if member_id is not None:
        keys.append(_detail_key(family_id, member_id))
    await invalidate(redis, *keys)


@router.get("", response_model=list[MemberResponse])
async def list_members(
    status: Literal["active", "inactive", "all"] = "active",
    ctx: DeviceContext = Depends(get_device_context),
    members_service: MemberService = Depends(get_member_service),
    redis: Redis = Depends(get_redis),
):
    key = _list_key(ctx.family_id, status)

    async def fetch():
        items = members_service.list(status)
        return [members_service.to_response(m).model_dump(mode="json") for m in items]

    payload = await cache_aside(redis, key, MEMBERS_TTL, fetch)
    return [MemberResponse.model_validate(p) for p in payload]


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def create_member(
    body: MemberCreateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    members_service: MemberService = Depends(get_member_service),
    redis: Redis = Depends(get_redis),
):
    member = await members_service.create(body)
    await _invalidate(redis, ctx.family_id, member.id)
    return members_service.to_response(member)


@router.get("/{member_id}", response_model=MemberResponse)
async def get_member(
    member_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    members_service: MemberService = Depends(get_member_service),
    redis: Redis = Depends(get_redis),
):
    key = _detail_key(ctx.family_id, member_id)

    async def fetch():
        member = members_service.get(member_id)
        return members_service.to_response(member).model_dump(mode="json")

    payload = await cache_aside(redis, key, MEMBERS_TTL, fetch)
    return MemberResponse.model_validate(payload)


@router.patch("/{member_id}", response_model=MemberResponse)
async def patch_member(
    member_id: UUID,
    body: MemberUpdateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    members_service: MemberService = Depends(get_member_service),
    redis: Redis = Depends(get_redis),
):
    member = await members_service.update(member_id, body)
    await _invalidate(redis, ctx.family_id, member_id)
    return members_service.to_response(member)


@router.post("/{member_id}/set-inactive", response_model=MemberResponse)
async def set_inactive(
    member_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    members_service: MemberService = Depends(get_member_service),
    redis: Redis = Depends(get_redis),
):
    member = await members_service.set_status(member_id, MemberStatus.inactive)
    await _invalidate(redis, ctx.family_id, member_id)
    return members_service.to_response(member)


@router.post("/{member_id}/set-active", response_model=MemberResponse)
async def set_active(
    member_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    members_service: MemberService = Depends(get_member_service),
    redis: Redis = Depends(get_redis),
):
    member = await members_service.set_status(member_id, MemberStatus.active)
    await _invalidate(redis, ctx.family_id, member_id)
    return members_service.to_response(member)

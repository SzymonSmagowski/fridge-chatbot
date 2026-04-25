"""Calendar-sync ops endpoints (§5.9)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.orm import Session, sessionmaker

from src.core.dependencies import (
    DeviceContext,
    get_db,
    get_device_context,
    get_redis,
    get_session_factory_dep,
    get_settings,
)
from src.core.settings import Settings
from src.models import (
    CalendarSyncState,
    GoogleToken,
    GoogleTokenStatus,
    Member,
)
from src.schemas.calendar_sync import SyncStateResponse
from src.services.crypto_service import CryptoService
from src.services.google_calendar_service import GoogleCalendarService
from src.workers.calendar_sync_worker import _pull_member

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/sync-state", response_model=list[SyncStateResponse])
def list_sync_state(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Member, CalendarSyncState, GoogleToken)
        .outerjoin(CalendarSyncState, CalendarSyncState.member_id == Member.id)
        .outerjoin(GoogleToken, GoogleToken.member_id == Member.id)
        .filter(Member.family_id == ctx.family_id)
        .all()
    )
    out: list[SyncStateResponse] = []
    for member, sync, token in rows:
        google_status = (
            token.status.value if token else "not_connected"
        )
        out.append(
            SyncStateResponse(
                member_id=member.id,
                member_name=member.nickname or member.name,
                last_pull_at=sync.last_pull_at if sync else None,
                last_error=sync.last_error if sync else None,
                last_error_at=sync.last_error_at if sync else None,
                consecutive_failures=sync.consecutive_failures if sync else 0,
                google_status=google_status,
            )
        )
    return out


@router.post("/sync/pull")
async def force_pull(
    member_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    session_factory: sessionmaker = Depends(get_session_factory_dep),
    settings: Settings = Depends(get_settings),
):
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.family_id == ctx.family_id)
        .first()
    )
    if not member:
        raise HTTPException(
            status_code=404,
            detail={"code": "members.not_found", "detail": "Member not found"},
        )
    token = db.query(GoogleToken).filter(GoogleToken.member_id == member_id).first()
    if not token or token.status != GoogleTokenStatus.connected:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "calendar.not_connected",
                "detail": "Member has no active Google connection",
            },
        )

    crypto = CryptoService(settings)
    calendar = GoogleCalendarService()
    await _pull_member(
        member_id=member.id,
        family_id=member.family_id,
        settings=settings,
        session_factory=session_factory,
        redis=redis,
        crypto=crypto,
        calendar=calendar,
    )
    return {"status": "ok", "member_id": str(member.id)}

"""Per-event-target Google Calendar write coroutines.

Each task is enqueued via FastAPI BackgroundTasks after the request returns
`201` with `sync_status=pending`. Tasks open their own DB session via the
session factory closure (do NOT reuse the request session).
"""
from __future__ import annotations

import asyncio
from typing import Iterable
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import sessionmaker

from src.core.family_events import family_event_payload
from src.models import Event, EventTarget, EventTargetSyncStatus
from src.services.chat_streaming import ChatStreamer
from src.services.crypto_service import CryptoService
from src.services.google_calendar_service import GoogleCalendarService
from src.services.google_token_service import GoogleTokenService
from src.services.logger import get_logger
from src.core.settings import Settings

logger = get_logger("calendar_write_worker")

WRITE_LOCK_KEY = "lock:event_write:{event_id}:{member_id}"
WRITE_LOCK_TTL = 30  # seconds — single-flight per (event, member)
MAX_RETRIES = 3


async def fan_out_event(
    *,
    event_id: UUID,
    target_ids: Iterable[UUID],
    settings: Settings,
    session_factory: sessionmaker,
    redis: Redis,
) -> None:
    """Run all per-target writes in parallel for a single event."""
    tasks = [
        sync_target(
            event_id=event_id,
            target_id=tid,
            settings=settings,
            session_factory=session_factory,
            redis=redis,
        )
        for tid in target_ids
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    family_id = _family_id_for_event(session_factory, event_id)
    if not family_id:
        return

    streamer = ChatStreamer(redis)
    await streamer.publish_family_event(
        family_id,
        family_event_payload(
            type="event.synced",
            entity="events",
            id=event_id,
            actor="sync-worker",
        ),
    )


def _family_id_for_event(session_factory: sessionmaker, event_id: UUID) -> str:
    with session_factory() as db:
        ev = db.query(Event).filter(Event.id == event_id).first()
        return str(ev.family_id) if ev else ""


async def sync_target(
    *,
    event_id: UUID,
    target_id: UUID,
    settings: Settings,
    session_factory: sessionmaker,
    redis: Redis,
) -> None:
    lock_key = WRITE_LOCK_KEY.format(event_id=event_id, member_id=target_id)
    try:
        got = await redis.set(lock_key, "1", nx=True, ex=WRITE_LOCK_TTL)
    except RedisError:
        got = True  # degrade gracefully if Redis is down
    if not got:
        return

    crypto = CryptoService(settings)
    calendar = GoogleCalendarService()
    try:
        with session_factory() as db:
            target = (
                db.query(EventTarget).filter(EventTarget.id == target_id).first()
            )
            if not target or target.sync_status != EventTargetSyncStatus.pending:
                return
            ev = db.query(Event).filter(Event.id == event_id).first()
            if not ev:
                return

            tokens = GoogleTokenService(settings, db, redis, crypto)
            access_token = await tokens.get_access_token(target.member_id)
            if not access_token:
                target.sync_status = EventTargetSyncStatus.skipped
                target.last_error = "no_access_token"
                db.commit()
                return

            try:
                google_event_id = await calendar.insert(
                    access_token,
                    title=ev.title,
                    description=ev.description,
                    start_at=ev.start_at,
                    end_at=ev.end_at,
                    timezone=ev.timezone,
                    location=ev.location,
                    rrule=ev.rrule,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "calendar insert failed for target %s: %s", target_id, exc
                )
                target.retry_count += 1
                if target.retry_count >= MAX_RETRIES:
                    target.sync_status = EventTargetSyncStatus.failed
                target.last_error = str(exc)[:500]
                db.commit()
                return

            target.google_event_id = google_event_id
            target.sync_status = EventTargetSyncStatus.synced
            target.last_error = None
            db.commit()
    finally:
        try:
            await redis.delete(lock_key)
        except RedisError:
            pass

"""Polling sync loop for connected members' Google Calendars (D3 / D4).

Started in `lifespan` as `asyncio.create_task(...)`; cancelled cleanly on
shutdown. Uses each member's `calendar_sync_state.last_pull_sync_token` for
incremental reads. Failures bump `consecutive_failures`; ≥5 failures flips
the token row to `reconnect_needed`.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import sessionmaker

from src.core.cache import family_key, invalidate
from src.core.pubsub import family_events_channel
from src.core.settings import Settings
from src.models import (
    CalendarSyncState,
    EventTarget,
    ExternalEventCacheRow,
    Family,
    GoogleToken,
    GoogleTokenStatus,
    Member,
    MemberStatus,
)
from src.services.crypto_service import CryptoService
from src.services.google_calendar_service import GoogleCalendarService
from src.services.google_token_service import GoogleTokenService
from src.services.logger import get_logger

logger = get_logger("calendar_sync_worker")

MAX_CONSECUTIVE_FAILURES = 5


async def run_polling_loop(
    *,
    settings: Settings,
    session_factory: sessionmaker,
    redis: Redis,
    stop_event: asyncio.Event,
) -> None:
    """Poll every connected member at a configurable cadence."""
    crypto = CryptoService(settings)
    calendar = GoogleCalendarService()

    interval = settings.SYNC_INTERVAL_SEC_DEFAULT
    while not stop_event.is_set():
        try:
            with session_factory() as db:
                members = (
                    db.query(Member)
                    .join(GoogleToken, GoogleToken.member_id == Member.id)
                    .filter(
                        Member.status == MemberStatus.active,
                        GoogleToken.status == GoogleTokenStatus.connected,
                    )
                    .all()
                )

            for member in members:
                try:
                    await _pull_member(
                        member_id=member.id,
                        family_id=member.family_id,
                        settings=settings,
                        session_factory=session_factory,
                        redis=redis,
                        crypto=crypto,
                        calendar=calendar,
                    )
                except Exception as exc:  # noqa: BLE001 — never let one member break the loop
                    logger.warning("pull_member failed for %s: %s", member.id, exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("polling loop iteration failed: %s", exc, exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def _pull_member(
    *,
    member_id,
    family_id,
    settings: Settings,
    session_factory: sessionmaker,
    redis: Redis,
    crypto: CryptoService,
    calendar: GoogleCalendarService,
) -> None:
    with session_factory() as db:
        sync_state = (
            db.query(CalendarSyncState)
            .filter(CalendarSyncState.member_id == member_id)
            .first()
        )
        if sync_state is None:
            sync_state = CalendarSyncState(member_id=member_id)
            db.add(sync_state)
            db.commit()
            db.refresh(sync_state)

        sync_token = sync_state.last_pull_sync_token

        tokens = GoogleTokenService(settings, db, redis, crypto)
        access_token = await tokens.get_access_token(member_id)
        if not access_token:
            sync_state.last_error = "no_access_token"
            sync_state.last_error_at = datetime.utcnow()
            sync_state.consecutive_failures += 1
            if sync_state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                token = (
                    db.query(GoogleToken)
                    .filter(GoogleToken.member_id == member_id)
                    .first()
                )
                if token:
                    token.status = GoogleTokenStatus.reconnect_needed
            db.commit()
            return

        try:
            time_min = datetime.now(tz=timezone.utc) - timedelta(days=7)
            result = await calendar.list_events(
                access_token,
                sync_token=sync_token,
                time_min=None if sync_token else time_min,
            )
        except Exception as exc:  # noqa: BLE001
            sync_state.last_error = str(exc)[:500]
            sync_state.last_error_at = datetime.utcnow()
            sync_state.consecutive_failures += 1
            db.commit()
            return

        items: list[dict[str, Any]] = result.get("items", [])
        next_sync = result.get("next_sync_token")
        changed = _upsert_external_events(db, family_id, member_id, items)

        sync_state.last_pull_at = datetime.utcnow()
        sync_state.last_error = None
        sync_state.last_error_at = None
        sync_state.consecutive_failures = 0
        if next_sync:
            sync_state.last_pull_sync_token = next_sync
        db.commit()

    if changed:
        try:
            await invalidate(redis, family_key(family_id, "events:*"))
            await redis.publish(
                family_events_channel(family_id),
                f'{{"type":"external_events.updated","member_id":"{member_id}"}}',
            )
        except RedisError:
            pass


def _upsert_external_events(
    db, family_id, member_id, items: list[dict[str, Any]]
) -> int:
    """Upsert each Google event into external_events_cache. Returns rows changed."""
    if not items:
        return 0

    google_event_ids = [item.get("id") for item in items if item.get("id")]
    fridge_target_ids = {
        row.google_event_id
        for row in db.query(EventTarget)
        .filter(
            EventTarget.member_id == member_id,
            EventTarget.google_event_id.in_(google_event_ids),
        )
        .all()
    }

    changed = 0
    now = datetime.utcnow()
    for item in items:
        google_event_id = item.get("id")
        if not google_event_id:
            continue

        if item.get("status") == "cancelled":
            db.query(ExternalEventCacheRow).filter(
                ExternalEventCacheRow.member_id == member_id,
                ExternalEventCacheRow.google_event_id == google_event_id,
            ).delete()
            changed += 1
            continue

        start = _parse_event_time(item.get("start", {}))
        end = _parse_event_time(item.get("end", {}))
        if start is None or end is None:
            continue
        is_all_day = "date" in (item.get("start") or {})
        rrule = None
        recurrence = item.get("recurrence") or []
        for entry in recurrence:
            if entry.startswith("RRULE:"):
                rrule = entry[len("RRULE:") :]
                break

        existing = (
            db.query(ExternalEventCacheRow)
            .filter(
                ExternalEventCacheRow.member_id == member_id,
                ExternalEventCacheRow.google_event_id == google_event_id,
            )
            .first()
        )
        created_by_fridge = google_event_id in fridge_target_ids

        if existing:
            existing.title = item.get("summary")
            existing.description = item.get("description")
            existing.start_at = start
            existing.end_at = end
            existing.location = item.get("location")
            existing.is_all_day = is_all_day
            existing.rrule = rrule
            existing.created_by_fridge = created_by_fridge
            existing.last_seen_at = now
        else:
            db.add(
                ExternalEventCacheRow(
                    family_id=family_id,
                    member_id=member_id,
                    google_event_id=google_event_id,
                    title=item.get("summary"),
                    description=item.get("description"),
                    start_at=start,
                    end_at=end,
                    location=item.get("location"),
                    is_all_day=is_all_day,
                    rrule=rrule,
                    created_by_fridge=created_by_fridge,
                    last_seen_at=now,
                )
            )
        changed += 1
    db.commit()
    return changed


def _parse_event_time(raw: dict | None) -> datetime | None:
    if not raw:
        return None
    if "dateTime" in raw:
        return datetime.fromisoformat(raw["dateTime"].replace("Z", "+00:00"))
    if "date" in raw:
        return datetime.fromisoformat(raw["date"]).replace(tzinfo=timezone.utc)
    return None


async def warm_family_cache(
    *,
    family_id,
    session_factory: sessionmaker,
    redis: Redis,
) -> None:
    """Pre-populate the hot cache keys for one family on startup."""
    import json

    with session_factory() as db:
        family = db.query(Family).filter(Family.id == family_id).first()
        if not family:
            return
        prefs = family.preferences

    try:
        if family:
            await redis.set(
                family_key(family_id, "family"),
                json.dumps(
                    {
                        "id": str(family.id),
                        "name": family.name,
                        "timezone": family.timezone,
                        "created_at": family.created_at.isoformat(),
                    }
                ),
                ex=900,
            )
        if prefs:
            await redis.set(
                family_key(family_id, "family_preferences"),
                json.dumps(
                    {
                        "family_id": str(prefs.family_id),
                        "sync_interval_sec": prefs.sync_interval_sec,
                        "fanout_enabled": prefs.fanout_enabled,
                        "voice_wake_enabled": prefs.voice_wake_enabled,
                        "always_on": prefs.always_on,
                        "auto_create_shopping_list": prefs.auto_create_shopping_list,
                        "updated_at": prefs.updated_at.isoformat(),
                    }
                ),
                ex=900,
            )
        # Members cache uses the active-only filter hash exactly as the route
        # composes it — see routes/members.py::_filter_hash.
        # We intentionally skip pre-warming members here to avoid coupling to
        # the route's filter hash; the first GET will populate it.
    except RedisError as exc:
        logger.warning("warm_family_cache failed: %s", exc)

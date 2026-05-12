"""GoogleCalendarService — insert/update/delete on a member's primary calendar
+ list events for the polling job (incremental via syncToken).

Wraps `google-api-python-client`. All API I/O is offloaded to a thread via
`asyncio.to_thread` because the SDK is blocking.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.services.logger import get_logger

logger = get_logger("google_calendar")


def _build_service(access_token: str):
    creds = Credentials(token=access_token)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _to_event_body(
    *,
    title: str,
    description: str | None,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    location: str | None,
    rrule: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start_at.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_at.isoformat(), "timeZone": timezone},
    }
    if description is not None:
        body["description"] = description
    if location is not None:
        body["location"] = location
    if rrule:
        body["recurrence"] = [rrule if rrule.startswith("RRULE:") else f"RRULE:{rrule}"]
    return body


class GoogleCalendarService:
    async def insert(
        self,
        access_token: str,
        *,
        title: str,
        description: str | None,
        start_at: datetime,
        end_at: datetime,
        timezone: str,
        location: str | None,
        rrule: str | None,
    ) -> str:
        body = _to_event_body(
            title=title,
            description=description,
            start_at=start_at,
            end_at=end_at,
            timezone=timezone,
            location=location,
            rrule=rrule,
        )

        def _do() -> str:
            service = _build_service(access_token)
            inserted = service.events().insert(calendarId="primary", body=body).execute()
            return inserted["id"]

        return await asyncio.to_thread(_do)

    async def update(
        self,
        access_token: str,
        google_event_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        def _do() -> dict[str, Any]:
            service = _build_service(access_token)
            return (
                service.events()
                .patch(calendarId="primary", eventId=google_event_id, body=body)
                .execute()
            )

        return await asyncio.to_thread(_do)

    async def get(
        self,
        access_token: str,
        google_event_id: str,
    ) -> dict[str, Any]:
        def _do() -> dict[str, Any]:
            service = _build_service(access_token)
            return (
                service.events()
                .get(calendarId="primary", eventId=google_event_id)
                .execute()
            )

        return await asyncio.to_thread(_do)

    async def insert_raw(
        self,
        access_token: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert with a fully-formed event body (used for recurring-series split)."""

        def _do() -> dict[str, Any]:
            service = _build_service(access_token)
            return (
                service.events()
                .insert(calendarId="primary", body=body)
                .execute()
            )

        return await asyncio.to_thread(_do)

    async def delete(self, access_token: str, google_event_id: str) -> bool:
        def _do() -> bool:
            service = _build_service(access_token)
            try:
                service.events().delete(
                    calendarId="primary", eventId=google_event_id
                ).execute()
                return True
            except HttpError as exc:
                if exc.resp.status in (404, 410):
                    return True
                raise

        return await asyncio.to_thread(_do)

    async def list_events(
        self,
        access_token: str,
        *,
        sync_token: str | None,
        time_min: datetime | None = None,
    ) -> dict[str, Any]:
        """Return a dict with `items: list, next_sync_token: str | None`.

        Falls back to a time-bounded list when no sync token is present (first
        pull or after an `invalid_grant` reset).
        """

        def _do() -> dict[str, Any]:
            service = _build_service(access_token)
            kwargs: dict[str, Any] = {
                "calendarId": "primary",
                "singleEvents": False,
                "showDeleted": True,
                "maxResults": 250,
            }
            if sync_token:
                kwargs["syncToken"] = sync_token
            elif time_min:
                # RFC 3339: a tz-aware UTC datetime already serializes as
                # "...+00:00" — appending "Z" produces "+00:00Z" which Google
                # rejects with 400. Normalize to the Z form instead.
                kwargs["timeMin"] = time_min.isoformat().replace("+00:00", "Z")

            items: list[dict[str, Any]] = []
            page_token: str | None = None
            next_sync: str | None = None
            while True:
                if page_token:
                    kwargs["pageToken"] = page_token
                resp = service.events().list(**kwargs).execute()
                items.extend(resp.get("items", []))
                page_token = resp.get("nextPageToken")
                next_sync = resp.get("nextSyncToken") or next_sync
                if not page_token:
                    break
            return {"items": items, "next_sync_token": next_sync}

        return await asyncio.to_thread(_do)

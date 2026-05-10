"""Feedback endpoints (§B.6).

POST creates a new family-scoped feedback row from the kiosk UI. GET lists
the family's own feedback, cursor-paginated. The shape of the list envelope
matches `MessagesPageResponse` so the FE has one mental model for both.

Per the design, there is intentionally no PATCH yet — the developer-side
triage UI is not in scope, so adding write-state churn would be premature.
"""
from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.core.dependencies import (
    DeviceContext,
    get_device_context,
    get_feedback_service,
)
from src.core.rate_limit import get_limiter
from src.models.feedback import FeedbackCategory, FeedbackStatus
from src.schemas.feedback import (
    FeedbackCreateRequest,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackStatusLiteral,
)
from src.services.feedback_service import FeedbackListFilters, FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])
_limiter = get_limiter()

DEFAULT_LIMIT = 30
MAX_LIMIT = 100


def _device_rate_key(request: Request) -> str:
    """Per-device rate-limit key derived from the JWT subject.

    Same shape as calendar_sync._calendar_pull_rate_key — falls back to the
    remote IP when the header is absent or malformed (those requests will be
    rejected by the auth dep moments later anyway).
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        try:
            parts = token.split(".")
            if len(parts) >= 2:
                pad = "=" * (-len(parts[1]) % 4)
                claims = json.loads(
                    base64.urlsafe_b64decode((parts[1] + pad).encode())
                )
                sub = claims.get("sub")
                if sub:
                    return f"device:{sub}"
        except Exception:  # noqa: BLE001 — fall back below
            pass
    from slowapi.util import get_remote_address

    return get_remote_address(request)


def _encode_feedback_cursor(created_at: datetime, feedback_id: UUID) -> str:
    raw = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(feedback_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_feedback_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + pad).encode()).decode()
        data = json.loads(raw)
        return datetime.fromisoformat(data["created_at"]), UUID(data["id"])
    except (
        ValueError,
        KeyError,
        TypeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
@_limiter.limit("10/minute", key_func=_device_rate_key)
async def create_feedback(
    request: Request,  # required by slowapi
    body: FeedbackCreateRequest,
    ctx: DeviceContext = Depends(get_device_context),
    service: FeedbackService = Depends(get_feedback_service),
):
    row = await service.submit_from_user(
        category=FeedbackCategory(body.category),
        message=body.message,
        thread_id=body.thread_id,
        member_id=None,  # kiosk has no logged-in member
        device_id=ctx.device_id,
    )
    return FeedbackResponse.model_validate(row)


@router.get("", response_model=FeedbackListResponse)
def list_feedback(
    status: Optional[FeedbackStatusLiteral] = None,
    limit: int = DEFAULT_LIMIT,
    before: Optional[str] = None,
    ctx: DeviceContext = Depends(get_device_context),  # noqa: ARG001
    service: FeedbackService = Depends(get_feedback_service),
):
    if not (1 <= limit <= MAX_LIMIT):
        raise HTTPException(
            status_code=422,
            detail=f"limit must be between 1 and {MAX_LIMIT}",
        )

    cursor = _decode_feedback_cursor(before) if before else None
    items, has_more = service.list_page(
        FeedbackListFilters(
            status=FeedbackStatus(status) if status else None,
            limit=limit,
            before=cursor,
        )
    )
    next_cursor = (
        _encode_feedback_cursor(items[-1].created_at, items[-1].id)
        if items and has_more
        else None
    )
    return FeedbackListResponse(
        items=[FeedbackResponse.model_validate(r) for r in items],
        has_more=has_more,
        next_cursor=next_cursor,
    )

"""Pairing endpoints (§4.1, §5.1).

`POST /pairing/start` is the only unauthenticated endpoint in the new API.
The matching `GET /oauth/google/callback` (handled in `routes/oauth.py`) is
state-bearer auth — anyone with the unguessable nonce can complete the pair.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.core.dependencies import get_google_oauth_service, get_redis
from src.core.rate_limit import get_limiter
from src.schemas.oauth import (
    PairingStartRequest,
    PairingStartResponse,
    PairingStatusResponse,
)
from src.services.google_oauth_service import GoogleOAuthService

router = APIRouter(prefix="/pairing", tags=["pairing"])
_limiter = get_limiter()

PAIRING_KEY_PREFIX = "pairing:"
PAIRING_VERIFIER_KEY_PREFIX = "pairing:verifier:"
PAIRING_DONE_KEY_PREFIX = "pairing:done:"
PAIRING_TTL_SECONDS = 600  # 10 min — covers a slow Google OAuth round-trip on phone.
PAIRING_DONE_TTL_SECONDS = 180  # 3 min — kiosk poll catches the JWT then clears it.


@router.post("/start", response_model=PairingStartResponse)
@_limiter.limit("10/minute")
async def start_pairing(
    request: Request,  # required by slowapi to read the client IP
    body: PairingStartRequest | None = None,
    redis: Redis = Depends(get_redis),
    oauth: GoogleOAuthService = Depends(get_google_oauth_service),
):
    pairing_id = secrets.token_urlsafe(24)
    label = body.device_label if body else None
    state = f"pair:{pairing_id}"

    try:
        url, code_verifier = oauth.build_authorize_url(state=state)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Persist the label and the PKCE code_verifier under the pairing id with
    # the same TTL — both are read on the OAuth callback.
    try:
        await redis.set(
            f"{PAIRING_KEY_PREFIX}{pairing_id}",
            label or "",
            ex=PAIRING_TTL_SECONDS,
        )
        await redis.set(
            f"{PAIRING_VERIFIER_KEY_PREFIX}{pairing_id}",
            code_verifier,
            ex=PAIRING_TTL_SECONDS,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=503, detail="Pairing temporarily unavailable"
        ) from exc

    return PairingStartResponse(pairing_id=pairing_id, authorize_url=url)


@router.get("/status/{pairing_id}", response_model=PairingStatusResponse)
@_limiter.limit("60/minute")
async def pairing_status(
    request: Request,  # required by slowapi to read the client IP
    pairing_id: str,
    redis: Redis = Depends(get_redis),
):
    """Kiosk polls this while displaying the QR code.

    Three terminal states:
    - ``pending``  — pair session live, no callback yet (kiosk keeps polling).
    - ``complete`` — Google callback finished; returns the device JWT. The
      ``pairing:done:<id>`` Redis key is deleted after read so the same token
      is never handed out twice (the kiosk persists it to localStorage and
      that's the new auth credential).
    - ``expired``  — neither key exists. Either Google was never completed
      within ``PAIRING_TTL_SECONDS``, or the JWT was already polled. Kiosk
      should surface a retry CTA.
    """
    try:
        done_token = await redis.get(f"{PAIRING_DONE_KEY_PREFIX}{pairing_id}")
        if done_token is not None:
            await redis.delete(f"{PAIRING_DONE_KEY_PREFIX}{pairing_id}")
            return PairingStatusResponse(status="complete", token=done_token)
        pending = await redis.get(f"{PAIRING_KEY_PREFIX}{pairing_id}")
        if pending is not None:
            return PairingStatusResponse(status="pending")
    except RedisError as exc:
        raise HTTPException(
            status_code=503, detail="Pairing temporarily unavailable"
        ) from exc
    return PairingStatusResponse(status="expired")

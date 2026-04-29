"""Pairing endpoints (§4.1, §5.1).

`POST /pairing/start` is the only unauthenticated endpoint in the new API.
The matching `GET /oauth/google/callback` (handled in `routes/oauth.py`) is
state-bearer auth — anyone with the unguessable nonce can complete the pair.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.core.dependencies import get_google_oauth_service, get_redis
from src.schemas.oauth import PairingStartRequest, PairingStartResponse
from src.services.google_oauth_service import GoogleOAuthService

router = APIRouter(prefix="/pairing", tags=["pairing"])

PAIRING_KEY_PREFIX = "pairing:"
PAIRING_VERIFIER_KEY_PREFIX = "pairing:verifier:"
PAIRING_TTL_SECONDS = 600  # 10 min


@router.post("/start", response_model=PairingStartResponse)
async def start_pairing(
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

"""LiveKit JWT minting for the voice transport.

The fridge frontend POSTs `/api/livekit/token` with a device JWT, gets back a
short-lived LiveKit JWT scoped to the family's room. The browser then opens a
WebRTC connection to the dev LiveKit server using that token — and the running
`voice_worker` process picks up the dispatch and joins the same room as an
agent.

The room name is `<prefix>-<family_id>`. The voice worker parses the family
UUID back out of the room name on join; the JWT's `room` grant pins which room
the kiosk can join, so a kiosk cannot reach another family's room even by
fabricating a name.

Why a dedicated route and not a query-param shortcut: minting a LiveKit JWT
needs the LiveKit api_secret, which the browser must never see. The frontend
auths with its existing device JWT (already family-scoped) and exchanges it
here for a LiveKit JWT.
"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends
from livekit import api
from pydantic import BaseModel

from src.core.dependencies import DeviceContext, get_device_context, get_settings
from src.core.settings import Settings

router = APIRouter(prefix="/livekit", tags=["livekit"])


class LiveKitTokenResponse(BaseModel):
    url: str
    token: str
    room: str
    identity: str


@router.post("/token", response_model=LiveKitTokenResponse)
def mint_livekit_token(
    ctx: DeviceContext = Depends(get_device_context),
    settings: Settings = Depends(get_settings),
) -> LiveKitTokenResponse:
    # Per-mint session nonce in front of the family UUID. Two reasons:
    # 1. Each /voice page load gets a fresh room, so a worker crash from a
    #    prior session doesn't poison subsequent dispatch retries (LiveKit's
    #    dev server tracks per-room dispatch state).
    # 2. The trailing 36 characters are still the family UUID, so the worker's
    #    `_family_id_from_room_name(name[-36:])` keeps working unchanged.
    nonce = uuid4().hex[:8]
    room_name = f"{settings.LIVEKIT_ROOM_PREFIX}-{nonce}-{ctx.family_id}"
    identity = f"kiosk-{uuid4().hex[:12]}"

    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
        # The kiosk creates the room on first join; the agent worker dispatches
        # in. No room-admin rights for the participant.
        room_create=True,
    )

    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("Fridge Kiosk")
        .with_grants(grants)
        .with_ttl(timedelta(seconds=settings.LIVEKIT_TOKEN_TTL_SECONDS))
        .to_jwt()
    )

    return LiveKitTokenResponse(
        url=settings.LIVEKIT_PUBLIC_URL,
        token=token,
        room=room_name,
        identity=identity,
    )

"""Google OAuth — pair (first-time) and connect (additional members).

State format: ``"pair:<pairing_id>"`` or ``"connect:<member_id>"``.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from urllib.parse import quote

from src.core.dependencies import (
    DeviceContext,
    get_auth_service,
    get_chat_streamer,
    get_crypto_service,
    get_db,
    get_device_context,
    get_google_oauth_service,
    get_redis,
    get_session_factory_dep,
    get_settings,
)
from src.core.family_events import family_event_payload
from src.core.labels import RESERVED_DISPLAY_NAMES, RESERVED_SLUGS
from src.core.settings import Settings
from src.models import (
    Device,
    Family,
    FamilyPreferences,
    GoogleTokenStatus,
    Label,
    Member,
    MemberStatus,
    Note,
    NoteLabel,
    User,
)
from src.routes.pairing import (
    PAIRING_DONE_KEY_PREFIX,
    PAIRING_DONE_TTL_SECONDS,
    PAIRING_KEY_PREFIX,
    PAIRING_VERIFIER_KEY_PREFIX,
)
from src.schemas.oauth import AuthorizeUrlResponse
from src.services.auth_service import AuthService
from src.services.crypto_service import CryptoService
from src.services.chat_streaming import ChatStreamer
from src.services.google_calendar_service import GoogleCalendarService
from src.services.google_oauth_service import GoogleOAuthService
from src.services.google_token_service import GoogleTokenService
from src.services.logger import get_logger
from src.workers.calendar_sync_worker import _pull_member

router = APIRouter(prefix="/oauth/google", tags=["oauth"])
logger = get_logger("oauth")

DEFAULT_COLOR = "sage"
CONNECT_STATE_KEY = "oauth_connect:"
CONNECT_VERIFIER_KEY = "oauth_connect:verifier:"
CONNECT_STATE_TTL = 600


@router.get("/authorize", response_model=AuthorizeUrlResponse)
async def authorize_for_member(
    member_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    oauth: GoogleOAuthService = Depends(get_google_oauth_service),
):
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.family_id == ctx.family_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    state_id = secrets.token_urlsafe(24)
    state = f"connect:{state_id}"
    url, code_verifier = oauth.build_authorize_url(state=state)
    try:
        await redis.set(
            f"{CONNECT_STATE_KEY}{state_id}",
            str(member.id),
            ex=CONNECT_STATE_TTL,
        )
        await redis.set(
            f"{CONNECT_VERIFIER_KEY}{state_id}",
            code_verifier,
            ex=CONNECT_STATE_TTL,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=503, detail="OAuth temporarily unavailable"
        ) from exc

    return AuthorizeUrlResponse(authorize_url=url)


@router.delete("/{member_id}")
async def revoke_member(
    member_id: UUID,
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    oauth: GoogleOAuthService = Depends(get_google_oauth_service),
    crypto: CryptoService = Depends(get_crypto_service),
    settings: Settings = Depends(get_settings),
):
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.family_id == ctx.family_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    tokens = GoogleTokenService(settings, db, redis, crypto)
    token_row = tokens.load(member_id)
    if token_row:
        try:
            refresh_token = crypto.decrypt(token_row.refresh_token_encrypted)
            await oauth.revoke(refresh_token)
        except Exception as exc:  # noqa: BLE001 — best-effort revoke
            logger.warning("revoke for member %s failed: %s", member_id, exc)
        token_row.status = GoogleTokenStatus.revoked
        db.commit()
    return {"status": "revoked"}


@router.get("/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    oauth: GoogleOAuthService = Depends(get_google_oauth_service),
    crypto: CryptoService = Depends(get_crypto_service),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
    streamer: ChatStreamer = Depends(get_chat_streamer),
    session_factory=Depends(get_session_factory_dep),
):
    kind, _, ident = state.partition(":")
    if kind == "pair":
        return await _handle_pair_callback(
            pairing_id=ident,
            code=code,
            db=db,
            redis=redis,
            oauth=oauth,
            crypto=crypto,
            auth_service=auth_service,
            settings=settings,
        )
    if kind == "connect":
        return await _handle_connect_callback(
            state_id=ident,
            code=code,
            db=db,
            redis=redis,
            oauth=oauth,
            crypto=crypto,
            settings=settings,
            streamer=streamer,
            session_factory=session_factory,
        )
    raise HTTPException(status_code=400, detail="Unknown OAuth state kind")


async def _handle_pair_callback(
    *,
    pairing_id: str,
    code: str,
    db: Session,
    redis: Redis,
    oauth: GoogleOAuthService,
    crypto: CryptoService,
    auth_service: AuthService,
    settings: Settings,
) -> RedirectResponse:
    label_value = await redis.get(f"{PAIRING_KEY_PREFIX}{pairing_id}")
    if label_value is None:
        raise HTTPException(status_code=400, detail="Pairing session expired")
    code_verifier = await redis.get(f"{PAIRING_VERIFIER_KEY_PREFIX}{pairing_id}")
    await redis.delete(f"{PAIRING_KEY_PREFIX}{pairing_id}")
    await redis.delete(f"{PAIRING_VERIFIER_KEY_PREFIX}{pairing_id}")

    tokens = oauth.exchange_code(code, code_verifier=code_verifier)
    if not tokens.get("refresh_token"):
        raise HTTPException(
            status_code=400,
            detail="Google did not return a refresh_token; re-consent is required",
        )

    given = (tokens.get("google_given_name") or tokens.get("google_email") or "User")
    family_name = f"{given}'s Family"

    family = Family(name=family_name)
    db.add(family)
    db.flush()

    db.add(
        FamilyPreferences(
            family_id=family.id,
            sync_interval_sec=settings.SYNC_INTERVAL_SEC_DEFAULT,
            auto_create_shopping_list=settings.AUTO_CREATE_SHOPPING_LIST_DEFAULT,
            # Polish-first: the target users are 60+ Polish-speaking parents.
            # `voice_locale="pl"` pins both chat and voice graphs to Polish on
            # the first turn; the detect_language node still flips to English
            # for unmistakably English input. The language switcher in Settings
            # (PATCH /api/family/preferences) lets households override this.
            voice_locale="pl",
            updated_at=datetime.utcnow(),
        )
    )

    shadow_username = f"device-{family.id.hex[:12]}"
    # bcrypt 5.x truncates secrets to 72 bytes; keep our generated value short.
    shadow_password = secrets.token_urlsafe(32)[:60]
    shadow_user = User(
        username=shadow_username,
        email=None,
        hashed_password=auth_service.get_password_hash(shadow_password),
        is_active=True,
    )
    db.add(shadow_user)
    db.flush()

    device = Device(
        family_id=family.id,
        label=label_value or "Kitchen Fridge",
        paired_at=datetime.utcnow(),
        shadow_user_id=shadow_user.id,
    )
    db.add(device)
    db.flush()

    member = Member(
        family_id=family.id,
        name=given,
        color=DEFAULT_COLOR,
        status=MemberStatus.active,
        is_setup_owner=True,
    )
    db.add(member)
    db.flush()

    google_tokens = GoogleTokenService(settings, db, redis, crypto)
    google_tokens.store(
        member_id=member.id,
        refresh_token=tokens["refresh_token"],
        google_sub=tokens.get("google_sub") or "",
        google_email=tokens.get("google_email") or "",
        scope=tokens.get("scope") or "",
    )

    for slug in RESERVED_SLUGS:
        db.add(
            Label(
                family_id=family.id,
                slug=slug,
                display_name=RESERVED_DISPLAY_NAMES.get(slug, slug),
            )
        )
    db.flush()

    if settings.AUTO_CREATE_SHOPPING_LIST_DEFAULT:
        shopping_note = Note(
            family_id=family.id, content="", pinned=True
        )
        db.add(shopping_note)
        db.flush()
        db.add(
            NoteLabel(
                note_id=shopping_note.id,
                family_id=family.id,
                label_slug="shopping-list",
            )
        )

    db.commit()

    device_token = auth_service.create_device_token(
        device_id=device.id, family_id=family.id
    )

    # Stash the JWT for the kiosk to poll. The QR-code pairing flow shows the
    # consent URL on the kiosk → user completes Google sign-in on their phone
    # → callback runs in the phone's browser (this code path) → kiosk never
    # sees the redirect. The kiosk polls /api/pairing/status/<id> on a 2s loop
    # and the polling endpoint hands it this JWT once. Best-effort: if Redis
    # blips here we still 302 to /pair/complete?token=… so the legacy
    # "Use this device" fallback (kiosk does OAuth itself) still works.
    try:
        await redis.set(
            f"{PAIRING_DONE_KEY_PREFIX}{pairing_id}",
            device_token,
            ex=PAIRING_DONE_TTL_SECONDS,
        )
    except RedisError as exc:
        logger.warning(
            "pairing done-flag write failed for %s: %s", pairing_id, exc
        )

    # The query-string token remains for the fallback path (kiosk did OAuth
    # itself, so the kiosk's browser is the one landing on /pair/complete).
    # In the QR/phone path the phone lands here; the /pair/complete page
    # branches on a localStorage marker to avoid persisting the kiosk's JWT
    # into the phone's auth state.
    return RedirectResponse(
        url=f"{settings.FRONTEND_BASE_URL}/pair/complete?token={device_token}",
        status_code=status.HTTP_302_FOUND,
    )


async def _handle_connect_callback(
    *,
    state_id: str,
    code: str,
    db: Session,
    redis: Redis,
    oauth: GoogleOAuthService,
    crypto: CryptoService,
    settings: Settings,
    streamer: ChatStreamer,
    session_factory,
) -> RedirectResponse:
    member_id_raw = await redis.get(f"{CONNECT_STATE_KEY}{state_id}")
    if member_id_raw is None:
        raise HTTPException(status_code=400, detail="OAuth state expired")
    code_verifier = await redis.get(f"{CONNECT_VERIFIER_KEY}{state_id}")
    await redis.delete(f"{CONNECT_STATE_KEY}{state_id}")
    await redis.delete(f"{CONNECT_VERIFIER_KEY}{state_id}")

    member = db.query(Member).filter(Member.id == member_id_raw).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    tokens = oauth.exchange_code(code, code_verifier=code_verifier)
    if not tokens.get("refresh_token"):
        raise HTTPException(
            status_code=400,
            detail="Google did not return a refresh_token; re-consent is required",
        )

    google_tokens = GoogleTokenService(settings, db, redis, crypto)
    google_tokens.store(
        member_id=member.id,
        refresh_token=tokens["refresh_token"],
        google_sub=tokens.get("google_sub") or "",
        google_email=tokens.get("google_email") or "",
        scope=tokens.get("scope") or "",
    )

    # Notify the kiosk (and any other family-events subscriber) so the open
    # ConnectGoogleModal can dismiss itself and the member-row Google badge
    # can flip from "not_connected" to "connected" without a manual refresh.
    await streamer.publish_family_event(
        member.family_id,
        family_event_payload(
            type="member.google_connected",
            entity="members",
            id=member.id,
        ),
    )

    # Pull this member's Google Calendar immediately so their events appear
    # on the kiosk without waiting for the next polling cycle (5 min).
    try:
        await _pull_member(
            member_id=member.id,
            family_id=member.family_id,
            settings=settings,
            session_factory=session_factory,
            redis=redis,
            crypto=crypto,
            calendar=GoogleCalendarService(),
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; polling will retry
        logger.warning("immediate pull for member %s failed: %s", member.id, exc)

    google_email = tokens.get("google_email") or ""
    return RedirectResponse(
        url=(
            f"{settings.FRONTEND_BASE_URL}/connected"
            f"?member={quote(member.name)}"
            f"&email={quote(google_email)}"
        ),
        status_code=status.HTTP_302_FOUND,
    )

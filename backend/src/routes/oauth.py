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

from src.core.dependencies import (
    DeviceContext,
    get_auth_service,
    get_crypto_service,
    get_db,
    get_device_context,
    get_google_oauth_service,
    get_redis,
    get_settings,
)
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
from src.routes.pairing import PAIRING_KEY_PREFIX
from src.schemas.oauth import AuthorizeUrlResponse
from src.services.auth_service import AuthService
from src.services.crypto_service import CryptoService
from src.services.google_oauth_service import GoogleOAuthService
from src.services.google_token_service import GoogleTokenService
from src.services.logger import get_logger

router = APIRouter(prefix="/oauth/google", tags=["oauth"])
logger = get_logger("oauth")

DEFAULT_COLOR = "sage"
CONNECT_STATE_KEY = "oauth_connect:"
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
    try:
        await redis.set(
            f"{CONNECT_STATE_KEY}{state_id}",
            str(member.id),
            ex=CONNECT_STATE_TTL,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=503, detail="OAuth temporarily unavailable"
        ) from exc

    return AuthorizeUrlResponse(authorize_url=oauth.build_authorize_url(state=state))


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
    await redis.delete(f"{PAIRING_KEY_PREFIX}{pairing_id}")

    tokens = oauth.exchange_code(code)
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
    # v1 hardening trade-off (spec §11): the device token is delivered in the
    # URL query string so the SPA's `/pair/complete` page can grab it without a
    # backend session. Acceptable for a one-shot pairing redirect; the cookie
    # path is gone — frontend persists to localStorage + cookie itself.
    return RedirectResponse(
        url=f"/pair/complete?token={device_token}",
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
) -> RedirectResponse:
    member_id_raw = await redis.get(f"{CONNECT_STATE_KEY}{state_id}")
    if member_id_raw is None:
        raise HTTPException(status_code=400, detail="OAuth state expired")
    await redis.delete(f"{CONNECT_STATE_KEY}{state_id}")

    member = db.query(Member).filter(Member.id == member_id_raw).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    tokens = oauth.exchange_code(code)
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

    return RedirectResponse(
        url=(
            f"/settings?connected={member.id}"
            f"&email={tokens.get('google_email') or ''}"
        ),
        status_code=status.HTTP_302_FOUND,
    )

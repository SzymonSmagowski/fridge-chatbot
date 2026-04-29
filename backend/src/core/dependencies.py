from functools import lru_cache
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.orm import Session, sessionmaker

from src.core.context import current_actor
from src.core.settings import Settings
from src.db.postgres import Database
from src.db.shared_engine import get_session_factory
from src.llm_graphs.parent_router import ParentRouter
from src.services.auth_service import AuthService
from src.services.car_service import CarService
from src.services.chat_streaming import ChatStreamer
from src.services.crypto_service import CryptoService
from src.services.db_operations_service import DatabaseOperationsService
from src.services.event_service import EventService
from src.services.event_target_resolver import EventTargetResolver
from src.services.family_preferences_service import FamilyPreferencesService
from src.services.family_service import FamilyService
from src.services.google_calendar_service import GoogleCalendarService
from src.services.google_oauth_service import GoogleOAuthService
from src.services.google_token_service import GoogleTokenService
from src.services.label_service import LabelService
from src.services.llm_utils import LLMUtilsService
from src.services.member_service import MemberService
from src.services.note_service import NoteService
from src.services.redis_service import get_redis_client

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/pairing/start", auto_error=False)

_parent_router_instance: ParentRouter | None = None


# ---------------------------------------------------------------------------
# Core singletons
# ---------------------------------------------------------------------------
@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_db_service(settings: Settings = Depends(get_settings)) -> Database:
    return Database(settings)


def get_db(db_service: Database = Depends(get_db_service)) -> Session:
    with db_service.get_db() as session:
        yield session


def get_session_factory_dep(
    settings: Settings = Depends(get_settings),
) -> sessionmaker:
    return get_session_factory(settings)


def get_redis(settings: Settings = Depends(get_settings)) -> Redis:
    return get_redis_client(settings)


def get_auth_service(settings: Settings = Depends(get_settings)) -> AuthService:
    return AuthService(settings)


def get_db_operations_service(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> DatabaseOperationsService:
    return DatabaseOperationsService(settings, db)


@lru_cache
def get_llm_utils(settings: Settings = Depends(get_settings)) -> LLMUtilsService:
    return LLMUtilsService(settings)


def get_crypto_service(
    settings: Settings = Depends(get_settings),
) -> CryptoService:
    return CryptoService(settings)


def get_google_oauth_service(
    settings: Settings = Depends(get_settings),
) -> GoogleOAuthService:
    return GoogleOAuthService(settings)


def get_google_calendar_service() -> GoogleCalendarService:
    return GoogleCalendarService()


def get_google_token_service(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    crypto: CryptoService = Depends(get_crypto_service),
) -> GoogleTokenService:
    return GoogleTokenService(settings, db, redis, crypto)


def get_chat_streamer(redis: Redis = Depends(get_redis)) -> ChatStreamer:
    return ChatStreamer(redis)


# ---------------------------------------------------------------------------
# DeviceContext (D1) — extracted from the JWT, scopes every per-family service
# ---------------------------------------------------------------------------
class DeviceContext(BaseModel):
    device_id: UUID
    family_id: UUID


_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Missing or invalid device token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_device_context(
    token: str | None = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> DeviceContext:
    if not token:
        raise _credentials_exception
    payload = auth_service.decode_token(token)
    if payload.get("typ") != "device":
        raise _credentials_exception
    device_id = payload.get("sub")
    family_id = payload.get("family_id")
    if not device_id or not family_id:
        raise _credentials_exception
    try:
        ctx = DeviceContext(
            device_id=UUID(device_id), family_id=UUID(family_id)
        )
    except (ValueError, TypeError) as exc:
        raise _credentials_exception from exc

    # Stamp the per-request actor for downstream service-layer publishes (§6.6).
    # Idempotent — "rest" is the default — but explicit so a request leaving the
    # actor as "chat-tool" from a previous task on this thread is impossible.
    current_actor.set("rest")
    return ctx


# ---------------------------------------------------------------------------
# Per-family service factories
# ---------------------------------------------------------------------------
def get_family_service(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    streamer: ChatStreamer = Depends(get_chat_streamer),
) -> FamilyService:
    return FamilyService(db, ctx.family_id, streamer)


def get_family_preferences_service(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    streamer: ChatStreamer = Depends(get_chat_streamer),
) -> FamilyPreferencesService:
    return FamilyPreferencesService(db, ctx.family_id, streamer)


def get_member_service(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    streamer: ChatStreamer = Depends(get_chat_streamer),
) -> MemberService:
    return MemberService(db, ctx.family_id, streamer)


def get_car_service(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    streamer: ChatStreamer = Depends(get_chat_streamer),
) -> CarService:
    return CarService(db, ctx.family_id, streamer)


def get_label_service(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    streamer: ChatStreamer = Depends(get_chat_streamer),
) -> LabelService:
    return LabelService(db, ctx.family_id, streamer)


def get_note_service(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    streamer: ChatStreamer = Depends(get_chat_streamer),
) -> NoteService:
    return NoteService(db, ctx.family_id, label_service, streamer)


def get_event_target_resolver(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
) -> EventTargetResolver:
    return EventTargetResolver(db, ctx.family_id)


def get_event_service(
    ctx: DeviceContext = Depends(get_device_context),
    db: Session = Depends(get_db),
    resolver: EventTargetResolver = Depends(get_event_target_resolver),
    streamer: ChatStreamer = Depends(get_chat_streamer),
    calendar: GoogleCalendarService = Depends(get_google_calendar_service),
    token_service: GoogleTokenService = Depends(get_google_token_service),
) -> EventService:
    return EventService(
        db,
        ctx.family_id,
        resolver,
        streamer,
        calendar=calendar,
        token_service=token_service,
    )


# ---------------------------------------------------------------------------
# Parent router (chat) — unchanged
# ---------------------------------------------------------------------------
def initialize_parent_router(settings: Settings, db: Session) -> None:
    global _parent_router_instance
    if _parent_router_instance is None:
        db_ops = DatabaseOperationsService(settings, db)
        _parent_router_instance = ParentRouter(
            settings=settings, db_operations_service=db_ops
        )


async def get_parent_router() -> ParentRouter:
    if _parent_router_instance is None:
        raise RuntimeError("ParentRouter not initialized")
    return _parent_router_instance

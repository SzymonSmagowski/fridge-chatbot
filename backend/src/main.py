import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler  # noqa: F401 — kept for reference
from slowapi.errors import RateLimitExceeded

from src.core.dependencies import (
    get_db_service,
    get_parent_router,
    get_settings,
    initialize_parent_router,
)
from src.core.migrations import run_alembic_upgrade
from src.core.rate_limit import get_limiter, rate_limit_exceeded_handler
from src.db.shared_engine import get_session_factory
from src.routes import (
    auth,
    calendar_sync,
    cars,
    events,
    family,
    family_events_ws,
    labels,
    members,
    notes,
    oauth,
    pairing,
    threads,
    users,
)
from src.services.langfuse_service import LangfuseService
from src.services.langsmith_tracing import LangSmithTracing
from src.services.logger import get_logger
from src.services.redis_service import close_redis_client, get_redis_client
from src.workers.calendar_sync_worker import run_polling_loop

logger = get_logger("main")

_polling_task: asyncio.Task | None = None
_polling_stop: asyncio.Event | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _polling_task, _polling_stop

    settings = get_settings()

    if settings.AUTO_MIGRATE:
        await asyncio.to_thread(run_alembic_upgrade, settings)
    else:
        logger.info("AUTO_MIGRATE disabled; skipping Alembic upgrade")

    db_service = get_db_service(settings)
    # Schema is now Alembic-managed; init_db() is a no-op safety net for tests.
    db_service.init_db()

    LangfuseService.initialize(settings)
    LangSmithTracing.initialize(settings)

    with db_service.get_db() as db:
        initialize_parent_router(settings, db)

    redis = get_redis_client(settings)
    session_factory = get_session_factory(settings)
    _polling_stop = asyncio.Event()
    _polling_task = asyncio.create_task(
        run_polling_loop(
            settings=settings,
            session_factory=session_factory,
            redis=redis,
            stop_event=_polling_stop,
        )
    )

    try:
        yield
    finally:
        if _polling_stop is not None:
            _polling_stop.set()
        if _polling_task is not None:
            try:
                await asyncio.wait_for(_polling_task, timeout=2.0)
            except asyncio.TimeoutError:
                _polling_task.cancel()
                try:
                    await _polling_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

        parent_router = await get_parent_router()
        await parent_router.cleanup()
        await close_redis_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Fridge Chatbot API",
        description="FastAPI + LangGraph backend for the fridge chatbot.",
        version="0.2.0",
        lifespan=lifespan,
    )

    settings = get_settings()
    origins = settings.ALLOWED_ORIGINS_LIST
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiter (slowapi) — Redis-backed; counters shared across workers.
    app.state.limiter = get_limiter(settings)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Bare-path routers (excluded from the /api/ prefix per architecture §5.0):
    #  - /auth/*  legacy machinery for thread FKs, JWT clients depend on it
    #  - /oauth/* Google's redirect_uri is registered without /api/
    #  - /ws/*    WebSocket convention in this codebase is no /api/ prefix
    #  - /users, /threads — pre-existing chat surface kept stable
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(threads.router)
    app.include_router(oauth.router)
    app.include_router(family_events_ws.router)

    # Family-scoped REST routers — namespaced under /api/ per architecture §5.0
    app.include_router(pairing.router, prefix="/api")
    app.include_router(family.router, prefix="/api")
    app.include_router(members.router, prefix="/api")
    app.include_router(cars.router, prefix="/api")
    app.include_router(notes.router, prefix="/api")
    app.include_router(labels.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(calendar_sync.router, prefix="/api")

    @app.get("/health")
    def health_check():
        return {"status": "healthy", "service": "fridge-chatbot-backend"}

    return app


app = create_app()

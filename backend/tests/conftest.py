"""Top-level pytest fixtures for the fridge-chatbot backend test suite.

Discipline:
- Real Postgres (separate `dev_test` DB on the dev sidecar).
- Real Redis (test-prefixed keys + flush per session start).
- External HTTP boundaries (Google OAuth + Calendar) are mocked at the service
  layer via dependency overrides — never via real network calls.

The harness deliberately avoids mocking the DB or Redis because they are the
parts most likely to silently drift from the production code if mocked.
"""
from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timedelta
from typing import AsyncIterator, Iterator
from uuid import UUID, uuid4

import jwt
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# Test environment — set BEFORE importing settings so the Settings singleton
# loads with the test DB name.
# ---------------------------------------------------------------------------

os.environ.setdefault("POSTGRES_DB", "dev_test")
os.environ.setdefault("AUTO_MIGRATE", "false")  # we provision schema directly
os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key-for-pytest-must-be-at-least-32-bytes-long",
)
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("OPENAI_API_KEY", "")  # disables LLM init paths

from src.core.settings import Settings  # noqa: E402
from src.db.postgres import Base  # noqa: E402
import src.models  # noqa: E402, F401 — registers every table on Base.metadata
from src.models import (  # noqa: E402
    Device,
    Family,
    FamilyPreferences,
    User,
)


# ---------------------------------------------------------------------------
# pytest-asyncio configuration — every async test runs on its own loop, but we
# share one session-scoped loop for the engine/redis fixtures so they survive
# the whole run.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Settings + DB engine / schema lifecycle
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Shared Settings instance pointing at the dev_test database.

    Note: src.core.dependencies.get_settings is `lru_cache`-d. We override it
    via FastAPI's dependency_overrides so the route layer also sees this
    instance.
    """
    return Settings()


@pytest.fixture(scope="session")
def admin_engine() -> Engine:
    """Engine on the `postgres` maintenance DB used to create/drop test DB."""
    return create_engine(
        "postgresql+psycopg://postgres:postgres@postgres:5432/postgres",
        isolation_level="AUTOCOMMIT",
    )


@pytest.fixture(scope="session", autouse=True)
def provision_test_database(admin_engine: Engine, test_settings: Settings) -> Iterator[None]:
    """Drop + recreate the test DB once per session, then apply the schema."""
    db_name = test_settings.POSTGRES_DB
    with admin_engine.connect() as conn:
        # Terminate any leftover connections, drop, recreate.
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": db_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    # Apply schema via Base.metadata.create_all — fast and matches what models
    # produce. The migration test (tests/migrations/test_alembic.py) covers
    # Alembic up/down separately on a sandbox DB.
    engine = create_engine(test_settings.DATABASE_URL)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    yield
    # Teardown: drop the DB so a re-run starts clean.
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": db_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))


@pytest.fixture(scope="session")
def engine(test_settings: Settings) -> Iterator[Engine]:
    eng = create_engine(test_settings.DATABASE_URL, pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def truncate_db(engine: Engine) -> Iterator[None]:
    """Truncate every table after each test for isolation.

    Faster than rebuilding the schema; safe because tests don't run in
    parallel within one worker. Order matters only for sequences; TRUNCATE
    CASCADE handles FK chains.
    """
    yield
    with engine.connect() as conn:
        # Reflect tables in dependency-safe order using TRUNCATE … CASCADE.
        conn.execute(
            text(
                "TRUNCATE TABLE "
                + ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
                + " RESTART IDENTITY CASCADE"
            )
        )
        conn.commit()


@pytest.fixture
def db(session_factory: sessionmaker) -> Iterator[Session]:
    """Plain DB session for tests that touch the DB directly."""
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Redis lifecycle
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis_client(test_settings: Settings) -> AsyncIterator[AsyncRedis]:
    client = AsyncRedis.from_url(
        test_settings.REDIS_URL, encoding="utf-8", decode_responses=True
    )
    # Wipe any leftover state so cache-aside / pub-sub tests start clean.
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


# ---------------------------------------------------------------------------
# FastAPI app + TestClient with dependency overrides
# ---------------------------------------------------------------------------


@pytest.fixture
def app(test_settings: Settings, session_factory: sessionmaker, request):
    """Build a FastAPI app with the lifespan disabled and DB/Redis pinned to
    the test fixtures. Each test gets a fresh app so dependency_overrides do
    not leak across tests."""
    from contextlib import asynccontextmanager

    from src.main import create_app
    from src.core import dependencies as deps
    from src.services import redis_service as redis_module

    # Force the global Settings cache + Database cache + Redis cache to use
    # the test instance.
    deps.get_settings.cache_clear()
    deps.get_db_service.cache_clear()
    deps.get_llm_utils.cache_clear()
    # Reset the redis_service singleton — every test gets a brand-new Redis
    # client bound to the TestClient's portal event loop. Without this, a
    # client built on a prior (now-closed) loop raises "Event loop is closed".
    redis_module._client = None

    # No-op lifespan — we don't want migrations, Langfuse, ParentRouter, or
    # workers to run during tests.
    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    # Patch the lifespan before create_app reads it.
    import src.main as main_module
    original_lifespan = main_module.lifespan
    main_module.lifespan = _noop_lifespan
    try:
        application = create_app()
    finally:
        main_module.lifespan = original_lifespan

    # Override `get_db` so the route layer reads from the test session
    # factory.
    def _override_get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    application.dependency_overrides[deps.get_db] = _override_get_db
    application.dependency_overrides[deps.get_settings] = lambda: test_settings
    # Note: get_redis is NOT overridden here — it pulls from the
    # redis_service singleton, which we just reset above. The route handlers
    # therefore build a fresh client on the request thread's event loop.

    yield application
    application.dependency_overrides.clear()
    # Best-effort: close the singleton so its connection pool releases.
    try:
        client = redis_module._client
        if client is not None:
            try:
                import asyncio as _asyncio
                loop = _asyncio.new_event_loop()
                loop.run_until_complete(client.aclose())
                loop.close()
            except Exception:
                pass
    finally:
        redis_module._client = None


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Family / device / JWT factories
# ---------------------------------------------------------------------------


@pytest.fixture
def make_family(db: Session, test_settings: Settings):
    """Factory: create a fresh family + device + JWT.

    Returns a `(family_id, device_id, token)` tuple.
    """

    def _make(
        *,
        family_name: str = "Test Family",
        timezone: str = "Europe/Warsaw",
    ) -> tuple[UUID, UUID, str]:
        family = Family(name=family_name, timezone=timezone)
        db.add(family)
        db.flush()
        db.add(
            FamilyPreferences(
                family_id=family.id,
                sync_interval_sec=300,
                auto_create_shopping_list=True,
                updated_at=datetime.utcnow(),
            )
        )
        # Shadow user (legacy thread FK) — kept simple.
        shadow = User(
            username=f"device-{family.id.hex[:12]}",
            email=None,
            hashed_password="$2b$12$abcdefghijklmnopqrstuv",  # not verified in tests
            is_active=True,
        )
        db.add(shadow)
        db.flush()
        device = Device(
            family_id=family.id,
            label="Test Fridge",
            paired_at=datetime.utcnow(),
            shadow_user_id=shadow.id,
        )
        db.add(device)
        db.commit()
        db.refresh(family)
        db.refresh(device)

        token = _make_device_jwt(
            settings=test_settings,
            device_id=device.id,
            family_id=family.id,
        )
        return family.id, device.id, token

    return _make


@pytest.fixture
def family(make_family) -> tuple[UUID, UUID, str]:
    """Default family for tests that only need one."""
    return make_family()


@pytest.fixture
def auth_headers(family) -> dict[str, str]:
    _family_id, _device_id, token = family
    return {"Authorization": f"Bearer {token}"}


def _make_device_jwt(*, settings: Settings, device_id: UUID, family_id: UUID) -> str:
    payload = {
        "sub": str(device_id),
        "family_id": str(family_id),
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=settings.DEVICE_TOKEN_EXPIRE_DAYS),
        "typ": "device",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def make_jwt(test_settings: Settings):
    """Factory for crafting custom JWTs (mismatched family, wrong typ, etc.)."""

    def _make(
        *,
        device_id: UUID | None = None,
        family_id: UUID | None = None,
        typ: str = "device",
        expires_delta: timedelta | None = None,
        secret: str | None = None,
    ) -> str:
        payload: dict = {
            "sub": str(device_id or uuid4()),
            "family_id": str(family_id or uuid4()),
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + (expires_delta or timedelta(days=1)),
            "typ": typ,
        }
        return jwt.encode(
            payload,
            secret or test_settings.SECRET_KEY,
            algorithm=test_settings.JWT_ALGORITHM,
        )

    return _make


# ---------------------------------------------------------------------------
# Pub/sub helper — subscribe BEFORE write, then assert
# ---------------------------------------------------------------------------


class FamilyEventCollector:
    """Subscribe to `family:{id}:events` and collect frames.

    Use as a context manager: messages received during the block are stored
    on `.frames` after exit.
    """

    def __init__(self, redis: AsyncRedis, family_id: UUID) -> None:
        self.redis = redis
        self.family_id = family_id
        self.frames: list[dict] = []
        self._task: asyncio.Task | None = None
        self._pubsub = None
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()

    async def __aenter__(self) -> "FamilyEventCollector":
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(f"family:{self.family_id}:events")
        # Drain the subscribe-ack message so .listen() yields events only.
        self._task = asyncio.create_task(self._collect())
        # Give the subscriber a moment to be ready before returning.
        await asyncio.sleep(0.05)
        return self

    async def _collect(self) -> None:
        import json
        try:
            async for raw in self._pubsub.listen():
                if raw is None:
                    continue
                if raw.get("type") != "message":
                    continue
                data = raw.get("data")
                if data is None:
                    continue
                try:
                    self.frames.append(json.loads(data))
                except (TypeError, ValueError):
                    continue
                if self._stop.is_set():
                    return
        except asyncio.CancelledError:
            return

    async def wait_for(self, n: int = 1, timeout: float = 2.0) -> list[dict]:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if len(self.frames) >= n:
                return self.frames[:n]
            await asyncio.sleep(0.05)
        return self.frames

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                pass


@pytest_asyncio.fixture
async def family_event_collector(redis_client: AsyncRedis):
    """Returns a factory that builds a FamilyEventCollector for a given family."""

    def _make(family_id: UUID) -> FamilyEventCollector:
        return FamilyEventCollector(redis_client, family_id)

    return _make


# ---------------------------------------------------------------------------
# Convenience: short id for unique color tokens etc.
# ---------------------------------------------------------------------------


def _short_token() -> str:
    return secrets.token_hex(3)

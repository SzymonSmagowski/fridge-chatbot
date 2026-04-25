"""Shared database engine and session factory (singleton)."""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.settings import Settings

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_shared_engine(settings: Settings) -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.SQL_ECHO,
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return _engine


def get_session_factory(settings: Settings) -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_shared_engine(settings)
        )
    return _SessionLocal


@contextmanager
def get_db_session(settings: Settings) -> Generator[Session, None, None]:
    session = get_session_factory(settings)()
    try:
        yield session
    finally:
        session.close()

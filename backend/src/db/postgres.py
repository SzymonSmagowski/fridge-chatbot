from contextlib import contextmanager
from typing import Generator

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from src.core.settings import Settings
from src.db.shared_engine import get_session_factory, get_shared_engine

Base = declarative_base()


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = get_shared_engine(settings)
        self.SessionLocal = get_session_factory(settings)

    @contextmanager
    def get_db(self) -> Generator[Session, None, None]:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def init_db(self) -> None:
        Base.metadata.create_all(bind=self.engine)

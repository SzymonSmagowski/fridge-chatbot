"""Small debug helper — prints current User/Thread contents."""
from sqlalchemy.orm import Session

from src.models.database import Thread, User
from src.services.logger import get_logger

logger = get_logger("db_state")


def print_database_state(db: Session, title: str = "Database State") -> None:
    logger.info("=== %s ===", title)
    for u in db.query(User).all():
        logger.info("User id=%s username=%s email=%s active=%s", u.id, u.username, u.email, u.is_active)
    for t in db.query(Thread).all():
        logger.info("Thread id=%s uuid=%s user_id=%s title=%s", t.id, t.thread_id, t.user_id, t.title)

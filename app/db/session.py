import logging
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False},
    pool_size=50,
    max_overflow=50
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
logger = logging.getLogger(__name__)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        logger.info("Attempting to set SQLite PRAGMAs...")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout = 30000;")
        logger.info("SQLite PRAGMAs (journal_mode=WAL, foreign_keys=ON, busy_timeout=30000) set.")
    except Exception as e:
        logger.error(f"Failed to set SQLite PRAGMAs: {e}", exc_info=True)
    finally:
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        print("Session.py: Attempting to set PRAGMAs...")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout = 15000;")
        print("Session.py: SQLite PRAGMAs (journal_mode=WAL, foreign_keys=ON, busy_timeout=15000) set.")
    except Exception as e:
        print(f"Session.py: Failed to set SQLite PRAGMAs: {e}")
    finally:
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

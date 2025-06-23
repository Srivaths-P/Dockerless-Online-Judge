import os
import shutil
from typing import Generator, Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.main import app
from app.api.deps import get_db
from app.db.base_class import Base
from app.crud import crud_user
from app.schemas.user import UserCreate
from app.services import contest_service

TEST_DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    if os.path.exists("./test.db"):
        os.remove("./test.db")

    if os.path.exists("./test.db-shm"):
        os.remove("./test.db-shm")

    if os.path.exists("./test.db-wal"):
        os.remove("./test.db-wal")

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    yield

    if os.path.exists("./test.db"):
        os.remove("./test.db")

    if os.path.exists("./test.db-shm"):
        os.remove("./test.db-shm")

    if os.path.exists("./test.db-wal"):
        os.remove("./test.db-wal")


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, Any, None]:
    for table in reversed(Base.metadata.sorted_tables):
        with engine.connect() as connection:
            connection.execute(table.delete())
            connection.commit()

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, Any, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    del app.dependency_overrides[get_db]


@pytest.fixture(scope="session")
def test_server_data_path():
    test_data_dir = "test_server_data"
    contests_dir = os.path.join(test_data_dir, "contests")
    if os.path.exists(test_data_dir):
        shutil.rmtree(test_data_dir)
    os.makedirs(os.path.join(contests_dir, "test-contest-1", "add-two", "tests"), exist_ok=True)
    with open(os.path.join(contests_dir, "test-contest-1", "settings.json"), "w") as f:
        f.write('{"title": "Test Contest 1"}')
    with open(os.path.join(contests_dir, "test-contest-1", "add-two", "settings.json"), "w") as f:
        f.write(
            '{"title": "Add Two Numbers", "time_limit_sec": 1, "memory_limit_mb": 64, "allowed_languages": ["python", "c++"], "submission_cooldown_sec": 2}')
    with open(os.path.join(contests_dir, "test-contest-1", "add-two", "index.md"), "w") as f:
        f.write("Add two numbers A and B.")
    with open(os.path.join(contests_dir, "test-contest-1", "add-two", "tests", "sample.in"), "w") as f:
        f.write("2 3")
    with open(os.path.join(contests_dir, "test-contest-1", "add-two", "tests", "sample.out"), "w") as f:
        f.write("5")
    yield contests_dir
    shutil.rmtree(test_data_dir)


@pytest.fixture(scope="function", autouse=True)
def mock_contest_service_path(test_server_data_path, monkeypatch):
    monkeypatch.setattr(contest_service, "CONTESTS_PATH", test_server_data_path)
    contest_service.load_server_data()
    yield


@pytest.fixture(scope="function")
def test_user(db_session: Session):
    user_in = UserCreate(email="test@example.com")
    user = crud_user.user.create(db_session, obj_in=user_in)
    return user

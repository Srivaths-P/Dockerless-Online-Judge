import asyncio
from typing import AsyncGenerator, Generator

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.api.deps import get_db
from app.core.security import create_access_token
from app.crud import crud_user
from app.db.base_class import Base
from app.main import app
from app.schemas.user import UserCreate

# --- Test Database Setup ---
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Creates an instance of the default event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provides a clean database for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
async def client(db: Session) -> AsyncGenerator[AsyncClient, None]:
    """Provides an async test client with the db dependency overridden."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c
    del app.dependency_overrides[get_db]


@pytest.fixture
async def authenticated_client(client: AsyncClient, db: Session) -> AsyncClient:
    """
    Creates a test user in the DB and returns an authenticated client.
    This consolidated fixture solves session visibility issues.
    """
    # 1. Create the user directly in the database session for this test.
    user_in = UserCreate(email="test@example.com", password="password123")
    user = crud_user.user.create(db, obj_in=user_in)

    # 2. Create the token for that specific user.
    access_token = create_access_token(data={"sub": user.email})

    # 3. Set the authentication cookie on the client.
    client.cookies.set("access_token_cookie", access_token)

    return client

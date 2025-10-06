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
from app.db.models import User
from app.main import app
from app.schemas.user import UserCreate

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
async def client(db: Session) -> AsyncGenerator[AsyncClient, None]:
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c
    del app.dependency_overrides[get_db]


@pytest.fixture
def test_user(db: Session) -> User:
    user_in = UserCreate(email="test@example.com", password="password123")
    user = crud_user.user.create(db, obj_in=user_in)
    return user


@pytest.fixture
async def authenticated_client(client: AsyncClient, test_user: User) -> AsyncClient:
    access_token = create_access_token(data={"sub": test_user.email})
    client.cookies.set("access_token_cookie", access_token)
    return client

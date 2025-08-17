from typing import Generator, Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import crud_user
from app.db import models as db_models
from app.db.session import SessionLocal
from app.schemas.token import TokenData


def get_db() -> Generator:
    """
    Provides a database session for dependency injection in FastAPI routes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_user_cookie(
        request: Request, db: Session = Depends(get_db)
) -> db_models.User:
    """
    Reads and validates a JWT from a cookie. Used for API endpoints called by the UI.
    """
    token = request.cookies.get("access_token_cookie")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = crud_user.user.get_by_email(db, email=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_user_auth_cookie(
        current_user: db_models.User = Depends(get_user_cookie),
) -> db_models.User:
    """
    Checks if a user authenticated via cookie is active.
    """
    if not crud_user.user.is_active(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def verify_reload_token(
        auth: HTTPAuthorizationCredentials = Depends(HTTPBearer())
) -> bool:
    """
    Verifies the reload token provided in the Authorization header.
    """
    if not settings.ADMIN_RELOAD_TOKEN:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Reload key not configured.")

    if auth.scheme != "Bearer" or auth.credentials != settings.ADMIN_RELOAD_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing reload key",
        )
    return True

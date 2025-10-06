from typing import Generator, Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.auth import get_user_from_request
from app.core.config import settings
from app.crud import crud_user
from app.db import models as db_models
from app.db.session import SessionLocal


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_user_cookie(
        request: Request, db: Session = Depends(get_db)
) -> db_models.User:
    user = await get_user_from_request(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


async def get_user_auth_cookie(
        current_user: db_models.User = Depends(get_user_cookie),
) -> db_models.User:
    if not crud_user.user.is_active(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def verify_reload_token(
        auth: HTTPAuthorizationCredentials = Depends(HTTPBearer())
) -> bool:
    if not settings.ADMIN_RELOAD_TOKEN:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Reload key not configured.")

    if auth.scheme != "Bearer" or auth.credentials != settings.ADMIN_RELOAD_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing reload key",
        )
    return True

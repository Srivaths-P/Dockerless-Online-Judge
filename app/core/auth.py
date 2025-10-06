from typing import Optional

from fastapi import Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import crud_user
from app.db import models as db_models


async def get_user_from_request(request: Request, db: Session) -> Optional[db_models.User]:
    token = request.cookies.get("access_token_cookie")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            return None

        user = crud_user.user.get_by_email(db, email=username)
        if user and crud_user.user.is_active(user):
            return user
    except JWTError:
        return None
    return None

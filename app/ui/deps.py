from typing import Optional, List, Dict

from fastapi import Request, Depends
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import crud_user
from app.db import models as db_models
from app.db.session import get_db


async def get_current_user_from_cookie(
        request: Request, db: Session = Depends(get_db)
) -> Optional[db_models.User]:
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


def flash(request: Request, message: str, category: str = "info"):
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})


def get_flashed_messages(request: Request) -> List[Dict[str, str]]:
    messages = request.session.pop("_messages", [])
    return messages

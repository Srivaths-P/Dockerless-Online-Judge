from typing import Optional, List, Dict

from fastapi import Request, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_user_from_request
from app.db import models as db_models
from app.db.session import get_db


async def get_current_user_from_cookie(
        request: Request, db: Session = Depends(get_db)
) -> Optional[db_models.User]:
    """
    Retrieves the current user from the request cookie.
    Returns the user object if authenticated and active, otherwise None.
    """
    return await get_user_from_request(request, db)


def flash(request: Request, message: str, category: str = "info"):
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})


def get_flashed_messages(request: Request) -> List[Dict[str, str]]:
    messages = request.session.pop("_messages", [])
    return messages

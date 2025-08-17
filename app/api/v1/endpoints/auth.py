from typing import Any

from fastapi import APIRouter, Depends

from app.api import deps
from app.db import models as db_models
from app.schemas.user import UserPublic

router = APIRouter()


@router.get("/me", response_model=UserPublic)
async def read_users_me(
        current_user: db_models.User = Depends(deps.get_user_auth_cookie)
) -> Any:
    """
    Get current user information.
    """
    return current_user

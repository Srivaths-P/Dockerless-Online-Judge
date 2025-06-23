from typing import Any

from fastapi import APIRouter, Depends

from app.api import deps
from app.db import models as db_models
from app.schemas.user import User as UserSchema

router = APIRouter()


@router.get("/me", response_model=UserSchema)
async def read_users_me(
        current_user: db_models.User = Depends(deps.get_current_active_user_from_cookie)
) -> Any:
    return current_user

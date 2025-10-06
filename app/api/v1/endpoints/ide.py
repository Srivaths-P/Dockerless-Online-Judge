import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_user_auth_cookie, get_db
from app.db import models as db_models
from app.schemas.ide import IdeRunRequest, IdeRunResult
from app.services import ide_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/run", response_model=IdeRunResult)
async def run_ide_code(
        run_request: IdeRunRequest,
        current_user: db_models.User = Depends(get_user_auth_cookie),
        db: Session = Depends(get_db)
) -> IdeRunResult:
    try:
        result = await ide_service.run_ide_code_service(
            code=run_request.code,
            language=run_request.language,
            input_str=run_request.input_str,
            current_user=current_user,
            db=db
        )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"API Error running IDE code for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while running the code."
        )

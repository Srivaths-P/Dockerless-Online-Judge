import traceback
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user_from_cookie, get_db
from app.db import models as db_models
from app.sandbox.engine import run_sandboxed
from app.schemas.ide import IdeRunRequest, IdeRunResult

router = APIRouter()

IDE_TIME_LIMIT_SEC = 1
IDE_MEMORY_LIMIT_MB = 64
IDE_RUN_COOLDOWN_SEC = 3


@router.post("/run", response_model=IdeRunResult)
async def run_ide_code(
    run_request: IdeRunRequest,
    current_user: db_models.User = Depends(get_current_active_user_from_cookie),
    db: Session = Depends(get_db)
) -> IdeRunResult:
    now = datetime.now(timezone.utc)
    cooldown = timedelta(seconds=IDE_RUN_COOLDOWN_SEC)

    last_ide_run_at = current_user.last_ide_run_at
    if last_ide_run_at and last_ide_run_at.tzinfo is None:
        last_ide_run_at = last_ide_run_at.replace(tzinfo=timezone.utc)

    if last_ide_run_at and (now - last_ide_run_at) < cooldown:
        remaining = (last_ide_run_at + cooldown - now).total_seconds()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining:.1f} seconds before running code again."
        )

    try:
        current_user.last_ide_run_at = now
        db.add(current_user)
        db.commit()

        sandbox_result = await run_sandboxed(
            code=run_request.code,
            language=run_request.language,
            run_input=run_request.input_str,
            time_limit_sec=IDE_TIME_LIMIT_SEC,
            memory_limit_mb=IDE_MEMORY_LIMIT_MB,
            unit_name_prefix=f"ide-{current_user.id}"
        )
        return IdeRunResult(**sandbox_result.model_dump())
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"API Error running IDE code for user {current_user.email}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while running the code."
        )

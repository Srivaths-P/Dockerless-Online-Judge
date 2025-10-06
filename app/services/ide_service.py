import logging
import traceback
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import log_user_event
from app.db import models as db_models
from app.sandbox.engine import run_sandboxed
from app.schemas.ide import IdeRunResult

logger = logging.getLogger(__name__)


async def run_ide_code_service(
        code: str,
        language: str,
        input_str: str,
        current_user: db_models.User,
        db: Session
) -> IdeRunResult:
    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="ide_run_request",
                   details={"language": language, "code_length": len(code), "input_length": len(input_str)}
                   )

    now = datetime.now(timezone.utc)
    cooldown = timedelta(seconds=settings.IDE_RUN_COOLDOWN_SEC)

    last_ide_run_at = current_user.last_ide_run_at
    if last_ide_run_at and last_ide_run_at.tzinfo is None:
        last_ide_run_at = last_ide_run_at.replace(tzinfo=timezone.utc)

    if last_ide_run_at and (now - last_ide_run_at) < cooldown:
        remaining = (last_ide_run_at + cooldown - now).total_seconds()
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="ide_run_rate_limited",
                       details={"language": language, "remaining_wait_sec": remaining})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining:.1f} seconds before running code again."
        )

    try:
        current_user.last_ide_run_at = now
        db.merge(current_user)
        db.commit()
        db.refresh(current_user)

        sandbox_result = await run_sandboxed(
            code=code,
            language=language,
            run_input=input_str,
            time_limit_sec=settings.IDE_TIME_LIMIT_SEC,
            memory_limit_mb=settings.IDE_MEMORY_LIMIT_MB,
            unit_name_prefix=f"ide-{current_user.id}"
        )

        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type=f"ide_run_result",
                       details={
                           "language": language,
                           "sandbox_status": sandbox_result.status,
                           "exit_code": sandbox_result.exit_code,
                           "execution_time_ms": sandbox_result.execution_time_ms,
                           "memory_used_kb": sandbox_result.memory_used_kb,
                           "has_stdout": bool(sandbox_result.stdout),
                           "has_stderr": bool(sandbox_result.stderr),
                           "has_compilation_stderr": bool(sandbox_result.compilation_stderr)
                       })

        return IdeRunResult(**sandbox_result.model_dump())

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Service Error running IDE code for user {current_user.email}: {e}", exc_info=True)
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="ide_run_error",
                       details={"language": language, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request."
        )

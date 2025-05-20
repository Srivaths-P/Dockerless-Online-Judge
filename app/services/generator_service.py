import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging_config import log_user_event
from app.db import models as db_models
from app.sandbox.executor import run_generator_in_sandbox
from app.services.contest_service import get_problem_by_id

DEFAULT_GENERATOR_COOLDOWN_SEC = 10


async def generate_sample_testcase(
        db: Session,
        contest_id: str,
        problem_id: str,
        current_user: db_models.User
) -> Dict[str, Any]:
    print(f"Service: generate_sample_testcase called by user {current_user.email} for problem {problem_id}")

    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="generator_request",
                   details={"contest_id": contest_id, "problem_id": problem_id})

    problem = get_problem_by_id(contest_id, problem_id)
    if not problem:
        print(f"Service: Problem not found: {contest_id}/{problem_id}")
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="generator_problem_not_found",
                       details={"contest_id": contest_id, "problem_id": problem_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")

    if not problem.generator_code:
        print(f"Service: Generator code not found for problem {problem.id}")
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="generator_not_available",
                       details={"contest_id": contest_id, "problem_id": problem_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Test case generator not available for this problem.")

    now = datetime.now(timezone.utc)
    cooldown_sec = problem.generator_cooldown_sec if problem.generator_cooldown_sec is not None else DEFAULT_GENERATOR_COOLDOWN_SEC
    cooldown_period = timedelta(seconds=cooldown_sec)

    last_gen_at_aware = current_user.last_generation_at
    if last_gen_at_aware and last_gen_at_aware.tzinfo is None:
        last_gen_at_aware = last_gen_at_aware.replace(tzinfo=timezone.utc)

    if last_gen_at_aware and (now - last_gen_at_aware) < cooldown_period:
        remaining_wait = (last_gen_at_aware + cooldown_period - now).total_seconds()
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="generator_rate_limited",
                       details={"contest_id": contest_id, "problem_id": problem_id, "wait_seconds": remaining_wait})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining_wait:.1f} seconds before generating another test case."
        )

    try:
        current_user.last_generation_at = now
        db.merge(current_user)
        db.commit()

        generator_result = await run_generator_in_sandbox(
            problem_for_generator=problem,
            generator_language="python"
        )

        log_user_event(user_id=current_user.id, user_email=current_user.email,
                       event_type=f"generator_result_{generator_result.get('status', 'unknown')}",
                       details={
                           "contest_id": contest_id,
                           "problem_id": problem_id,
                           "execution_time_ms": generator_result.get("execution_time_ms"),
                           "memory_used_kb": generator_result.get("memory_used_kb"),
                           "has_input": generator_result.get("input") is not None,
                           "has_output": generator_result.get("output") is not None,
                           "has_error": generator_result.get("error") is not None,
                           "sandbox_status": generator_result.get("status")
                       })

        return generator_result

    except HTTPException as e:
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="generator_http_exception",
                       details={"contest_id": contest_id, "problem_id": problem_id, "detail": e.detail,
                                "status_code": e.status_code})
        raise e
    except Exception as e:
        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="generator_internal_error",
                       details={"contest_id": contest_id, "problem_id": problem_id, "error": str(e)})
        print(f"Service: Error running generator for {problem_id}: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to run test case generator.") from e

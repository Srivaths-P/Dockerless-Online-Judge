import logging
import os
import signal
import traceback
from typing import List, Dict, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_reload_token, get_user_auth_cookie
from app.db import models as db_models
from app.schemas.contest import Contest, ContestMinimal
from app.schemas.problem import ProblemPublic
from app.services import contest_service
from app.services import generator_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/reload", status_code=status.HTTP_202_ACCEPTED)
async def reload_contest_data(
        _: bool = Depends(verify_reload_token)
):
    if 'GUNICORN_PID' in os.environ:
        try:
            master_pid = os.getppid()
            logger.info(f"ADMIN ACTION: Gunicorn environment detected. Sending SIGHUP to master (PID: {master_pid}).")
            os.kill(master_pid, signal.SIGHUP)
            return {"message": "Graceful worker reload signal sent to Gunicorn master.", "method": "sighup"}
        except Exception as e:
            logger.error(f"API Error attempting to signal Gunicorn master: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to signal Gunicorn for reload. Check server logs."
            )
    else:
        try:
            logger.info("ADMIN ACTION: Non-Gunicorn environment detected. Reloading data in-memory.")
            contest_service.load_server_data()
            return {"message": "Contest data reloaded directly in memory.", "method": "direct_call"}
        except Exception as e:
            logger.error(f"API Error attempting to reload data directly: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reload contest data directly. Check server logs."
            )


@router.get("/", response_model=List[ContestMinimal])
async def read_contests(
        current_user: db_models.User = Depends(get_user_auth_cookie)):
    return contest_service.get_all_contests()


@router.get("/{contest_id}", response_model=Contest)
async def read_contest(contest_id: str,
                       current_user: db_models.User = Depends(get_user_auth_cookie)):
    contest = contest_service.get_contest_by_id(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    return contest


@router.get("/{contest_id}/problems/{problem_id}", response_model=ProblemPublic)
async def read_problem_details(
        contest_id: str,
        problem_id: str,
        current_user: db_models.User = Depends(get_user_auth_cookie)
):
    problem = contest_service.get_contest_problem(
        contest_id=contest_id, problem_id=problem_id
    )

    return ProblemPublic(
        **problem.model_dump(),
        generator_available=bool(problem.generator_code)
    )


@router.post("/{contest_id}/problems/{problem_id}/generate_testcase", response_model=Dict[str, Optional[str]])
async def generate_problem_testcase(
        contest_id: str,
        problem_id: str,
        db: Session = Depends(get_db),
        current_user: db_models.User = Depends(get_user_auth_cookie)
) -> Dict[str, Optional[str]]:
    try:
        contest_service.get_contest_problem(
            contest_id=contest_id, problem_id=problem_id
        )

        result = await generator_service.generate_sample_testcase(
            db=db,
            contest_id=contest_id,
            problem_id=problem_id,
            current_user=current_user
        )
        return {"input": result.get("input"), "output": result.get("output"), "error": result.get("error")}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"API Error generating test case for {problem_id}: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate test case.")

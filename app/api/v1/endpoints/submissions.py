import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db import models as db_models
from app.schemas.submission import SubmissionCreate, SubmissionPublic, SubmissionInfo
from app.services import contest_service, submission_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=SubmissionInfo, status_code=status.HTTP_202_ACCEPTED)
async def create_new_submission(
        submission_in: SubmissionCreate,
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_user_auth_cookie)
):
    contest_service.get_contest_problem(
        contest_id=submission_in.contest_id, problem_id=submission_in.problem_id
    )

    try:
        submission_info = await submission_service.create_submission(
            db=db,
            submission_data=submission_in,
            current_user=current_user
        )
        return submission_info
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"API Error creating submission: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process submission.")


@router.get("/{submission_id}", response_model=SubmissionPublic)
async def get_submission_details(
        submission_id: str,
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_user_auth_cookie)
):
    submission = submission_service.get_submission_by_id(db=db, submission_id=submission_id, current_user=current_user)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found or not authorized")
    return submission


@router.get("/", response_model=List[SubmissionInfo])
async def get_user_submissions_api(
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_user_auth_cookie)
):
    return submission_service.get_all_submissions_for_user(db=db, current_user=current_user)

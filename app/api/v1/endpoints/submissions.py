from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db import models as db_models
from app.schemas.submission import SubmissionCreate, Submission as SubmissionSchema, SubmissionInfo
from app.services import submission_service

router = APIRouter()


@router.post("/", response_model=SubmissionInfo, status_code=status.HTTP_202_ACCEPTED)
async def create_new_submission(
        submission_in: SubmissionCreate,
        background_tasks: BackgroundTasks,
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_current_active_user)
):
    try:
        submission_info = await submission_service.create_submission(
            db=db,
            submission_data=submission_in,
            current_user=current_user,
            background_tasks=background_tasks
        )
        return submission_info
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{submission_id}", response_model=SubmissionSchema)
async def get_submission_details(
        submission_id: str,
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_current_active_user)
):
    submission = submission_service.get_submission_by_id(db, submission_id, current_user)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found or not authorized")
    return submission


@router.get("/", response_model=List[SubmissionInfo])
async def get_user_submissions_api(
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_current_active_user)
):
    return submission_service.get_all_submissions_for_user(db, current_user)

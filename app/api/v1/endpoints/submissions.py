from typing import List

from fastapi import APIRouter, Depends, HTTPException, status  # Keep BackgroundTasks import if needed elsewhere
from sqlalchemy.orm import Session

# Adjust imports based on your project structure
from app.api import deps
from app.db import models as db_models
from app.schemas.submission import SubmissionCreate, Submission as SubmissionSchema, SubmissionInfo
from app.services import submission_service

router = APIRouter()


@router.post("/", response_model=SubmissionInfo, status_code=status.HTTP_202_ACCEPTED)
async def create_new_submission(
        submission_in: SubmissionCreate,
        # background_tasks: BackgroundTasks, # <- Remove this dependency if not used elsewhere in this function
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_current_active_user)
):
    """
    API endpoint to create a new submission.
    It calls the submission service which handles persistence and enqueuing.
    """
    try:
        # --- FIX: Remove the background_tasks argument from the call ---
        submission_info = await submission_service.create_submission(
            db=db,  # Pass the DB session
            submission_data=submission_in,  # Pass the submission data schema
            current_user=current_user  # Pass the authenticated user object
            # No background_tasks argument here anymore
        )
        # --- End of FIX ---
        return submission_info
    except ValueError as e:
        # Catch specific validation errors from the service if they are raised
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException as e:
        # Re-raise HTTPExceptions raised by the service (like 404 problem not found)
        raise e
    except Exception as e:
        # Catch unexpected errors during service call
        print(f"API Error creating submission: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process submission.")


@router.get("/{submission_id}", response_model=SubmissionSchema)
async def get_submission_details(
        submission_id: str,
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_current_active_user)
):
    """
    API endpoint to retrieve details of a specific submission.
    """
    submission = submission_service.get_submission_by_id(db=db, submission_id=submission_id, current_user=current_user)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found or not authorized")
    return submission


@router.get("/", response_model=List[SubmissionInfo])
async def get_user_submissions_api(
        db: Session = Depends(deps.get_db),
        current_user: db_models.User = Depends(deps.get_current_active_user)
):
    """
    API endpoint to retrieve a list of submissions for the current user.
    """
    return submission_service.get_all_submissions_for_user(db=db, current_user=current_user)

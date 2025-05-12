# In app/services/submission_service.py
import asyncio
import json
import uuid  # Import uuid
from typing import List # Ensure List is imported

from fastapi import HTTPException, Depends # Import Depends
from sqlalchemy.orm import Session

# Adjust these imports based on your project structure
from app.crud import crud_submission
from app.db import models as db_models
from app.db.session import get_db # Assuming get_db dependency provider
# Import the globally instantiated queue
from app.sandbox.executor import submission_processing_queue
from app.schemas.submission import (
    SubmissionCreate, SubmissionStatus, SubmissionInfo, TestCaseResult,
    Submission as SubmissionSchema # Alias to avoid naming conflict
)
from app.services.contest_service import get_problem_by_id


# Placeholder for getting the current user - replace with your actual dependency
# This dependency should be defined where your API/UI routes are, not necessarily here
# But keeping it here for the service function signature compatibility
async def get_current_active_user(db: Session = Depends(get_db)) -> db_models.User:
    # Replace with your actual user fetching logic based on token/session
    # This dummy implementation is just for type hinting and example
    user = db.query(db_models.User).filter(db_models.User.email == "asd@asd.com").first() # Example fetch
    if not user:
        # In a real app, you'd raise an authentication exception
        # print("Warning: get_current_active_user dummy function failed to find user 'asd@asd.com'")
        # As this is a placeholder, let's allow it to return None or raise a specific auth error
        # Assuming it *must* return a user for this service function to be called,
        # the authentication should happen *before* calling the service.
        # If called via a route dependency, the dependency handles the HTTPException.
        # If calling service directly, handle the None case or ensure user exists.
        # Raising HTTPException here aligns with FastAPI dependency pattern.
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def create_submission(
        db: Session, # Use Depends here as this is the service entry point from a route
        submission_data: SubmissionCreate,
        current_user: db_models.User = Depends(get_current_active_user) # Use Depends here
) -> SubmissionInfo:
    """
    Creates a new submission record, enqueues it for processing,
    and returns immediately.
    """
    print(f"Service: create_submission called by user {current_user.email} for problem {submission_data.problem_id}")

    # 1. Validate problem and language
    problem = get_problem_by_id(submission_data.contest_id, submission_data.problem_id)
    if not problem:
        print(f"Service: Problem not found: {submission_data.contest_id}/{submission_data.problem_id}")
        raise HTTPException(status_code=404, detail="Problem not found")
    if submission_data.language not in problem.allowed_languages:
        print(f"Service: Language '{submission_data.language}' not allowed for problem {problem.id}")
        raise HTTPException(status_code=400,
                            detail=f"Language {submission_data.language} not allowed for this problem.")

    # 2. Persist initial submission record using CRUD
    # The CRUD method now handles the commit internally
    try:
        print(f"Service: Calling crud_submission.submission.create_with_owner...")
        # The CRUD function signature expects `submitter_id: int`, ensure current_user.id is an int
        db_submission = crud_submission.submission.create_with_owner(
            db=db, obj_in=submission_data, submitter_id=current_user.id # Pass user ID (int)
        )
        # CRUD method handles commit and refresh now
        # db_submission.id is already populated after refresh in CRUD
        submission_id_str = str(db_submission.id) # Convert UUID (or string) to string for the queue
        print(f"Service: Submission record created by CRUD with ID: {submission_id_str[:8]}...")
    except Exception as e:
        print(f"Service: Database error during submission creation via CRUD: {type(e).__name__}: {e}")
        # No explicit rollback needed here if CRUD handles it, but re-raise
        # Convert specific DB errors to HTTPExceptions if desired
        import traceback
        traceback.print_exc() # Log the traceback from the database error
        # Raise a general 500 error for DB issues during creation
        raise HTTPException(status_code=500, detail=f"Failed to save submission record.") from e


    # 3. Enqueue submission for asynchronous processing
    # Use asyncio.create_task to run the enqueue operation in the background
    # without blocking the response. enqueue itself is quick (just adds to queue).
    # Pass the string ID from the committed db_submission object
    asyncio.create_task(submission_processing_queue.enqueue(submission_id_str))
    print(f"Service: Submission {submission_id_str[:8]} enqueued for processing.")

    # 4. Return initial submission info immediately
    # The status here will be the initial one set by the CRUD (e.g., PENDING)
    return SubmissionInfo(
        id=submission_id_str, # Use the string ID
        problem_id=db_submission.problem_id,
        contest_id=db_submission.contest_id,
        user_email=current_user.email, # Assuming User model has email
        language=db_submission.language,
        status=SubmissionStatus(db_submission.status), # Reflect initial status
        submitted_at=db_submission.submitted_at
    )


# Function to get submission details remains largely the same
def get_submission_by_id(
        db: Session,
        submission_id: str, # Expecting string UUID from path parameter
        current_user: db_models.User = Depends(get_current_active_user)
    ) -> SubmissionSchema:
    """
    Retrieves details for a specific submission owned by the current user.
    Uses the CRUD get method which handles the string ID.
    """
    print(f"Service: Fetching submission {submission_id} for user {current_user.email}")

    # Fetch submission using CRUD, passing the string ID.
    # The CRUD get method will handle any necessary UUID conversion or validation.
    db_submission = crud_submission.submission.get(db, id_=submission_id)


    if not db_submission:
        print(f"Service: Submission {submission_id} not found in DB.")
        raise HTTPException(status_code=404, detail="Submission not found.")

    # Check ownership (Assuming submitter_id in DB is int)
    if db_submission.submitter_id != current_user.id:
        print(f"Service: User {current_user.email} (ID: {current_user.id}) tried to access submission {submission_id} owned by user ID {db_submission.submitter_id}.")
        # Add logic here if admins have bypass rights
        raise HTTPException(status_code=403, detail="Not authorized to view this submission.")

    # Parse results_json (remains the same)
    parsed_results: List[TestCaseResult] = []
    if db_submission.results_json:
        try:
            results_list_of_dicts = json.loads(db_submission.results_json)
            if isinstance(results_list_of_dicts, list):
                # Validate each item is a dict before creating TestCaseResult
                parsed_results = [TestCaseResult(**res_dict) for res_dict in results_list_of_dicts if isinstance(res_dict, dict)]
            else:
                print(f"Warning: Service: results_json for submission {db_submission.id} is not a list: {type(results_list_of_dicts)}")
                parsed_results = [TestCaseResult(test_case_name="Result Parsing", status=SubmissionStatus.INTERNAL_ERROR, stderr="Invalid result format stored.")]
        except json.JSONDecodeError:
            print(f"Error decoding results_json for submission {db_submission.id}")
            parsed_results = [TestCaseResult(test_case_name="Result Parsing", status=SubmissionStatus.INTERNAL_ERROR, stderr="Failed to parse results JSON.")]
        except Exception as e: # Catch errors during Pydantic model creation
            print(f"Error creating TestCaseResult models for submission {db_submission.id}: {e}")
            parsed_results = [TestCaseResult(test_case_name="Result Processing", status=SubmissionStatus.INTERNAL_ERROR, stderr=f"Failed to process results: {e}")]


    # Ensure status is a valid enum member
    try:
        status_enum = SubmissionStatus(db_submission.status)
    except ValueError:
        print(f"Warning: Service: Invalid status value '{db_submission.status}' in DB for submission {db_submission.id}. Defaulting to INTERNAL_ERROR.")
        status_enum = SubmissionStatus.INTERNAL_ERROR

    return SubmissionSchema(
        id=str(db_submission.id), # Return string ID
        problem_id=db_submission.problem_id,
        contest_id=db_submission.contest_id,
        language=db_submission.language,
        code=db_submission.code,
        submitter_id=db_submission.submitter_id, # Return int ID as per model
        status=status_enum,
        results=parsed_results,
        submitted_at=db_submission.submitted_at
    )


# Function to get all submissions for a user remains largely the same
def get_all_submissions_for_user(
        db: Session = Depends(get_db),
        current_user: db_models.User = Depends(get_current_active_user)
    ) -> List[SubmissionInfo]:
    """
    Retrieves a list of all submissions made by the current user.
    """
    print(f"Service: Fetching all submissions for user {current_user.email} (ID: {current_user.id})")
    db_submissions = crud_submission.submission.get_multi_by_owner(
        db, submitter_id=current_user.id, skip=0, limit=100 # Add pagination later
    )

    submissions_info_list: List[SubmissionInfo] = []
    for sub in db_submissions:
        # Ensure status is a valid enum member
        try:
            status_enum = SubmissionStatus(sub.status)
        except ValueError:
            print(f"Warning: Service: Invalid status value '{sub.status}' in DB for submission {sub.id}. Defaulting to INTERNAL_ERROR.")
            status_enum = SubmissionStatus.INTERNAL_ERROR

        submissions_info_list.append(
            SubmissionInfo(
                id=str(sub.id), # Return string ID
                problem_id=sub.problem_id,
                contest_id=sub.contest_id,
                user_email=current_user.email, # Assuming User model has email
                language=sub.language or "N/A",
                status=status_enum,
                submitted_at=sub.submitted_at
            )
        )
    # Sort by submission time, newest first
    return sorted(submissions_info_list, key=lambda s: s.submitted_at, reverse=True)
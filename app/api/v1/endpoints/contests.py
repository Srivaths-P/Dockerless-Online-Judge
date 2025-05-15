from typing import List, Dict, Optional
import traceback # Import traceback

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db # Keep get_db
# Import the cookie-based dependency from the UI layer
from app.ui.deps import get_current_user_from_cookie
# Import db_models for type hinting
from app.db import models as db_models
# from app.schemas.user import User # Remove schema import if using db_models directly in endpoint sig

from app.schemas.contest import Contest, ContestMinimal
from app.schemas.problem import Problem
# Removed User schema import as we'll use db_models.User for the dependency return type

from app.services import contest_service
from app.services import generator_service # Import the new service

router = APIRouter()


@router.get("/", response_model=List[ContestMinimal])
# This endpoint still uses Bearer token auth via get_current_active_user from api.deps
# Assuming API endpoints should be Bearer token authenticated unless explicitly changed
async def read_contests(current_user: db_models.User = Depends(get_current_user_from_cookie)): # Changed dependency for UI consistency
    return contest_service.get_all_contests()


@router.get("/{contest_id}", response_model=Contest)
async def read_contest(contest_id: str, current_user: db_models.User = Depends(get_current_user_from_cookie)): # Changed dependency
    contest = contest_service.get_contest_by_id(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    return contest


@router.get("/{contest_id}/problems/{problem_id}", response_model=Problem)
async def read_problem_details(
        contest_id: str,
        problem_id: str,
        current_user: db_models.User = Depends(get_current_user_from_cookie) # Changed dependency
):
    problem = contest_service.get_problem_by_id(contest_id, problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    return problem

# New Endpoint for Test Case Generation
@router.post("/{contest_id}/problems/{problem_id}/generate_testcase", response_model=Dict[str, Optional[str]])
async def generate_problem_testcase(
    contest_id: str,
    problem_id: str,
    db: Session = Depends(get_db),
    # Use the cookie-based UI authentication dependency
    current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)
) -> Dict[str, Optional[str]]:
    """
    Generates a sample test case for a problem using its generator code.
    Applies rate limiting. Returns generated input/output or an error.
    Requires UI cookie authentication.
    """
    # Explicitly check if user is authenticated via the cookie
    if current_user is None:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (cookie missing or invalid)"
        )

    try:
        # Pass the db_models.User object to the service
        result = await generator_service.generate_sample_testcase(
             db=db,
             contest_id=contest_id,
             problem_id=problem_id,
             current_user=current_user
        )
        # Generator service returns {'input': ..., 'output': ..., 'error': ..., 'status': ...}
        # API endpoint schema is Dict[str, Optional[str]], so return only input/output/error
        return {"input": result.get("input"), "output": result.get("output"), "error": result.get("error")}

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"API Error generating test case for {problem_id}: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate test case.")
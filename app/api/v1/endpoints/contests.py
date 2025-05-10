from typing import List

from fastapi import APIRouter, HTTPException, Depends, status

from app.api.deps import get_current_active_user
from app.schemas.contest import Contest, ContestMinimal
from app.schemas.problem import Problem
from app.schemas.user import User
from app.services import contest_service

router = APIRouter()


@router.get("/", response_model=List[ContestMinimal])
async def read_contests(current_user: User = Depends(get_current_active_user)):
    return contest_service.get_all_contests()


@router.get("/{contest_id}", response_model=Contest)
async def read_contest(contest_id: str, current_user: User = Depends(get_current_active_user)):
    contest = contest_service.get_contest_by_id(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    return contest


@router.get("/{contest_id}/problems/{problem_id}", response_model=Problem)
async def read_problem_details(
        contest_id: str,
        problem_id: str,
        current_user: User = Depends(get_current_active_user)
):
    problem = contest_service.get_problem_by_id(contest_id, problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    return problem

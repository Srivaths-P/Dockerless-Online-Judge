from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.status import HTTP_404_NOT_FOUND, HTTP_303_SEE_OTHER

from app.core.logging_config import log_user_event
from app.crud import crud_submission
from app.db import models as db_models
from app.db.session import get_db
from app.services import contest_service
from app.ui.deps import get_current_user_from_cookie, flash

router = APIRouter()


def get_contest_status(contest: contest_service.ContestMinimal):
    now = datetime.now(timezone.utc)
    if not contest.start_time:
        return "Active", "Active"

    # --- START OF NEW, UNIFIED LOGIC ---
    def format_timedelta(td: timedelta, prefix: str) -> str:
        """Helper function to format time remaining in a consistent way."""
        seconds = int(td.total_seconds())

        days = seconds // 86400
        if days > 365:
            years = days // 365
            return f"{prefix} in ~{years} year(s)"
        if days > 1:
            hours = (seconds % 86400) // 3600
            return f"{prefix} in {days}d {hours}h"

        hours = seconds // 3600
        if hours > 0:
            minutes = (seconds % 3600) // 60
            return f"{prefix} in {hours}h {minutes}m"

        minutes = seconds // 60
        if minutes > 0:
            secs = seconds % 60
            return f"{prefix} in {minutes}m {secs}s"

        return f"{prefix} in {seconds}s"

    if now < contest.start_time:
        return "Upcoming", format_timedelta(contest.start_time - now, "Starts")

    if contest.duration_minutes is not None:
        end_time = contest.start_time + timedelta(minutes=contest.duration_minutes)
        if now < end_time:
            return "Active", format_timedelta(end_time - now, "Ends")
        else:
            return "Ended", "Ended"

    return "Active", "Active"


@router.get("/", response_class=HTMLResponse, name="ui_list_contests")
async def list_contests(request: Request,
                        current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie),
                        db: Session = Depends(get_db)
                        ):
    if not current_user:
        flash(request, "Please login to view contests.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    all_contests = contest_service.get_all_contests()

    upcoming_contests = []
    active_contests = []
    ended_contests = []

    for contest in all_contests:
        category, status_str = get_contest_status(contest)
        contest_dict = contest.model_dump()
        contest_dict['status_str'] = status_str

        if category == "Upcoming":
            upcoming_contests.append(contest_dict)
        elif category == "Active":
            active_contests.append(contest_dict)
        else:
            ended_contests.append(contest_dict)

    upcoming_contests.sort(key=lambda c: c.get('start_time') or datetime.now(timezone.utc))
    active_contests.sort(key=lambda c: c.get('start_time') or datetime.now(timezone.utc), reverse=True)
    ended_contests.sort(key=lambda c: c.get('start_time') or datetime.now(timezone.utc), reverse=True)

    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="contest_list_view")

    from app.main import templates
    return templates.TemplateResponse("contests_list.html", {
        "request": request,
        "upcoming_contests": upcoming_contests,
        "active_contests": active_contests,
        "ended_contests": ended_contests,
        "current_user": current_user
    })


@router.get("/{contest_id}", response_class=HTMLResponse, name="ui_contest_detail")
async def contest_detail(request: Request, contest_id: str,
                         current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie),
                         db: Session = Depends(get_db)
                         ):
    if not current_user:
        flash(request, "Please login to view contest details.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    contest = contest_service.get_contest_by_id(contest_id)
    if not contest:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Contest not found")

    contest_dict = contest.model_dump()
    category, status_str = get_contest_status(contest)
    contest_dict['status_str'] = status_str
    contest_dict['category'] = category

    is_upcoming = category == "Upcoming"

    if not is_upcoming:
        user_submissions = crud_submission.submission.get_user_submissions_for_contest(
            db, submitter_id=current_user.id, contest_id=contest_id
        )

        problem_statuses = {}
        for sub in user_submissions:
            if sub.status == "ACCEPTED":
                problem_statuses[sub.problem_id] = "ACCEPTED"
            elif sub.problem_id not in problem_statuses:
                problem_statuses[sub.problem_id] = "ATTEMPTED"

        for problem in contest_dict["problems"]:
            problem["user_status"] = problem_statuses.get(problem["id"], None)
    else:
        contest_dict["problems"] = []

    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="contest_view",
                   details={"contest_id": contest_id})

    from app.main import templates
    return templates.TemplateResponse("contest_detail.html",
                                      {"request": request, "contest": contest_dict, "current_user": current_user})


@router.get("/{contest_id}/problems/{problem_id}", response_class=HTMLResponse, name="ui_problem_detail")
async def problem_detail(request: Request, contest_id: str, problem_id: str,
                         current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie),
                         db: Session = Depends(get_db)
                         ):
    if not current_user:
        flash(request, "Please login to view problem details.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    try:
        problem = contest_service.check_contest_access_and_get_problem(
            contest_id=contest_id, problem_id=problem_id, allow_ended=True
        )
    except HTTPException as e:
        flash(request, str(e.detail), "danger")
        return RedirectResponse(url=request.url_for("ui_contest_detail", contest_id=contest_id),
                                status_code=HTTP_303_SEE_OTHER)

    contest = contest_service.get_contest_by_id(contest_id)

    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="problem_view",
                   details={"contest_id": contest_id, "problem_id": problem_id})

    from app.main import templates
    return templates.TemplateResponse("problem_detail.html", {
        "request": request,
        "problem": problem,
        "contest_id": contest_id,
        "contest_title": contest.title if contest else contest_id,
        "current_user": current_user,
        "generator_available": problem.generator_code is not None
    })

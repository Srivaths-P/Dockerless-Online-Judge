from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.status import HTTP_404_NOT_FOUND, HTTP_303_SEE_OTHER

from app.db import models as db_models
from app.db.session import get_db
from app.schemas.submission import SubmissionCreate
from app.services import submission_service
from app.ui.deps import get_current_user_from_cookie, flash

router = APIRouter()


@router.post("/contests/{contest_id}/problems/{problem_id}", name="ui_handle_submission")
async def handle_submission(
        request: Request, contest_id: str, problem_id: str,
        background_tasks: BackgroundTasks, db: Session = Depends(get_db),
        language: str = Form(...), code: str = Form(...),
        current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        flash(request, "Please login to submit.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    submission_data = SubmissionCreate(
        problem_id=problem_id, contest_id=contest_id, language=language, code=code
    )
    try:
        submission_info = await submission_service.create_submission(
            db=db, submission_data=submission_data,
            current_user=current_user, background_tasks=background_tasks
        )
        flash(request, f"Submission {submission_info.id} received!", "success")
        return RedirectResponse(url=request.url_for("ui_submission_detail", submission_id=submission_info.id),
                                status_code=HTTP_303_SEE_OTHER)
    except ValueError as e:
        flash(request, f"Submission error: {str(e)}", "danger")
        return RedirectResponse(url=request.url_for("ui_problem_detail", contest_id=contest_id, problem_id=problem_id),
                                status_code=HTTP_303_SEE_OTHER)


@router.get("/{submission_id}", response_class=HTMLResponse, name="ui_submission_detail")
async def submission_detail(
        request: Request, submission_id: str,
        db: Session = Depends(get_db),
        current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        flash(request, "Please login to view submission details.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    submission_pydantic = submission_service.get_submission_by_id(db, submission_id, current_user)
    if not submission_pydantic:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Submission not found or not authorized")

    from app.main import templates
    return templates.TemplateResponse("submission_detail.html", {"request": request, "submission": submission_pydantic,
                                                                 "current_user": current_user})


@router.get("/", response_class=HTMLResponse, name="ui_my_submissions")
async def my_submissions(
        request: Request, db: Session = Depends(get_db),
        current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        flash(request, "Please login to view your submissions.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    submissions_info = submission_service.get_all_submissions_for_user(db, current_user)
    from app.main import templates
    return templates.TemplateResponse("my_submissions.html", {"request": request, "submissions": submissions_info,
                                                              "current_user": current_user})

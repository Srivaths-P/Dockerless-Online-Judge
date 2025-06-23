from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette import status
from starlette.status import HTTP_303_SEE_OTHER

from app.core.logging_config import log_user_event
from app.core.templating import templates
from app.db import models as db_models
from app.db.session import get_db
from app.schemas.submission import SubmissionCreate
from app.services import submission_service
from app.ui.deps import get_current_user_from_cookie, flash

router = APIRouter()


@router.post("/contests/{contest_id}/problems/{problem_id}", name="ui_handle_submission")
async def handle_submission(
        request: Request,
        contest_id: str,
        problem_id: str,
        db: Session = Depends(get_db),
        language: str = Form(...),
        code: str = Form(...),
        current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        login_url = request.url_for("ui_login_form")
        next_url = request.url_for("ui_problem_detail", contest_id=contest_id, problem_id=problem_id)
        return RedirectResponse(url=f"{login_url}?next={next_url}", status_code=status.HTTP_303_SEE_OTHER)

    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="attempt_submission",
                   details={"contest_id": contest_id, "problem_id": problem_id,
                            "language": language, "code_length": len(code)})

    try:
        submission_info = await submission_service.create_submission(
            db=db,
            submission_data=SubmissionCreate(problem_id=problem_id, contest_id=contest_id, language=language,
                                             code=code),
            current_user=current_user
        )

        flash(request, f"Submission {submission_info.id[:8]}... received! Processing in background.", "success")
        return RedirectResponse(url=request.url_for("ui_submission_detail", submission_id=submission_info.id),
                                status_code=status.HTTP_303_SEE_OTHER)

    except HTTPException as e:
        flash(request, f"Submission error: {str(e.detail)}", "danger")
        return RedirectResponse(url=request.url_for("ui_problem_detail", contest_id=contest_id, problem_id=problem_id),
                                status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        log_user_event(user_id=current_user.id, user_email=current_user.email,
                       event_type="submission_failed_unexpected",
                       details={"contest_id": contest_id, "problem_id": problem_id,
                                "language": language, "error": str(e)})

        flash(request, f"An unexpected error occurred during submission: {str(e)}", "danger")
        print(f"ERROR during submission creation: {e}")
        import traceback
        traceback.print_exc()
        return RedirectResponse(url=request.url_for("ui_problem_detail", contest_id=contest_id, problem_id=problem_id),
                                status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{submission_id}", response_class=HTMLResponse, name="ui_submission_detail")
async def submission_detail(
        request: Request, submission_id: str,
        db: Session = Depends(get_db),
        current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        login_url = request.url_for("ui_login_form")
        return RedirectResponse(url=f"{login_url}?next={request.url.path}", status_code=HTTP_303_SEE_OTHER)

    try:
        submission = submission_service.get_submission_by_id(
            db=db,
            submission_id=submission_id,
            current_user=current_user
        )

        log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="view_submission_detail",
                       details={"submission_id": submission_id, "problem_id": submission.problem_id,
                                "contest_id": submission.contest_id, "status": submission.status.value})

        return templates.TemplateResponse("submission_detail.html",
                                          {"request": request, "submission": submission,
                                           "current_user": current_user})
    except HTTPException as e:
        raise e


@router.get("/", response_class=HTMLResponse, name="ui_my_submissions")
async def my_submissions(
        request: Request, db: Session = Depends(get_db),
        current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        login_url = request.url_for("ui_login_form")
        return RedirectResponse(url=f"{login_url}?next={request.url.path}", status_code=HTTP_303_SEE_OTHER)

    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="view_submission_list")

    submissions_info = submission_service.get_all_submissions_for_user(db, current_user)
    return templates.TemplateResponse("my_submissions.html", {"request": request, "submissions": submissions_info,
                                                              "current_user": current_user})

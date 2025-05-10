from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_303_SEE_OTHER

from app.db import models as db_models
from app.services import contest_service
from app.ui.deps import get_current_user_from_cookie, flash

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="ui_list_contests")
async def list_contests(request: Request,
                        current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)):
    if not current_user:
        flash(request, "Please login to view contests.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    contests = contest_service.get_all_contests()
    from app.main import templates
    return templates.TemplateResponse("contests_list.html",
                                      {"request": request, "contests": contests, "current_user": current_user})


@router.get("/{contest_id}", response_class=HTMLResponse, name="ui_contest_detail")
async def contest_detail(request: Request, contest_id: str,
                         current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)):
    if not current_user:
        flash(request, "Please login to view contest details.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    contest = contest_service.get_contest_by_id(contest_id)
    if not contest:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Contest not found")
    from app.main import templates
    return templates.TemplateResponse("contest_detail.html",
                                      {"request": request, "contest": contest, "current_user": current_user})


@router.get("/{contest_id}/problems/{problem_id}", response_class=HTMLResponse, name="ui_problem_detail")
async def problem_detail(request: Request, contest_id: str, problem_id: str,
                         current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)):
    if not current_user:
        flash(request, "Please login to view problem details.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    problem = contest_service.get_problem_by_id(contest_id, problem_id)
    if not problem:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Problem not found")
    from app.main import templates
    return templates.TemplateResponse("problem_detail.html", {
        "request": request, "problem": problem,
        "contest_id": contest_id, "current_user": current_user
    })

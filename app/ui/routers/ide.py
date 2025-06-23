from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status

from app.db import models as db_models
from app.ui.deps import get_current_user_from_cookie, flash
from app.sandbox.common import SUPPORTED_IDE_LANGUAGES
from app.main import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="ui_ide")
async def ide_page(
    request: Request,
    current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        flash(request, "Please login to use the IDE.", "warning")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse("ide.html", {
        "request": request,
        "current_user": current_user,
        "supported_languages": SUPPORTED_IDE_LANGUAGES
    })

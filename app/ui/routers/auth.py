# app/ui/routers/auth.py
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.status import HTTP_303_SEE_OTHER

from app.core.config import settings
from app.core.logging_config import log_user_event, log_audit_event
from app.core.security import create_access_token
from app.crud import crud_user
from app.db import models as db_models
from app.db.session import get_db
from app.ui.deps import flash, get_current_user_from_cookie
from app.core.templating import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse, name="ui_login_form")
async def login_form(request: Request, current_user: Optional[db_models.User] = Depends(get_current_user_from_cookie)):
    if current_user:
        return RedirectResponse(url=request.url_for("ui_home"), status_code=HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(request, "login.html", {"current_user": None})


@router.post("/login", name="ui_handle_login")
async def handle_login(
        request: Request, db: Session = Depends(get_db),
        email: str = Form(...), password: str = Form(...)
):
    user = crud_user.user.authenticate(db=db, email=email, password=password)

    if not user or not crud_user.user.is_active(user):
        log_user_event(None, email, "login_failed", {"reason": "Incorrect credentials or inactive account"})
        flash(request, "Incorrect email or password, or inactive account.", "danger")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    ip_address = request.client.host if request.client else "unknown"
    log_audit_event(username=user.email, ip_address=ip_address)

    log_user_event(user.id, user.email, "user_login_password")
    access_token = create_access_token(data={"sub": user.email})

    response = RedirectResponse(url=request.url_for("ui_home"), status_code=HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token_cookie", value=access_token, httponly=True,
        samesite="lax", secure=False, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    flash(request, "Login successful!", "success")
    return response


@router.get("/logout", name="ui_logout")
async def logout(request: Request, current_user: db_models.User = Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse(url=request.url_for("ui_home"), status_code=HTTP_303_SEE_OTHER)

    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="user_logout")

    flash(request, "You have been logged out.", "info")
    response = RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)
    request.session.clear()
    response.delete_cookie("access_token_cookie")
    return response

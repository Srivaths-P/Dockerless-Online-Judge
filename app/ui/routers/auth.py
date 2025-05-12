from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.status import HTTP_303_SEE_OTHER

from app.core.config import settings
from app.core.security import create_access_token
from app.crud import crud_user
from app.db.session import get_db
from app.schemas.user import UserCreate, User as UserSchema, UserBase
from app.ui.deps import flash, get_current_user_from_cookie

router = APIRouter()


@router.get("/login", response_class=HTMLResponse, name="ui_login_form")
async def login_form(request: Request, current_user: Optional[UserSchema] = Depends(get_current_user_from_cookie)):
    if current_user:
        return RedirectResponse(url=request.url_for("ui_home"), status_code=HTTP_303_SEE_OTHER)
    from app.main import templates
    return templates.TemplateResponse("login.html", {"request": request, "current_user": current_user})


@router.post("/login", name="ui_handle_login")
async def handle_login(
        request: Request, db: Session = Depends(get_db),
        username: str = Form(...), password: str = Form(...)
):
    user = crud_user.user.authenticate(db=db, email=username, password=password)
    if not user or not crud_user.user.is_active(user):
        flash(request, "Incorrect email or password, or inactive account.", "danger")
        return RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)

    access_token = create_access_token(data={"sub": user.email})
    response = RedirectResponse(url=request.url_for("ui_home"), status_code=HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token_cookie", value=access_token, httponly=True,
        samesite="lax", secure=False, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    flash(request, "Login successful!", "success")
    return response


@router.get("/register", response_class=HTMLResponse, name="ui_register_form")
async def register_form(request: Request, current_user: Optional[UserSchema] = Depends(get_current_user_from_cookie)):
    if current_user:
        return RedirectResponse(url=request.url_for("ui_home"), status_code=HTTP_303_SEE_OTHER)
    from app.main import templates
    return templates.TemplateResponse("register.html", {"request": request, "current_user": current_user})


@router.post("/register", name="ui_handle_register")
async def handle_register(
        request: Request, db: Session = Depends(get_db),
        email: str = Form(...), password: str = Form(...)
):
    try:
        UserBase(email=email)
    except ValidationError:
        flash(request, "Invalid email format.", "danger")
        return RedirectResponse(url=request.url_for("ui_register_form"), status_code=HTTP_303_SEE_OTHER)

    if crud_user.user.get_by_email(db=db, email=email):
        flash(request, "Email already registered.", "danger")
        return RedirectResponse(url=request.url_for("ui_register_form"), status_code=HTTP_303_SEE_OTHER)

    new_user = crud_user.user.create(db, obj_in=UserCreate(email=email, password=password))
    access_token = create_access_token(data={"sub": new_user.email})
    response = RedirectResponse(url=request.url_for("ui_home"), status_code=HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token_cookie", value=access_token, httponly=True,
        samesite="lax", secure=False, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    flash(request, "Registration successful! You are now logged in.", "success")
    return response


@router.get("/logout", name="ui_logout")
async def logout(request: Request):
    flash(request, "You have been logged out.", "info")
    response = RedirectResponse(url=request.url_for("ui_login_form"), status_code=HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token_cookie")
    return response

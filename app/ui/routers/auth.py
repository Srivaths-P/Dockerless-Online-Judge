from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.config import Config
from starlette.status import HTTP_303_SEE_OTHER

from app.core.config import settings
from app.core.logging_config import log_user_event
from app.core.security import create_access_token
from app.crud import crud_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.user import UserCreate
from app.ui.deps import flash, get_current_user_from_cookie

router = APIRouter()

config = Config('.env')
oauth = OAuth(config)

oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    client_kwargs={
        'scope': 'openid email profile'
    }
)


@router.get('/login', name='ui_login_form')
async def login(request: Request, current_user: User = Depends(get_current_user_from_cookie)):
    if current_user:
        return RedirectResponse(url=request.url_for("ui_home"))

    redirect_uri = request.url_for('auth_callback')

    next_url = request.query_params.get('next', str(request.url_for('ui_home')))
    request.session['next_url_after_login'] = next_url

    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get('/callback', name='auth_callback')
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    next_url = request.session.pop('next_url_after_login', str(request.url_for('ui_home')))

    try:
        token = await oauth.google.authorize_access_token(request)

        user_info = token.get('userinfo')
        if not user_info:
            flash(request, "Could not retrieve user information from Google.", "danger")
            return RedirectResponse(url=str(request.url_for("ui_home")), status_code=HTTP_303_SEE_OTHER)

        user_email = user_info.get('email')
        if not user_email:
            flash(request, "Email not provided by Google. Please ensure you grant email permissions.", "danger")
            return RedirectResponse(url=str(request.url_for("ui_home")), status_code=HTTP_303_SEE_OTHER)

        if settings.ALLOWED_EMAIL_DOMAINS:
            domain = user_email.split('@')[-1]
            if domain not in settings.ALLOWED_EMAIL_DOMAINS:
                log_user_event(None, user_email, "login_failed", {"reason": "Domain not allowed"})
                flash(request, "Access denied. Only users from allowed domains can log in.", "danger")
                return RedirectResponse(url=str(request.url_for("ui_home")), status_code=HTTP_303_SEE_OTHER)

        user = crud_user.user.get_by_email(db, email=user_email)
        if "_messages" in request.session:
            request.session.pop("_messages")

        if not user:
            user_in = UserCreate(email=user_email)
            user = crud_user.user.create(db, obj_in=user_in)
            log_user_event(user.id, user.email, "user_register_google")
            flash(request, "Account created and logged in successfully!", "success")
        else:
            if not user.is_active:
                log_user_event(user.id, user.email, "login_failed", {"reason": "Inactive user"})
                flash(request, "Your account is inactive. Please contact an administrator.", "danger")
                return RedirectResponse(url=str(request.url_for("ui_home")), status_code=HTTP_303_SEE_OTHER)
            log_user_event(user.id, user.email, "user_login_google")
            flash(request, "Login successful!", "success")

        access_token = create_access_token(data={"sub": user.email})
        response = RedirectResponse(url=next_url, status_code=HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="access_token_cookie", value=access_token, httponly=True,
            samesite="lax", secure=False, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

        return response

    except Exception as e:
        error_type = type(e).__name__
        error_str = str(e)
        if 'mismatching_state' in error_str or 'missing_state' in error_str:
            user_message = "Security token mismatch. Please try logging in again."
        else:
            user_message = error_str if error_str else "An unspecified authentication error occurred."

        log_detail = f"OAuth callback error: {error_type}: {user_message}"
        log_user_event(None, None, "login_failed", {"reason": log_detail})
        print(f"ERROR in auth_callback: {log_detail}")

        flash(request, f"An error occurred during login: {user_message}", "danger")
        return RedirectResponse(url=str(request.url_for("ui_home")), status_code=HTTP_303_SEE_OTHER)


@router.get("/logout", name="ui_logout")
async def logout(request: Request, current_user: User = Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse(url=str(request.url_for("ui_home")), status_code=HTTP_303_SEE_OTHER)
    log_user_event(user_id=current_user.id, user_email=current_user.email, event_type="user_logout")

    flash(request, "You have been logged out.", "info")

    response = RedirectResponse(url=str(request.url_for("ui_home")), status_code=HTTP_303_SEE_OTHER)
    request.session.clear()
    response.delete_cookie("access_token_cookie")
    return response

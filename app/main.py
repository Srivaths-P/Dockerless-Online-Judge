import os
import traceback
from datetime import datetime

import markdown
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.api import api_router as api_v1_router
from app.core.config import settings
from app.db.session import get_db
from app.services.contest_service import load_contests_on_startup
from app.ui.deps import get_current_user_from_cookie, get_flashed_messages
from app.ui.routers import auth as ui_auth_router
from app.ui.routers import contests as ui_contests_router
from app.ui.routers import submissions as ui_submissions_router

app = FastAPI(title="Online Judge")

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BASE_DIR, ".."))
STATIC_DIR = os.path.join(_PROJECT_ROOT, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print(f"Warning: Static directory not found at {STATIC_DIR}. Static files will not be served.")

TEMPLATES_DIR = os.path.join(_PROJECT_ROOT, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
if not os.path.exists(TEMPLATES_DIR):
    print(f"Error: Templates directory not found at {TEMPLATES_DIR}.")
templates.env.globals["get_flashed_messages"] = get_flashed_messages
templates.env.globals['G'] = {'datetime_class': datetime}


def markdown_filter(text):
    if text is None: return ""
    return markdown.markdown(text, extensions=['fenced_code', 'tables', 'sane_lists'])


templates.env.filters['markdown'] = markdown_filter

app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)


@app.on_event("startup")
async def startup_event():
    load_contests_on_startup()
    print("Contests loaded.")
    try:
        db = next(get_db())
        db.connection()
        print("Database connection successful on startup.")
        db.close()
    except Exception as e:
        print(f"Error connecting to database on startup: {e}")


app.include_router(api_v1_router, prefix="/api/v1", tags=["API"])
app.include_router(ui_auth_router.router, prefix="/auth", tags=["UI Auth"])
app.include_router(ui_contests_router.router, prefix="/contests", tags=["UI Contests"])
app.include_router(ui_submissions_router.router, prefix="/my_submissions", tags=["UI Submissions"])


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    print(f"HTTP Exception: {exc.status_code} for {request.url} - Detail: {exc.detail}")
    if exc.status_code == 404:
        try:
            db_session_gen = get_db()
            db = next(db_session_gen)
            current_user = await get_current_user_from_cookie(request, db=db)
            return templates.TemplateResponse(
                "404.html",
                {"request": request, "current_user": current_user, "detail": exc.detail},
                status_code=404
            )
        except Exception as template_error:
            print(f"Error rendering custom 404 page: {template_error}")
            traceback.print_exc()
        finally:
            if 'db' in locals() and db_session_gen:
                try:
                    db_session_gen.close()
                except Exception:
                    pass

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled Internal Server Error for {request.url}:")
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


@app.get("/", response_class=HTMLResponse, name="ui_home")
async def root_ui(request: Request, db: Session = Depends(get_db)):
    current_user = await get_current_user_from_cookie(request, db=db)
    return templates.TemplateResponse("home.html", {"request": request, "current_user": current_user})

import os
import traceback
from contextlib import asynccontextmanager
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
from app.sandbox.executor import submission_processing_queue
from app.services.contest_service import load_contests_on_startup
from app.ui.deps import get_current_user_from_cookie, get_flashed_messages
from app.ui.routers import auth as ui_auth_router
from app.ui.routers import contests as ui_contests_router
from app.ui.routers import submissions as ui_submissions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup sequence initiated...")
    print("Loading contests...")

    load_contests_on_startup()

    print("Contests loaded.")
    print("Starting submission queue workers...")

    try:
        await submission_processing_queue.start_workers()
        print("Submission queue workers started.")
    except RuntimeError as e:
        print(f"ERROR: Failed to start submission queue workers: {e}")
        traceback.print_exc()

    try:
        with next(get_db()) as db:
            db.connection()
            print("Database connection check successful during startup.")
    except Exception as e:
        print(f"WARNING: Database connection check failed during startup: {type(e).__name__}: {e}")

    print("Application startup complete. Ready to accept requests.")
    yield

    print("Application shutdown sequence initiated...")
    print("Stopping submission queue workers...")

    await submission_processing_queue.stop_workers()

    print("Submission queue workers stopped.")
    print("Application shutdown complete.")


app = FastAPI(
    title="Online Judge",
    lifespan=lifespan
)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BASE_DIR, ".."))

STATIC_DIR = os.path.join(_PROJECT_ROOT, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print(f"Warning: Static directory not found at {STATIC_DIR}. Static files will not be served.")

TEMPLATES_DIR = os.path.join(_PROJECT_ROOT, "templates")
if not os.path.exists(TEMPLATES_DIR):
    print(f"CRITICAL ERROR: Templates directory not found at {TEMPLATES_DIR}.")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

templates.env.globals["get_flashed_messages"] = get_flashed_messages
templates.env.globals['G'] = {'datetime_class': datetime}


def markdown_filter(text):
    if text is None: return ""
    return markdown.markdown(text, extensions=['fenced_code', 'tables', 'sane_lists', 'extra', 'codehilite'])


templates.env.filters['markdown'] = markdown_filter

app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)
app.include_router(api_v1_router, prefix="/api/v1", tags=["API"])
app.include_router(ui_auth_router.router, prefix="/auth", tags=["UI Auth"])
app.include_router(ui_contests_router.router, prefix="/contests", tags=["UI Contests"])
app.include_router(ui_submissions_router.router, prefix="/my_submissions", tags=["UI Submissions"])


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    print(f"HTTP Exception: {exc.status_code} for {request.url} - Detail: {exc.detail}")
    if exc.status_code == 404:
        try:
            return templates.TemplateResponse(
                "404.html",
                {"request": request, "current_user": None, "detail": exc.detail},
                status_code=404
            )
        except Exception as template_error:
            print(f"Error rendering custom 404 page: {template_error}")
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled Internal Server Error for {request.url}:")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )


@app.get("/", response_class=HTMLResponse, name="ui_home")
async def root_ui(request: Request, db: Session = Depends(get_db)):
    current_user = await get_current_user_from_cookie(request, db=db)
    return templates.TemplateResponse("home.html", {"request": request, "current_user": current_user})

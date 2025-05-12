# In app/main.py
import asyncio # Import asyncio
import os
import traceback
from contextlib import asynccontextmanager # Import asynccontextmanager
from datetime import datetime

import markdown
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

# --- Core App Imports ---
from app.core.config import settings
from app.db.session import get_db # Keep this if used elsewhere

# --- Service Imports ---
from app.services.contest_service import load_contests_on_startup

# --- Background Task Queue Import ---
# Import the globally instantiated queue from executor
from app.sandbox.executor import submission_processing_queue

# --- API Router Imports ---
from app.api.v1.api import api_router as api_v1_router

# --- UI Router Imports ---
from app.ui.deps import get_current_user_from_cookie, get_flashed_messages
from app.ui.routers import auth as ui_auth_router
from app.ui.routers import contests as ui_contests_router
from app.ui.routers import submissions as ui_submissions_router


# --- Lifespan Management for Background Tasks ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    print("Application startup sequence initiated...")

    # 1. Load contests (as before)
    print("Loading contests...")
    load_contests_on_startup()
    print("Contests loaded.")

    # 2. Start the submission queue workers
    print("Starting submission queue workers...")
    # Ensure the event loop is running before calling start_workers
    try:
        await submission_processing_queue.start_workers()
        print("Submission queue workers started.")
    except RuntimeError as e:
        print(f"ERROR: Failed to start submission queue workers: {e}")
        traceback.print_exc()
        # Depending on how critical the queue is, you might exit here or just warn

    # Optional: Database connection check (less critical now)
    try:
        # Create a short-lived session for a quick check
        with next(get_db()) as db:
             db.connection() # Check connection
             print("Database connection check successful during startup.")
    except Exception as e:
        print(f"WARNING: Database connection check failed during startup: {type(e).__name__}: {e}")
        # Decide if this should be a fatal error? Probably not.

    print("Application startup complete. Ready to accept requests.")
    yield # The application runs while in this yield block

    # ---- Shutdown ----
    print("Application shutdown sequence initiated...")

    # 1. Gracefully stop the submission queue workers
    print("Stopping submission queue workers...")
    await submission_processing_queue.stop_workers()
    print("Submission queue workers stopped.")

    print("Application shutdown complete.")


# --- FastAPI App Initialization ---
# Pass the lifespan manager to the FastAPI constructor
app = FastAPI(
    title="Online Judge",
    lifespan=lifespan # Register the lifespan context manager
)

# --- Static Files and Templates Setup ---
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BASE_DIR, ".."))

# Static files
STATIC_DIR = os.path.join(_PROJECT_ROOT, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print(f"Warning: Static directory not found at {STATIC_DIR}. Static files will not be served.")

# Templates
TEMPLATES_DIR = os.path.join(_PROJECT_ROOT, "templates")
if not os.path.exists(TEMPLATES_DIR):
    # This is likely a fatal error, consider raising an exception
    print(f"CRITICAL ERROR: Templates directory not found at {TEMPLATES_DIR}.")
    # raise RuntimeError(f"Templates directory not found: {TEMPLATES_DIR}") # Optional: make it fatal

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Template Globals & Filters
templates.env.globals["get_flashed_messages"] = get_flashed_messages
templates.env.globals['G'] = {'datetime_class': datetime}

def markdown_filter(text):
    if text is None: return ""
    # Added 'extra' for things like footnotes, abbreviations if needed later
    # Added 'codehilite' for syntax highlighting (requires Pygments installed)
    return markdown.markdown(text, extensions=['fenced_code', 'tables', 'sane_lists', 'extra', 'codehilite'])

templates.env.filters['markdown'] = markdown_filter

# --- Middleware ---
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)


# --- Include Routers ---
# API Routers
app.include_router(api_v1_router, prefix="/api/v1", tags=["API"])

# UI Routers
app.include_router(ui_auth_router.router, prefix="/auth", tags=["UI Auth"])
app.include_router(ui_contests_router.router, prefix="/contests", tags=["UI Contests"])
app.include_router(ui_submissions_router.router, prefix="/my_submissions", tags=["UI Submissions"])


# --- Exception Handlers ---
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    print(f"HTTP Exception: {exc.status_code} for {request.url} - Detail: {exc.detail}")
    if exc.status_code == 404:
        # Avoid creating a new DB session here if possible, adds complexity
        # Try to render without user-specific data or pass None if template handles it
        # Or rely on the generic JSON response for simplicity
        try:
            # Simplification: Render generic 404 without user context for handler
            return templates.TemplateResponse(
                "404.html",
                {"request": request, "current_user": None, "detail": exc.detail}, # Pass None for user
                status_code=404
            )
        except Exception as template_error:
             print(f"Error rendering custom 404 page: {template_error}")
             # Fallback to default JSON response
             return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # Handle other HTTP exceptions as JSON
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled Internal Server Error for {request.url}:")
    traceback.print_exc() # Log the full traceback to the console/logs
    # Return a generic error message to the client
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )


# --- Root Endpoint ---
@app.get("/", response_class=HTMLResponse, name="ui_home")
async def root_ui(request: Request, db: Session = Depends(get_db)):
    # This dependency injection handles DB session per request correctly
    current_user = await get_current_user_from_cookie(request, db=db)
    return templates.TemplateResponse("home.html", {"request": request, "current_user": current_user})
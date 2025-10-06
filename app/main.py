import logging
import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.templating import templates
from app.api.v1.api import api_router as api_v1_router
from app.core.config import settings
from app.db.session import get_db
from app.sandbox.executor import submission_processing_queue
from app.services import contest_service
from app.ui.deps import get_current_user_from_cookie, get_flashed_messages, flash
from app.ui.routers import auth as ui_auth_router
from app.ui.routers import contests as ui_contests_router
from app.ui.routers import submissions as ui_submissions_router
from app.ui.routers import ide as ui_ide_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup sequence initiated...")

    if 'GUNICORN_PID' not in os.environ:
        try:
            logger.info("ADMIN ACTION: Non-Gunicorn environment detected. Reloading data in-memory.")
            contest_service.load_server_data()
        except Exception as e:
            logger.error(f"Error attempting to reload data directly: {e}", exc_info=True)

    logger.info("Starting submission queue workers...")

    try:
        await submission_processing_queue.start_workers()
        logger.info("Submission queue workers started.")
    except RuntimeError as e:
        logger.error(f"Failed to start submission queue workers: {e}", exc_info=True)

    try:
        with next(get_db()) as db:
            db.connection()
            logger.info("Database connection check successful during startup.")
    except Exception as e:
        logger.warning(f"Database connection check failed during startup: {type(e).__name__}: {e}")

    logger.info("Application startup complete. Ready to accept requests.")
    yield

    logger.info("Application shutdown sequence initiated...")
    logger.info("Stopping submission queue workers...")

    await submission_processing_queue.stop_workers()

    logger.info("Submission queue workers stopped.")
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="DOJ",
    lifespan=lifespan
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BASE_DIR, ".."))

STATIC_DIR = os.path.join(_PROJECT_ROOT, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning(f"Static directory not found at {STATIC_DIR}. Static files will not be served.")

app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)
app.include_router(api_v1_router, prefix="/api/v1", tags=["API"])
app.include_router(ui_auth_router.router, prefix="/auth", tags=["UI Auth"])
app.include_router(ui_contests_router.router, prefix="/contests", tags=["UI Contests"])
app.include_router(ui_submissions_router.router, prefix="/my_submissions", tags=["UI Submissions"])
app.include_router(ui_ide_router.router, prefix="/ide", tags=["UI IDE"])


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"HTTP Exception: {exc.status_code} for {request.url} - Detail: {exc.detail}")

    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

    current_user = None
    try:
        db_session = next(get_db())
        current_user = await get_current_user_from_cookie(request, db=db_session)
    except Exception:
        db_session = None
    finally:
        if db_session:
            db_session.close()

    if exc.status_code == status.HTTP_404_NOT_FOUND:
        try:
            return templates.TemplateResponse(
                request,
                "404.html",
                {"current_user": current_user, "detail": exc.detail},
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as template_error:
            logger.error(f"Error rendering custom 404 page: {template_error}", exc_info=True)
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        flash(request, exc.detail or "Too many requests. Please wait.", "warning")
        referrer = request.headers.get("Referer")

        is_same_origin = False
        if referrer and request.url.hostname and request.url.port:
            from urllib.parse import urlparse
            ref_parsed = urlparse(referrer)
            if ref_parsed.hostname == request.url.hostname and ref_parsed.port == request.url.port:
                is_same_origin = True

        if is_same_origin:
            return RedirectResponse(url=referrer, status_code=status.HTTP_303_SEE_OTHER)
        else:
            return RedirectResponse(url=request.url_for("ui_home"), status_code=status.HTTP_303_SEE_OTHER)

    flash(request, f"Error {exc.status_code}: {exc.detail}", "danger")
    return RedirectResponse(url=request.url_for("ui_home"), status_code=status.HTTP_303_SEE_OTHER)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Internal Server Error for {request.url}:", exc_info=True)

    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred. Please try again later."}
        )
    else:
        flash(request, "An unexpected error occurred. Please try again later.", "danger")
        referrer = request.headers.get("Referer")
        is_same_origin = False
        if referrer and request.url.hostname and request.url.port:
            from urllib.parse import urlparse
            ref_parsed = urlparse(referrer)
            if ref_parsed.hostname == request.url.hostname and ref_parsed.port == request.url.port:
                is_same_origin = True

        if is_same_origin:
            return RedirectResponse(url=referrer, status_code=status.HTTP_303_SEE_OTHER)
        else:
            return RedirectResponse(url=request.url_for("ui_home"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/", response_class=HTMLResponse, name="ui_home")
async def root_ui(request: Request, db: Session = Depends(get_db)):
    current_user = await get_current_user_from_cookie(request, db=db)
    return templates.TemplateResponse(request, "home.html", {"current_user": current_user})

from fastapi import APIRouter

from app.api.v1.endpoints import auth, contests, submissions

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(contests.router, prefix="/contests", tags=["contests"])
api_router.include_router(submissions.router, prefix="/submissions", tags=["submissions"])

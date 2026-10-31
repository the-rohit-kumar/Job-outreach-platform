"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .db import SessionLocal, init_models
from .routers import (
    analytics,
    auth,
    extension,
    gmail,
    help as help_router,
    health,
    leads,
    manual_import,
    onboarding,
    pipeline,
    profile,
    review,
    settings_api,
    sources,
    stats,
    tokens,
    tracker,
)
from .seed import seed

logger = logging.getLogger("outreachhub")


def _startup() -> None:
    init_models()
    db = SessionLocal()
    try:
        seed(db)
        from .services import collector_runner

        collector_runner.sync_registry(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup()
    from . import scheduler

    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret,
    session_cookie=settings.session_cookie,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=False,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


ROUTERS = (
    health.router,
    auth.router,
    profile.router,
    onboarding.router,
    tokens.router,
    extension.router,
    sources.router,
    leads.router,
    pipeline.router,
    review.router,
    tracker.router,
    gmail.router,
    settings_api.router,
    stats.router,
    analytics.router,
    help_router.router,
    manual_import.router,
)
for router in ROUTERS:
    app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "docs": "/docs", "api": "/api"}

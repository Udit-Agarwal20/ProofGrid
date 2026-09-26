"""FastAPI main entrypoint for ProofGrid Core API service."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(service_name=settings.APP_NAME, log_level=settings.LOG_LEVEL)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown events."""
    logger.info(
        "ProofGrid API service starting",
        extra={
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "env": settings.APP_ENV,
        },
    )
    yield
    logger.info("ProofGrid API service shutting down")


app = FastAPI(
    title="ProofGrid API",
    description="Evidence-first data intelligence platform. LLM plans, code executes, evidence proves, PostgreSQL owns truth.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Correlation ID middleware
app.add_middleware(CorrelationIdMiddleware)

# Cross-Origin Resource Sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health/live",
    tags=["Health"],
    summary="Process Liveness Check",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
)
async def health_live() -> dict[str, Any]:
    """Check if the process is up and accepting HTTP traffic."""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get(
    "/health/ready",
    tags=["Health"],
    summary="Service Readiness Check",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
)
async def health_ready() -> dict[str, Any]:
    """Check if configuration has initialized successfully.

    (In Phase 1, database checks are deferred to Phase 2).
    """
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ready": True,
        "environment": settings.APP_ENV,
    }

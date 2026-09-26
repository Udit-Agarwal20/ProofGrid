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
from app.db.engine import dispose_async_engine
from app.db.health import check_database_health

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
    await dispose_async_engine()


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
)
async def health_ready() -> JSONResponse:
    """Check if the service and configured dependencies are ready for traffic."""
    response_payload: dict[str, Any] = {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "ready": True,
    }

    if settings.DATABASE_URL:
        db_health = await check_database_health()
        if db_health.status == "healthy":
            response_payload["database"] = {
                "status": "healthy",
                "latency_ms": db_health.latency_ms,
            }
        else:
            response_payload["status"] = "degraded"
            response_payload["ready"] = False
            response_payload["database"] = {
                "status": "unhealthy",
                "error": db_health.error,
            }
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=response_payload,
            )
    else:
        # Offline / unconfigured environment retains deterministic Phase 1 compatibility
        response_payload["database"] = {"status": "unconfigured"}

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_payload,
    )

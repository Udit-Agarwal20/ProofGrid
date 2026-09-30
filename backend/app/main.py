"""FastAPI main entrypoint for ProofGrid Core API service."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.exceptions import (
    AIProviderAuthenticationError,
    AIProviderBillingError,
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderMalformedOutputError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
)
from app.api.routes import router
from app.application.requirement_compiler.errors import (
    CompilerProviderError,
    CompilerValidationError,
)
from app.core.config import get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.errors import ProofGridError
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

app.include_router(router)


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's default errors include the submitted input. Never echo secrets or raw bodies.
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "REQUEST_INVALID",
                "message": "Request does not match the API contract.",
                "retryable": False,
                "correlation_id": getattr(request.state, "correlation_id", None),
                "fields": [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()],
            }
        },
    )


@app.exception_handler(ProofGridError)
async def product_error(request: Request, exc: ProofGridError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        },
    )


@app.exception_handler(CompilerValidationError)
async def compiler_validation_error(request: Request, exc: CompilerValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "correlation_id": getattr(request.state, "correlation_id", None),
                "code": "COMPILER_VALIDATION",
                "message": "The provider proposal failed deterministic validation.",
                "retryable": True,
            }
        },
    )


@app.exception_handler(AIProviderError)
async def ai_provider_error(request: Request, exc: AIProviderError) -> JSONResponse:
    categories = {
        AIProviderConfigurationError: ("PROVIDER_CONFIGURATION", False),
        AIProviderAuthenticationError: ("PROVIDER_AUTHENTICATION", False),
        AIProviderBillingError: ("PROVIDER_BILLING", False),
        AIProviderRateLimitError: ("PROVIDER_RATE_LIMIT", True),
        AIProviderTimeoutError: ("PROVIDER_TIMEOUT", True),
        AIProviderMalformedOutputError: ("PROVIDER_MALFORMED_OUTPUT", True),
    }
    code, retryable = categories.get(type(exc), ("PROVIDER_UNAVAILABLE", True))
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "correlation_id": getattr(request.state, "correlation_id", None),
                "code": code,
                "message": "The configured provider could not complete this request.",
                "retryable": retryable,
            }
        },
    )


@app.exception_handler(CompilerProviderError)
async def compiler_provider_error(request: Request, exc: CompilerProviderError) -> JSONResponse:
    cause = exc.__cause__
    return await ai_provider_error(
        request, cause if isinstance(cause, AIProviderError) else AIProviderError()
    )


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "correlation_id": getattr(request.state, "correlation_id", None),
                "code": "INTERNAL_ERROR",
                "message": "Request could not be completed.",
                "retryable": False,
            }
        },
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
        response_payload["database"] = {"status": "unconfigured"}
        response_payload["ready"] = False
        return JSONResponse(status_code=503, content=response_payload)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_payload,
    )

"""Correlation ID middleware for request tracing and structured logging."""

import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import set_correlation_id

CORRELATION_ID_HEADER = "X-Correlation-ID"
_VALID_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{8,64}$")


def is_valid_correlation_id(correlation_id: str | None) -> bool:
    """Validate whether an incoming correlation ID string is safe."""
    if not correlation_id:
        return False
    return bool(_VALID_ID_REGEX.match(correlation_id))


def generate_correlation_id() -> str:
    """Generate a clean RFC 4122 v4 correlation ID."""
    return str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that reads, generates, logs, and returns the correlation ID."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming_id = request.headers.get(CORRELATION_ID_HEADER)
        if incoming_id and is_valid_correlation_id(incoming_id):
            correlation_id = incoming_id
        else:
            correlation_id = generate_correlation_id()

        # Set into context variable for logging and request state for handlers
        set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id

        try:
            response = await call_next(request)
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            return response
        finally:
            # Clean up context for this task
            set_correlation_id(None)

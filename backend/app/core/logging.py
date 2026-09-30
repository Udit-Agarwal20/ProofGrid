"""Structured logging foundation carrying timestamp, level, service, message, and correlation_id.

No heavy external observability platforms. Clean, standard library logging interface.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# ContextVar for request-scoped correlation ID
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Retrieve the active correlation ID for the current context."""
    return correlation_id_ctx.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """Set the active correlation ID for the current context."""
    correlation_id_ctx.set(correlation_id)


SENSITIVE = re.compile(
    r"authorization|cookie|password|secret|api.?key|raw.?body|document.?content", re.I
)


def redact(value: Any, key: str = "") -> Any:
    if SENSITIVE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", value)
        value = re.sub(r"(://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        value = re.sub(
            r"(?i)((?:api[_-]?key|password|secret|token)=)[^&\s]+", r"\1[REDACTED]", value
        )
    return value


class StructuredJsonFormatter(logging.Formatter):
    """Format log records as structured JSON dictionaries."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "message": record.getMessage(),
            "logger": record.name,
            "correlation_id": get_correlation_id(),
        }

        # Include any extra structured attributes passed in extra={}
        for key, value in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "id",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ):
                log_data[key] = value

        if record.exc_info:
            log_data["exception_type"] = type(record.exc_info[1]).__name__

        return json.dumps(redact(log_data), default=str)


def configure_logging(service_name: str = "proofgrid-api", log_level: str = "INFO") -> None:
    """Configure the root logger with the structured formatter."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)
    for name in ("httpx", "httpcore", "groq", "google", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter(service_name=service_name))
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)

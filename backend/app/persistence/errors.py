"""Typed persistence error hierarchy and error sanitization for ProofGrid.

Ensures that database-level errors are translated into structured application exceptions
without leaking connection strings, passwords, or raw secrets.
"""

from __future__ import annotations

import re
from typing import Any

# Regex to detect connection strings like postgresql://user:pass@host:port/db
_DSN_SECRET_REGEX = re.compile(r"://([^:]+):([^@]+)@", re.IGNORECASE)
_PASSWORD_REGEX = re.compile(r"password=([^\s]+)", re.IGNORECASE)


def sanitize_error_message(message: str) -> str:
    """Mask credentials and sensitive connection parameters in error strings."""
    sanitized = _DSN_SECRET_REGEX.sub(r"://\1:***@", message)
    sanitized = _PASSWORD_REGEX.sub(r"password=***", sanitized)
    return sanitized


class PersistenceError(Exception):
    """Base exception for all persistence layer errors."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        safe_msg = sanitize_error_message(message)
        super().__init__(safe_msg)
        self.message = safe_msg
        self.original_error = original_error


class PersistenceNotFoundError(PersistenceError):
    """Raised when a requested persistent entity does not exist."""

    def __init__(self, entity_name: str, identifier: Any) -> None:
        super().__init__(f"{entity_name} with identifier '{identifier}' not found.")
        self.entity_name = entity_name
        self.identifier = identifier


class PersistenceConflictError(PersistenceError):
    """Raised when a unique constraint or idempotency conflict occurs."""

    def __init__(
        self,
        message: str,
        conflict_key: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, original_error)
        self.conflict_key = conflict_key


class PersistenceIntegrityError(PersistenceError):
    """Raised when a foreign key, check constraint, or data integrity rule is violated."""

    def __init__(
        self,
        message: str,
        constraint_name: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, original_error)
        self.constraint_name = constraint_name


class PersistenceConnectionError(PersistenceError):
    """Raised when database connectivity or connection pool operations fail."""

    pass


def translate_db_error(exc: Exception) -> PersistenceError:
    """Translate lower-level database exceptions into sanitized PersistenceErrors."""
    msg = sanitize_error_message(str(exc))
    lower_msg = msg.lower()

    if "unique constraint" in lower_msg or "duplicate key" in lower_msg:
        # Extract constraint name if present
        match = re.search(r'constraint "([^"]+)"', msg)
        constraint = match.group(1) if match else None
        return PersistenceConflictError(
            f"Unique constraint violation: {constraint or msg}",
            conflict_key=constraint,
            original_error=exc,
        )

    if "foreign key constraint" in lower_msg:
        match = re.search(r'constraint "([^"]+)"', msg)
        constraint = match.group(1) if match else None
        return PersistenceIntegrityError(
            f"Foreign key constraint violation: {constraint or msg}",
            constraint_name=constraint,
            original_error=exc,
        )

    if "check constraint" in lower_msg:
        match = re.search(r'constraint "([^"]+)"', msg)
        constraint = match.group(1) if match else None
        return PersistenceIntegrityError(
            f"Check constraint violation: {constraint or msg}",
            constraint_name=constraint,
            original_error=exc,
        )

    return PersistenceError(f"Database operation failed: {msg}", original_error=exc)

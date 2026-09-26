"""ProofGrid Database Package Foundation.

Exposes declarative base, engine management, session dependency, and health checks.
"""

from app.db import models
from app.db.base import Base
from app.db.engine import (
    create_engine_instance,
    dispose_async_engine,
    get_async_engine,
)
from app.db.health import DatabaseHealthResult, check_database_health
from app.db.session import get_db_session, get_session_factory

__all__ = [
    "Base",
    "DatabaseHealthResult",
    "check_database_health",
    "create_engine_instance",
    "dispose_async_engine",
    "get_async_engine",
    "get_db_session",
    "get_session_factory",
    "models",
]

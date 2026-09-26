"""SQLAlchemy 2.0 DeclarativeBase foundation.

Phase 2A establishes only the declarative metadata base.
ProofGrid business ORM models are strictly deferred to Phase 2B.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass

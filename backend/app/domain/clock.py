"""Clock boundary shared by domain contracts and application services."""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def __call__(self) -> datetime: ...


def utc_now() -> datetime:
    return datetime.now(UTC)

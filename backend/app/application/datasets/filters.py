"""Whitelisted typed comparisons shared by materialization and API validation."""

from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.contracts import RequirementSpec


def compare(value: Any, operator: str, expected: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict) and "amount" in value:
        if isinstance(expected, dict):
            if value.get("currency") != expected.get("currency"):
                return False
            expected = expected["amount"]
        value = value["amount"]
    if isinstance(value, dict) and "value" in value:
        value = value["value"]
    if operator == "in":
        return isinstance(expected, list) and value in expected
    if operator == "contains":
        return (
            expected in value
            if isinstance(value, list)
            else str(expected).casefold() in str(value).casefold()
        )
    try:
        left, right = Decimal(str(value)), Decimal(str(expected))
    except InvalidOperation:
        left, right = str(value).casefold(), str(expected).casefold()  # type: ignore[assignment]
    return {
        "eq": left == right,
        "neq": left != right,
        "gt": left > right,
        "gte": left >= right,
        "lt": left < right,
        "lte": left <= right,
    }.get(operator, False)


def matches_requirement(data: dict[str, Any], spec: RequirementSpec) -> bool:
    if any(
        not compare(data.get(rule.field_key), rule.operator, rule.value) for rule in spec.filters
    ):
        return False
    if spec.geography:
        location = str(
            data.get("headquarters") or data.get("location") or data.get("country") or ""
        )
        if not any(country.casefold() in location.casefold() for country in spec.geography):
            return False
    if spec.time_window:
        observed = data.get("funding_date") or data.get("announced_date") or data.get("date")
        if observed is None:
            return False
        observed = str(observed.get("value")) if isinstance(observed, dict) else str(observed)
        if spec.time_window.start and observed < spec.time_window.start:
            return False
        if spec.time_window.end and observed > spec.time_window.end:
            return False
    return True

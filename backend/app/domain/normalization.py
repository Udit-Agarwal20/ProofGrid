"""Typed deterministic normalization and field-specific material disagreement."""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class NormalizationError(ValueError):
    pass


def clean_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalized_name(value: str) -> str:
    name = re.sub(r"[^\w\s]", " ", clean_text(value).casefold())
    return re.sub(
        r"\s+(?:(?:private|pvt|limited|ltd|inc|llc|corp|corporation)\s*)+$", "", name
    ).strip()


def money(value: Any) -> dict[str, str]:
    if isinstance(value, float):
        raise NormalizationError("MONEY_FLOAT_REJECTED")
    if isinstance(value, dict):
        if isinstance(value.get("amount"), (bool, float)):
            raise NormalizationError("MONEY_FLOAT_REJECTED")
        amount = Decimal(str(value["amount"]))
        currency = str(value["currency"]).upper()
    else:
        text = clean_text(str(value)).upper().replace(",", "")
        currency = next(
            (
                code
                for token, code in [
                    ("US$", "USD"),
                    ("USD", "USD"),
                    ("$", "USD"),
                    ("INR", "INR"),
                    ("₹", "INR"),
                    ("EUR", "EUR"),
                    ("€", "EUR"),
                    ("GBP", "GBP"),
                    ("£", "GBP"),
                ]
                if token in text
            ),
            "",
        )
        if not currency:
            raise NormalizationError("MONEY_CURRENCY_MISSING")
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*(BILLION|MILLION|CRORE|LAKH|[BMK])?", text)
        if not match:
            raise NormalizationError("MONEY_AMOUNT_INVALID")
        amount = (
            Decimal(match[1])
            * {
                None: Decimal(1),
                "BILLION": Decimal("1e9"),
                "B": Decimal("1e9"),
                "MILLION": Decimal("1e6"),
                "M": Decimal("1e6"),
                "CRORE": Decimal("1e7"),
                "LAKH": Decimal("1e5"),
                "K": Decimal("1e3"),
            }[match[2]]
        )
    if not amount.is_finite() or amount < 0 or not re.fullmatch(r"[A-Z]{3}", currency):
        raise NormalizationError("MONEY_INVALID")
    return {"amount": format(amount, "f"), "currency": currency}


def normalize(value: Any, data_type: str) -> Any:
    if value is None or value == "":
        return None
    try:
        if data_type == "money":
            return money(value)
        if data_type == "number":
            if isinstance(value, (bool, float)):
                raise NormalizationError("NUMBER_INVALID")
            number = Decimal(str(value).replace(",", ""))
            if not number.is_finite():
                raise NormalizationError("NUMBER_INVALID")
            return format(number, "f")
        if data_type == "boolean":
            if isinstance(value, bool):
                return value
            if str(value).lower() in {"true", "yes", "1"}:
                return True
            if str(value).lower() in {"false", "no", "0"}:
                return False
            raise NormalizationError("BOOLEAN_INVALID")
        if data_type == "date":
            text = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", clean_text(str(value)))
            if re.fullmatch(r"\d{4}", text):
                date(int(text), 1, 1)
                return {"value": text, "precision": "year"}
            if re.fullmatch(r"\d{4}-\d{2}", text):
                date.fromisoformat(text + "-01")
                return {"value": text, "precision": "month"}
            try:
                return date.fromisoformat(text[:10]).isoformat()
            except ValueError:
                for fmt in ("%d %B %Y", "%B %d, %Y", "%d %b %Y", "%b %d, %Y"):
                    try:
                        return datetime.strptime(text, fmt).date().isoformat()
                    except ValueError:
                        continue
                raise NormalizationError("DATE_INVALID") from None
        if data_type == "url":
            parsed = urlsplit(str(value))
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise NormalizationError("URL_INVALID")
            return urlunsplit(
                (
                    parsed.scheme.lower(),
                    parsed.netloc.lower(),
                    parsed.path.rstrip("/"),
                    urlencode(
                        [(k, v) for k, v in parse_qsl(parsed.query) if not k.startswith("utm_")]
                    ),
                    "",
                )
            )
        if data_type == "entity_list":
            values = value if isinstance(value, list) else str(value).split(",")
            return sorted({clean_text(str(v)) for v in values if str(v).strip()}, key=str.casefold)
        if data_type == "location":
            text = clean_text(str(value))
            return re.sub(r"\bBangalore\b", "Bengaluru", text, flags=re.I)
        if data_type in {"entity_ref", "text"}:
            if not isinstance(value, str):
                raise NormalizationError("TEXT_INVALID")
            return clean_text(value)
        raise NormalizationError("TYPE_UNSUPPORTED")
    except (ValueError, TypeError, KeyError, InvalidOperation):
        raise NormalizationError("NORMALIZATION_FAILED") from None


def values_agree(left: Any, right: Any, data_type: str) -> bool:
    if data_type == "money":
        return left["currency"] == right["currency"] and Decimal(left["amount"]) == Decimal(
            right["amount"]
        )
    if data_type == "date":
        a = str(left.get("value")) if isinstance(left, dict) else str(left)
        b = str(right.get("value")) if isinstance(right, dict) else str(right)
        return a.startswith(b) or b.startswith(a)
    if data_type == "entity_list":
        return {normalized_name(str(x)) for x in left} == {normalized_name(str(x)) for x in right}
    if data_type in {"entity_ref", "location", "text"}:
        return normalized_name(str(left)) == normalized_name(str(right))
    return bool(left == right)

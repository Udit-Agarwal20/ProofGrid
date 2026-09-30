"""Resolve evidence against stored source representations, never model authority."""

import json
import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup

from app.domain.contracts import EvidenceAnchor
from app.domain.enums import EvidenceStatus


def normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("Invalid pointer")
    result = document
    for token in pointer[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise ValueError("Invalid escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(result, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError("Invalid index")
            result = result[int(token)]
        elif isinstance(result, dict):
            result = result[token]
        else:
            raise ValueError("Non-container pointer")
    return result


def verify_anchor(content: str, anchor: EvidenceAnchor, raw_value: Any) -> EvidenceAnchor:
    failed = anchor.model_copy(update={"verified": False, "status": EvidenceStatus.UNANCHORED})
    try:
        if anchor.anchor_type in {"JSON_POINTER", "API_RESPONSE_POINTER", "STRUCTURED_FIELD"}:
            pointer = anchor.json_pointer if anchor.json_pointer is not None else anchor.field_path
            if pointer is None:
                return failed
            representation = content
            if anchor.field_path and anchor.field_path.startswith("jsonld:"):
                index = int(anchor.field_path.split(":", 1)[1])
                if index < 0:
                    return failed
                representation = (
                    BeautifulSoup(content, "html.parser")
                    .select('script[type="application/ld+json"]')[index]
                    .get_text()
                )
            resolved = json_pointer(json.loads(representation), pointer)
            if type(resolved) is not type(raw_value) or resolved != raw_value:
                return failed
            return anchor.model_copy(
                update={"verified": True, "status": EvidenceStatus.JSON_POINTER}
            )
        if anchor.anchor_type == "DOM_SELECTOR":
            if not anchor.dom_selector:
                return failed
            nodes = BeautifulSoup(content, "html.parser").select(anchor.dom_selector)
            if len(nodes) != 1:
                return failed
            value = nodes[0].get_text(" ", strip=True)
            if normalized_text(value) != normalized_text(str(raw_value)) or (
                anchor.quote and normalized_text(anchor.quote) != normalized_text(value)
            ):
                return failed
            return anchor.model_copy(
                update={"verified": True, "status": EvidenceStatus.DOM_SELECTOR}
            )
        if anchor.field_path == "html_visible_text:v1":
            content = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
        quote = anchor.quote
        if not quote or normalized_text(str(raw_value)) not in normalized_text(quote):
            return failed
        offset = content.find(quote)
        if offset >= 0:
            return anchor.model_copy(
                update={
                    "verified": True,
                    "status": EvidenceStatus.EXACT,
                    "char_start": offset,
                    "char_end": offset + len(quote),
                }
            )
        # Preserve concrete offsets through Unicode expansion and whitespace folding.
        chars: list[str] = []
        positions: list[int] = []
        for index, character in enumerate(content):
            for normalized in unicodedata.normalize("NFKC", character):
                if normalized.isspace():
                    if chars and chars[-1] != " ":
                        chars.append(" ")
                        positions.append(index)
                else:
                    chars.append(normalized)
                    positions.append(index)
        text = "".join(chars)
        sought = normalized_text(quote)
        start = text.find(sought)
        if start >= 0 and sought:
            return anchor.model_copy(
                update={
                    "verified": True,
                    "status": EvidenceStatus.NORMALIZED,
                    "char_start": positions[start],
                    "char_end": positions[start + len(sought) - 1] + 1,
                }
            )
    except (ValueError, KeyError, IndexError, TypeError):
        return failed
    return failed

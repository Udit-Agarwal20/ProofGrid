"""Conservative identity decisions with inspectable features and hard vetoes."""

from typing import Any
from urllib.parse import urlsplit

from rapidfuzz.fuzz import ratio

from app.application.acquisition.safety import registrable_domain
from app.domain.normalization import normalized_name


def identity_decision(left: dict[str, Any], right: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    name_a, name_b = (
        normalized_name(str(left.get("name", ""))),
        normalized_name(str(right.get("name", ""))),
    )
    domain_a = registrable_domain(urlsplit(str(left.get("website", ""))).hostname or "")
    domain_b = registrable_domain(urlsplit(str(right.get("website", ""))).hostname or "")
    features: dict[str, Any] = {
        "name_similarity": ratio(name_a, name_b),
        "exact_domain": bool(domain_a and domain_a == domain_b),
        "exact_name": bool(name_a and name_a == name_b),
    }
    if left.get("legal_id") and right.get("legal_id") and left["legal_id"] != right["legal_id"]:
        return "KEEP_SEPARATE", {**features, "reason": "CONTRADICTORY_IDENTIFIERS"}
    if left.get("parent") or right.get("parent"):
        return "REVIEW", {**features, "reason": "PARENT_SUBSIDIARY_GUARD"}
    if features["exact_name"] and features["exact_domain"]:
        return "AUTO_MERGE", {**features, "reason": "EXACT_NAME_AND_DOMAIN"}
    if features["exact_domain"] or features["name_similarity"] >= 85:
        return "REVIEW", {**features, "reason": "IDENTITY_AMBIGUOUS"}
    return "KEEP_SEPARATE", {**features, "reason": "INSUFFICIENT_AGREEMENT"}

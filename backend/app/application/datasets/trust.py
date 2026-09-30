"""Conflict-aware canonicalization from verified source assertions."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from rapidfuzz.fuzz import ratio

from app.application.acquisition.safety import registrable_domain
from app.domain.contracts import TrustContract
from app.domain.normalization import values_agree


class TrustClaim(BaseModel):
    id: str
    value: Any
    domain: str
    content_hash: str
    document_text: str = ""
    first_party: bool = False
    verified: bool = False
    flags: list[str] = Field(default_factory=list)
    observed_at: datetime


def independent_count(claims: list[TrustClaim]) -> int:
    clusters: list[TrustClaim] = []
    for claim in claims:
        if any(
            registrable_domain(claim.domain) == registrable_domain(other.domain)
            or claim.content_hash == other.content_hash
            or (
                claim.document_text
                and other.document_text
                and ratio(claim.document_text, other.document_text) >= 95
            )
            for other in clusters
        ):
            continue
        clusters.append(claim)
    return len(clusters)


def canonicalize(
    claims: list[TrustClaim], data_type: str, contract: TrustContract, now: datetime
) -> dict[str, Any]:
    valid = [
        claim
        for claim in claims
        if claim.value is not None
        and claim.verified
        and not claim.flags
        and (contract.allow_secondary_sources or claim.first_party)
        and (
            contract.max_source_age_days is None
            or (now - claim.observed_at).total_seconds() <= contract.max_source_age_days * 86400
        )
    ]
    if not valid:
        return {
            "value": None,
            "status": "NEEDS_REVIEW" if claims else "MISSING",
            "selected_claim_id": None,
            "claim_ids": [c.id for c in claims],
            "independent_sources": 0,
            "reason": "NO_ELIGIBLE_EVIDENCE",
        }
    groups: list[list[TrustClaim]] = []
    for claim in valid:
        group = next(
            (
                group
                for group in groups
                if all(values_agree(claim.value, other.value, data_type) for other in group)
            ),
            None,
        )
        if group is None:
            groups.append([claim])
        else:
            group.append(claim)
    groups.sort(
        key=lambda group: (
            any(c.first_party for c in group) if contract.prefer_first_party else False,
            independent_count(group),
            max(c.observed_at for c in group),
        ),
        reverse=True,
    )
    selected = sorted(
        groups[0],
        key=lambda c: (
            c.first_party if contract.prefer_first_party else False,
            c.observed_at,
            c.id,
        ),
        reverse=True,
    )[0]
    count = independent_count(groups[0])
    if len(groups) > 1:
        status, reason = "CONFLICTING", "MATERIAL_DISAGREEMENT_PRESERVED"
    elif count < contract.minimum_independent_sources:
        status, reason = "NEEDS_REVIEW", "INDEPENDENT_SUPPORT_BELOW_CONTRACT"
    elif selected.first_party:
        status, reason = "VERIFIED", "FIRST_PARTY_AND_CONTRACT_SATISFIED"
    elif count >= 2:
        status, reason = "SUPPORTED", "INDEPENDENT_ANCHORED_AGREEMENT"
    elif contract.allow_single_source_output:
        status, reason = "SINGLE_SOURCE", "ONE_ANCHORED_SOURCE"
    else:
        status, reason = "NEEDS_REVIEW", "SINGLE_SOURCE_DISALLOWED"
    return {
        "value": selected.value,
        "status": status,
        "selected_claim_id": selected.id,
        "claim_ids": [c.id for c in claims],
        "independent_sources": count,
        "reason": reason,
        "conflicting_claim_ids": [c.id for group in groups[1:] for c in group],
    }

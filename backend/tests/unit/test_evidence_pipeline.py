from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.application.datasets.entities import identity_decision
from app.application.datasets.trust import TrustClaim, canonicalize
from app.application.extraction.evidence import verify_anchor
from app.domain.contracts import EvidenceAnchor, TrustContract
from app.domain.enums import EvidenceType
from app.domain.normalization import NormalizationError, money, normalize, values_agree


def test_verification_rejects_quote_without_value_and_hallucinated_quote() -> None:
    assert not verify_anchor(
        "Company raised $2M.",
        EvidenceAnchor(anchor_type=EvidenceType.TEXT_SPAN, quote="raised $4M"),
        "$4M",
    ).verified
    assert not verify_anchor(
        "Company raised $2M.",
        EvidenceAnchor(anchor_type=EvidenceType.TEXT_SPAN, quote="Company"),
        "$4M",
    ).verified
    assert verify_anchor(
        "Company raised $2M.",
        EvidenceAnchor(anchor_type=EvidenceType.TEXT_SPAN, quote="raised $2M"),
        "$2M",
    ).verified
    anchor = verify_anchor(
        "Company\n raised  $2M.",
        EvidenceAnchor(anchor_type=EvidenceType.NORMALIZED_TEXT_SPAN, quote="Company raised $2M."),
        "$2M",
    )
    assert anchor.verified and anchor.char_start == 0 and anchor.char_end == 21


def test_json_pointer_must_resolve_to_asserted_raw_value() -> None:
    anchor = EvidenceAnchor(anchor_type=EvidenceType.JSON_POINTER, json_pointer="/a~1b/0")
    assert verify_anchor('{"a/b":["$2M"]}', anchor, "$2M").verified
    assert not verify_anchor('{"a/b":["$2M"]}', anchor, "$3M").verified


def test_money_precision_currency_and_dates() -> None:
    assert money("USD 1.234567 million") == {"amount": "1234567", "currency": "USD"}
    assert Decimal(money("₹2 crore")["amount"]) == Decimal("20000000")
    with pytest.raises(NormalizationError):
        money(1.1)
    assert not values_agree(money("$2M"), money("INR 2M"), "money")
    assert values_agree(normalize("2026-05", "date"), normalize("2026-05-15", "date"), "date")


def test_trust_preserves_conflicts_and_rejects_syndicated_support() -> None:
    now = datetime(2026, 9, 30, tzinfo=UTC)
    a = TrustClaim(
        id="a",
        value=money("$2M"),
        domain="company.com",
        content_hash="a",
        first_party=True,
        verified=True,
        observed_at=now,
    )
    b = a.model_copy(
        update={
            "id": "b",
            "domain": "news.com",
            "value": money("$3M"),
            "content_hash": "b",
            "first_party": False,
        }
    )
    result = canonicalize([a, b], "money", TrustContract(), now)
    assert result["status"] == "CONFLICTING" and result["claim_ids"] == ["a", "b"]
    b = a.model_copy(update={"id": "b", "domain": "news.com"})
    assert (
        canonicalize([a, b], "money", TrustContract(minimum_independent_sources=2), now)["status"]
        == "NEEDS_REVIEW"
    )


def test_entity_negative_pairs_and_review_band() -> None:
    a = {"name": "Acme AI Pvt Ltd", "website": "https://acme.ai"}
    assert (
        identity_decision(a, {"name": "Acme AI", "website": "https://acme.ai"})[0] == "AUTO_MERGE"
    )
    assert (
        identity_decision(
            a, {"name": "Acme AI Labs", "website": "https://acme.ai", "parent": "Acme AI"}
        )[0]
        == "REVIEW"
    )
    assert identity_decision({**a, "legal_id": "1"}, {**a, "legal_id": "2"})[0] == "KEEP_SEPARATE"


def test_json_pointer_does_not_confuse_boolean_and_numeric_values() -> None:
    anchor = EvidenceAnchor(anchor_type=EvidenceType.JSON_POINTER, json_pointer="/value")
    assert not verify_anchor('{"value":1}', anchor, True).verified
    with pytest.raises(NormalizationError):
        money({"amount": 1.1, "currency": "USD"})


def test_jsonld_list_anchor_resolves_inside_named_script() -> None:
    source = '<script type="application/ld+json">{"founders":["Asha", "Vivek"]}</script>'
    anchor = EvidenceAnchor(
        anchor_type=EvidenceType.JSON_POINTER, json_pointer="/founders", field_path="jsonld:0"
    )
    assert verify_anchor(source, anchor, ["Asha", "Vivek"]).verified
    assert not verify_anchor(source, anchor, ["Asha", "Someone else"]).verified

"""Narrow public announcement parser. Only literal assertions receive anchors.

Headlines identify fundraising announcements; this is not a general article reasoner.
Publication metadata is deliberately not treated as the funding event date.
"""

import re

from bs4 import BeautifulSoup

from app.application.extraction.models import ClaimDraft
from app.domain.contracts import DatasetSchema, EvidenceAnchor
from app.domain.enums import EvidenceType


def announcement_claims(content: str, schema: DatasetSchema) -> list[ClaimDraft]:
    soup = BeautifulSoup(content, "html.parser")
    title = soup.find("h1")
    headline = title.get_text(" ", strip=True) if title else ""
    match = re.match(
        r"(?P<company>[\w .&-]+?) (?:secures|raises) .*?(?P<amount>\$[\d,.]+\s*(?:million|billion))",
        headline,
        re.I,
    )
    if not match:
        return []
    name, amount = match["company"], match["amount"]
    assertions: dict[str, tuple[str, str]] = {
        "company_name": (name, headline),
        "funding_amount": (amount, headline),
    }
    round_match = re.search(r"\b(Series [A-Z]|Seed)\b", headline, re.I)
    if round_match:
        assertions["funding_round"] = (round_match[0], headline)
    if re.search(r"\bAI\b", headline):
        assertions["industry"] = ("AI", headline)
    paragraphs = [p.get_text(" ", strip=True) for p in soup.select("p")]
    for paragraph in paragraphs:
        # An explicit funding dateline is stronger than site datePublished/dateModified.
        date = re.search(r"\b(\d{1,2}(?:st|nd|rd|th)? [A-Z][a-z]+ 20\d{2})", paragraph)
        if date and name in paragraph and re.search(r"raising|raised|funding", paragraph, re.I):
            assertions.setdefault("funding_date", (date[0], paragraph))
        if name in paragraph and "Domiciled in India" in paragraph:
            assertions["country"] = ("India", paragraph)
        if name in paragraph and "India’s first" in paragraph:
            assertions.setdefault("country", ("India", paragraph))
    if "funding_date" in assertions:
        assertions["announced_date"] = assertions["funding_date"]
    keys = {field.key for field in schema.fields}
    return [
        ClaimDraft(
            entity_key=name,
            field_key=key,
            raw_value=value,
            evidence=EvidenceAnchor(
                anchor_type=EvidenceType.NORMALIZED_TEXT_SPAN,
                field_path="html_visible_text:v1",
                quote=quote,
            ),
            extraction_method="deterministic:announcement-v1",
        )
        for key, (value, quote) in assertions.items()
        if key in keys
    ]

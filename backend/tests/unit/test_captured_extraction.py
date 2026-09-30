"""Offline captured-source goldens; source dates and missing values remain honest."""

import hashlib
from datetime import UTC, datetime

from app.ai.fixture_provider import FixtureProvider
from app.application.execution.operators import fixture_documents
from app.application.extraction.service import deterministic_extract
from app.application.requirement_compiler.models import CompilationContext, CompilerResult
from app.application.requirement_compiler.service import RequirementCompiler
from app.domain.contracts import FieldSpec
from app.domain.enums import FieldDataType
from app.domain.normalization import normalize


async def test_real_captured_announcements_preserve_event_dates_and_missing_fields() -> None:
    result = await RequirementCompiler(FixtureProvider()).compile(
        "Find Indian AI startups that raised more than $1M in the last 12 months.",
        context=CompilationContext(reference_date=datetime(2024, 9, 30, tzinfo=UTC)),
    )
    assert isinstance(result, CompilerResult)
    schema = result.dataset_schema_proposal
    schema = schema.model_copy(
        update={
            "fields": [
                *schema.fields,
                FieldSpec(key="country", label="Country", data_type=FieldDataType.LOCATION),
            ]
        }
    )
    documents = fixture_documents("captured")
    assert len(documents) == 2
    for doc in documents:
        assert doc.acquisition_method == "FIXTURE" and not doc.metadata["synthetic"]
        assert hashlib.sha256(doc.content.encode()).hexdigest() == doc.metadata["capture_sha256"]
        claims = deterministic_extract(doc.content, doc.content_type, schema)
        verified = {c.field_key: c for c in claims if c.evidence.verified}
        assert "funding_amount" in verified and "company_name" in verified and "country" in verified
        amount = normalize(verified["funding_amount"].raw_value, "money")
        if "sarvam" in doc.url:
            assert amount == {"amount": "41000000", "currency": "USD"}
            assert normalize(verified["announced_date"].raw_value, "date") == "2023-12-07"
        else:
            assert amount == {"amount": "20000000", "currency": "USD"}
            # Page CMS metadata says 2025; it is not a defensible funding event date.
            assert "announced_date" not in verified
        assert "headquarters" not in verified

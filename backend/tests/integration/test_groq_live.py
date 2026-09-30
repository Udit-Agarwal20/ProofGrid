"""Live integration tests for GroqProvider and RequirementCompiler against GroqCloud.

Requires real GROQ_API_KEY in backend/.env.
Opt-in execution ONLY via:
    make test-groq-live
Never runs in CI or make check.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from app.ai.contracts import StructuredGenerationRequest
from app.ai.groq_provider import GroqProvider
from app.application.requirement_compiler.models import (
    CandidateCompilationDraft,
)
from app.core.config import get_settings

pytestmark = pytest.mark.llm_live


@pytest.fixture
async def live_groq_provider() -> AsyncIterator[GroqProvider]:
    settings = get_settings()
    key = settings.groq_api_key_unmasked
    if not key:
        pytest.skip("Skipping live Groq test: GROQ_API_KEY not configured in backend/.env")
    provider = GroqProvider(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        timeout_ms=settings.GROQ_TIMEOUT_MS,
    )
    try:
        yield provider
    finally:
        await provider.aclose()


# -----------------------------------------------------------------------------
# LIVE SMOKE TEST: Full CandidateCompilationDraft Schema Smoke Test
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_groq_structured_provider_smoke(
    live_groq_provider: GroqProvider,
) -> None:
    """Verify real GroqCloud openai/gpt-oss-120b generates full CandidateCompilationDraft.

    Proves the REAL ProofGrid full schema is compatible with Groq strict mode:
    1. Successful real network call
    2. Strict schema generation (strict: True, json_schema)
    3. Pydantic validation (CandidateCompilationDraft)
    4. Deterministic ProofGrid validation (validate_compilation_draft)
    5. requires_confirmation=True
    6. No tools
    7. No PlanDAG
    8. No acquisition
    9. Metadata captured (latency_ms, prompt_tokens, completion_tokens, raw_finish_reason)
    """
    from app.application.requirement_compiler.validation import validate_compilation_draft

    request = StructuredGenerationRequest(
        system_prompt=(
            "You are the ProofGrid Requirement Compiler. Reference date: 2026-09-27. Last 18 months means start 2025-03-27, end 2026-09-27. "
            "Return a structured requirement draft matching the schema. "
            "Do not perform research, do not output PlanDAG, and do not execute code. "
            "Field data_types must be one of: text, url, money, date, location, entity_ref, entity_list, number, boolean. "
            "If filters are provided, filter field_key must exist in fields, and operator must be one of: eq, neq, gt, gte, lt, lte, in, contains. "
            "Clarification questions must only reference ambiguities with WARNING or BLOCKING severity."
        ),
        user_prompt="Find Indian AI startups that raised funding in the last 18 months.",
        temperature=0.0,
    )

    # 1. Real network call + strict schema generation + Pydantic validation
    draft, metadata = await live_groq_provider.generate_structured(
        request=request,
        output_schema=CandidateCompilationDraft,
    )

    # 2. Schema and Pydantic validation assertions
    assert isinstance(draft, CandidateCompilationDraft)
    assert draft.entity_type.strip() != ""
    assert len(draft.fields) > 0

    # 3. Deterministic ProofGrid validation
    pinned_ref_date = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
    outcome = validate_compilation_draft(
        draft=draft,
        provider_metadata=metadata,
        reference_date=pinned_ref_date,
        raw_prompt=request.user_prompt,
    )

    # 4. Mandatory confirmation boundary
    assert outcome.requires_confirmation is True
    assert outcome.status in ("COMPILED", "NEEDS_CLARIFICATION")

    # 5. Security & Boundary checks: No tools, No PlanDAG, No acquisition
    assert "PlanDAG" not in repr(outcome)
    assert "FETCH_HTTP" not in repr(outcome)
    assert getattr(draft, "plan_dag", None) is None
    assert getattr(draft, "nodes", None) is None

    # 6. Provider audit metadata captured
    assert metadata.provider_name == "groq"
    assert metadata.model_name == live_groq_provider.model
    assert metadata.latency_ms is not None and metadata.latency_ms > 0
    assert metadata.prompt_tokens is not None and metadata.prompt_tokens > 0
    assert metadata.completion_tokens is not None and metadata.completion_tokens > 0
    assert metadata.raw_finish_reason == "stop"

    # 7. Secret safety: no API key leaked
    assert "gsk_" not in repr(live_groq_provider)

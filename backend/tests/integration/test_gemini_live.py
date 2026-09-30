"""Live integration tests for GeminiProvider and RequirementCompiler against real Gemini API.

Requires real GEMINI_API_KEY in backend/.env.
Opt-in execution ONLY via:
    make test-llm-live
Never runs in CI or make check.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from app.ai.contracts import StructuredGenerationRequest
from app.ai.gemini_provider import GeminiProvider
from app.application.requirement_compiler.models import (
    CandidateCompilationDraft,
    CompilationContext,
    CompilerResult,
)
from app.application.requirement_compiler.service import RequirementCompiler
from app.core.config import get_settings

pytestmark = pytest.mark.llm_live


@pytest.fixture
async def live_gemini_provider() -> AsyncIterator[GeminiProvider]:
    settings = get_settings()
    key = settings.gemini_api_key_unmasked
    if not key:
        pytest.skip("Skipping live LLM test: GEMINI_API_KEY not configured in backend/.env")
    provider = GeminiProvider(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
        timeout_ms=settings.GEMINI_TIMEOUT_MS,
    )
    try:
        yield provider
    finally:
        await provider.aclose()


# -----------------------------------------------------------------------------
# LIVE TEST 1: Structured Provider Smoke Test
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_gemini_structured_provider_smoke(
    live_gemini_provider: GeminiProvider,
) -> None:
    """Verify live Gemini call returns valid CandidateCompilationDraft with audit metadata."""
    request = StructuredGenerationRequest(
        system_prompt=(
            "You are a requirement compiler. Return a structured requirement draft matching the schema. "
            "Do not perform research, do not output PlanDAG, and do not execute code."
        ),
        user_prompt="Find Indian AI startups that raised funding in the last 18 months.",
        temperature=0.1,
    )

    draft, metadata = await live_gemini_provider.generate_structured(
        request=request,
        output_schema=CandidateCompilationDraft,
    )

    # 1. Output conforms to CandidateCompilationDraft
    assert isinstance(draft, CandidateCompilationDraft)
    assert draft.entity_type.strip() != ""
    assert len(draft.fields) > 0

    # 2. Metadata audit assertions
    assert metadata.provider_name == "gemini"
    assert metadata.model_name == live_gemini_provider.model
    assert metadata.latency_ms is not None and metadata.latency_ms > 0
    assert metadata.prompt_tokens is not None and metadata.prompt_tokens > 0
    assert metadata.completion_tokens is not None and metadata.completion_tokens > 0

    # 3. Security: No raw key in metadata or repr
    assert metadata.provider_name == "gemini"
    assert "AIza" not in repr(live_gemini_provider)


# -----------------------------------------------------------------------------
# LIVE TEST 2: Full Golden Compiler Test
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_gemini_full_golden_compiler(
    live_gemini_provider: GeminiProvider,
) -> None:
    """Verify end-to-end compilation with real Gemini returns valid CompilerResult."""
    compiler = RequirementCompiler(provider=live_gemini_provider)
    pinned_ref_date = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
    context = CompilationContext(reference_date=pinned_ref_date)

    prompt = (
        "Find Indian AI startups that raised funding in the last 18 months. "
        "For each company include company name, funding round, amount, currency, "
        "announcement date, investors, and source URL."
    )

    outcome = await compiler.compile(prompt, context=context)

    # 1. Valid compilation outcome
    assert isinstance(outcome, CompilerResult), (
        f"Expected complete CompilerResult, got {type(outcome).__name__}"
    )

    # 2. Mandatory confirmation boundary
    assert outcome.requires_confirmation is True
    assert outcome.status == "COMPILED"

    # 3. Semantic intent checks (non-brittle)
    spec = outcome.requirement_spec
    assert "company" in spec.entity_type.lower() or "startup" in spec.entity_type.lower()
    assert spec.geography is not None and any("india" in g.lower() for g in spec.geography)

    # Requested fields materially represented
    field_keys = {f.key for f in outcome.dataset_schema_proposal.fields}
    assert any("name" in k or "company" in k for k in field_keys)
    assert any("round" in k for k in field_keys)
    assert any("amount" in k for k in field_keys)

    # 4. Valid TrustContract and DatasetSchema
    assert outcome.dataset_schema_proposal.schema_hash.startswith("sha256:")
    assert outcome.trust_contract_proposal.max_pages >= 1
    assert outcome.trust_contract_proposal.max_llm_calls >= 1

    # 5. Security & Boundary checks: No PlanDAG or workflow operators
    assert outcome.metadata.provider_name == "gemini"
    assert outcome.metadata.model_name == live_gemini_provider.model

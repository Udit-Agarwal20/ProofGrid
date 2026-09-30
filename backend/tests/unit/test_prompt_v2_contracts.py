"""Unit tests verifying requirement-compiler-v2 prompt contracts and historical v1 preservation."""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.requirement_compiler.prompts import (
    PROMPT_VERSION_V1,
    PROMPT_VERSION_V2,
    REQUIREMENT_COMPILER_PROMPT_VERSION,
    build_compiler_request,
    build_system_instruction,
    build_system_instruction_v1,
    build_system_instruction_v2,
)


def test_prompt_version_constants() -> None:
    """Verify version identifiers and default active version."""
    assert PROMPT_VERSION_V1 == "requirement-compiler-v1"
    assert PROMPT_VERSION_V2 == "requirement-compiler-v2"
    assert REQUIREMENT_COMPILER_PROMPT_VERSION == "requirement-compiler-v2"


def test_historical_v1_preservation() -> None:
    """Verify v1 system instruction remains accessible and unaltered."""
    v1_prompt = build_system_instruction_v1(reference_date=datetime(2026, 9, 27, tzinfo=UTC))
    assert f"Prompt Version: {PROMPT_VERSION_V1}" in v1_prompt
    assert "You are the ProofGrid Requirement Compiler." in v1_prompt
    assert "2026-09-27" in v1_prompt


def test_v2_prompt_contract_and_default_routing() -> None:
    """Verify default build_system_instruction routes to v2 with correct version stamp."""
    default_prompt = build_system_instruction(reference_date=datetime(2026, 9, 27, tzinfo=UTC))
    v2_prompt = build_system_instruction_v2(reference_date=datetime(2026, 9, 27, tzinfo=UTC))
    assert default_prompt == v2_prompt
    assert f"Prompt Version: {PROMPT_VERSION_V2}" in v2_prompt


def test_v2_canonical_filter_operators_contract() -> None:
    """Verify v2 prompt includes canonical operator registry and explicitly forbids synonyms."""
    prompt = build_system_instruction_v2()
    canonical_ops = ["eq", "neq", "gt", "gte", "lt", "lte", "in", "contains"]
    for op in canonical_ops:
        assert f"'{op}'" in prompt

    assert "NEVER emit" in prompt
    assert "equals" in prompt
    assert ">" in prompt
    assert "==" in prompt


def test_v2_filter_field_integrity_contract() -> None:
    """Verify v2 prompt instructs that all filtered fields must exist in proposed schema."""
    prompt = build_system_instruction_v2()
    assert "FILTER FIELD INTEGRITY" in prompt
    assert "'field_key' MUST exactly reference a field key declared in 'fields'" in prompt


def test_v2_ambiguity_severity_and_info_contract() -> None:
    """Verify v2 prompt forbids generating clarification questions for INFO ambiguities."""
    prompt = build_system_instruction_v2()
    assert (
        "'INFO': Informative observation only. NEVER generates a clarification question" in prompt
    )
    assert "Never generate a clarification question for an ambiguity with severity 'INFO'" in prompt


def test_v2_blocking_clarification_boundary_contract() -> None:
    """Verify v2 prompt restricts NEEDS_CLARIFICATION to genuinely blocking cases."""
    prompt = build_system_instruction_v2()
    assert "NEEDS_CLARIFICATION BOUNDARY" in prompt
    assert "Unknown referent/entity" in prompt
    assert "Mutually contradictory constraints" in prompt
    assert "STANDARD CATEGORY ASSUMPTIONS" in prompt


def test_v2_explicit_date_preservation_contract() -> None:
    """Verify v2 prompt mandates that explicit user dates win over relative reference dates."""
    prompt = build_system_instruction_v2()
    assert "TEMPORAL RESOLUTION & EXPLICIT DATES" in prompt
    assert "MUST be preserved exactly" in prompt


def test_v2_security_boundary_contract() -> None:
    """Verify v2 prompt maintains strict tool and execution isolation."""
    prompt = build_system_instruction_v2()
    assert "UNTRUSTED INPUT & SECURITY" in prompt
    assert "COMPILE ONLY (NO TOOLS / NO PLANS)" in prompt
    assert "PlanDAG" in prompt
    assert "operators" in prompt


def test_v2_conciseness_and_pre_return_self_check() -> None:
    """Verify v2 prompt requires conciseness and includes pre-return checklist."""
    prompt = build_system_instruction_v2()
    assert "CONCISE AMBIGUITIES & ASSUMPTIONS" in prompt
    assert "Maximum 3 questions total" in prompt
    assert "PRE-RETURN SELF-CHECK" in prompt


def test_build_compiler_request_metadata_and_version() -> None:
    """Verify build_compiler_request stamps prompt_version accurately."""
    req_v2 = build_compiler_request(user_prompt="test request")
    assert req_v2.metadata["prompt_version"] == "requirement-compiler-v2"
    assert f"Prompt Version: {PROMPT_VERSION_V2}" in req_v2.system_prompt

    req_v1 = build_compiler_request(user_prompt="test request", prompt_version=PROMPT_VERSION_V1)
    assert req_v1.metadata["prompt_version"] == "requirement-compiler-v1"
    assert f"Prompt Version: {PROMPT_VERSION_V1}" in req_v1.system_prompt

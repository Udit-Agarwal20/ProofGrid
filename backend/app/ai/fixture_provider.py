"""Deterministic fixture provider for offline requirement compilation testing.

Zero network calls, zero vendor SDK dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar, cast

from app.ai.contracts import ProviderMetadata, StructuredGenerationRequest
from app.ai.exceptions import AIProviderConfigurationError, AIProviderError, AIProviderTimeoutError
from app.application.requirement_compiler.models import (
    Ambiguity,
    AmbiguitySeverity,
    Assumption,
    CandidateCompilationDraft,
    CandidateFieldSpec,
    CandidateFilterSpec,
    CandidateTrustPreferences,
    ClarificationQuestion,
)
from app.domain.contracts import DateRange

T = TypeVar("T")


class FixtureProvider:
    """Deterministic, offline structured generation provider for test suites."""

    def __init__(self, default_scenario: str = "golden_indian_ai_funding") -> None:
        self.default_scenario = default_scenario

    def _resolve_scenario(self, request: StructuredGenerationRequest) -> str:
        """Determine scenario from request metadata or prompt heuristics."""
        scenario_meta = request.metadata.get("scenario")
        if scenario_meta:
            return str(scenario_meta)

        prompt_lower = request.user_prompt.lower()
        if "best ones in india" in prompt_lower or (
            "best ones" in prompt_lower and "india" in prompt_lower
        ):
            return "blocking_user_ambiguity_missing_entity"
        if (
            "raised funding in the last 18 months" in prompt_lower
            or "indian ai startups" in prompt_lower
        ):
            return "golden_indian_ai_funding"
        if (
            "best recent ai startups" in prompt_lower
            or "best" in prompt_lower
            and "recent" in prompt_lower
        ):
            return "ambiguous_startups"
        if "contradiction" in prompt_lower or (
            "founded after" in prompt_lower and "before" in prompt_lower
        ):
            return "blocking_contradiction"
        if "ignore" in prompt_lower and ("python" in prompt_lower or "rm -rf" in prompt_lower):
            return "prompt_injection_inert"

        return self.default_scenario

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        output_schema: type[T],
    ) -> tuple[T, ProviderMetadata]:
        """Produce deterministic scenario output without network calls."""
        scenario = self._resolve_scenario(request)

        metadata = ProviderMetadata(
            provider_name="fixture",
            model_name="deterministic-fixture-v1",
            prompt_tokens=42,
            completion_tokens=128,
            latency_ms=1.2,
            raw_finish_reason="stop",
            scenario=scenario,
        )

        if scenario == "provider_timeout":
            raise AIProviderTimeoutError("Simulation: provider timed out after 30s")

        if scenario == "provider_failure":
            raise AIProviderError("Simulation: provider connection failed with 503")

        draft = self._build_scenario_draft(scenario, request)
        if not isinstance(draft, output_schema):
            # Attempt parsing through output_schema if a dict or compatible model
            if isinstance(draft, dict) and hasattr(output_schema, "model_validate"):
                validated_model: T = cast(Any, output_schema).model_validate(draft)
                return validated_model, metadata
            raise AIProviderConfigurationError(
                f"Fixture scenario '{scenario}' returned {type(draft)}, expected {output_schema}."
            )

        return draft, metadata

    def _build_scenario_draft(
        self,
        scenario: str,
        request: StructuredGenerationRequest,
    ) -> CandidateCompilationDraft:
        """Build the CandidateCompilationDraft for a specified scenario."""
        if scenario == "golden_indian_ai_funding":
            ref_str = request.metadata.get("reference_date")
            if ref_str:
                ref_dt = datetime.fromisoformat(ref_str)
            else:
                ref_dt = datetime(2025, 3, 1, 12, 0, 0, tzinfo=UTC)

            # Deterministic trailing 18 months relative to reference_date
            end_date = ref_dt.astimezone(UTC).strftime("%Y-%m-%d")
            total_months = ref_dt.year * 12 + (ref_dt.month - 1) - 18
            start_year = total_months // 12
            start_month = (total_months % 12) + 1
            start_day = min(ref_dt.day, 28)
            start_date = f"{start_year:04d}-{start_month:02d}-{start_day:02d}"

            return CandidateCompilationDraft(
                entity_type="company",
                goal="Find Indian AI startups that raised funding in the last 18 months",
                fields=[
                    CandidateFieldSpec(
                        key="company_name",
                        label="Company Name",
                        data_type="text",
                        required=True,
                        origin="user",
                        description="Legal or commercial name of the startup",
                    ),
                    CandidateFieldSpec(
                        key="funding_round",
                        label="Funding Round",
                        data_type="text",
                        required=True,
                        origin="user",
                        description="Investment stage (e.g. Seed, Series A, Series B)",
                    ),
                    CandidateFieldSpec(
                        key="funding_amount",
                        label="Funding Amount",
                        data_type="money",
                        required=True,
                        origin="user",
                        description="Monetary amount raised in this round",
                    ),
                    CandidateFieldSpec(
                        key="currency",
                        label="Currency",
                        data_type="text",
                        required=False,
                        origin="user",
                        description="Three-letter currency code (e.g. USD, INR)",
                    ),
                    CandidateFieldSpec(
                        key="announced_date",
                        label="Announcement Date",
                        data_type="date",
                        required=True,
                        origin="user",
                        description="Public disclosure date of the funding event",
                    ),
                    CandidateFieldSpec(
                        key="investors",
                        label="Investors",
                        data_type="entity_list",
                        required=False,
                        origin="user",
                        description="Institutional and angel investors participating in the round",
                    ),
                    CandidateFieldSpec(
                        key="source_url",
                        label="Source URL",
                        data_type="url",
                        required=True,
                        origin="user",
                        description="Direct reference URL for the announcement",
                    ),
                ],
                filters=[
                    CandidateFilterSpec(
                        field_key="announced_date",
                        operator="gte",
                        value=start_date,
                    )
                ],
                geography=["India"],
                time_window=DateRange(start=start_date, end=end_date),
                source_hints=["press_release", "regulatory_filing", "tech_news"],
                limit=50,
                trust_preferences=CandidateTrustPreferences(
                    require_evidence_anchor=True,
                    minimum_independent_sources=1,
                    prefer_first_party=True,
                    allow_secondary_sources=True,
                    allow_single_source_output=True,
                    preserve_conflicts=True,
                    strict_required_fields=False,
                    max_pages=60,
                    max_browser_pages=5,
                    max_llm_calls=80,
                    max_run_seconds=180,
                    max_estimated_cost_usd=Decimal("3.00"),
                ),
                ambiguities=[
                    Ambiguity(
                        code="RELATIVE_TIME_WINDOW",
                        field_path="time_window",
                        message="'last 18 months' is relative to execution date.",
                        severity=AmbiguitySeverity.INFO,
                        blocking=False,
                        possible_interpretations=[
                            "Trailing 18 calendar months",
                            "Trailing 548 days",
                        ],
                    ),
                    Ambiguity(
                        code="GEOGRAPHIC_CRITERION",
                        field_path="geography",
                        message="'Indian startups' can mean headquartered, founded, or operating in India.",
                        severity=AmbiguitySeverity.WARNING,
                        blocking=False,
                        possible_interpretations=[
                            "Headquartered in India",
                            "Founded in India and operating globally",
                            "Operating in India regardless of headquarters",
                        ],
                    ),
                ],
                assumptions=[
                    Assumption(
                        code="GEO_HEADQUARTERS_DEFAULT",
                        description="Assumed 'Indian startup' refers to companies headquartered in India.",
                        affected_field="geography",
                        reversible=True,
                    ),
                    Assumption(
                        code="CURRENCY_DEFAULT_USD",
                        description="Funding amounts default to local reported currency, normalized to USD presentation.",
                        affected_field="currency",
                        reversible=True,
                    ),
                ],
                clarification_questions=[
                    ClarificationQuestion(
                        question_id="Q1",
                        ambiguity_code="GEOGRAPHIC_CRITERION",
                        question="Should 'Indian startup' include only companies headquartered in India, or also companies founded by Indian founders headquartered abroad?",
                        options=[
                            "Headquartered in India only",
                            "Founded in India / Indian-founded abroad",
                            "Any company with major operations in India",
                        ],
                        impact_summary="Affects filtering of overseas-domiciled entities (e.g., US/Singapore-flip startups).",
                    )
                ],
            )

        if scenario == "ambiguous_startups":
            return CandidateCompilationDraft(
                entity_type="company",
                goal="Find the best recent AI startups in India",
                fields=[
                    CandidateFieldSpec(
                        key="company_name",
                        label="Company Name",
                        data_type="text",
                        required=True,
                    ),
                    CandidateFieldSpec(
                        key="domain",
                        label="Domain",
                        data_type="text",
                        required=True,
                    ),
                    CandidateFieldSpec(
                        key="location",
                        label="Location",
                        data_type="location",
                        required=True,
                    ),
                ],
                filters=[],
                geography=["India"],
                time_window=None,
                ambiguities=[
                    Ambiguity(
                        code="SUBJECTIVE_BEST",
                        field_path="goal",
                        message="'Best' is subjective without clear ranking metric or objective criteria.",
                        severity=AmbiguitySeverity.WARNING,
                        blocking=False,
                        possible_interpretations=[
                            "Highest funding raised",
                            "Highest employee count or growth",
                            "Community recognition or award winners",
                        ],
                    ),
                    Ambiguity(
                        code="AMBIGUOUS_RECENCY",
                        field_path="time_window",
                        message="'Recent' lacks a specific calendar timeframe.",
                        severity=AmbiguitySeverity.WARNING,
                        blocking=False,
                        possible_interpretations=[
                            "Founded in last 12 months",
                            "Founded in last 24 months",
                            "Funded recently",
                        ],
                    ),
                ],
                assumptions=[
                    Assumption(
                        code="ASSUME_TOP_FUNDED",
                        description="Interpreted 'best' as startups with highest total capital raised.",
                        affected_field="goal",
                        reversible=True,
                    ),
                    Assumption(
                        code="ASSUME_RECENCY_24M",
                        description="Interpreted 'recent' as founded within the last 24 calendar months.",
                        affected_field="time_window",
                        reversible=True,
                    ),
                ],
                clarification_questions=[
                    ClarificationQuestion(
                        question_id="Q1",
                        ambiguity_code="SUBJECTIVE_BEST",
                        question="How would you like to define 'best' startups for this dataset?",
                        options=[
                            "Highest funding raised",
                            "Fastest growing headcount",
                            "Featured in notable industry reports",
                        ],
                        impact_summary="Determines sorting, ranking, and filtering criteria.",
                    ),
                    ClarificationQuestion(
                        question_id="Q2",
                        ambiguity_code="AMBIGUOUS_RECENCY",
                        question="What founding timeframe should be used for 'recent' startups?",
                        options=[
                            "Last 12 months",
                            "Last 24 months",
                            "Last 36 months",
                        ],
                        impact_summary="Defines the bounding date range for company founding.",
                    ),
                ],
            )

        if scenario == "blocking_contradiction":
            return CandidateCompilationDraft(
                entity_type="company",
                goal="Find startups founded after 2024 that raised Series B before 2020",
                fields=[
                    CandidateFieldSpec(
                        key="company_name",
                        label="Company Name",
                        data_type="text",
                        required=True,
                    ),
                    CandidateFieldSpec(
                        key="founding_date",
                        label="Founding Date",
                        data_type="date",
                        required=True,
                    ),
                ],
                filters=[],
                geography=[],
                time_window=DateRange(start="2024-01-01", end="2020-01-01"),
                ambiguities=[
                    Ambiguity(
                        code="CONTRADICTORY_DATE_RANGE",
                        field_path="time_window",
                        message="Requested date range is contradictory: start (2024-01-01) cannot be after end (2020-01-01).",
                        severity=AmbiguitySeverity.BLOCKING,
                        blocking=True,
                        possible_interpretations=[
                            "Typo in calendar bounds",
                            "Mutually exclusive filters",
                        ],
                    )
                ],
                clarification_questions=[
                    ClarificationQuestion(
                        question_id="Q_BLOCK_1",
                        ambiguity_code="CONTRADICTORY_DATE_RANGE",
                        question="The requested date range is contradictory (start 2024-01-01 after end 2020-01-01). Which timeframe was intended?",
                        options=[
                            "Startups founded after 2024",
                            "Startups funded before 2020",
                        ],
                        impact_summary="Execution cannot proceed with impossible date filters.",
                    )
                ],
            )

        if scenario == "invalid_duplicate_fields":
            return CandidateCompilationDraft(
                entity_type="company",
                goal="Find startups with duplicate fields",
                fields=[
                    CandidateFieldSpec(
                        key="company_name",
                        label="Company Name",
                        data_type="text",
                        required=True,
                    ),
                    CandidateFieldSpec(
                        key="company_name",
                        label="Company Name Duplicate",
                        data_type="text",
                        required=False,
                    ),
                ],
            )

        if scenario == "invalid_unsupported_field_type":
            return CandidateCompilationDraft(
                entity_type="company",
                goal="Find startups with unsupported field types",
                fields=[
                    CandidateFieldSpec(
                        key="wallet_payload",
                        label="Wallet Payload",
                        data_type="unsupported_binary_blob",
                        required=True,
                    )
                ],
            )

        if scenario == "invalid_negative_budget":
            return CandidateCompilationDraft(
                entity_type="company",
                goal="Find startups with negative budget",
                fields=[
                    CandidateFieldSpec(
                        key="company_name",
                        label="Company Name",
                        data_type="text",
                        required=True,
                    )
                ],
                trust_preferences=CandidateTrustPreferences(
                    max_pages=-10,
                    max_estimated_cost_usd=Decimal("-5.00"),
                ),
            )

        if scenario == "invalid_plandag_injection":
            return CandidateCompilationDraft(
                entity_type="company",
                goal="Find startups with plandag injection",
                fields=[
                    CandidateFieldSpec(
                        key="company_name",
                        label="Company Name",
                        data_type="text",
                        required=True,
                    )
                ],
                plan_dag={"nodes": [{"id": "fetch_1", "operator": "FETCH_HTTP"}]},
            )

        if scenario == "blocking_user_ambiguity_missing_entity":
            return CandidateCompilationDraft(
                entity_type="",
                goal="Find the best ones in India",
                fields=[
                    CandidateFieldSpec(
                        key="name",
                        label="Name",
                        data_type="text",
                        required=True,
                    )
                ],
                geography=["India"],
                ambiguities=[
                    Ambiguity(
                        code="AMBIGUOUS_TARGET_ENTITY",
                        field_path="entity_type",
                        message="Target entity is not specified (e.g. startups, investors, colleges).",
                        severity=AmbiguitySeverity.BLOCKING,
                        blocking=True,
                        possible_interpretations=[
                            "AI startups / companies",
                            "Venture capital / investors",
                            "Academic / research institutions",
                        ],
                    )
                ],
                clarification_questions=[
                    ClarificationQuestion(
                        question_id="Q_ENTITY",
                        ambiguity_code="AMBIGUOUS_TARGET_ENTITY",
                        question="What type of entity are you looking for in India?",
                        options=[
                            "AI startups / companies",
                            "Venture capital / investors",
                            "Academic / research institutions",
                        ],
                        impact_summary="Defines the core entity type and required schema attributes.",
                    )
                ],
            )

        if scenario == "missing_entity":
            return CandidateCompilationDraft(
                entity_type="",
                goal="Find data without entity type",
                fields=[
                    CandidateFieldSpec(
                        key="company_name",
                        label="Company Name",
                        data_type="text",
                        required=True,
                    )
                ],
            )

        if scenario == "prompt_injection_inert":
            # The prompt text is interpreted strictly as data, not code to run
            return CandidateCompilationDraft(
                entity_type="script_analysis",
                goal=f"Analyze data request: {request.user_prompt[:50]}",
                fields=[
                    CandidateFieldSpec(
                        key="input_text",
                        label="Input Text",
                        data_type="text",
                        required=True,
                        description="Verbatim user prompt text",
                    )
                ],
                ambiguities=[
                    Ambiguity(
                        code="ADVERSARIAL_INTENT_SUSPECTED",
                        field_path="goal",
                        message="User prompt contains imperative code execution directives which are inert data in ProofGrid.",
                        severity=AmbiguitySeverity.WARNING,
                        blocking=False,
                        possible_interpretations=[
                            "User prompt was a security test",
                            "User pasted script contents into prompt",
                        ],
                    )
                ],
            )

        raise AIProviderConfigurationError(f"Unknown fixture scenario: '{scenario}'.")

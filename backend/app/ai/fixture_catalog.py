"""Explicit deterministic generalization cases for the compiler's offline A-H corpus."""

import re

from app.application.requirement_compiler.models import (
    Ambiguity,
    AmbiguitySeverity,
    CandidateCompilationDraft,
    CandidateFieldSpec,
    CandidateFilterSpec,
)
from app.domain.contracts import DateRange


def catalog_draft(prompt: str) -> CandidateCompilationDraft | None:
    value = prompt.lower()
    fields = [
        CandidateFieldSpec(key="company_name", label="Company", data_type="text", required=True),
        CandidateFieldSpec(key="website", label="Website", data_type="url"),
    ]
    filters: list[CandidateFilterSpec] = []
    geography: list[str] = []
    ambiguities: list[Ambiguity] = []
    window = None
    if "fintech" in value and "revenue" in value:
        geography = ["India"]
        fields.extend(
            [
                CandidateFieldSpec(
                    key="industry", label="Industry", data_type="text", origin="ai_inferred"
                ),
                CandidateFieldSpec(
                    key="revenue", label="Revenue", data_type="money", required=True
                ),
            ]
        )
        filters = [
            CandidateFilterSpec(field_key="industry", operator="eq", value="fintech"),
            CandidateFilterSpec(
                field_key="revenue", operator="gt", value={"amount": "10000000", "currency": "USD"}
            ),
        ]
        ambiguities = [
            Ambiguity(
                code="REVENUE_PERIOD_UNSPECIFIED",
                message="Revenue period and audited versus estimated reporting were not specified.",
                severity=AmbiguitySeverity.WARNING,
                blocking=False,
            )
        ]
    elif "germany" in value or "german" in value:
        geography = ["Germany"]
        fields.extend(
            [
                CandidateFieldSpec(key="headquarters", label="Headquarters", data_type="location"),
                CandidateFieldSpec(key="founding_year", label="Founding year", data_type="number"),
                CandidateFieldSpec(
                    key="industry", label="Industry", data_type="text", origin="ai_inferred"
                ),
            ]
        )
        filters = [
            CandidateFilterSpec(
                field_key="industry", operator="eq", value="electric vehicle manufacturing"
            )
        ]
    elif "singapore" in value and "cybersecurity" in value:
        geography = ["Singapore"]
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", prompt)
        if len(dates) == 2:
            window = DateRange(start=dates[0], end=dates[1])
        fields.extend(
            [
                CandidateFieldSpec(key="funding_round", label="Round", data_type="text"),
                CandidateFieldSpec(key="funding_date", label="Funding date", data_type="date"),
                CandidateFieldSpec(
                    key="industry", label="Industry", data_type="text", origin="ai_inferred"
                ),
            ]
        )
        filters = [
            CandidateFilterSpec(field_key="funding_round", operator="eq", value="Series A"),
            CandidateFilterSpec(field_key="industry", operator="eq", value="cybersecurity"),
        ]
    elif "japan" in value and "companies" in value:
        geography = ["Japan"]
        fields.append(
            CandidateFieldSpec(
                key="industry", label="Industry", data_type="text", origin="ai_inferred"
            )
        )
        filters = [CandidateFilterSpec(field_key="industry", operator="eq", value="AI")]
    else:
        return None
    return CandidateCompilationDraft(
        goal="Find companies matching the supplied business criteria",
        entity_type="company",
        fields=fields,
        filters=filters,
        geography=geography,
        time_window=window,
        ambiguities=ambiguities,
    )

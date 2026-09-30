import pytest

from app.ai.fixture_provider import FixtureProvider
from app.application.planning.service import fixture_plan, validate_plan
from app.application.requirement_compiler.models import CompilerResult
from app.application.requirement_compiler.service import RequirementCompiler
from app.core.errors import ProofGridError
from app.domain.contracts import PlanDAG
from app.domain.states import transition_step


async def test_plan_validation_rejects_cycles_unknown_fields_and_code() -> None:
    result = await RequirementCompiler(FixtureProvider()).compile(
        "Find Indian AI startups in the last 12 months"
    )
    assert isinstance(result, CompilerResult)
    spec, schema, trust = (
        result.requirement_spec,
        result.dataset_schema_proposal,
        result.trust_contract_proposal,
    )
    plan = fixture_plan(spec, trust)
    assert validate_plan(plan, spec, schema, trust)[-1] == "materialize"
    data = plan.model_dump(mode="json")
    data["nodes"][0]["depends_on"] = ["materialize"]
    with pytest.raises(ProofGridError, match="cycle"):
        validate_plan(PlanDAG.model_validate(data), spec, schema, trust)
    data = plan.model_dump(mode="json")
    data["nodes"][1]["params"] = {"nested": {"code": "print(1)"}}
    with pytest.raises(ProofGridError, match="parameters"):
        validate_plan(PlanDAG.model_validate(data), spec, schema, trust)


def test_terminal_steps_cannot_restart() -> None:
    with pytest.raises(ValueError):
        transition_step("SUCCEEDED", "READY")


async def test_edited_filters_and_trust_cannot_bypass_validation() -> None:
    from app.domain.contracts import FilterSpec

    result = await RequirementCompiler(FixtureProvider()).compile(
        "Find Indian AI startups in the last 12 months"
    )
    assert isinstance(result, CompilerResult)
    spec, schema, trust = (
        result.requirement_spec,
        result.dataset_schema_proposal,
        result.trust_contract_proposal,
    )
    bad = spec.model_copy(
        update={
            "filters": [FilterSpec(field_key="funding_amount", operator="contains", value="USD")]
        }
    )
    with pytest.raises(ProofGridError, match="schema field type"):
        validate_plan(fixture_plan(spec, trust), bad, schema, trust)
    with pytest.raises(ProofGridError, match="mandatory"):
        validate_plan(
            fixture_plan(spec, trust),
            spec,
            schema,
            trust.model_copy(update={"preserve_conflicts": False}),
        )

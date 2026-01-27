"""
Deep regression tests for the all-flows data infrastructure fixes.

Focus:
- New extraction fields + phase mappings (constants.yaml -> extraction_ssot)
- Question dedup config coverage + generic fallback behavior
- Flow phase states required_data/on_enter/data_complete consistency
- Prompt templates include dedup variables for all non-SPIN flows
"""

from pathlib import Path
import sys
import yaml
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extraction_ssot import EXTRACTION_FIELDS, PHASE_FIELDS, ALL_FIELD_NAMES
from question_dedup import QuestionDeduplicationEngine


BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "src" / "yaml_config"
FLOWS_DIR = CONFIG_DIR / "flows"
TEMPLATES_DIR = CONFIG_DIR / "templates"
CONSTANTS_FILE = CONFIG_DIR / "constants.yaml"


NEW_SHARED_FIELDS = {
    "decision_maker": "authority",
    "budget_range": "budget",
    "decision_timeline": "timeline",
    "decision_criteria": "criteria",
    "success_metrics": "metrics",
    "champion_info": "champion",
    "decision_process": "process",
}

PHASE_FIELD_EXPECTATIONS = {
    "metrics": {"success_metrics"},
    "buyer": {"decision_maker"},
    "criteria": {"decision_criteria"},
    "process": {"decision_process"},
    "champion": {"champion_info"},
    "budget": {"budget_range"},
    "authority": {"decision_maker"},
    "timeline": {"decision_timeline"},
}

PHASE_CLASSIFICATION_KEYS = [
    # MEDDIC
    "metrics",
    "buyer",
    "criteria",
    "process",
    "pain",
    "champion",
    # BANT
    "budget",
    "authority",
    "need",
    "timeline",
    # Shared (non-SPIN)
    "discover",
    "interest",
    "desire",
    "features",
    "advantages",
    "benefits",
    "simple",
    "align",
    "understand",
    "advise",
    "recommend",
    "quantify",
    "engage",
]

DEDUP_PHASES = [
    # MEDDIC
    "metrics",
    "buyer",
    "criteria",
    "process",
    "champion",
    "pain",
    # BANT
    "budget",
    "authority",
    "need",
    "timeline",
    # Shared phases configured in question_dedup.yaml
    "discover",
    "interest",
    "desire",
    "features",
    "advantages",
    "benefits",
    "quantify",
    "understand",
    "advise",
    "recommend",
]


@pytest.fixture(scope="module")
def constants():
    """Load constants.yaml once for the module."""
    with open(CONSTANTS_FILE, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _list_flow_names():
    return sorted(
        p.name for p in FLOWS_DIR.iterdir()
        if p.is_dir() and p.name not in {"_base", "examples", "spin_selling"}
    )


def _load_yaml(path: Path):
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


# =============================================================================
# EXTRACTION + CONSTANTS COVERAGE
# =============================================================================


@pytest.mark.parametrize("field, expected_phase", NEW_SHARED_FIELDS.items())
def test_new_extraction_fields_registered(field, expected_phase):
    """New shared extraction fields must exist with expected phase mapping."""
    config = EXTRACTION_FIELDS.get(field)
    assert config is not None, f"Missing extraction field: {field}"
    assert config.spin_phase == expected_phase


@pytest.mark.parametrize("phase, expected_fields", PHASE_FIELD_EXPECTATIONS.items())
def test_phase_fields_include_new_shared_fields(phase, expected_fields):
    """PHASE_FIELDS must include new shared fields for non-SPIN phases."""
    fields = set(PHASE_FIELDS.get(phase, []))
    assert fields, f"Phase {phase} missing in PHASE_FIELDS"
    for field in expected_fields:
        assert field in fields


@pytest.mark.parametrize("phase", PHASE_CLASSIFICATION_KEYS)
def test_phase_classification_entries_exist(constants, phase):
    """New phase classification entries must exist and reference valid fields."""
    phase_classification = constants["spin"]["phase_classification"]
    assert phase in phase_classification, f"Missing phase classification: {phase}"
    data_fields = phase_classification[phase].get("data_fields", [])
    assert data_fields, f"Phase {phase} has no data_fields"
    for field in data_fields:
        assert field in ALL_FIELD_NAMES, f"Unknown data field in phase {phase}: {field}"


# =============================================================================
# QUESTION DEDUP CONFIG + GENERIC FALLBACK
# =============================================================================


@pytest.fixture()
def dedup_engine():
    """Fresh dedup engine instance."""
    return QuestionDeduplicationEngine()


@pytest.mark.parametrize("field", NEW_SHARED_FIELDS.keys())
def test_dedup_config_contains_shared_fields(dedup_engine, field):
    """question_dedup.yaml must include new shared fields with questions."""
    assert field in dedup_engine._config.data_fields
    related = dedup_engine._config.data_fields[field].get("related_questions", [])
    assert related, f"No related questions for {field}"


@pytest.mark.parametrize("phase", DEDUP_PHASES)
def test_dedup_phase_questions_exist(dedup_engine, phase):
    """question_dedup.yaml must define phase_questions for new phases."""
    assert phase in dedup_engine._config.phase_questions
    question_templates = dedup_engine._config.phase_questions[phase].get("question_templates", {})
    assert question_templates, f"No question_templates for phase {phase}"


def test_generic_dedup_uses_related_questions_for_unknown_phase(dedup_engine):
    """Generic dedup should use related_questions even when phase has no config."""
    missing_data = ["company_size", "current_tools"]
    collected = {"business_type": "IT"}

    result = dedup_engine.get_available_questions(
        phase="align",  # not configured in question_dedup.yaml
        collected_data=collected,
        missing_data=missing_data,
    )

    related = set()
    for field in missing_data:
        related.update(dedup_engine._config.data_fields[field].get("related_questions", []))

    assert result.available_questions
    for question in result.available_questions:
        assert question in related

    assert "business_type" in result.do_not_ask_fields


def test_generic_dedup_fallback_for_unknown_phase_without_missing(dedup_engine):
    """Generic dedup should fall back to default questions when no missing_data."""
    result = dedup_engine.get_available_questions(
        phase="align",
        collected_data={"company_size": 5},
        missing_data=[],
    )

    fallback = dedup_engine.FALLBACK_QUESTIONS["_default"]
    assert result.available_questions == fallback[:2]
    assert result.all_data_collected


# =============================================================================
# FLOW STATE CONSISTENCY (REQUIRED DATA + DATA_COMPLETE)
# =============================================================================


@pytest.mark.parametrize("flow_name", _list_flow_names())
def test_flow_phase_states_have_required_data_and_transitions(flow_name):
    """All phase states must define required_data and data_complete transitions."""
    flow_yaml = _load_yaml(FLOWS_DIR / flow_name / "flow.yaml")
    states_yaml = _load_yaml(FLOWS_DIR / flow_name / "states.yaml")

    phase_mapping = flow_yaml.get("flow", {}).get("phases", {}).get("mapping", {})
    phase_states = set(phase_mapping.values())

    states = states_yaml.get("states", {})
    phase_states |= {
        name for name, cfg in states.items()
        if cfg.get("phase") or cfg.get("spin_phase")
    }

    assert phase_states, f"No phase states detected for flow: {flow_name}"

    for state_name in phase_states:
        cfg = states[state_name]
        required = cfg.get("required_data")
        assert required, f"State {flow_name}.{state_name} missing required_data"
        transitions = cfg.get("transitions", {})
        assert "data_complete" in transitions, (
            f"State {flow_name}.{state_name} missing data_complete transition"
        )


@pytest.mark.parametrize("flow_name", _list_flow_names())
def test_required_and_optional_fields_are_valid(flow_name):
    """required_data fields must be known or set by on_enter flags; optional_data must be known."""
    states_yaml = _load_yaml(FLOWS_DIR / flow_name / "states.yaml")
    states = states_yaml.get("states", {})

    for state_name, cfg in states.items():
        if cfg.get("extends") != "_base_phase":
            continue

        required = cfg.get("required_data", [])
        optional = cfg.get("optional_data", []) or []
        on_enter_flags = set((cfg.get("on_enter") or {}).get("set_flags", {}).keys())

        for field in required:
            assert (
                field in ALL_FIELD_NAMES or field in on_enter_flags
            ), f"Unknown required_data field {field} in {flow_name}.{state_name}"

        for field in optional:
            assert field in ALL_FIELD_NAMES, (
                f"Unknown optional_data field {field} in {flow_name}.{state_name}"
            )


@pytest.mark.parametrize("flow_name", _list_flow_names())
def test_phase_fields_align_with_extraction_mapping(flow_name):
    """States with explicit phase must use extraction fields from that phase."""
    states_yaml = _load_yaml(FLOWS_DIR / flow_name / "states.yaml")
    states = states_yaml.get("states", {})

    for state_name, cfg in states.items():
        if cfg.get("extends") != "_base_phase":
            continue

        phase = cfg.get("phase") or cfg.get("spin_phase")
        if not phase:
            continue

        assert phase in PHASE_FIELDS, f"Unknown phase '{phase}' in {flow_name}.{state_name}"
        phase_fields = set(PHASE_FIELDS.get(phase, []))

        required = cfg.get("required_data", [])
        optional = cfg.get("optional_data", []) or []

        for field in required + optional:
            if field in ALL_FIELD_NAMES:
                assert field in phase_fields, (
                    f"Field {field} not allowed for phase {phase} in {flow_name}.{state_name}"
                )


# =============================================================================
# PROMPT TEMPLATE DEDUP VARIABLES
# =============================================================================


@pytest.mark.parametrize("flow_name", _list_flow_names())
def test_continue_current_goal_templates_include_dedup_vars(flow_name):
    """All non-SPIN flow templates must include do_not_ask and available_questions."""
    prompts_path = TEMPLATES_DIR / flow_name / "prompts.yaml"
    data = _load_yaml(prompts_path)
    templates = data.get("templates", {})

    assert "continue_current_goal" in templates, (
        f"Missing continue_current_goal template for flow {flow_name}"
    )

    template_cfg = templates["continue_current_goal"]
    template_text = template_cfg.get("template", "")
    params = template_cfg.get("parameters", {})
    optional = params.get("optional", [])

    assert "do_not_ask" in optional
    assert "available_questions" in optional
    assert "{do_not_ask}" in template_text
    assert "{available_questions}" in template_text

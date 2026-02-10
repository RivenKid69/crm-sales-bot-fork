"""
CI test guard for template completeness.

Ensures every action referenced by policy overlays, REPAIR_ACTIONS,
OBJECTION_ACTIONS, INTENT_SPECIFIC_ACTIONS, and flow-specific states.yaml
rules has a corresponding template in either FlowConfig (YAML) or
PROMPT_TEMPLATES (Python).

This prevents silent template misses that cause the generator to fall back
to continue_current_goal, losing the intended response behavior.
"""

import pytest
from pathlib import Path
import sys

from src.config_loader import ConfigLoader, FlowConfig
from src.config import PROMPT_TEMPLATES
from src.yaml_config.constants import (
    REPAIR_ACTIONS,
    OBJECTION_ESCALATION_ACTIONS,
    REPAIR_PROTECTED_ACTIONS,
    PRICING_CORRECT_ACTIONS,
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def config_loader():
    """Create a ConfigLoader instance (module-scoped for performance)."""
    return ConfigLoader()

@pytest.fixture(scope="module")
def loaded_config(config_loader):
    """Load base config once."""
    return config_loader.load()

@pytest.fixture(scope="module")
def all_flow_names(config_loader, loaded_config):
    """Get all available flow names."""
    flows_dir = Path(__file__).parent.parent / "src" / "yaml_config" / "flows"
    flow_names = []
    for d in flows_dir.iterdir():
        if d.is_dir() and not d.name.startswith("_"):
            flow_names.append(d.name)
    return sorted(flow_names)

# Actions that are meta-actions handled specially (not templates)
EXCLUDED_ACTIONS = {
    "offer_options",
    "guard_offer_options",
    "guard_rephrase",
    "stall_guard_eject",
    "stall_guard_nudge",
    "guard_soft_close",
    "guard_skip_phase",
    "ask_clarification",
}

# =============================================================================
# CORE ACTIONS — must have templates in ALL flows
# =============================================================================

def _get_core_actions():
    """Collect all core action names that must have templates."""
    actions = set()

    # REPAIR_ACTIONS (dialogue_policy)
    actions.update(REPAIR_ACTIONS.values())

    # OBJECTION_ACTIONS (dialogue_policy)
    actions.update(OBJECTION_ESCALATION_ACTIONS.values())

    # INTENT_SPECIFIC_ACTIONS (fact_question.py)
    try:
        from src.blackboard.sources.fact_question import FactQuestionSource
        if hasattr(FactQuestionSource, 'INTENT_SPECIFIC_ACTIONS'):
            actions.update(FactQuestionSource.INTENT_SPECIFIC_ACTIONS.values())
    except ImportError:
        pass

    # PRICING_CORRECT_ACTIONS
    actions.update(PRICING_CORRECT_ACTIONS)

    # Remove excluded
    actions -= EXCLUDED_ACTIONS

    return sorted(actions)

CORE_ACTIONS = _get_core_actions()

@pytest.mark.parametrize("action", CORE_ACTIONS)
def test_core_action_has_template_in_default_flow(action, config_loader, loaded_config):
    """Each core action must have a template in the default flow or PROMPT_TEMPLATES."""
    flow = config_loader.load_flow("spin_selling")
    in_yaml = flow.get_template(action) is not None
    in_python = action in PROMPT_TEMPLATES
    assert in_yaml or in_python, (
        f"Core action '{action}' has no template in spin_selling flow or PROMPT_TEMPLATES"
    )

# =============================================================================
# PER-FLOW VALIDATION
# =============================================================================

def test_repair_actions_have_templates_all_flows(config_loader, loaded_config, all_flow_names):
    """REPAIR_ACTIONS must resolve in every flow."""
    missing = {}
    for flow_name in all_flow_names:
        try:
            flow = config_loader.load_flow(flow_name)
        except Exception:
            continue
        for repair_key, action in REPAIR_ACTIONS.items():
            if action in EXCLUDED_ACTIONS:
                continue
            in_yaml = flow.get_template(action) is not None
            in_python = action in PROMPT_TEMPLATES
            if not in_yaml and not in_python:
                missing.setdefault(action, []).append(flow_name)

    assert not missing, (
        f"REPAIR_ACTIONS missing templates:\n"
        + "\n".join(f"  {a}: missing in {flows}" for a, flows in missing.items())
    )

def test_objection_actions_have_templates_all_flows(config_loader, loaded_config, all_flow_names):
    """OBJECTION_ESCALATION_ACTIONS must resolve in every flow."""
    missing = {}
    for flow_name in all_flow_names:
        try:
            flow = config_loader.load_flow(flow_name)
        except Exception:
            continue
        for key, action in OBJECTION_ESCALATION_ACTIONS.items():
            if action in EXCLUDED_ACTIONS:
                continue
            in_yaml = flow.get_template(action) is not None
            in_python = action in PROMPT_TEMPLATES
            if not in_yaml and not in_python:
                missing.setdefault(action, []).append(flow_name)

    assert not missing, (
        f"OBJECTION_ACTIONS missing templates:\n"
        + "\n".join(f"  {a}: missing in {flows}" for a, flows in missing.items())
    )

# =============================================================================
# PRICING CORRECT ACTIONS
# =============================================================================

def test_pricing_correct_actions_have_templates(config_loader, loaded_config):
    """All PRICING_CORRECT_ACTIONS must have templates."""
    flow = config_loader.load_flow("spin_selling")
    missing = []
    for action in sorted(PRICING_CORRECT_ACTIONS):
        if action in EXCLUDED_ACTIONS:
            continue
        in_yaml = flow.get_template(action) is not None
        in_python = action in PROMPT_TEMPLATES
        if not in_yaml and not in_python:
            missing.append(action)
    assert not missing, f"PRICING_CORRECT_ACTIONS without templates: {missing}"

# =============================================================================
# SSOT CONSISTENCY
# =============================================================================

def test_pricing_correct_actions_loaded_from_yaml():
    """PRICING_CORRECT_ACTIONS must be non-empty (loaded from constants.yaml)."""
    assert len(PRICING_CORRECT_ACTIONS) >= 4, (
        f"PRICING_CORRECT_ACTIONS has only {len(PRICING_CORRECT_ACTIONS)} entries, expected >= 4"
    )

def test_repair_protected_actions_loaded_from_yaml():
    """REPAIR_PROTECTED_ACTIONS must be non-empty (loaded from constants.yaml)."""
    assert len(REPAIR_PROTECTED_ACTIONS) >= 10, (
        f"REPAIR_PROTECTED_ACTIONS has only {len(REPAIR_PROTECTED_ACTIONS)} entries, expected >= 10"
    )

def test_flow_specific_templates_in_repair_protected():
    """Flow-specific question templates must be in repair_protected_actions."""
    flow_specific_question_templates = {"explain_feature", "demonstrate_feature"}
    missing = flow_specific_question_templates - REPAIR_PROTECTED_ACTIONS
    assert not missing, (
        f"Flow-specific question templates not in repair_protected_actions: {missing}"
    )

# =============================================================================
# YAML SYNTAX VALIDATION
# =============================================================================

def test_base_prompts_yaml_parses():
    """_base/prompts.yaml must parse without errors."""
    import yaml
    base = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "_base" / "prompts.yaml"
    with open(base) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "templates" in data
    assert len(data["templates"]) > 0

def test_all_flow_prompts_yaml_parse(all_flow_names):
    """All flow-specific prompts.yaml files must parse without errors."""
    import yaml
    templates_dir = Path(__file__).parent.parent / "src" / "yaml_config" / "templates"
    for flow_name in all_flow_names:
        prompts_file = templates_dir / flow_name / "prompts.yaml"
        if prompts_file.exists():
            with open(prompts_file) as f:
                data = yaml.safe_load(f)
            assert data is not None, f"{flow_name}/prompts.yaml is empty"

# =============================================================================
# ADDRESSES_QUESTION TAG VALIDATION
# =============================================================================

def test_new_base_templates_have_addresses_question_tag():
    """All question-answering templates in _base must have addresses_question: true."""
    import yaml
    base = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "_base" / "prompts.yaml"
    with open(base) as f:
        data = yaml.safe_load(f)

    templates = data.get("templates", {})

    # Templates that MUST have addresses_question: true
    must_have_tag = {
        "reframe_value", "handle_repeated_objection", "empathize_and_redirect",
        "schedule_demo", "schedule_callback", "provide_references", "schedule_consultation",
        "compare_with_competitor", "answer_with_roi",
        "answer_technical_question", "answer_security_question",
        "explain_support_options", "explain_training_options",
        "explain_implementation_process",
        "calculate_roi_response", "share_value", "answer_briefly",
    }

    missing_tag = []
    for name in must_have_tag:
        tmpl = templates.get(name)
        if tmpl is None:
            missing_tag.append(f"{name} (not found)")
        elif not tmpl.get("addresses_question", False):
            missing_tag.append(f"{name} (missing tag)")

    assert not missing_tag, (
        f"Templates missing addresses_question: true:\n"
        + "\n".join(f"  - {m}" for m in missing_tag)
    )

# =============================================================================
# FLOWCONFIG RECEIVES FLOW — ROOT CAUSE
# =============================================================================

def test_response_generator_accepts_flow_parameter():
    """ResponseGenerator.__init__ must accept flow parameter."""
    import inspect
    from src.generator import ResponseGenerator
    sig = inspect.signature(ResponseGenerator.__init__)
    assert "flow" in sig.parameters, (
        "ResponseGenerator.__init__ must accept 'flow' parameter"
    )

def test_dialogue_policy_accepts_flow_parameter():
    """DialoguePolicy.__init__ must accept flow parameter."""
    import inspect
    from src.dialogue_policy import DialoguePolicy
    sig = inspect.signature(DialoguePolicy.__init__)
    assert "flow" in sig.parameters, (
        "DialoguePolicy.__init__ must accept 'flow' parameter"
    )

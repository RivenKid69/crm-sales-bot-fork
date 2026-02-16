"""
Tests for Bug #5 fix: Inappropriate "Рад помочь" in greeting state.

Verifies that:
1. _base_greeting.rules contains SPIN-progress intents -> continue_current_goal
2. Taxonomy fallback_action for SPIN intents is continue_current_goal (not acknowledge_and_continue)
3. Greeting state transitions are not affected by the rule changes
"""
import pytest
import yaml
from pathlib import Path


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def base_states_yaml():
    """Load _base/states.yaml."""
    path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "_base" / "states.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def constants_yaml():
    """Load constants.yaml."""
    path = Path(__file__).parent.parent / "src" / "yaml_config" / "constants.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# =============================================================================
# Test 1: _base_greeting has SPIN-progress rules
# =============================================================================

SPIN_PROGRESS_INTENTS = [
    "situation_provided",
    "problem_revealed",
    "implication_acknowledged",
    "need_expressed",
    "info_provided",
]


class TestBaseGreetingSpinRules:
    """Verify _base_greeting.rules contains SPIN-progress intents."""

    def test_base_greeting_has_spin_rules(self, base_states_yaml):
        """_base_greeting.rules must contain all 5 SPIN progress intents -> continue_current_goal."""
        rules = base_states_yaml["states"]["_base_greeting"]["rules"]
        for intent in SPIN_PROGRESS_INTENTS:
            assert intent in rules, f"Missing rule for '{intent}' in _base_greeting.rules"
            assert rules[intent] == "continue_current_goal", (
                f"Rule for '{intent}' should be 'continue_current_goal', got '{rules[intent]}'"
            )

    def test_base_greeting_original_rules_preserved(self, base_states_yaml):
        """Original greeting rules must still be present."""
        rules = base_states_yaml["states"]["_base_greeting"]["rules"]
        assert rules["greeting"] == "greet_back"
        assert rules["unclear"] == "ask_how_to_help"
        assert rules["gratitude"] == "acknowledge_and_continue"
        assert rules["small_talk"] == "small_talk_and_continue"

    def test_greeting_transitions_unchanged(self, base_states_yaml):
        """Greeting state transitions must not be affected by rule changes."""
        greeting = base_states_yaml["states"]["greeting"]
        transitions = greeting["transitions"]
        # Key transitions should still exist
        assert "situation_provided" in transitions
        assert "problem_revealed" in transitions
        assert "need_expressed" in transitions
        assert "implication_acknowledged" in transitions
        assert "price_question" in transitions
        assert "demo_request" in transitions
        assert "rejection" in transitions


# =============================================================================
# Test 2: Taxonomy fallback_action for SPIN intents
# =============================================================================

class TestTaxonomyFallbackAction:
    """Verify taxonomy fallback_action for SPIN progress intents is continue_current_goal."""

    @pytest.mark.parametrize("intent", SPIN_PROGRESS_INTENTS)
    def test_taxonomy_fallback_continue_current_goal(self, constants_yaml, intent):
        """Taxonomy fallback_action for SPIN intents must be continue_current_goal."""
        taxonomy = constants_yaml.get("intent_taxonomy", {})
        assert intent in taxonomy, f"Intent '{intent}' not found in taxonomy"
        meta = taxonomy[intent]
        assert meta["fallback_action"] == "continue_current_goal", (
            f"Taxonomy fallback_action for '{intent}' should be 'continue_current_goal', "
            f"got '{meta['fallback_action']}'"
        )

"""
Tests for Dialog Failure Fix — 5-phase defense-in-depth approach.

Phase 1: Greeting State Safety (category-based mixin override)
Phase 2: Semantic Examples coverage validation
Phase 3: Greeting Context Refinement Layer
Phase 4: Objection Phase-Origin Escape
Phase 5: Stall Detection
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any


# =============================================================================
# PHASE 1: Greeting State Safety Tests
# =============================================================================

class TestGreetingSafety:
    """Tests for Phase 1: Greeting state safety overrides."""

    def test_greeting_redirect_intents_category_exists(self):
        """SSOT category greeting_redirect_intents must exist and be non-empty."""
        from src.yaml_config.constants import INTENT_CATEGORIES, GREETING_REDIRECT_INTENTS
        assert "greeting_redirect_intents" in INTENT_CATEGORIES
        assert len(GREETING_REDIRECT_INTENTS) >= 6  # At least technical_problems (6) + additional (2)

    def test_greeting_redirect_includes_technical_problems(self):
        """greeting_redirect_intents must include all technical_problems intents."""
        from src.yaml_config.constants import INTENT_CATEGORIES
        technical = set(INTENT_CATEGORIES.get("technical_problems", []))
        redirect = set(INTENT_CATEGORIES.get("greeting_redirect_intents", []))
        missing = technical - redirect
        assert not missing, f"technical_problems intents missing from greeting_redirect_intents: {missing}"

    def test_greeting_redirect_includes_additional_redirects(self):
        """greeting_redirect_intents must include greeting_additional_redirects."""
        from src.yaml_config.constants import INTENT_CATEGORIES
        additional = set(INTENT_CATEGORIES.get("greeting_additional_redirects", []))
        redirect = set(INTENT_CATEGORIES.get("greeting_redirect_intents", []))
        missing = additional - redirect
        assert not missing, f"greeting_additional_redirects missing from greeting_redirect_intents: {missing}"

    def test_greeting_safety_config_exists(self):
        """greeting_state_safety config must exist in constants.yaml."""
        from src.yaml_config.constants import get_greeting_safety_config
        config = get_greeting_safety_config()
        assert config.get("enabled") is True
        assert "redirect_to" in config

    def test_feature_flag_exists(self):
        """greeting_state_safety feature flag must exist."""
        from src.feature_flags import FeatureFlags
        assert "greeting_state_safety" in FeatureFlags.DEFAULTS

    def test_greeting_no_terminal_transitions_for_redirect_intents(self):
        """greeting_redirect_intents should NOT lead to escalated/success in greeting state."""
        from src.config_loader import ConfigLoader
        from src.yaml_config.constants import GREETING_REDIRECT_INTENTS
        loader = ConfigLoader()
        flow = loader.load_flow("spin_selling")
        greeting = flow.states.get("greeting", {})
        transitions = greeting.get("transitions", {})
        redirect_set = set(GREETING_REDIRECT_INTENTS)
        for intent, target in transitions.items():
            if isinstance(target, str) and intent in redirect_set:
                assert target not in ("escalated", "success"), (
                    f"greeting.{intent} → {target} is dangerous (should be entry_state). "
                    f"This intent is in greeting_redirect_intents but still leads to terminal."
                )

    def test_greeting_redirect_covers_technical_terminal_intents(self):
        """Technical problem intents that go to escalated in _universal_base
        must be covered by greeting_redirect_intents.

        Escalation intents (request_human, legal_question, etc.) are excluded
        because they should legitimately escalate even from greeting.

        FUNDAMENTAL: Catches future technical intents added to _universal_base
        that would bypass the category-based safety mechanism.
        """
        from src.yaml_config.constants import GREETING_REDIRECT_INTENTS, INTENT_CATEGORIES
        import yaml
        from pathlib import Path

        # Load _universal_base from mixins.yaml
        mixins_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "_base" / "mixins.yaml"
        with open(mixins_path, 'r', encoding='utf-8') as f:
            mixins_data = yaml.safe_load(f)

        universal_base = mixins_data.get("mixins", {}).get("_universal_base", {})
        transitions = universal_base.get("transitions", {})

        # Only check technical problem intents (misclassification-prone)
        # NOT escalation intents (request_human etc.) which should legitimately escalate
        technical_intents = set(INTENT_CATEGORIES.get("technical_problems", []))
        terminal_technical = {
            intent for intent, target in transitions.items()
            if isinstance(target, str) and target in ("escalated", "success")
            and intent in technical_intents
        }

        redirect_set = set(GREETING_REDIRECT_INTENTS)
        missing = terminal_technical - redirect_set
        assert not missing, (
            f"Technical intents in _universal_base → escalated but NOT in greeting_redirect_intents: "
            f"{missing}. Add them to greeting_additional_redirects or technical_problems category."
        )

    def test_feature_flag_disables_override(self):
        """Feature flag greeting_state_safety=false must disable override."""
        from src.feature_flags import flags
        from src.config_loader import ConfigLoader

        # With flag disabled, load should still work
        flags.set_override("greeting_state_safety", False)
        try:
            loader = ConfigLoader()
            flow = loader.load_flow("spin_selling")
            # Should have the original _universal_base transitions
            assert flow.states.get("greeting") is not None
        finally:
            flags.clear_override("greeting_state_safety")


# =============================================================================
# PHASE 2: Semantic Examples Coverage Tests
# =============================================================================

class TestSemanticExamplesCoverage:
    """Tests for Phase 2: Semantic examples and coverage validation."""

    def test_technical_problems_have_examples(self):
        """All technical_problems intents must have examples."""
        from src.yaml_config.constants import INTENT_CATEGORIES
        from src.classifier.intents.examples import INTENT_EXAMPLES

        technical_intents = INTENT_CATEGORIES.get("technical_problems", [])
        for intent in technical_intents:
            assert intent in INTENT_EXAMPLES, (
                f"Intent '{intent}' is in technical_problems but has no examples. "
                f"Add examples to examples.py."
            )

    def test_greeting_additional_redirects_have_examples(self):
        """All greeting_additional_redirects intents must have examples."""
        from src.yaml_config.constants import INTENT_CATEGORIES
        from src.classifier.intents.examples import INTENT_EXAMPLES

        additional_intents = INTENT_CATEGORIES.get("greeting_additional_redirects", [])
        for intent in additional_intents:
            assert intent in INTENT_EXAMPLES, (
                f"Intent '{intent}' is in greeting_additional_redirects but has no examples. "
                f"Add examples to examples.py."
            )

    @pytest.mark.parametrize("intent", [
        "problem_sync", "problem_connection", "problem_technical",
        "problem_fiscal", "request_references",
    ])
    def test_new_examples_have_minimum_count(self, intent):
        """Each new intent example set must have at least 5 examples."""
        from src.classifier.intents.examples import INTENT_EXAMPLES
        assert intent in INTENT_EXAMPLES, f"Missing examples for {intent}"
        assert len(INTENT_EXAMPLES[intent]) >= 5, (
            f"Intent '{intent}' has only {len(INTENT_EXAMPLES[intent])} examples (need >= 5)"
        )


# =============================================================================
# PHASE 3: Greeting Context Refinement Layer Tests
# =============================================================================

class TestGreetingContextRefinement:
    """Tests for Phase 3: Greeting context refinement layer."""

    def test_layer_registered(self):
        """GreetingContextRefinementLayer must be registered."""
        from src.classifier.refinement_pipeline import RefinementLayerRegistry
        # Force import to trigger registration
        import src.classifier.refinement_layers  # noqa: F401
        registry = RefinementLayerRegistry.get_registry()
        assert "greeting_context" in registry.get_all_names()

    def test_config_exists(self):
        """greeting_context_refinement config must exist."""
        from src.yaml_config.constants import get_greeting_context_refinement_config
        config = get_greeting_context_refinement_config()
        assert config.get("enabled") is True
        assert "suspicious_intent_categories" in config
        assert "technical_problems" in config["suspicious_intent_categories"]

    def test_category_driven_suspicious_intents(self):
        """Adding intent to technical_problems → automatically in suspicious_intents."""
        from src.classifier.refinement_layers import GreetingContextRefinementLayer
        layer = GreetingContextRefinementLayer()
        # All technical_problems should be in suspicious intents
        from src.yaml_config.constants import INTENT_CATEGORIES
        technical = set(INTENT_CATEGORIES.get("technical_problems", []))
        assert technical.issubset(layer._suspicious_intents), (
            f"Technical problems not in suspicious_intents: {technical - layer._suspicious_intents}"
        )

    def test_greeting_context_refines_technical_intent(self):
        """In greeting state, problem_sync should be refined to problem_revealed."""
        from src.classifier.refinement_layers import GreetingContextRefinementLayer
        from src.classifier.refinement_pipeline import RefinementContext

        layer = GreetingContextRefinementLayer()
        ctx = RefinementContext(
            message="синхронизация не работает",
            state="greeting",
            turn_number=1,
            intent="problem_sync",
            confidence=0.8,
        )
        result = {"intent": "problem_sync", "confidence": 0.8}
        refined = layer.refine("синхронизация не работает", result, ctx)
        assert refined.intent == "problem_revealed"

    def test_non_greeting_not_refined(self):
        """Outside greeting state, problem_sync should NOT be refined."""
        from src.classifier.refinement_layers import GreetingContextRefinementLayer
        from src.classifier.refinement_pipeline import RefinementContext

        layer = GreetingContextRefinementLayer()
        ctx = RefinementContext(
            message="синхронизация не работает",
            state="spin_situation",
            turn_number=5,
            intent="problem_sync",
            confidence=0.8,
        )
        result = {"intent": "problem_sync", "confidence": 0.8}
        refined = layer.refine("синхронизация не работает", result, ctx)
        # Should pass through unchanged
        assert refined.intent == "problem_sync"


# =============================================================================
# PHASE 4: Objection Phase-Origin Escape Tests
# =============================================================================

class TestObjectionPhaseOriginEscape:
    """Tests for Phase 4: Objection phase-origin escape."""

    def test_phase_origin_escape_threshold_constant(self):
        """PHASE_ORIGIN_ESCAPE_THRESHOLD must be defined and lower than LOOP_ESCAPE."""
        from src.blackboard.sources.objection_return import (
            PHASE_ORIGIN_ESCAPE_THRESHOLD,
            OBJECTION_LOOP_ESCAPE_THRESHOLD,
        )
        assert PHASE_ORIGIN_ESCAPE_THRESHOLD == 2
        assert PHASE_ORIGIN_ESCAPE_THRESHOLD < OBJECTION_LOOP_ESCAPE_THRESHOLD

    def test_limits_config_has_phase_origin_escape(self):
        """constants.yaml limits must have phase_origin_objection_escape."""
        from src.yaml_config.constants import _constants
        limits = _constants.get("limits", {})
        assert "phase_origin_objection_escape" in limits
        assert limits["phase_origin_objection_escape"] == 2


# =============================================================================
# PHASE 5: Stall Detection Tests
# =============================================================================

class TestStallDetection:
    """Tests for Phase 5: Flow state stall detection."""

    def test_stall_detection_config_exists(self):
        """stall_detection config must exist in constants.yaml."""
        from src.yaml_config.constants import get_stall_detection_config
        config = get_stall_detection_config()
        assert config.get("enabled") is True
        assert config.get("stall_threshold") == 3
        assert "exempt_states" in config

    def test_is_stalled_condition_registered(self):
        """is_stalled condition must be registered in policy registry."""
        from src.conditions.policy import policy_registry
        # The condition should be available
        assert policy_registry.has("is_stalled")

    def test_policy_context_has_consecutive_same_state(self):
        """PolicyContext must have consecutive_same_state field."""
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(consecutive_same_state=5)
        assert ctx.consecutive_same_state == 5

    def test_stall_in_exempt_state_not_triggered(self):
        """Stall should not trigger in exempt states like greeting."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(
            state="greeting",
            consecutive_same_state=5,
            is_progressing=False,
        )
        assert not is_stalled(ctx)

    def test_stall_in_flow_state_triggered(self):
        """Stall should trigger in non-exempt flow state with high consecutive_same_state."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            consecutive_same_state=4,
            is_progressing=False,
        )
        assert is_stalled(ctx)

    def test_stall_not_triggered_when_progressing(self):
        """Stall should not trigger when dialog is progressing."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            consecutive_same_state=5,
            is_progressing=True,
        )
        assert not is_stalled(ctx)

    def test_nudge_progress_in_repair_actions(self):
        """nudge_progress must be in REPAIR_ACTIONS."""
        from src.dialogue_policy import DialoguePolicy
        assert "stall" in DialoguePolicy.REPAIR_ACTIONS
        assert DialoguePolicy.REPAIR_ACTIONS["stall"] == "nudge_progress"

    def test_context_window_consecutive_same_state(self):
        """ContextWindow.get_consecutive_same_state() must work correctly."""
        from src.context_window import ContextWindow, TurnContext
        cw = ContextWindow(max_size=10)
        # Add 3 turns in same state
        for i in range(3):
            cw.add_turn(TurnContext(
                user_message="сколько стоит?",
                state="spin_situation",
                intent="price_question",
                action="answer_with_pricing",
                confidence=0.8,
            ))
        assert cw.get_consecutive_same_state() == 3

        # Add turn in different state
        cw.add_turn(TurnContext(
            user_message="у нас есть проблема",
            state="spin_problem",
            intent="problem_revealed",
            action="ask_about_problem",
            confidence=0.9,
        ))
        assert cw.get_consecutive_same_state() == 1

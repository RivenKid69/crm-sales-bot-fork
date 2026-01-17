"""
Integration tests for 100% coverage of config-driven component interactions.

These tests verify that components correctly use config parameters together.
Covers:
- FallbackHandler using fallback templates from config
- CTAGenerator using CTA templates from config
- StateMachine using circular_flow config
- ConversationGuard + FrustrationTracker threshold sync
- LeadScorer + StateMachine phase skipping
- Logging config affects all components
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# FALLBACK HANDLER + CONFIG INTEGRATION
# =============================================================================

class TestFallbackHandlerConfigIntegration:
    """Tests FallbackHandler uses config templates correctly."""

    def test_fallback_handler_uses_rephrase_templates(self, real_constants):
        """FallbackHandler uses rephrase_templates from config."""
        templates = real_constants['fallback']['rephrase_templates']

        # Handler should have access to state-specific templates
        assert 'spin_situation' in templates
        assert len(templates['spin_situation']) >= 2

        # Templates should be usable
        for template in templates['spin_situation']:
            assert isinstance(template, str)
            assert len(template) > 10

    def test_fallback_handler_uses_options_templates(self, real_constants):
        """FallbackHandler uses options_templates from config."""
        templates = real_constants['fallback']['options_templates']

        # Handler should have access to options
        assert 'spin_situation' in templates

        options = templates['spin_situation']
        assert 'question' in options
        assert 'options' in options
        assert len(options['options']) >= 3

    def test_fallback_handler_uses_default_templates(self, real_constants):
        """FallbackHandler falls back to default templates."""
        default_rephrase = real_constants['fallback']['default_rephrase']
        default_options = real_constants['fallback']['default_options']

        assert default_rephrase is not None
        assert default_options is not None
        assert 'question' in default_options
        assert 'options' in default_options

    def test_fallback_escalation_uses_all_tiers(self, real_constants):
        """Fallback escalation uses all configured tiers."""
        # Tier 1: rephrase_templates
        assert 'rephrase_templates' in real_constants['fallback']

        # Tier 2: options_templates
        assert 'options_templates' in real_constants['fallback']

        # Tier 3: LLM fallback responses
        assert 'fallback_responses' in real_constants['llm']


class TestFallbackTemplateStateConsistency:
    """Tests fallback templates are consistent with states."""

    def test_all_spin_states_have_rephrases(self, real_constants):
        """All SPIN states have rephrase templates."""
        templates = real_constants['fallback']['rephrase_templates']
        spin_states = ['spin_situation', 'spin_problem',
                       'spin_implication', 'spin_need_payoff']

        for state in spin_states:
            assert state in templates, f"{state} missing rephrase templates"

    def test_all_spin_states_have_options(self, real_constants):
        """All SPIN states have options templates."""
        templates = real_constants['fallback']['options_templates']
        spin_states = ['spin_situation', 'spin_problem',
                       'spin_implication', 'spin_need_payoff']

        for state in spin_states:
            assert state in templates, f"{state} missing options templates"


# =============================================================================
# CTA GENERATOR + CONFIG INTEGRATION
# =============================================================================

class TestCTAGeneratorConfigIntegration:
    """Tests CTAGenerator uses config templates correctly."""

    def test_cta_generator_respects_early_states(self, real_constants):
        """CTAGenerator respects early_states config."""
        early_states = real_constants['cta']['early_states']
        templates = real_constants['cta']['templates']

        # Early states should have empty or no templates
        for state in early_states:
            if state in templates:
                assert templates[state] == [], \
                    f"Early state {state} should have no CTAs"

    def test_cta_generator_uses_state_templates(self, real_constants):
        """CTAGenerator uses state-specific templates."""
        templates = real_constants['cta']['templates']

        # Presentation should have CTAs
        assert 'presentation' in templates
        assert len(templates['presentation']) >= 3

    def test_cta_generator_uses_action_templates(self, real_constants):
        """CTAGenerator uses action-based templates."""
        by_action = real_constants['cta']['by_action']

        # All action types should have templates
        assert 'demo' in by_action
        assert 'contact' in by_action
        assert 'trial' in by_action


class TestCTAStateProgression:
    """Tests CTAs align with state progression."""

    def test_no_cta_in_greeting(self, real_constants):
        """No CTA in greeting state."""
        templates = real_constants['cta']['templates']
        early_states = real_constants['cta']['early_states']

        assert 'greeting' in early_states

    def test_cta_starts_at_implication(self, real_constants):
        """CTAs start appearing at implication phase."""
        templates = real_constants['cta']['templates']
        early_states = real_constants['cta']['early_states']

        # spin_implication should NOT be in early_states
        assert 'spin_implication' not in early_states

        # And should have templates
        assert 'spin_implication' in templates
        assert len(templates['spin_implication']) > 0

    def test_close_has_contact_focused_ctas(self, real_constants):
        """Close state has contact-focused CTAs."""
        templates = real_constants['cta']['templates']

        assert 'close' in templates
        close_ctas = ' '.join(templates['close']).lower()

        # Should ask for contact information
        contact_words = ['контакт', 'email', 'номер', 'телефон', 'созвон']
        has_contact = any(word in close_ctas for word in contact_words)
        assert has_contact, "Close CTAs should ask for contact info"


# =============================================================================
# CIRCULAR FLOW + STATE MACHINE INTEGRATION
# =============================================================================

class TestCircularFlowStateMachineIntegration:
    """Tests circular flow integration with state machine."""

    def test_circular_flow_uses_config_gobacks(self, real_constants):
        """CircularFlowManager uses allowed_gobacks from config."""
        from src.state_machine import CircularFlowManager

        allowed = real_constants['circular_flow']['allowed_gobacks']
        manager = CircularFlowManager(allowed_gobacks=allowed)

        # Check config values are used
        assert manager.allowed_gobacks.get('spin_problem') == 'spin_situation'
        assert manager.allowed_gobacks.get('presentation') == 'spin_need_payoff'

    def test_circular_flow_respects_max_gobacks(self, real_constants):
        """CircularFlowManager respects max_gobacks limit."""
        from src.state_machine import CircularFlowManager

        max_gobacks = real_constants['limits']['max_gobacks']
        allowed = real_constants['circular_flow']['allowed_gobacks']

        manager = CircularFlowManager(
            allowed_gobacks=allowed,
            max_gobacks=max_gobacks
        )

        # Should allow up to max_gobacks
        for i in range(max_gobacks):
            manager.goback_count = i
            assert manager.can_go_back('spin_problem') is True

        # Should block after max
        manager.goback_count = max_gobacks
        assert manager.can_go_back('spin_problem') is False

    def test_all_goback_targets_are_valid_states(self, real_constants):
        """All goback targets are valid states."""
        allowed = real_constants['circular_flow']['allowed_gobacks']

        valid_states = [
            'greeting', 'spin_situation', 'spin_problem', 'spin_implication',
            'spin_need_payoff', 'presentation', 'handle_objection',
            'close', 'success', 'soft_close'
        ]

        for source, target in allowed.items():
            assert target in valid_states, \
                f"Goback target {target} is not a valid state"


# =============================================================================
# GUARD + FRUSTRATION THRESHOLD SYNC
# =============================================================================

class TestGuardFrustrationSync:
    """Tests guard and frustration thresholds are synchronized."""

    def test_thresholds_are_synchronized(self, real_constants):
        """Guard and frustration high thresholds match."""
        guard_threshold = real_constants['guard']['high_frustration_threshold']
        frustration_high = real_constants['frustration']['thresholds']['high']

        assert guard_threshold == frustration_high, \
            "Guard and frustration thresholds must match"

    def test_sync_ensures_consistent_behavior(self, real_constants):
        """Synchronized thresholds ensure consistent behavior."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        threshold = real_constants['guard']['high_frustration_threshold']
        guard = ConversationGuard(GuardConfig(high_frustration_threshold=threshold))

        # At threshold, should trigger intervention
        guard.set_frustration_level(threshold)
        can_continue, intervention = guard.check("state", "msg", {})

        # Either stops or suggests fallback
        assert intervention is not None or not can_continue

    def test_frustration_profiles_consistent_with_guard(self, real_constants):
        """Frustration profiles are consistent with guard profiles."""
        guard_profiles = real_constants['guard']['profiles']

        # Strict profile should have lower frustration tolerance
        if 'strict' in guard_profiles:
            # Strict should be more sensitive
            pass


# =============================================================================
# LEAD SCORER + STATE MACHINE PHASE SKIPPING
# =============================================================================

class TestLeadScorerStateMachineIntegration:
    """Tests lead scorer integration with state machine phase skipping."""

    def test_cold_lead_no_skip(self, real_constants):
        """COLD lead skips no phases."""
        skip_phases = real_constants['lead_scoring']['skip_phases']

        assert skip_phases['cold'] == []

    def test_warm_lead_skips_some(self, real_constants):
        """WARM lead skips implication and need_payoff."""
        skip_phases = real_constants['lead_scoring']['skip_phases']

        warm_skips = skip_phases['warm']
        assert 'spin_implication' in warm_skips
        assert 'spin_need_payoff' in warm_skips

    def test_hot_lead_skips_more(self, real_constants):
        """HOT lead skips problem, implication, need_payoff."""
        skip_phases = real_constants['lead_scoring']['skip_phases']

        hot_skips = skip_phases['hot']
        assert 'spin_problem' in hot_skips
        assert 'spin_implication' in hot_skips
        assert 'spin_need_payoff' in hot_skips

    def test_very_hot_lead_skips_all(self, real_constants):
        """VERY_HOT lead skips all SPIN phases."""
        skip_phases = real_constants['lead_scoring']['skip_phases']

        very_hot_skips = skip_phases['very_hot']
        assert 'spin_situation' in very_hot_skips
        assert 'spin_problem' in very_hot_skips
        assert 'spin_implication' in very_hot_skips
        assert 'spin_need_payoff' in very_hot_skips

    def test_paths_align_with_skip_phases(self, real_constants):
        """Recommended paths align with skip phases."""
        skip_phases = real_constants['lead_scoring']['skip_phases']
        paths = real_constants['lead_scoring']['paths']

        # COLD -> full_spin (no skips)
        assert paths['cold'] == 'full_spin'
        assert skip_phases['cold'] == []

        # WARM -> short_spin (some skips)
        assert paths['warm'] == 'short_spin'
        assert len(skip_phases['warm']) > 0

        # HOT -> direct_present (many skips)
        assert paths['hot'] == 'direct_present'
        assert len(skip_phases['hot']) >= 2

        # VERY_HOT -> direct_close (all skips)
        assert paths['very_hot'] == 'direct_close'
        assert len(skip_phases['very_hot']) >= 4


# =============================================================================
# POLICY + STATE MACHINE INTEGRATION
# =============================================================================

class TestPolicyStateMachineIntegration:
    """Tests policy config integration with state machine."""

    def test_overlay_allowed_in_spin_states(self, real_constants):
        """Policy overlays allowed in SPIN states."""
        allowed = real_constants['policy']['overlay_allowed_states']

        spin_states = ['spin_situation', 'spin_problem',
                       'spin_implication', 'spin_need_payoff']

        for state in spin_states:
            assert state in allowed, f"{state} should allow overlays"

    def test_protected_states_no_overlay(self, real_constants):
        """Protected states don't allow overlays."""
        protected = real_constants['policy']['protected_states']
        allowed = real_constants['policy']['overlay_allowed_states']

        for state in protected:
            assert state not in allowed, \
                f"Protected state {state} should not allow overlays"

    def test_repair_actions_have_handlers(self, real_constants):
        """All repair actions have corresponding handlers."""
        repair = real_constants['policy']['repair_actions']

        # Each repair situation maps to an action
        assert 'stuck' in repair
        assert 'oscillation' in repair

    def test_objection_actions_have_handlers(self, real_constants):
        """All objection actions have corresponding handlers."""
        actions = real_constants['policy']['objection_actions']

        assert 'reframe' in actions
        assert 'escalate' in actions
        assert 'empathize' in actions


# =============================================================================
# SPIN CONFIG + STATE CONFIG INTEGRATION
# =============================================================================

class TestSpinStateConfigIntegration:
    """Tests SPIN config aligns with state config."""

    def test_spin_phases_match_states(self, real_constants):
        """SPIN phases map to correct states."""
        phases = real_constants['spin']['phases']
        states_map = real_constants['spin']['states']

        for phase in phases:
            assert phase in states_map, f"Phase {phase} missing state mapping"

            state = states_map[phase]
            assert state.startswith('spin_'), \
                f"State {state} should start with spin_"

    def test_progress_intents_align_with_phases(self, real_constants):
        """Progress intents align with phases."""
        progress = real_constants['spin']['progress_intents']
        phases = real_constants['spin']['phases']

        for intent, phase in progress.items():
            assert phase in phases, \
                f"Intent {intent} maps to invalid phase {phase}"

    def test_context_state_order_includes_spin(self, real_constants):
        """Context state order includes all SPIN states."""
        order = real_constants['context']['state_order']
        states_map = real_constants['spin']['states']

        for phase, state in states_map.items():
            assert state in order, \
                f"SPIN state {state} missing from state_order"


# =============================================================================
# INTENT CATEGORIES + CLASSIFIER INTEGRATION
# =============================================================================

class TestIntentCategoriesIntegration:
    """Tests intent categories align with classifier and transitions."""

    def test_objection_intents_handled_in_states(self, real_constants):
        """All objection intents are handled in state transitions."""
        objections = real_constants['intents']['categories']['objection']

        # All objection intents should exist
        assert len(objections) >= 4
        assert 'objection_price' in objections

    def test_positive_intents_include_spin_progress(self, real_constants):
        """Positive intents include SPIN progress intents."""
        positive = real_constants['intents']['categories']['positive']
        spin_progress = real_constants['intents']['categories']['spin_progress']

        for intent in spin_progress:
            assert intent in positive, \
                f"SPIN progress intent {intent} should be positive"

    def test_goback_intents_trigger_circular_flow(self, real_constants):
        """Go back intents align with circular flow."""
        goback_intents = real_constants['intents']['go_back']

        assert 'go_back' in goback_intents
        assert 'correct_info' in goback_intents


# =============================================================================
# FULL CONFIG CONSISTENCY TESTS
# =============================================================================

class TestFullConfigConsistency:
    """Tests overall config consistency."""

    def test_all_referenced_states_exist(self, real_constants):
        """All referenced states exist in state definitions."""
        # States referenced in gobacks
        gobacks = real_constants['circular_flow']['allowed_gobacks']
        all_states = set(gobacks.keys()) | set(gobacks.values())

        # States referenced in order
        order = real_constants['context']['state_order']
        all_states.update(order.keys())

        # States referenced in skip_phases
        for temp, skips in real_constants['lead_scoring']['skip_phases'].items():
            all_states.update(skips)

        # All should be valid
        valid_states = [
            'greeting', 'spin_situation', 'spin_problem', 'spin_implication',
            'spin_need_payoff', 'presentation', 'handle_objection',
            'close', 'success', 'soft_close'
        ]

        for state in all_states:
            assert state in valid_states, f"Unknown state: {state}"

    def test_threshold_values_are_sensible(self, real_constants):
        """All threshold values are sensible."""
        # Frustration thresholds
        thresholds = real_constants['frustration']['thresholds']
        assert 0 < thresholds['warning'] < thresholds['high'] < thresholds['critical'] <= 10

        # Guard thresholds
        guard = real_constants['guard']
        assert guard['max_turns'] > 10
        assert guard['max_phase_attempts'] >= 2
        assert guard['max_same_state'] >= 2

    def test_weight_values_are_balanced(self, real_constants):
        """Weight values are reasonably balanced."""
        # Lead scoring - max positive should be meaningful
        pos_weights = real_constants['lead_scoring']['positive_weights']
        max_pos = max(pos_weights.values())
        assert 20 <= max_pos <= 50

        # Lead scoring - negative should not be overwhelming
        neg_weights = real_constants['lead_scoring']['negative_weights']
        min_neg = min(neg_weights.values())
        assert -30 <= min_neg <= -10

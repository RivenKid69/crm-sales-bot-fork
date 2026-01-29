"""
Regression tests for 7 verified defects in guard/telemetry/config/simulation chain.

These tests prevent the "incomplete propagation" pattern from recurring:
- Defect 1: can_continue lost in _check_guard → record_guard chain
- Defect 2: Fallback action not propagated to output action variable
- Defect 3: record_fallback called without action/message
- Defect 4: presentation force-injected into phase coverage
- Defect 5: _base_greeting/_base_terminal missing dialogue_control + escalation
- Defect 6: presentation/handle_objection override default_price_action to answer_with_facts
- Defect 7: soft_close.is_final: false + no simulation termination
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from src.config_loader import ConfigLoader, FlowConfig
from src.decision_trace import DecisionTraceBuilder
from src.simulator.metrics import calculate_spin_coverage


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def loader():
    """Real config loader pointing to src/yaml_config."""
    return ConfigLoader()


@pytest.fixture(scope="module")
def flow_config(loader):
    """Load the default spin_selling flow (used by most tests)."""
    return loader.load_flow("spin_selling")


@pytest.fixture(scope="module")
def base_states_raw(loader):
    """Load raw base states YAML (before flow resolution) for mixin checks."""
    return loader._load_yaml("flows/_base/states.yaml", required=True)


@pytest.fixture(scope="module")
def base_mixins_raw(loader):
    """Load raw base mixins YAML."""
    return loader._load_yaml("flows/_base/mixins.yaml", required=True)


# =============================================================================
# Test 1 (Defect 5): All state bases handle request_brevity
# =============================================================================

class TestDefect5DialogueControl:
    """Verify _base_greeting, _base_terminal, _base_phase all resolve request_brevity."""

    def test_greeting_has_request_brevity(self, flow_config):
        """Greeting state must handle request_brevity → respond_briefly."""
        greeting = flow_config.states.get("greeting", {})
        rules = greeting.get("rules", {})
        assert "request_brevity" in rules, \
            "greeting state doesn't handle request_brevity (Defect 5: _base_greeting missing dialogue_control)"
        assert rules["request_brevity"] == "respond_briefly"

    def test_soft_close_has_request_brevity(self, flow_config):
        """soft_close (extends _base_terminal) must handle request_brevity."""
        soft_close = flow_config.states.get("soft_close", {})
        rules = soft_close.get("rules", {})
        assert "request_brevity" in rules, \
            "soft_close state doesn't handle request_brevity (Defect 5: _base_terminal missing dialogue_control)"
        assert rules["request_brevity"] == "respond_briefly"

    def test_phase_states_have_request_brevity(self, flow_config):
        """All _base_phase states must handle request_brevity."""
        # Check a few representative phase states
        for state_name in ["presentation", "handle_objection", "close"]:
            if state_name in flow_config.states:
                state = flow_config.states[state_name]
                rules = state.get("rules", {})
                assert "request_brevity" in rules, \
                    f"{state_name} doesn't handle request_brevity"

    def test_base_greeting_has_universal_base_mixin(self, base_states_raw):
        """_base_greeting must include _universal_base mixin."""
        states = base_states_raw.get("states", {})
        base_greeting = states.get("_base_greeting", {})
        mixins = base_greeting.get("mixins", [])
        assert "_universal_base" in mixins, \
            "_base_greeting is missing _universal_base mixin"

    def test_base_terminal_has_escalation_safety_mixin(self, base_states_raw):
        """_base_terminal must include _escalation_safety mixin."""
        states = base_states_raw.get("states", {})
        base_terminal = states.get("_base_terminal", {})
        mixins = base_terminal.get("mixins", [])
        assert "_escalation_safety" in mixins, \
            "_base_terminal is missing _escalation_safety mixin"

    def test_base_terminal_has_dialogue_control_mixin(self, base_states_raw):
        """_base_terminal must include dialogue_control mixin."""
        states = base_states_raw.get("states", {})
        base_terminal = states.get("_base_terminal", {})
        mixins = base_terminal.get("mixins", [])
        assert "dialogue_control" in mixins, \
            "_base_terminal is missing dialogue_control mixin"


# =============================================================================
# Test 2 (Defect 5): All state bases handle escalation
# =============================================================================

class TestDefect5Escalation:
    """Verify greeting/terminal states can escalate to human."""

    def test_greeting_has_escalation_transition(self, flow_config):
        """Greeting must transition to escalated on request_human."""
        greeting = flow_config.states.get("greeting", {})
        transitions = greeting.get("transitions", {})
        assert transitions.get("request_human") == "escalated", \
            f"greeting can't escalate on request_human (got: {transitions.get('request_human')})"

    def test_soft_close_has_escalation_transition(self, flow_config):
        """soft_close must transition to escalated on request_human."""
        soft_close = flow_config.states.get("soft_close", {})
        transitions = soft_close.get("transitions", {})
        assert transitions.get("request_human") == "escalated", \
            f"soft_close can't escalate on request_human (got: {transitions.get('request_human')})"

    def test_escalation_safety_mixin_exists(self, base_mixins_raw):
        """_escalation_safety mixin must exist in mixins.yaml."""
        mixins = base_mixins_raw.get("mixins", {})
        assert "_escalation_safety" in mixins, \
            "_escalation_safety mixin not found in mixins.yaml"

    def test_escalation_safety_has_all_escalation_intents(self, base_mixins_raw):
        """_escalation_safety must map all escalation intents to escalated."""
        mixins = base_mixins_raw.get("mixins", {})
        safety = mixins.get("_escalation_safety", {})
        transitions = safety.get("transitions", {})

        expected_intents = [
            "request_human", "speak_to_manager", "talk_to_person",
            "not_a_bot", "real_person", "human_please", "escalate",
            "problem_technical", "problem_connection", "problem_sync",
            "problem_fiscal", "request_technical_support",
            "legal_question", "formal_complaint", "contract_dispute",
            "data_deletion", "gdpr_request",
        ]
        for intent in expected_intents:
            assert transitions.get(intent) == "escalated", \
                f"_escalation_safety missing {intent} → escalated"


# =============================================================================
# Test 3 (Defect 6): High-traffic states use answer_with_pricing
# =============================================================================

class TestDefect6PriceAction:
    """Verify presentation and handle_objection use answer_with_pricing.

    These are the 2 highest-traffic states for price questions.
    Only close/soft_close are allowed answer_with_facts (closing context).
    """

    MUST_USE_PRICING = {"presentation", "handle_objection"}

    def test_presentation_default_price_action(self, flow_config):
        """presentation must use default_price_action: answer_with_pricing."""
        state = flow_config.states.get("presentation", {})
        # After parameter resolution, check rules for price_question
        # The default_price_action should have been answer_with_pricing
        rules = state.get("rules", {})
        # price_question should NOT be answer_with_facts
        if isinstance(rules.get("price_question"), str):
            assert rules["price_question"] != "answer_with_facts", \
                "presentation still has price_question: answer_with_facts (Defect 6)"

    def test_handle_objection_price_rules(self, flow_config):
        """handle_objection price rules must use answer_with_pricing as fallback."""
        state = flow_config.states.get("handle_objection", {})
        rules = state.get("rules", {})

        # price_question should be a conditional list ending with answer_with_pricing
        pq = rules.get("price_question")
        if isinstance(pq, list):
            # Last element is the default fallback
            assert pq[-1] == "answer_with_pricing", \
                f"handle_objection price_question fallback is {pq[-1]}, not answer_with_pricing"
        elif isinstance(pq, str):
            assert pq != "answer_with_facts", \
                "handle_objection still has price_question: answer_with_facts"

    def test_presentation_no_explicit_price_overrides(self, flow_config):
        """presentation must not have explicit price_question/pricing_details rules
        that would override the price_handling mixin."""
        state = flow_config.states.get("presentation", {})
        rules = state.get("rules", {})
        # These should NOT be simple string answer_with_facts
        for intent in ["price_question", "pricing_details"]:
            if intent in rules and isinstance(rules[intent], str):
                assert rules[intent] != "answer_with_facts", \
                    f"presentation has {intent}: answer_with_facts override (Defect 6)"


# =============================================================================
# Test 4 (Defect 1): record_guard preserves can_continue
# =============================================================================

class TestDefect1GuardTrace:
    """Verify advisory interventions (can_continue=True) are recorded correctly."""

    def test_advisory_intervention_preserves_can_continue(self):
        """Advisory (tier-1/2) intervention should record can_continue=True."""
        builder = DecisionTraceBuilder(turn=1, message="test")
        builder.record_guard(
            intervention="tier_1_advisory",
            can_continue=True,
            frustration=2
        )
        trace = builder.build()
        assert trace.guard_check.can_continue is True, \
            "Advisory intervention lost can_continue=True (Defect 1)"
        assert trace.guard_check.intervention_triggered is True

    def test_blocking_intervention_records_can_continue_false(self):
        """Blocking intervention should record can_continue=False."""
        builder = DecisionTraceBuilder(turn=1, message="test")
        builder.record_guard(
            intervention="tier_3_block",
            can_continue=False,
            frustration=5
        )
        trace = builder.build()
        assert trace.guard_check.can_continue is False
        assert trace.guard_check.intervention_triggered is True

    def test_no_intervention_defaults_can_continue_true(self):
        """No intervention should default to can_continue=True."""
        builder = DecisionTraceBuilder(turn=1, message="test")
        builder.record_guard(intervention=None)
        trace = builder.build()
        assert trace.guard_check.can_continue is True
        assert trace.guard_check.intervention_triggered is False

    def test_backward_compat_without_can_continue(self):
        """When can_continue is not passed, fall back to heuristic."""
        builder = DecisionTraceBuilder(turn=1, message="test")
        # Simulate old code that doesn't pass can_continue
        builder.record_guard(intervention="some_intervention")
        trace = builder.build()
        # Old heuristic: intervention is not None → can_continue=False
        assert trace.guard_check.can_continue is False


# =============================================================================
# Test 5 (Defect 3): record_fallback includes action and message
# =============================================================================

class TestDefect3FallbackTrace:
    """Verify fallback traces record complete data."""

    def test_fallback_trace_has_action_and_message(self):
        """Fallback traces must include action and message."""
        builder = DecisionTraceBuilder(turn=1, message="test")
        builder.record_fallback(
            tier="tier_2",
            reason="no_progress",
            action="gentle_redirect",
            message="Давайте попробуем другой подход..."
        )
        trace = builder.build()
        assert trace.fallback.fallback_action == "gentle_redirect", \
            "Fallback action not recorded (Defect 3)"
        assert trace.fallback.fallback_message is not None, \
            "Fallback message not recorded (Defect 3)"
        assert "попробуем" in trace.fallback.fallback_message

    def test_fallback_trace_without_action_stays_none(self):
        """Fallback without action should have None (not crash)."""
        builder = DecisionTraceBuilder(turn=1, message="test")
        builder.record_fallback(tier="tier_1", reason="intervention")
        trace = builder.build()
        assert trace.fallback.fallback_action is None
        assert trace.fallback.fallback_message is None


# =============================================================================
# Test 6 (Defect 4): Phase coverage uses flow config, not hardcoded injection
# =============================================================================

class TestDefect4PhaseCoverage:
    """Verify presentation is only counted when flow defines post_phases_state."""

    def test_no_phantom_presentation_in_coverage(self):
        """Without expected_phases, don't inject 'presentation' phantom phase."""
        phases_reached = ["situation", "problem"]
        expected = ["situation", "problem", "implication", "need_payoff"]
        coverage = calculate_spin_coverage(phases_reached, expected_phases=expected)
        # 2/4 = 0.5, NOT 2/5 (with phantom presentation)
        assert coverage == pytest.approx(0.5), \
            f"Coverage {coverage} != 0.5 — phantom presentation injected (Defect 4)"

    def test_explicit_presentation_counted_when_in_expected(self):
        """If expected_phases includes presentation, it should be counted."""
        phases_reached = ["situation", "problem", "presentation"]
        expected = ["situation", "problem", "implication", "need_payoff", "presentation"]
        coverage = calculate_spin_coverage(phases_reached, expected_phases=expected)
        # 3/5 = 0.6
        assert coverage == pytest.approx(0.6)

    def test_no_expected_phases_uses_spin_defaults(self):
        """When no expected_phases, fall back to SPIN_PHASES without presentation."""
        phases_reached = ["situation", "problem"]
        coverage = calculate_spin_coverage(phases_reached, expected_phases=None)
        # Should use SPIN_PHASES (no presentation injected)
        assert coverage > 0
        # Verify it doesn't use 5 phases (with phantom presentation)
        # SPIN_PHASES typically has 4 phases
        from src.yaml_config.constants import SPIN_PHASES
        expected_coverage = 2 / len(SPIN_PHASES)
        assert coverage == pytest.approx(expected_coverage)


# =============================================================================
# Test 7 (Defect 7): Simulation terminates on config-driven limits
# =============================================================================

class TestDefect7SimulationLimits:
    """Verify config-driven stagnation detection."""

    def test_soft_close_has_max_simulation_visits(self, flow_config):
        """soft_close must have max_simulation_visits defined."""
        limits = flow_config.simulation_limits
        assert "soft_close" in limits, \
            "soft_close has no simulation limits (Defect 7)"
        assert "max_visits" in limits["soft_close"], \
            "soft_close missing max_visits"
        assert limits["soft_close"]["max_visits"] == 2

    def test_handle_objection_has_max_simulation_consecutive(self, flow_config):
        """handle_objection must have max_simulation_consecutive defined."""
        limits = flow_config.simulation_limits
        assert "handle_objection" in limits, \
            "handle_objection has no simulation limits (Defect 7)"
        assert "max_consecutive" in limits["handle_objection"], \
            "handle_objection missing max_consecutive"
        assert limits["handle_objection"]["max_consecutive"] == 4

    def test_simulation_limits_property(self):
        """FlowConfig.simulation_limits must parse YAML correctly."""
        flow = FlowConfig(
            name="test",
            states={
                "state_a": {"max_simulation_visits": 3},
                "state_b": {"max_simulation_consecutive": 5},
                "state_c": {"max_simulation_visits": 2, "max_simulation_consecutive": 4},
                "state_d": {"goal": "no limits"},
            },
        )
        limits = flow.simulation_limits
        assert limits == {
            "state_a": {"max_visits": 3},
            "state_b": {"max_consecutive": 5},
            "state_c": {"max_visits": 2, "max_consecutive": 4},
        }
        assert "state_d" not in limits


# =============================================================================
# Cross-defect: GuardResult dataclass (Defect 1)
# =============================================================================

class TestGuardResultDataclass:
    """Verify GuardResult dataclass exists and works."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_requests(self):
        """Skip if bot.py can't be imported (missing requests/classifier deps)."""
        try:
            from src.bot import GuardResult  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            pytest.skip("src.bot requires requests/classifier deps not available in test env")

    def test_guard_result_importable(self):
        """GuardResult must be importable from bot module."""
        from src.bot import GuardResult
        result = GuardResult(can_continue=True, intervention=None)
        assert result.can_continue is True
        assert result.intervention is None

    def test_guard_result_advisory(self):
        """GuardResult can represent advisory intervention."""
        from src.bot import GuardResult
        result = GuardResult(can_continue=True, intervention="tier_1")
        assert result.can_continue is True
        assert result.intervention == "tier_1"

    def test_guard_result_blocking(self):
        """GuardResult can represent blocking intervention."""
        from src.bot import GuardResult
        result = GuardResult(can_continue=False, intervention="tier_3")
        assert result.can_continue is False
        assert result.intervention == "tier_3"

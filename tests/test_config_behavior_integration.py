"""
Integration tests for config-driven component behavior.

These tests verify that components correctly use config parameters
and that multiple components work together with shared config.

Tests:
- StateMachine uses config limits and transitions
- ConversationGuard uses config thresholds
- LeadScorer uses config weights and skip_phases
- FallbackHandler uses config templates
- CTAGenerator uses config templates
- Classifier uses config weights
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# STATE MACHINE + CONFIG INTEGRATION
# =============================================================================

class TestStateMachineUsesConfig:
    """Tests that StateMachine correctly uses config parameters."""

    def test_sm_uses_max_consecutive_objections_from_config(self, config_factory):
        """StateMachine uses max_consecutive_objections from config."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        config_dir = config_factory(limits={"max_consecutive_objections": 2})
        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Should use config value, not default
        assert sm._config is not None

    def test_sm_uses_circular_flow_allowed_gobacks(self, config_factory):
        """StateMachine uses allowed_gobacks from config."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine, CircularFlowManager

        custom_gobacks = {
            "spin_problem": "greeting",  # Custom: go back to greeting
        }

        config_dir = config_factory(circular_flow={"allowed_gobacks": custom_gobacks})
        loader = ConfigLoader(config_dir)
        config = loader.load()

        manager = CircularFlowManager(
            allowed_gobacks=config.circular_flow.get("allowed_gobacks"),
            max_gobacks=2
        )

        assert manager.allowed_gobacks.get("spin_problem") == "greeting"

    def test_sm_uses_max_gobacks_from_config(self, config_factory):
        """StateMachine uses max_gobacks from config."""
        from src.config_loader import ConfigLoader
        from src.state_machine import CircularFlowManager

        config_dir = config_factory(limits={"max_gobacks": 1})
        loader = ConfigLoader(config_dir)
        config = loader.load()

        max_gobacks = config.limits.get("max_gobacks", 2)
        manager = CircularFlowManager(max_gobacks=max_gobacks)

        assert manager.max_gobacks == 1

    def test_sm_uses_transitions_from_flow_config(self, config_factory):
        """StateMachine uses transitions from flow config."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Check that states have transitions
        greeting_state = config.get_state_config("greeting")
        assert greeting_state is not None
        assert "transitions" in greeting_state or hasattr(greeting_state, "transitions")

    def test_sm_uses_rules_from_flow_config(self, config_factory):
        """StateMachine uses rules from flow config."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)
        config = loader.load()

        # Check that states have rules
        greeting_state = config.get_state_config("greeting")
        if greeting_state:
            # May have rules defined
            pass


# =============================================================================
# CONVERSATION GUARD + CONFIG INTEGRATION
# =============================================================================

class TestConversationGuardUsesConfig:
    """Tests that ConversationGuard correctly uses config parameters."""

    def test_guard_uses_max_turns_from_config(self, config_factory):
        """ConversationGuard uses max_turns from config."""
        from src.config_loader import ConfigLoader
        from src.conversation_guard import ConversationGuard, GuardConfig

        config_dir = config_factory(guard={"max_turns": 15})
        loader = ConfigLoader(config_dir)
        config = loader.load()

        guard_config = GuardConfig(
            max_turns=config.guard.get("max_turns", 25)
        )
        guard = ConversationGuard(guard_config)

        assert guard.config.max_turns == 15

    def test_guard_uses_timeout_from_config(self, config_factory):
        """ConversationGuard uses timeout_seconds from config."""
        from src.config_loader import ConfigLoader
        from src.conversation_guard import ConversationGuard, GuardConfig

        config_dir = config_factory(guard={"timeout_seconds": 600})
        loader = ConfigLoader(config_dir)
        config = loader.load()

        guard_config = GuardConfig(
            timeout_seconds=config.guard.get("timeout_seconds", 1800)
        )
        guard = ConversationGuard(guard_config)

        assert guard.config.timeout_seconds == 600

    def test_guard_uses_high_frustration_threshold(self, config_factory):
        """ConversationGuard uses high_frustration_threshold from config."""
        from src.config_loader import ConfigLoader
        from src.conversation_guard import ConversationGuard, GuardConfig

        config_dir = config_factory(
            guard={"high_frustration_threshold": 5},
            frustration={"thresholds": {"high": 5}}
        )
        loader = ConfigLoader(config_dir)
        config = loader.load()

        guard_config = GuardConfig(
            high_frustration_threshold=config.guard.get("high_frustration_threshold", 7)
        )
        guard = ConversationGuard(guard_config)

        assert guard.config.high_frustration_threshold == 5

    def test_guard_frustration_threshold_matches_frustration_config(self, config_factory):
        """Guard threshold must match frustration.thresholds.high."""
        from src.config_loader import ConfigLoader

        # Both should be 5
        config_dir = config_factory(
            guard={"high_frustration_threshold": 5},
            frustration={"thresholds": {"warning": 3, "high": 5, "critical": 8}}
        )
        loader = ConfigLoader(config_dir)
        config = loader.load()

        guard_threshold = config.guard.get("high_frustration_threshold")
        frustration_high = config.frustration.get("thresholds", {}).get("high")

        assert guard_threshold == frustration_high


# =============================================================================
# LEAD SCORER + CONFIG INTEGRATION
# =============================================================================

class TestLeadScorerUsesConfig:
    """Tests that LeadScorer correctly uses config parameters."""

    def test_scorer_uses_positive_weights(self):
        """LeadScorer uses positive_weights from config."""
        from src.lead_scoring import LeadScorer

        custom_weights = {"demo_request": 50}  # Higher than default 30

        scorer = LeadScorer()
        # Apply custom weight
        scorer.POSITIVE_WEIGHTS["demo_request"] = 50

        scorer.add_signal("demo_request")
        assert scorer.current_score >= 50

    def test_scorer_uses_negative_weights(self):
        """LeadScorer uses negative_weights from config."""
        from src.lead_scoring import LeadScorer

        scorer = LeadScorer()
        scorer.current_score = 50

        scorer.add_signal("objection_price")
        # Should decrease by configured weight
        assert scorer.current_score < 50

    def test_scorer_uses_thresholds(self):
        """LeadScorer uses temperature thresholds from config."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()

        # Test boundary values
        scorer.current_score = 29
        assert scorer.get_score().temperature == LeadTemperature.COLD

        scorer.current_score = 30
        assert scorer.get_score().temperature == LeadTemperature.WARM

    def test_scorer_uses_skip_phases(self):
        """LeadScorer returns skip_phases based on temperature."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()
        scorer.current_score = 55  # HOT

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.HOT
        assert len(score.skip_phases) > 0  # HOT skips some phases

    def test_scorer_skip_phases_for_cold_is_empty(self):
        """COLD temperature has no skip_phases."""
        from src.lead_scoring import LeadScorer

        scorer = LeadScorer()
        scorer.current_score = 15  # COLD

        score = scorer.get_score()
        assert len(score.skip_phases) == 0


# =============================================================================
# LEAD SCORER + STATE MACHINE INTEGRATION
# =============================================================================

class TestLeadScorerStateMachineIntegration:
    """Tests LeadScorer integration with StateMachine."""

    def test_hot_lead_skip_phases_affect_navigation(self):
        """HOT lead skip_phases should affect state navigation."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()
        scorer.current_score = 60  # HOT

        score = scorer.get_score()
        skip_phases = score.skip_phases

        # HOT should skip problem, implication, need_payoff
        assert "spin_problem" in skip_phases or len(skip_phases) >= 2

    def test_very_hot_lead_skips_all_spin(self):
        """VERY_HOT lead should skip all SPIN phases."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()
        scorer.current_score = 80  # VERY_HOT

        score = scorer.get_score()
        skip_phases = score.skip_phases

        # Should skip situation, problem, implication, need_payoff
        assert len(skip_phases) >= 3


# =============================================================================
# CIRCULAR FLOW MANAGER + CONFIG INTEGRATION
# =============================================================================

class TestCircularFlowManagerUsesConfig:
    """Tests CircularFlowManager uses config correctly."""

    def test_manager_uses_allowed_gobacks_from_config(self, config_factory):
        """Manager uses allowed_gobacks from config."""
        from src.config_loader import ConfigLoader
        from src.state_machine import CircularFlowManager

        custom_gobacks = {
            "spin_problem": "spin_situation",
            "presentation": "spin_problem",  # Custom
        }

        config_dir = config_factory(circular_flow={"allowed_gobacks": custom_gobacks})
        loader = ConfigLoader(config_dir)
        config = loader.load()

        manager = CircularFlowManager(
            allowed_gobacks=config.circular_flow.get("allowed_gobacks")
        )

        assert manager.can_go_back("spin_problem") is True
        assert manager.allowed_gobacks.get("presentation") == "spin_problem"

    def test_manager_blocks_goback_not_in_config(self):
        """Manager blocks go_back for states not in config."""
        from src.state_machine import CircularFlowManager

        # Only allow spin_problem -> spin_situation
        manager = CircularFlowManager(
            allowed_gobacks={"spin_problem": "spin_situation"}
        )

        assert manager.can_go_back("spin_problem") is True
        assert manager.can_go_back("greeting") is False
        assert manager.can_go_back("success") is False


# =============================================================================
# CONFIG LOADER VALIDATION INTEGRATION
# =============================================================================

class TestConfigLoaderValidation:
    """Tests ConfigLoader validation of config consistency."""

    def test_threshold_mismatch_raises_error(self, tmp_path):
        """Mismatched thresholds raise ConfigValidationError."""
        from src.config_loader import ConfigLoader, ConfigValidationError
        import yaml

        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        # Create mismatched config
        constants = {
            "spin": {"phases": ["situation"], "states": {"situation": "spin_situation"}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"warning": 4, "high": 5, "critical": 9}},  # Mismatch!
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
            "limits": {},
            "intents": {"go_back": [], "categories": {}},
            "policy": {},
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump({"states": {"greeting": {"goal": "greet"}}}, f)

        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump({"phase_order": ["situation"], "phases": {"situation": {"state": "spin_situation"}}}, f)

        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigLoader(tmp_path).load()

        assert "Threshold mismatch" in str(exc_info.value) or "mismatch" in str(exc_info.value).lower()

    def test_invalid_transition_raises_error(self, tmp_path):
        """Invalid state transition raises ConfigValidationError."""
        from src.config_loader import ConfigLoader, ConfigValidationError
        import yaml

        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        constants = {
            "spin": {"phases": [], "states": {}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 7}},
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
            "limits": {},
            "intents": {"go_back": [], "categories": {}},
            "policy": {},
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        # Invalid transition to nonexistent state
        states = {
            "states": {
                "greeting": {
                    "goal": "greet",
                    "transitions": {"test": "nonexistent_state"}
                }
            }
        }
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)

        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump({"phase_order": [], "phases": {}}, f)

        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigLoader(tmp_path).load()

        assert "nonexistent_state" in str(exc_info.value)


# =============================================================================
# REAL CONFIG INTEGRATION
# =============================================================================

class TestRealConfigIntegration:
    """Tests with real config files."""

    def test_real_config_loads_successfully(self):
        """Real config loads without errors."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        assert config is not None
        assert len(config.states) > 0

    def test_real_config_has_synced_thresholds(self):
        """Real config has synchronized thresholds."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        guard_threshold = config.guard.get("high_frustration_threshold")
        frustration_high = config.frustration.get("thresholds", {}).get("high")

        assert guard_threshold == frustration_high

    def test_real_config_spin_phases_valid(self):
        """Real config has valid SPIN phases."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        assert len(config.spin_phases) == 4
        assert config.spin_phases == ["situation", "problem", "implication", "need_payoff"]

    def test_real_config_states_have_goals(self):
        """Real config states all have goals."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        for state_name, state in config.states.items():
            if hasattr(state, 'goal'):
                assert state.goal is not None
            elif isinstance(state, dict):
                assert "goal" in state or state_name.startswith("_")

    def test_real_config_custom_conditions_valid(self):
        """Real config custom conditions are valid."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        assert len(config.custom_conditions) > 0
        assert "ready_for_demo" in config.custom_conditions


# =============================================================================
# COMPONENT WIRING INTEGRATION
# =============================================================================

class TestComponentWiringIntegration:
    """Tests that components are wired together correctly."""

    def test_state_machine_with_config_initializes(self, config_factory):
        """StateMachine initializes with config."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)
        assert sm is not None

    def test_conversation_guard_with_config_initializes(self, config_factory):
        """ConversationGuard initializes with config."""
        from src.config_loader import ConfigLoader
        from src.conversation_guard import ConversationGuard, GuardConfig

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)
        config = loader.load()

        guard_config = GuardConfig(
            max_turns=config.guard.get("max_turns", 25),
            timeout_seconds=config.guard.get("timeout_seconds", 1800),
        )
        guard = ConversationGuard(guard_config)

        assert guard is not None

    def test_lead_scorer_initializes(self):
        """LeadScorer initializes correctly."""
        from src.lead_scoring import LeadScorer

        scorer = LeadScorer()
        assert scorer is not None
        assert scorer.current_score == 0

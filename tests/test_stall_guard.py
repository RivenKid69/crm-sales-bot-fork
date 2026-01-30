# tests/test_stall_guard.py

"""
Tests for Universal Stall Guard mechanism (Mechanisms A, B, C).

Covers:
- StallGuardSource unit tests (A2)
- Feature flag auto-verification (B1, B2)
- Integration tests for greeting (RC1), handle_objection (RC2),
  presentation (RC3), and phase states (RC4)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from dataclasses import dataclass


# =============================================================================
# UNIT TESTS: StallGuardSource
# =============================================================================


class TestStallGuardSourceDisabled:
    """Tests for StallGuardSource when disabled by various means."""

    def _make_source(self, enabled=True):
        from src.blackboard.sources.stall_guard import StallGuardSource
        return StallGuardSource(enabled=enabled)

    def _make_blackboard(self, state="presentation", max_turns=5,
                         consecutive=5, fallback="close",
                         state_before_objection=None):
        """Create a mock blackboard with the given context."""
        bb = MagicMock()

        # ContextSnapshot mock
        envelope = Mock()
        envelope.consecutive_same_state = consecutive

        ctx = Mock()
        ctx.state = state
        ctx.state_config = {
            "max_turns_in_state": max_turns,
            "max_turns_fallback": fallback,
        }
        ctx.context_envelope = envelope

        bb.get_context.return_value = ctx

        # State machine mock (for _state_before_objection)
        sm = Mock()
        sm._state_before_objection = state_before_objection
        bb._state_machine = sm

        return bb

    def test_disabled_when_max_turns_zero(self):
        """Source should not contribute when max_turns_in_state is 0 (terminal states)."""
        source = self._make_source()
        bb = self._make_blackboard(state="success", max_turns=0, consecutive=10)
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_disabled_when_flag_off(self):
        """Source should not contribute when universal_stall_guard flag is off."""
        source = self._make_source()
        bb = self._make_blackboard()
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = False
            assert source.should_contribute(bb) is False

    def test_disabled_when_self_enabled_false(self):
        """Source should not contribute when self._enabled is False."""
        source = self._make_source(enabled=False)
        bb = self._make_blackboard()
        assert source.should_contribute(bb) is False

    def test_disabled_when_consecutive_below_threshold(self):
        """Source should not contribute when consecutive turns < max_turns_in_state."""
        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, consecutive=3)
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False


class TestStallGuardSourceFires:
    """Tests for StallGuardSource when it should fire."""

    def _make_source(self):
        from src.blackboard.sources.stall_guard import StallGuardSource
        return StallGuardSource()

    def _make_blackboard(self, state="presentation", max_turns=5,
                         consecutive=5, fallback="close",
                         state_before_objection=None):
        bb = MagicMock()

        envelope = Mock()
        envelope.consecutive_same_state = consecutive

        ctx = Mock()
        ctx.state = state
        ctx.state_config = {
            "max_turns_in_state": max_turns,
            "max_turns_fallback": fallback,
        }
        ctx.context_envelope = envelope

        bb.get_context.return_value = ctx

        sm = Mock()
        sm._state_before_objection = state_before_objection
        bb._state_machine = sm

        return bb

    def test_fires_at_threshold(self):
        """Source should contribute when consecutive == max_turns_in_state."""
        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, consecutive=5)
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is True

    def test_fires_above_threshold(self):
        """Source should contribute when consecutive > max_turns_in_state."""
        source = self._make_source()
        bb = self._make_blackboard(max_turns=4, consecutive=6)
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is True

    def test_uses_yaml_fallback_when_no_saved_state(self):
        """Should use max_turns_fallback from state_config when not a detour state."""
        source = self._make_source()
        bb = self._make_blackboard(
            state="presentation", max_turns=5, consecutive=5, fallback="close"
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            source.contribute(bb)

        # Verify propose_transition was called with "close"
        bb.propose_transition.assert_called_once()
        call_kwargs = bb.propose_transition.call_args
        assert call_kwargs.kwargs["next_state"] == "close"

    def test_returns_to_saved_state_for_handle_objection(self):
        """Should return to _state_before_objection for handle_objection."""
        source = self._make_source()
        bb = self._make_blackboard(
            state="handle_objection",
            max_turns=4,
            consecutive=4,
            fallback="{{entry_state}}",
            state_before_objection="bant_budget"
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            source.contribute(bb)

        # Should use saved state, not YAML fallback
        bb.propose_transition.assert_called_once()
        call_kwargs = bb.propose_transition.call_args
        assert call_kwargs.kwargs["next_state"] == "bant_budget"

    def test_uses_yaml_fallback_when_no_saved_state_in_objection(self):
        """Should fall back to YAML when handle_objection has no saved state."""
        source = self._make_source()
        bb = self._make_blackboard(
            state="handle_objection",
            max_turns=4,
            consecutive=4,
            fallback="presentation",
            state_before_objection=None
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            source.contribute(bb)

        bb.propose_transition.assert_called_once()
        call_kwargs = bb.propose_transition.call_args
        assert call_kwargs.kwargs["next_state"] == "presentation"

    def test_propose_transition_uses_correct_signature(self):
        """Verify propose_transition is called with all required kwargs."""
        from src.blackboard.enums import Priority

        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, consecutive=5, fallback="close")
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            source.contribute(bb)

        bb.propose_transition.assert_called_once()
        call_kwargs = bb.propose_transition.call_args.kwargs
        assert call_kwargs["next_state"] == "close"
        assert call_kwargs["priority"] == Priority.HIGH
        assert call_kwargs["reason_code"] == "max_turns_in_state_exceeded"
        assert call_kwargs["source_name"] == "StallGuardSource"
        assert "mechanism" in call_kwargs["metadata"]
        assert call_kwargs["metadata"]["mechanism"] == "stall_guard"

    def test_priority_below_objection_return(self):
        """StallGuardSource priority_order (45) > ObjectionReturnSource (35)."""
        from src.blackboard.source_registry import SourceRegistry

        stall_reg = SourceRegistry.get_registration("StallGuardSource")
        objection_reg = SourceRegistry.get_registration("ObjectionReturnSource")

        # StallGuardSource should have HIGHER priority_order number
        # (meaning it runs LATER)
        if stall_reg and objection_reg:
            assert stall_reg.priority_order > objection_reg.priority_order
            assert stall_reg.priority_order == 45
            assert objection_reg.priority_order == 35

    def test_context_snapshot_not_direct_access(self):
        """StallGuardSource should use blackboard.get_context(), not direct state."""
        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, consecutive=5)
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            source.contribute(bb)

        # Verify get_context was called (not direct attribute access)
        bb.get_context.assert_called()

    def test_handles_missing_context_envelope(self):
        """Should handle None context_envelope gracefully."""
        source = self._make_source()
        bb = MagicMock()
        ctx = Mock()
        ctx.state = "presentation"
        ctx.state_config = {"max_turns_in_state": 5}
        ctx.context_envelope = None
        bb.get_context.return_value = ctx

        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            # Should return False (consecutive=0 < max_turns=5)
            assert source.should_contribute(bb) is False

    def test_greeting_ttl_at_4(self):
        """Greeting should have max_turns_in_state=4."""
        source = self._make_source()
        bb = self._make_blackboard(
            state="greeting", max_turns=4, consecutive=4,
            fallback="spin_situation"
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is True
            source.contribute(bb)

        bb.propose_transition.assert_called_once()
        call_kwargs = bb.propose_transition.call_args.kwargs
        assert call_kwargs["next_state"] == "spin_situation"


# =============================================================================
# UNIT TESTS: Feature Flag Auto-Verification (Mechanism B)
# =============================================================================


class TestFeatureFlagAutoVerification:
    """Tests for Mechanism B: auto-verification of feature flags."""

    def test_auto_verification_catches_missing(self):
        """Auto-verification should detect missing flags and auto-register them."""
        from src.feature_flags import FeatureFlags, flags

        # Simulate a layer with a flag NOT in DEFAULTS
        mock_layer = Mock()
        mock_layer.FEATURE_FLAG = "_test_nonexistent_flag_xyz_"
        mock_layer.name = "TestLayer"

        # Ensure it's not in DEFAULTS
        if "_test_nonexistent_flag_xyz_" in FeatureFlags.DEFAULTS:
            del FeatureFlags.DEFAULTS["_test_nonexistent_flag_xyz_"]

        from src.classifier.refinement_pipeline import RefinementPipeline
        pipeline = RefinementPipeline.__new__(RefinementPipeline)
        pipeline._layers = [mock_layer]

        pipeline._verify_feature_flags()

        # Flag should now be auto-registered
        assert "_test_nonexistent_flag_xyz_" in FeatureFlags.DEFAULTS
        assert FeatureFlags.DEFAULTS["_test_nonexistent_flag_xyz_"] is True

        # Cleanup
        del FeatureFlags.DEFAULTS["_test_nonexistent_flag_xyz_"]
        flags._flags.pop("_test_nonexistent_flag_xyz_", None)

    def test_auto_verification_no_change_existing(self):
        """Auto-verification should not modify existing flags."""
        from src.feature_flags import FeatureFlags

        mock_layer = Mock()
        mock_layer.FEATURE_FLAG = "tone_analysis"  # Exists in DEFAULTS
        mock_layer.name = "TestLayer"

        original_value = FeatureFlags.DEFAULTS["tone_analysis"]

        from src.classifier.refinement_pipeline import RefinementPipeline
        pipeline = RefinementPipeline.__new__(RefinementPipeline)
        pipeline._layers = [mock_layer]

        pipeline._verify_feature_flags()

        # Value should not have changed
        assert FeatureFlags.DEFAULTS["tone_analysis"] == original_value

    def test_first_contact_refinement_in_defaults(self):
        """first_contact_refinement flag must exist in DEFAULTS (RC5 fix)."""
        from src.feature_flags import FeatureFlags
        assert "first_contact_refinement" in FeatureFlags.DEFAULTS
        assert FeatureFlags.DEFAULTS["first_contact_refinement"] is True

    def test_universal_stall_guard_in_defaults(self):
        """universal_stall_guard flag must exist in DEFAULTS."""
        from src.feature_flags import FeatureFlags
        assert "universal_stall_guard" in FeatureFlags.DEFAULTS
        assert FeatureFlags.DEFAULTS["universal_stall_guard"] is True

    def test_simulation_diagnostic_mode_in_defaults(self):
        """simulation_diagnostic_mode flag must exist in DEFAULTS (disabled)."""
        from src.feature_flags import FeatureFlags
        assert "simulation_diagnostic_mode" in FeatureFlags.DEFAULTS
        assert FeatureFlags.DEFAULTS["simulation_diagnostic_mode"] is False


# =============================================================================
# UNIT TESTS: Feature Flag Properties
# =============================================================================


class TestFeatureFlagProperties:
    """Tests for new typed properties on FeatureFlags."""

    def test_first_contact_refinement_property(self):
        from src.feature_flags import FeatureFlags
        ff = FeatureFlags()
        assert isinstance(ff.first_contact_refinement, bool)

    def test_universal_stall_guard_property(self):
        from src.feature_flags import FeatureFlags
        ff = FeatureFlags()
        assert isinstance(ff.universal_stall_guard, bool)

    def test_simulation_diagnostic_mode_property(self):
        from src.feature_flags import FeatureFlags
        ff = FeatureFlags()
        assert isinstance(ff.simulation_diagnostic_mode, bool)
        assert ff.simulation_diagnostic_mode is False  # Default is False


# =============================================================================
# INTEGRATION TESTS: Stall Detection (RC3)
# =============================================================================


class TestStallDetectionPresentationFix:
    """Tests for RC3 fix: presentation removed from exempt_states."""

    def test_presentation_not_in_exempt_states(self):
        """Presentation must NOT be in stall_detection exempt_states (RC3 fix)."""
        from src.yaml_config.constants import _constants
        config = _constants.get("stall_detection", {})
        exempt = config.get("exempt_states", [])
        assert "presentation" not in exempt

    def test_stall_fires_in_presentation(self):
        """is_stalled should fire for presentation state now."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext

        ctx = PolicyContext.create_test_context(
            state="presentation",
            consecutive_same_state=4,
            is_progressing=False,
        )
        assert is_stalled(ctx) is True

    def test_stall_still_exempt_for_greeting(self):
        """Greeting should still be exempt from stall detection."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext

        ctx = PolicyContext.create_test_context(
            state="greeting",
            consecutive_same_state=5,
            is_progressing=False,
        )
        assert is_stalled(ctx) is False

    def test_stall_still_exempt_for_handle_objection(self):
        """handle_objection should still be exempt from stall detection."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext

        ctx = PolicyContext.create_test_context(
            state="handle_objection",
            consecutive_same_state=5,
            is_progressing=False,
        )
        assert is_stalled(ctx) is False


# =============================================================================
# INTEGRATION TESTS: Greeting Meta-Intent Transitions (RC1)
# =============================================================================


class TestGreetingMetaIntentTransitions:
    """Tests for RC1 fix: meta-intent escape transitions in greeting."""

    def _load_greeting_transitions(self):
        """Load greeting state transitions from base states.yaml."""
        import yaml
        path = "src/yaml_config/flows/_base/states.yaml"
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        states = data.get("states", {})
        greeting = states.get("greeting", {})
        return greeting.get("transitions", {})

    def test_unclear_transition_exists(self):
        """Greeting must have conditional transition for unclear intent."""
        transitions = self._load_greeting_transitions()
        assert "unclear" in transitions
        # Should be a conditional list
        unclear = transitions["unclear"]
        assert isinstance(unclear, list)
        assert any(
            item.get("when") == "turn_number_gte_3"
            for item in unclear
            if isinstance(item, dict)
        )

    def test_small_talk_transition_exists(self):
        """Greeting must have conditional transition for small_talk intent."""
        transitions = self._load_greeting_transitions()
        assert "small_talk" in transitions
        small_talk = transitions["small_talk"]
        assert isinstance(small_talk, list)
        assert any(
            item.get("when") == "turn_number_gte_3"
            for item in small_talk
            if isinstance(item, dict)
        )

    def test_gratitude_transition_exists(self):
        """Greeting must have conditional transition for gratitude intent."""
        transitions = self._load_greeting_transitions()
        assert "gratitude" in transitions
        gratitude = transitions["gratitude"]
        assert isinstance(gratitude, list)
        assert any(
            item.get("when") == "turn_number_gte_3"
            for item in gratitude
            if isinstance(item, dict)
        )


# =============================================================================
# INTEGRATION TESTS: max_turns_in_state YAML Config (A1)
# =============================================================================


class TestMaxTurnsInStateConfig:
    """Tests for YAML configuration of max_turns_in_state."""

    def _load_states(self):
        import yaml
        path = "src/yaml_config/flows/_base/states.yaml"
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return data.get("states", {})

    def test_base_phase_has_max_turns(self):
        """_base_phase must have max_turns_in_state=6."""
        states = self._load_states()
        base_phase = states.get("_base_phase", {})
        assert base_phase.get("max_turns_in_state") == 6

    def test_greeting_has_max_turns_4(self):
        """greeting must have max_turns_in_state=4."""
        states = self._load_states()
        greeting = states.get("greeting", {})
        assert greeting.get("max_turns_in_state") == 4

    def test_presentation_has_max_turns_5(self):
        """presentation must have max_turns_in_state=5."""
        states = self._load_states()
        presentation = states.get("presentation", {})
        assert presentation.get("max_turns_in_state") == 5

    def test_handle_objection_has_max_turns_4(self):
        """handle_objection must have max_turns_in_state=4."""
        states = self._load_states()
        ho = states.get("handle_objection", {})
        assert ho.get("max_turns_in_state") == 4

    def test_close_has_max_turns_6(self):
        """close must have max_turns_in_state=6."""
        states = self._load_states()
        close = states.get("close", {})
        assert close.get("max_turns_in_state") == 6

    def test_success_has_max_turns_0(self):
        """success (terminal) must have max_turns_in_state=0 (disabled)."""
        states = self._load_states()
        success = states.get("success", {})
        assert success.get("max_turns_in_state") == 0

    def test_soft_close_has_max_turns_0(self):
        """soft_close (terminal) must have max_turns_in_state=0 (disabled)."""
        states = self._load_states()
        soft_close = states.get("soft_close", {})
        assert soft_close.get("max_turns_in_state") == 0

    def test_greeting_fallback_is_entry_state(self):
        """greeting max_turns_fallback must be {{entry_state}}."""
        states = self._load_states()
        greeting = states.get("greeting", {})
        assert greeting.get("max_turns_fallback") == "{{entry_state}}"

    def test_handle_objection_fallback_is_entry_state(self):
        """handle_objection max_turns_fallback must be {{entry_state}}."""
        states = self._load_states()
        ho = states.get("handle_objection", {})
        assert ho.get("max_turns_fallback") == "{{entry_state}}"

    def test_presentation_fallback_is_close(self):
        """presentation max_turns_fallback must be close."""
        states = self._load_states()
        pres = states.get("presentation", {})
        assert pres.get("max_turns_fallback") == "close"

    def test_close_fallback_is_soft_close(self):
        """close max_turns_fallback must be soft_close."""
        states = self._load_states()
        close = states.get("close", {})
        assert close.get("max_turns_fallback") == "soft_close"


# =============================================================================
# INTEGRATION TESTS: Source Registry
# =============================================================================


class TestStallGuardRegistration:
    """Tests for StallGuardSource registration in SourceRegistry."""

    def setup_method(self):
        """Save registry state before test."""
        from src.blackboard.source_registry import SourceRegistry
        self._saved_registry = dict(SourceRegistry._registry)
        self._saved_frozen = SourceRegistry._frozen

    def teardown_method(self):
        """Restore registry state to avoid cross-test pollution."""
        from src.blackboard.source_registry import SourceRegistry
        SourceRegistry._registry = self._saved_registry
        SourceRegistry._frozen = self._saved_frozen

    def test_stall_guard_registered(self):
        """StallGuardSource must be registered in SourceRegistry."""
        from src.blackboard.source_registry import SourceRegistry, register_builtin_sources
        SourceRegistry.reset()
        register_builtin_sources()
        reg = SourceRegistry.get_registration("StallGuardSource")
        assert reg is not None

    def test_stall_guard_priority_order(self):
        """StallGuardSource must have priority_order=45."""
        from src.blackboard.source_registry import SourceRegistry, register_builtin_sources
        SourceRegistry.reset()
        register_builtin_sources()
        reg = SourceRegistry.get_registration("StallGuardSource")
        assert reg is not None
        assert reg.priority_order == 45

    def test_stall_guard_between_objection_and_transition(self):
        """StallGuardSource must be between ObjectionReturnSource (35) and TransitionResolver (50)."""
        from src.blackboard.source_registry import SourceRegistry, register_builtin_sources
        SourceRegistry.reset()
        register_builtin_sources()

        stall = SourceRegistry.get_registration("StallGuardSource")
        objection = SourceRegistry.get_registration("ObjectionReturnSource")
        transition = SourceRegistry.get_registration("TransitionResolverSource")

        assert stall is not None
        assert objection is not None
        assert transition is not None

        assert objection.priority_order < stall.priority_order < transition.priority_order


# =============================================================================
# INTEGRATION TESTS: Simulation Diagnostic Config
# =============================================================================


class TestSimulationDiagnosticConfig:
    """Tests for simulation diagnostic mode configuration."""

    def test_diagnostic_config_exists(self):
        """Simulation diagnostic config must exist in constants.yaml."""
        from src.yaml_config.constants import _constants
        sim = _constants.get("simulation", {})
        diag = sim.get("diagnostic", {})
        assert "handle_objection_max_consecutive" in diag
        assert "soft_close_max_visits" in diag

    def test_diagnostic_values(self):
        """Diagnostic limits must be higher than normal."""
        from src.yaml_config.constants import _constants
        sim = _constants.get("simulation", {})
        diag = sim.get("diagnostic", {})
        assert diag["handle_objection_max_consecutive"] == 10
        assert diag["soft_close_max_visits"] == 5

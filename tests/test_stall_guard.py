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
        assert call_kwargs["metadata"]["mechanism"] == "stall_guard_hard"

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
        """_base_phase must have max_turns_in_state=5."""
        states = self._load_states()
        base_phase = states.get("_base_phase", {})
        assert base_phase.get("max_turns_in_state") == 5

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

# =============================================================================
# UNIT TESTS: Two-Tier StallGuard (FIX 2)
# =============================================================================

class TestStallGuardTwoTier:
    """Tests for two-tier StallGuard: soft (NORMAL) and hard (HIGH)."""

    def _make_source(self):
        from src.blackboard.sources.stall_guard import StallGuardSource
        return StallGuardSource()

    def _make_blackboard(self, state="presentation", max_turns=5,
                         consecutive=5, fallback="close",
                         is_progressing=False, has_extracted_data=False,
                         state_before_objection=None):
        bb = MagicMock()

        envelope = Mock()
        envelope.consecutive_same_state = consecutive
        envelope.is_progressing = is_progressing
        envelope.has_extracted_data = has_extracted_data

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

    def test_hard_threshold_fires_unconditionally(self):
        """Hard threshold (consecutive >= max_turns) always fires."""
        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, consecutive=5, is_progressing=True)
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is True

    def test_hard_threshold_uses_high_priority(self):
        """Hard threshold proposes with Priority.HIGH."""
        from src.blackboard.enums import Priority
        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, consecutive=5)
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            source.contribute(bb)
        call_kwargs = bb.propose_transition.call_args.kwargs
        assert call_kwargs["priority"] == Priority.HIGH
        assert call_kwargs["reason_code"] == "max_turns_in_state_exceeded"
        assert call_kwargs["metadata"]["mechanism"] == "stall_guard_hard"

    def test_soft_threshold_fires_when_not_progressing(self):
        """Soft threshold (max_turns - 1) fires when not progressing and no data."""
        source = self._make_source()
        bb = self._make_blackboard(
            max_turns=5, consecutive=4,
            is_progressing=False, has_extracted_data=False,
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is True

    def test_soft_threshold_uses_normal_priority(self):
        """Soft threshold proposes with Priority.NORMAL."""
        from src.blackboard.enums import Priority
        source = self._make_source()
        bb = self._make_blackboard(
            max_turns=5, consecutive=4,
            is_progressing=False, has_extracted_data=False,
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            source.contribute(bb)
        call_kwargs = bb.propose_transition.call_args.kwargs
        assert call_kwargs["priority"] == Priority.NORMAL
        assert call_kwargs["reason_code"] == "stall_soft_progression"
        assert call_kwargs["metadata"]["mechanism"] == "stall_guard_soft"

    def test_soft_threshold_blocked_by_is_progressing(self):
        """Soft threshold does NOT fire when is_progressing is True."""
        source = self._make_source()
        bb = self._make_blackboard(
            max_turns=5, consecutive=4,
            is_progressing=True, has_extracted_data=False,
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_soft_threshold_blocked_by_has_extracted_data(self):
        """Soft threshold does NOT fire when has_extracted_data is True."""
        source = self._make_source()
        bb = self._make_blackboard(
            max_turns=5, consecutive=4,
            is_progressing=False, has_extracted_data=True,
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_soft_threshold_minimum_3(self):
        """Soft threshold must be at least 3 (for greeting with max_turns=4)."""
        source = self._make_source()
        # max_turns=4 → soft_threshold=max(3,3)=3. consecutive=3 should fire.
        bb = self._make_blackboard(
            state="greeting", max_turns=4, consecutive=3,
            is_progressing=False, has_extracted_data=False,
            fallback="spin_situation",
        )
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is True

    def test_below_soft_threshold_does_not_fire(self):
        """Below soft threshold (consecutive < max_turns-1) does not fire."""
        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, consecutive=3)
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_greeting_timeline_soft_at_3_hard_at_4(self):
        """Greeting (max=4): soft at turn 3, hard at turn 4."""
        source = self._make_source()
        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True

            # Turn 2: no fire
            bb2 = self._make_blackboard(
                state="greeting", max_turns=4, consecutive=2,
                fallback="spin_situation",
            )
            assert source.should_contribute(bb2) is False

            # Turn 3: soft fire (not progressing, no data)
            bb3 = self._make_blackboard(
                state="greeting", max_turns=4, consecutive=3,
                is_progressing=False, has_extracted_data=False,
                fallback="spin_situation",
            )
            assert source.should_contribute(bb3) is True

            # Turn 4: hard fire (unconditional)
            bb4 = self._make_blackboard(
                state="greeting", max_turns=4, consecutive=4,
                is_progressing=True,  # Even progressing
                fallback="spin_situation",
            )
            assert source.should_contribute(bb4) is True

# =============================================================================
# UNIT TESTS: is_stalled with has_extracted_data guard (FIX 1b)
# =============================================================================

class TestIsStalledWithExtractedData:
    """Tests for is_stalled condition with has_extracted_data guard."""

    def test_stalled_without_data(self):
        """is_stalled fires when no data extracted and not progressing."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(
            state="presentation",
            consecutive_same_state=4,
            is_progressing=False,
            has_extracted_data=False,
        )
        assert is_stalled(ctx) is True

    def test_not_stalled_with_extracted_data(self):
        """is_stalled should NOT fire when has_extracted_data is True."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(
            state="presentation",
            consecutive_same_state=4,
            is_progressing=False,
            has_extracted_data=True,
        )
        assert is_stalled(ctx) is False

    def test_not_stalled_when_progressing(self):
        """is_stalled should NOT fire when is_progressing is True."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(
            state="presentation",
            consecutive_same_state=4,
            is_progressing=True,
            has_extracted_data=False,
        )
        assert is_stalled(ctx) is False

    def test_not_stalled_below_threshold(self):
        """is_stalled should NOT fire below stall_threshold."""
        from src.conditions.policy.conditions import is_stalled
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(
            state="presentation",
            consecutive_same_state=2,
            is_progressing=False,
            has_extracted_data=False,
        )
        assert is_stalled(ctx) is False

# =============================================================================
# UNIT TESTS: ContextEnvelope consecutive_same_state off-by-one fix (FIX 1)
# =============================================================================

class TestConsecutiveSameStateOffByOne:
    """Tests for the off-by-one fix in build_context_envelope."""

    def _make_turn(self, state="presentation"):
        """Create a minimal turn mock."""
        turn = Mock()
        turn.state = state
        return turn

    def test_first_turn_returns_1(self):
        """First turn (no turns in window) should return 1."""
        from src.context_envelope import ContextEnvelopeBuilder
        builder = ContextEnvelopeBuilder.__new__(ContextEnvelopeBuilder)
        builder.state_machine = Mock()
        builder.state_machine.state = "greeting"
        builder.state_machine.collected_data = {}
        builder.state_machine.in_disambiguation = False

        cw = Mock()
        cw.turns = []
        cw.get_consecutive_same_state.return_value = 0
        cw.detect_stuck_pattern.return_value = False
        cw.detect_repeated_question.return_value = None
        cw.get_confidence_trend.return_value = "stable"
        cw.get_average_confidence.return_value = 0.5
        cw.__len__ = lambda self: 0
        cw.get_last_turn.return_value = None
        cw.get_intent_history.return_value = []
        cw.get_action_history.return_value = []
        cw.get_objection_count.return_value = 0
        cw.get_positive_count.return_value = 0
        cw.get_question_count.return_value = 0
        cw.get_unclear_count.return_value = 0
        cw.detect_oscillation.return_value = False
        cw.get_structured_context.return_value = {}
        cw.get_momentum.return_value = 0.0
        cw.get_episodic_context.return_value = {}

        builder.context_window = cw
        builder.use_v2_engagement = False
        builder.current_intent = "greeting"

        envelope = Mock()
        envelope.state = "greeting"
        envelope.intent_history = []
        envelope.objection_count = 0
        envelope.total_objections = 0

        builder._fill_from_context_window(envelope)
        assert envelope.consecutive_same_state == 1

    def test_same_state_adds_one(self):
        """Same state as last turn should return raw_count + 1."""
        from src.context_envelope import ContextEnvelopeBuilder
        builder = ContextEnvelopeBuilder.__new__(ContextEnvelopeBuilder)
        builder.state_machine = Mock()  # Needed for _fill_from_context_window check

        cw = Mock()
        turns = [self._make_turn("presentation"), self._make_turn("presentation")]
        cw.turns = turns
        cw.get_consecutive_same_state.return_value = 2
        cw.detect_stuck_pattern.return_value = False
        cw.detect_repeated_question.return_value = None
        cw.get_confidence_trend.return_value = "stable"
        cw.get_average_confidence.return_value = 0.5
        cw.__len__ = lambda self: 2
        cw.get_last_turn.return_value = turns[-1]
        cw.get_intent_history.return_value = []
        cw.get_action_history.return_value = []
        cw.get_objection_count.return_value = 0
        cw.get_positive_count.return_value = 0
        cw.get_question_count.return_value = 0
        cw.get_unclear_count.return_value = 0
        cw.detect_oscillation.return_value = False
        cw.get_structured_context.return_value = {}
        cw.get_momentum.return_value = 0.0
        cw.get_episodic_context.return_value = {}

        builder.context_window = cw
        builder.use_v2_engagement = False
        builder.current_intent = "info_provided"

        envelope = Mock()
        envelope.state = "presentation"
        envelope.intent_history = []
        envelope.objection_count = 0
        envelope.total_objections = 0

        builder._fill_from_context_window(envelope)
        assert envelope.consecutive_same_state == 3  # 2 + 1

    def test_state_changed_returns_1(self):
        """Different state from last turn should return 1."""
        from src.context_envelope import ContextEnvelopeBuilder
        builder = ContextEnvelopeBuilder.__new__(ContextEnvelopeBuilder)
        builder.state_machine = Mock()  # Needed for _fill_from_context_window check

        cw = Mock()
        turns = [self._make_turn("greeting")]
        cw.turns = turns
        cw.get_consecutive_same_state.return_value = 1
        cw.detect_stuck_pattern.return_value = False
        cw.detect_repeated_question.return_value = None
        cw.get_confidence_trend.return_value = "stable"
        cw.get_average_confidence.return_value = 0.5
        cw.__len__ = lambda self: 1
        cw.get_last_turn.return_value = turns[-1]
        cw.get_intent_history.return_value = []
        cw.get_action_history.return_value = []
        cw.get_objection_count.return_value = 0
        cw.get_positive_count.return_value = 0
        cw.get_question_count.return_value = 0
        cw.get_unclear_count.return_value = 0
        cw.detect_oscillation.return_value = False
        cw.get_structured_context.return_value = {}
        cw.get_momentum.return_value = 0.0
        cw.get_episodic_context.return_value = {}

        builder.context_window = cw
        builder.use_v2_engagement = False
        builder.current_intent = "info_provided"

        envelope = Mock()
        envelope.state = "presentation"  # Different from last turn's "greeting"
        envelope.intent_history = []
        envelope.objection_count = 0
        envelope.total_objections = 0

        builder._fill_from_context_window(envelope)
        assert envelope.consecutive_same_state == 1

# =============================================================================
# UNIT TESTS: has_extracted_data in ContextEnvelope (FIX 1b)
# =============================================================================

class TestHasExtractedDataEnvelope:
    """Tests for has_extracted_data field population in ContextEnvelope."""

    def test_meaningful_data_sets_flag(self):
        """has_extracted_data should be True when meaningful data extracted."""
        from src.context_envelope import ContextEnvelopeBuilder
        builder = ContextEnvelopeBuilder.__new__(ContextEnvelopeBuilder)
        builder.classification_result = {
            "extracted_data": {"company_size": "50", "option_index": 1}
        }
        builder.state_machine = None
        builder.context_window = None
        builder.tone_info = {}
        builder.guard_info = {}
        builder.last_action = None
        builder.last_intent = None
        builder.current_intent = None
        builder.use_v2_engagement = False

        envelope = builder.build()
        assert envelope.has_extracted_data is True

    def test_trivial_data_does_not_set_flag(self):
        """has_extracted_data should be False for trivial fields only."""
        from src.context_envelope import ContextEnvelopeBuilder
        builder = ContextEnvelopeBuilder.__new__(ContextEnvelopeBuilder)
        builder.classification_result = {
            "extracted_data": {"option_index": 1, "high_interest": True}
        }
        builder.state_machine = None
        builder.context_window = None
        builder.tone_info = {}
        builder.guard_info = {}
        builder.last_action = None
        builder.last_intent = None
        builder.current_intent = None
        builder.use_v2_engagement = False

        envelope = builder.build()
        assert envelope.has_extracted_data is False

    def test_empty_data_does_not_set_flag(self):
        """has_extracted_data should be False when no data extracted."""
        from src.context_envelope import ContextEnvelopeBuilder
        builder = ContextEnvelopeBuilder.__new__(ContextEnvelopeBuilder)
        builder.classification_result = {"extracted_data": {}}
        builder.state_machine = None
        builder.context_window = None
        builder.tone_info = {}
        builder.guard_info = {}
        builder.last_action = None
        builder.last_intent = None
        builder.current_intent = None
        builder.use_v2_engagement = False

        envelope = builder.build()
        assert envelope.has_extracted_data is False

    def test_none_values_ignored(self):
        """has_extracted_data should ignore None values in meaningful fields."""
        from src.context_envelope import ContextEnvelopeBuilder
        builder = ContextEnvelopeBuilder.__new__(ContextEnvelopeBuilder)
        builder.classification_result = {
            "extracted_data": {"company_size": None, "role": ""}
        }
        builder.state_machine = None
        builder.context_window = None
        builder.tone_info = {}
        builder.guard_info = {}
        builder.last_action = None
        builder.last_intent = None
        builder.current_intent = None
        builder.use_v2_engagement = False

        envelope = builder.build()
        assert envelope.has_extracted_data is False

# =============================================================================
# UNIT TESTS: DataAwareRefinementLayer (FIX 4)
# =============================================================================

class TestDataAwareRefinementLayer:
    """Tests for DataAwareRefinementLayer."""

    def _make_ctx(self, intent="unclear", extracted_data=None):
        from src.classifier.refinement_pipeline import RefinementContext
        return RefinementContext(
            message="торгуем электроникой",
            state="spin_situation",
            intent=intent,
            confidence=0.4,
            extracted_data=extracted_data or {},
        )

    def test_promotes_unclear_with_meaningful_data(self):
        """Should promote unclear → info_provided when meaningful data present."""
        from src.classifier.data_aware_refinement import DataAwareRefinementLayer
        layer = DataAwareRefinementLayer()

        ctx = self._make_ctx(
            intent="unclear",
            extracted_data={"business_type": "electronics", "option_index": 1},
        )
        result = {"intent": "unclear", "confidence": 0.4, "extracted_data": ctx.extracted_data}
        refined = layer._do_refine("торгуем электроникой", result, ctx)
        assert refined.intent == "info_provided"
        assert refined.confidence == 0.75
        assert "data_aware" in refined.refinement_reason

    def test_does_not_promote_without_meaningful_data(self):
        """Should pass through when only trivial fields extracted."""
        from src.classifier.data_aware_refinement import DataAwareRefinementLayer
        layer = DataAwareRefinementLayer()

        ctx = self._make_ctx(
            intent="unclear",
            extracted_data={"option_index": 1},
        )
        result = {"intent": "unclear", "confidence": 0.4, "extracted_data": ctx.extracted_data}
        refined = layer._do_refine("1", result, ctx)
        assert refined.intent == "unclear"

    def test_should_not_apply_non_unclear(self):
        """Should not apply when intent is not 'unclear'."""
        from src.classifier.data_aware_refinement import DataAwareRefinementLayer
        layer = DataAwareRefinementLayer()
        ctx = self._make_ctx(
            intent="greeting",
            extracted_data={"company_size": "50"},
        )
        assert layer._should_apply(ctx) is False

    def test_should_not_apply_no_extracted_data(self):
        """Should not apply when no extracted data at all."""
        from src.classifier.data_aware_refinement import DataAwareRefinementLayer
        layer = DataAwareRefinementLayer()
        ctx = self._make_ctx(intent="unclear", extracted_data={})
        assert layer._should_apply(ctx) is False

    def test_should_apply_unclear_with_data(self):
        """Should apply when intent is unclear and extracted data exists."""
        from src.classifier.data_aware_refinement import DataAwareRefinementLayer
        layer = DataAwareRefinementLayer()
        ctx = self._make_ctx(
            intent="unclear",
            extracted_data={"pain_point": "slow processes"},
        )
        assert layer._should_apply(ctx) is True

# =============================================================================
# UNIT TESTS: Feature Flag for data_aware_refinement (FIX 4 wiring)
# =============================================================================

class TestDataAwareRefinementFeatureFlag:
    """Tests for data_aware_refinement feature flag."""

    def test_flag_in_defaults(self):
        """data_aware_refinement flag must exist in DEFAULTS and be enabled."""
        from src.feature_flags import FeatureFlags
        assert "data_aware_refinement" in FeatureFlags.DEFAULTS
        assert FeatureFlags.DEFAULTS["data_aware_refinement"] is True

    def test_flag_in_pipeline_group(self):
        """data_aware_refinement must be in refinement_pipeline_all group."""
        from src.feature_flags import FeatureFlags
        group = FeatureFlags.GROUPS.get("refinement_pipeline_all", [])
        assert "data_aware_refinement" in group

# =============================================================================
# UNIT TESTS: PolicyContext has_extracted_data transport (FIX 1b)
# =============================================================================

class TestPolicyContextHasExtractedData:
    """Tests for has_extracted_data in PolicyContext."""

    def test_field_exists_default_false(self):
        """PolicyContext should have has_extracted_data defaulting to False."""
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context()
        assert ctx.has_extracted_data is False

    def test_field_settable_via_create_test_context(self):
        """has_extracted_data should be settable via create_test_context."""
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(has_extracted_data=True)
        assert ctx.has_extracted_data is True

    def test_field_in_to_dict(self):
        """has_extracted_data should appear in to_dict output."""
        from src.conditions.policy.context import PolicyContext
        ctx = PolicyContext.create_test_context(has_extracted_data=True)
        d = ctx.to_dict()
        assert "has_extracted_data" in d
        assert d["has_extracted_data"] is True

    def test_from_envelope_transfers_field(self):
        """from_envelope should copy has_extracted_data from envelope."""
        from src.conditions.policy.context import PolicyContext
        envelope = Mock()
        envelope.collected_data = {}
        envelope.state = "presentation"
        envelope.total_turns = 3
        envelope.current_phase = "presentation"
        envelope.spin_phase = None
        envelope.last_action = None
        envelope.last_intent = None
        envelope.current_intent = None
        envelope.is_stuck = False
        envelope.consecutive_same_state = 2
        envelope.has_oscillation = False
        envelope.repeated_question = None
        envelope.confidence_trend = "stable"
        envelope.unclear_count = 0
        envelope.momentum = 0.0
        envelope.momentum_direction = "neutral"
        envelope.engagement_level = "medium"
        envelope.engagement_trend = "stable"
        envelope.funnel_velocity = 0.0
        envelope.is_progressing = False
        envelope.is_regressing = False
        envelope.has_extracted_data = True
        envelope.total_objections = 0
        envelope.repeated_objection_types = []
        envelope.has_breakthrough = False
        envelope.turns_since_breakthrough = None
        envelope.most_effective_action = None
        envelope.least_effective_action = None
        envelope.frustration_level = 0
        envelope.guard_intervention = None
        envelope.pre_intervention_triggered = False
        envelope.secondary_intents = []
        envelope.max_consecutive_objections = 3
        envelope.max_total_objections = 5

        ctx = PolicyContext.from_envelope(envelope)
        assert ctx.has_extracted_data is True

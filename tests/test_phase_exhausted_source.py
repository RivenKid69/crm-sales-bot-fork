# tests/test_phase_exhausted_source.py

"""
Tests for PhaseExhaustedSource Knowledge Source.

Covers:
- should_contribute: exclusive window logic [phase_threshold, stall_soft)
- should_contribute: respects feature flag, enabled state, terminal states
- should_contribute: respects progress flags (is_progressing, has_extracted_data)
- should_contribute: empty window states (greeting, handle_objection)
- contribute: proposes action="offer_options" at NORMAL priority, combinable=True
"""

import pytest
from unittest.mock import Mock, MagicMock, patch


class TestPhaseExhaustedShouldContribute:
    """Tests for PhaseExhaustedSource.should_contribute()."""

    def _make_source(self, enabled=True):
        from src.blackboard.sources.phase_exhausted import PhaseExhaustedSource
        return PhaseExhaustedSource(enabled=enabled)

    def _make_blackboard(
        self,
        state="presentation",
        max_turns=5,
        phase_exhaust_threshold=3,
        consecutive=3,
        is_progressing=False,
        has_extracted_data=False,
    ):
        """Create a mock blackboard with given context."""
        bb = MagicMock()

        envelope = Mock()
        envelope.consecutive_same_state = consecutive
        envelope.is_progressing = is_progressing
        envelope.has_extracted_data = has_extracted_data

        ctx = Mock()
        ctx.state = state
        ctx.state_config = {
            "max_turns_in_state": max_turns,
            "phase_exhaust_threshold": phase_exhaust_threshold,
        }
        ctx.context_envelope = envelope

        bb.get_context.return_value = ctx
        return bb

    def test_fires_in_exclusive_window(self):
        """should_contribute returns True when consecutive is in [threshold, stall_soft)."""
        source = self._make_source()
        # max_turns=5, threshold=3, stall_soft=max(5-1,3)=4
        # consecutive=3 is in [3, 4) -> should fire
        bb = self._make_blackboard(max_turns=5, phase_exhaust_threshold=3, consecutive=3)
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is True

    def test_does_not_fire_below_threshold(self):
        """should_contribute returns False when consecutive < phase_exhaust_threshold."""
        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, phase_exhaust_threshold=3, consecutive=2)
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_does_not_fire_at_stall_soft_threshold(self):
        """should_contribute returns False when consecutive >= stall_soft (StallGuard territory)."""
        source = self._make_source()
        # max_turns=5, stall_soft=max(5-1,3)=4
        # consecutive=4 >= stall_soft -> should NOT fire
        bb = self._make_blackboard(max_turns=5, phase_exhaust_threshold=3, consecutive=4)
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_does_not_fire_above_stall_soft(self):
        """should_contribute returns False when consecutive > stall_soft."""
        source = self._make_source()
        bb = self._make_blackboard(max_turns=5, phase_exhaust_threshold=3, consecutive=5)
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_does_not_fire_when_progressing(self):
        """should_contribute returns False when is_progressing=True."""
        source = self._make_source()
        bb = self._make_blackboard(
            max_turns=5, phase_exhaust_threshold=3, consecutive=3,
            is_progressing=True,
        )
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_does_not_fire_when_has_extracted_data(self):
        """should_contribute returns False when has_extracted_data=True."""
        source = self._make_source()
        bb = self._make_blackboard(
            max_turns=5, phase_exhaust_threshold=3, consecutive=3,
            has_extracted_data=True,
        )
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_empty_window_greeting(self):
        """Greeting (max_turns=4, threshold=3): stall_soft=max(3,3)=3, window=[3,3) is empty."""
        source = self._make_source()
        bb = self._make_blackboard(
            state="greeting", max_turns=4, phase_exhaust_threshold=3, consecutive=3
        )
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            # consecutive=3, stall_soft=max(4-1,3)=3 -> 3 >= 3 -> False
            assert source.should_contribute(bb) is False

    def test_empty_window_handle_objection(self):
        """handle_objection (max_turns=4, threshold=3): window=[3,3) is empty."""
        source = self._make_source()
        bb = self._make_blackboard(
            state="handle_objection", max_turns=4, phase_exhaust_threshold=3, consecutive=3
        )
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_wide_window_close(self):
        """close (max_turns=6, threshold=3): stall_soft=max(5,3)=5, window=[3,5)."""
        source = self._make_source()
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True

            # consecutive=3 -> in [3, 5) -> True
            bb = self._make_blackboard(
                state="close", max_turns=6, phase_exhaust_threshold=3, consecutive=3
            )
            assert source.should_contribute(bb) is True

            # consecutive=4 -> in [3, 5) -> True
            bb = self._make_blackboard(
                state="close", max_turns=6, phase_exhaust_threshold=3, consecutive=4
            )
            assert source.should_contribute(bb) is True

            # consecutive=5 -> 5 >= stall_soft=5 -> False (StallGuard fires)
            bb = self._make_blackboard(
                state="close", max_turns=6, phase_exhaust_threshold=3, consecutive=5
            )
            assert source.should_contribute(bb) is False

    def test_disabled_when_flag_off(self):
        """should_contribute returns False when feature flag is disabled."""
        source = self._make_source()
        bb = self._make_blackboard(consecutive=3)
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = False
            assert source.should_contribute(bb) is False

    def test_disabled_when_self_enabled_false(self):
        """should_contribute returns False when self._enabled is False."""
        source = self._make_source(enabled=False)
        bb = self._make_blackboard(consecutive=3)
        assert source.should_contribute(bb) is False

    def test_disabled_when_max_turns_zero(self):
        """should_contribute returns False for terminal states (max_turns=0)."""
        source = self._make_source()
        bb = self._make_blackboard(state="success", max_turns=0, consecutive=10)
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False

    def test_disabled_when_envelope_is_none(self):
        """should_contribute returns False when context_envelope is None."""
        source = self._make_source()
        bb = MagicMock()
        ctx = Mock()
        ctx.context_envelope = None
        bb.get_context.return_value = ctx
        with patch("src.blackboard.sources.phase_exhausted.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            assert source.should_contribute(bb) is False


class TestPhaseExhaustedContribute:
    """Tests for PhaseExhaustedSource.contribute()."""

    def _make_source(self):
        from src.blackboard.sources.phase_exhausted import PhaseExhaustedSource
        return PhaseExhaustedSource()

    def _make_blackboard(self, state="presentation", max_turns=5,
                         phase_exhaust_threshold=3, consecutive=3):
        bb = MagicMock()

        envelope = Mock()
        envelope.consecutive_same_state = consecutive

        ctx = Mock()
        ctx.state = state
        ctx.state_config = {
            "max_turns_in_state": max_turns,
            "phase_exhaust_threshold": phase_exhaust_threshold,
        }
        ctx.context_envelope = envelope

        bb.get_context.return_value = ctx
        return bb

    def test_proposes_offer_options_action(self):
        """contribute proposes action='offer_options' at NORMAL priority with combinable=True."""
        from src.blackboard.enums import Priority

        source = self._make_source()
        bb = self._make_blackboard()
        source.contribute(bb)

        bb.propose_action.assert_called_once()
        call_kwargs = bb.propose_action.call_args
        assert call_kwargs.kwargs["action"] == "offer_options"
        assert call_kwargs.kwargs["priority"] == Priority.NORMAL
        assert call_kwargs.kwargs["combinable"] is True
        assert call_kwargs.kwargs["reason_code"] == "phase_exhausted_options"
        assert call_kwargs.kwargs["source_name"] == "PhaseExhaustedSource"

    def test_metadata_contains_state_info(self):
        """contribute metadata includes state, consecutive turns, thresholds."""
        source = self._make_source()
        bb = self._make_blackboard(state="close", consecutive=4, max_turns=6)
        source.contribute(bb)

        metadata = bb.propose_action.call_args.kwargs["metadata"]
        assert metadata["options_type"] == "phase_exhausted"
        assert metadata["from_state"] == "close"
        assert metadata["consecutive_turns"] == 4
        assert metadata["max_turns_in_state"] == 6

    def test_does_not_propose_when_disabled(self):
        """contribute does nothing when self._enabled is False."""
        from src.blackboard.sources.phase_exhausted import PhaseExhaustedSource
        source = PhaseExhaustedSource(enabled=False)
        bb = self._make_blackboard()
        source.contribute(bb)
        bb.propose_action.assert_not_called()

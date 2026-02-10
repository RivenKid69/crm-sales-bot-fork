"""
Tests for phase coverage fix - ensuring visited_states is properly used
to extract phases during simulation.

This fixes the issue where fallback skip causes the bot to transition through
intermediate states (e.g., greeting -> spin_situation -> spin_problem) but only
the final state was recorded, leading to incorrect phase coverage calculations.

The fix:
1. bot.py now tracks all visited_states during a turn
2. runner.py records visited_states in turn_data
3. metrics.py extracts phases from visited_states as primary source
"""

import pytest
import sys
from pathlib import Path

from src.simulator.metrics import (
    extract_phases_from_dialogue,
    calculate_spin_coverage,
    build_phase_mapping_from_flow
)
from src.config_loader import ConfigLoader

class TestPhaseCoverageFix:
    """Tests for the phase coverage fix."""

    @pytest.fixture
    def flow_config(self):
        """Load SPIN selling flow config."""
        loader = ConfigLoader()
        return loader.load_flow("spin_selling")

    def test_visited_states_extracts_all_phases(self, flow_config):
        """Test that visited_states is used to extract all phases.

        Scenario: Fallback skip causes transition through spin_situation
        Old behavior: Only spin_problem recorded, situation phase missing
        New behavior: visited_states includes spin_situation, situation phase found
        """
        dialogue = [
            {"turn": 1, "state": "greeting", "visited_states": ["greeting"]},
            {"turn": 2, "state": "greeting", "visited_states": ["greeting"]},
            # Fallback skip: greeting -> spin_situation -> spin_problem
            {
                "turn": 3,
                "state": "spin_problem",
                "visited_states": ["greeting", "spin_situation", "spin_problem"],
            },
            {"turn": 4, "state": "close", "visited_states": ["spin_problem", "close"]},
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=flow_config)

        # Should include situation from visited_states
        assert "situation" in phases, "situation phase should be extracted from visited_states"
        assert "problem" in phases
        assert "presentation" in phases  # from close state

    def test_legacy_format_still_works(self, flow_config):
        """Test that legacy format without visited_states still works.

        Uses decision_trace as fallback source.
        """
        dialogue = [
            {"turn": 1, "state": "greeting"},
            {
                "turn": 2,
                "state": "spin_problem",
                "decision_trace": {
                    "state_machine": {
                        "prev_state": "spin_situation",
                        "next_state": "spin_problem",
                        "prev_phase": "situation",
                        "next_phase": "problem",
                    }
                },
            },
            {"turn": 3, "state": "close"},
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=flow_config)

        # Should find situation from decision_trace.state_machine.prev_state/prev_phase
        assert "situation" in phases
        assert "problem" in phases
        assert "presentation" in phases

    def test_empty_visited_states_uses_fallback(self, flow_config):
        """Test that empty visited_states falls back to other sources."""
        dialogue = [
            {"turn": 1, "state": "spin_situation", "visited_states": []},
            {"turn": 2, "state": "spin_problem"},  # No visited_states key
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=flow_config)

        assert "situation" in phases
        assert "problem" in phases

    def test_coverage_improves_with_visited_states(self, flow_config):
        """Test that phase coverage improves when visited_states is used.

        Before fix: Coverage = 2/4 = 0.50 (only problem, presentation)
        After fix: Coverage = 3/4 = 0.75 (situation, problem, presentation)
        """
        # Old format (broken)
        dialogue_old = [
            {"turn": 1, "state": "greeting"},
            {"turn": 2, "state": "greeting"},
            {"turn": 3, "state": "spin_problem"},  # Jumped over spin_situation!
            {"turn": 4, "state": "close"},
        ]

        # New format with visited_states
        dialogue_new = [
            {"turn": 1, "state": "greeting", "visited_states": ["greeting"]},
            {"turn": 2, "state": "greeting", "visited_states": ["greeting"]},
            {
                "turn": 3,
                "state": "spin_problem",
                "visited_states": ["greeting", "spin_situation", "spin_problem"],
            },
            {"turn": 4, "state": "close", "visited_states": ["spin_problem", "close"]},
        ]

        phases_old = extract_phases_from_dialogue(dialogue_old, flow_config=flow_config)
        phases_new = extract_phases_from_dialogue(dialogue_new, flow_config=flow_config)

        coverage_old = calculate_spin_coverage(phases_old, expected_phases=flow_config.phase_order)
        coverage_new = calculate_spin_coverage(phases_new, expected_phases=flow_config.phase_order)

        # Old format misses situation
        assert "situation" not in phases_old

        # New format captures situation
        assert "situation" in phases_new

        # Coverage should be better with new format
        assert coverage_new > coverage_old

    def test_multiple_fallback_skips(self, flow_config):
        """Test with multiple fallback skips in conversation."""
        dialogue = [
            {"turn": 1, "state": "greeting", "visited_states": ["greeting"]},
            # First skip: greeting -> spin_situation
            {
                "turn": 2,
                "state": "spin_situation",
                "visited_states": ["greeting", "spin_situation"],
            },
            # Second skip: spin_situation -> spin_problem -> spin_implication
            {
                "turn": 3,
                "state": "spin_implication",
                "visited_states": ["spin_situation", "spin_problem", "spin_implication"],
            },
            {"turn": 4, "state": "close", "visited_states": ["spin_implication", "close"]},
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=flow_config)

        # Should capture all phases from visited_states
        assert "situation" in phases
        assert "problem" in phases
        assert "implication" in phases
        assert "presentation" in phases  # from close

class TestBuildPhaseMapping:
    """Tests for build_phase_mapping_from_flow."""

    @pytest.fixture
    def flow_config(self):
        """Load SPIN selling flow config."""
        loader = ConfigLoader()
        return loader.load_flow("spin_selling")

    def test_mapping_includes_spin_states(self, flow_config):
        """Test that mapping includes SPIN states."""
        mapping = build_phase_mapping_from_flow(flow_config)

        assert "spin_situation" in mapping
        assert "spin_problem" in mapping
        assert "spin_implication" in mapping
        assert "spin_need_payoff" in mapping

        assert mapping["spin_situation"] == "situation"
        assert mapping["spin_problem"] == "problem"

    def test_mapping_includes_presentation_states(self, flow_config):
        """Test that presentation and close map to presentation phase."""
        mapping = build_phase_mapping_from_flow(flow_config)

        assert mapping.get("presentation") == "presentation"
        assert mapping.get("close") == "presentation"

class TestMultiFlowPhaseCoverage:
    """
    Parametrized tests to verify phase coverage works across ALL flows.

    This ensures the fix is universal and not SPIN-specific.
    """

    # Flow configurations: (flow_name, states, expected_phases)
    FLOW_TEST_CASES = [
        # SPIN Selling
        (
            "spin_selling",
            ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"],
            ["situation", "problem", "implication", "need_payoff"],
        ),
        # BANT
        (
            "bant",
            ["bant_budget", "bant_authority", "bant_need", "bant_timeline"],
            ["budget", "authority", "need", "timeline"],
        ),
        # Challenger Sale
        (
            "challenger",
            ["challenger_teach", "challenger_tailor", "challenger_close"],
            ["teach", "tailor", "take_control"],
        ),
        # Solution Selling (states from flow.yaml: solution_pain, solution_map, solution_value)
        (
            "solution",
            ["solution_pain", "solution_map", "solution_value"],
            ["pain_discovery", "solution_mapping", "value_proof"],
        ),
        # Consultative Selling (states from flow.yaml: consult_understand, consult_advise, consult_recommend)
        (
            "consultative",
            ["consult_understand", "consult_advise", "consult_recommend"],
            ["understand", "advise", "recommend"],
        ),
    ]

    @pytest.fixture
    def loader(self):
        """Config loader instance."""
        return ConfigLoader()

    @pytest.mark.parametrize("flow_name,states,expected_phases", FLOW_TEST_CASES)
    def test_flow_phase_mapping_is_correct(self, loader, flow_name, states, expected_phases):
        """Test that each flow has correct state->phase mapping."""
        flow_config = loader.load_flow(flow_name)
        mapping = build_phase_mapping_from_flow(flow_config)

        # Verify each state maps to expected phase
        for state, phase in zip(states, expected_phases):
            assert state in mapping, f"{flow_name}: state '{state}' not in mapping"
            assert mapping[state] == phase, f"{flow_name}: {state} should map to {phase}, got {mapping[state]}"

    @pytest.mark.parametrize("flow_name,states,expected_phases", FLOW_TEST_CASES)
    def test_visited_states_extracts_phases_for_flow(self, loader, flow_name, states, expected_phases):
        """Test that visited_states extraction works for each flow."""
        flow_config = loader.load_flow(flow_name)

        # Simulate fallback skip through first two states
        dialogue = [
            {"turn": 1, "state": "greeting", "visited_states": ["greeting"]},
            {
                "turn": 2,
                "state": states[1] if len(states) > 1 else states[0],
                "visited_states": ["greeting", states[0], states[1]] if len(states) > 1 else ["greeting", states[0]],
            },
            {"turn": 3, "state": "close", "visited_states": [states[-1], "close"]},
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=flow_config)

        # Should capture phases from visited_states
        assert expected_phases[0] in phases, f"{flow_name}: first phase '{expected_phases[0]}' not extracted"
        if len(expected_phases) > 1:
            assert expected_phases[1] in phases, f"{flow_name}: second phase '{expected_phases[1]}' not extracted"
        assert "presentation" in phases, f"{flow_name}: presentation phase not extracted from 'close' state"

    @pytest.mark.parametrize("flow_name,states,expected_phases", FLOW_TEST_CASES)
    def test_coverage_calculation_for_flow(self, loader, flow_name, states, expected_phases):
        """Test that coverage calculation works correctly for each flow."""
        flow_config = loader.load_flow(flow_name)

        # Simulate reaching all phases + presentation
        dialogue = [
            {"turn": 1, "state": "greeting", "visited_states": ["greeting"]},
        ]
        # Add all states
        for i, state in enumerate(states):
            dialogue.append({
                "turn": i + 2,
                "state": state,
                "visited_states": [state],
            })
        dialogue.append({
            "turn": len(states) + 2,
            "state": "close",
            "visited_states": ["close"],
        })

        phases = extract_phases_from_dialogue(dialogue, flow_config=flow_config)
        coverage = calculate_spin_coverage(phases, expected_phases=flow_config.phase_order)

        # Should have full coverage (all phases + presentation)
        assert coverage == 1.0, f"{flow_name}: expected 100% coverage, got {coverage}"

    @pytest.mark.parametrize("flow_name,states,expected_phases", FLOW_TEST_CASES)
    def test_partial_coverage_for_flow(self, loader, flow_name, states, expected_phases):
        """Test partial coverage when only some phases are reached."""
        flow_config = loader.load_flow(flow_name)

        # Only visit first state + close
        dialogue = [
            {"turn": 1, "state": states[0], "visited_states": [states[0]]},
            {"turn": 2, "state": "close", "visited_states": ["close"]},
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=flow_config)
        coverage = calculate_spin_coverage(phases, expected_phases=flow_config.phase_order)

        # Should have partial coverage (first phase + presentation out of all phases + presentation)
        expected_coverage = 2 / (len(expected_phases) + 1)  # 2 phases matched / total phases
        assert abs(coverage - expected_coverage) < 0.01, \
            f"{flow_name}: expected {expected_coverage:.2f} coverage, got {coverage:.2f}"

class TestCalculateSpinCoverage:
    """Tests for calculate_spin_coverage.

    Note: calculate_spin_coverage automatically adds 'presentation' to expected phases
    if not present. This increases the denominator by 1.
    """

    def test_full_coverage(self):
        """Test 100% coverage including presentation."""
        # Function adds 'presentation' to expected, so we need to include it
        phases = ["situation", "problem", "implication", "need_payoff", "presentation"]
        expected = ["situation", "problem", "implication", "need_payoff"]

        coverage = calculate_spin_coverage(phases, expected_phases=expected)
        # Expected has 4 phases + presentation added = 5 phases
        # All 5 matched = 100%
        assert coverage == 1.0

    def test_partial_coverage(self):
        """Test partial coverage."""
        phases = ["situation", "problem", "presentation"]
        expected = ["situation", "problem", "implication", "need_payoff"]

        coverage = calculate_spin_coverage(phases, expected_phases=expected)
        # Expected has 4 + presentation = 5 phases
        # We have 3 matching = 3/5 = 0.6
        assert coverage == 0.6

    def test_extra_phases_ignored(self):
        """Test that extra phases not in expected don't affect coverage."""
        phases = ["situation", "problem", "presentation", "extra_phase"]
        expected = ["situation", "problem", "implication", "need_payoff"]

        coverage = calculate_spin_coverage(phases, expected_phases=expected)
        # Expected has 4 + presentation = 5 phases
        # We have situation, problem, presentation matched = 3/5 = 0.6
        assert coverage == 0.6  # extra_phase is ignored

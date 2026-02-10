"""
Tests for dynamic flow configuration support.

Validates that:
1. Different flows (SPIN, BANT, Challenger, etc.) are loaded correctly
2. Phase extraction works with any flow, not just SPIN
3. StateMachine uses the correct flow's states and transitions
4. Flow switching works correctly in SalesBot
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Dict, List

from src.config_loader import ConfigLoader, FlowConfig
from src.simulator.metrics import (
    extract_phases_from_dialogue,
    calculate_spin_coverage,
    build_phase_mapping_from_flow,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def config_loader():
    """Create ConfigLoader instance."""
    return ConfigLoader()

@pytest.fixture
def spin_flow(config_loader):
    """Load SPIN Selling flow."""
    return config_loader.load_flow("spin_selling")

@pytest.fixture
def bant_flow(config_loader):
    """Load BANT flow."""
    return config_loader.load_flow("bant")

@pytest.fixture
def challenger_flow(config_loader):
    """Load Challenger flow."""
    return config_loader.load_flow("challenger")

@pytest.fixture
def all_flows(config_loader):
    """Load all available flows."""
    flows_dir = Path(__file__).parent.parent / "src" / "yaml_config" / "flows"
    # Exclude _base, examples, and other non-flow directories
    excluded = {"_base", "examples", "__pycache__"}
    flow_names = [
        d.name for d in flows_dir.iterdir()
        if d.is_dir() and d.name not in excluded and not d.name.startswith("_")
    ]
    return {name: config_loader.load_flow(name) for name in flow_names}

# =============================================================================
# Tests: FlowConfig Loading
# =============================================================================

class TestFlowConfigLoading:
    """Tests for correct flow configuration loading."""

    def test_spin_flow_has_correct_phases(self, spin_flow):
        """SPIN flow should have situation, problem, implication, need_payoff phases."""
        expected_phases = ["situation", "problem", "implication", "need_payoff"]
        assert spin_flow.phase_order == expected_phases

    def test_bant_flow_has_correct_phases(self, bant_flow):
        """BANT flow should have budget, authority, need, timeline phases."""
        expected_phases = ["budget", "authority", "need", "timeline"]
        assert bant_flow.phase_order == expected_phases

    def test_challenger_flow_has_correct_phases(self, challenger_flow):
        """Challenger flow should have teach, tailor, take_control phases."""
        expected_phases = ["teach", "tailor", "take_control"]
        assert challenger_flow.phase_order == expected_phases

    def test_spin_flow_phase_mapping(self, spin_flow):
        """SPIN phase mapping should map to spin_* states."""
        mapping = spin_flow.phase_mapping
        assert mapping.get("situation") == "spin_situation"
        assert mapping.get("problem") == "spin_problem"
        assert mapping.get("implication") == "spin_implication"
        assert mapping.get("need_payoff") == "spin_need_payoff"

    def test_bant_flow_phase_mapping(self, bant_flow):
        """BANT phase mapping should map to bant_* states."""
        mapping = bant_flow.phase_mapping
        assert mapping.get("budget") == "bant_budget"
        assert mapping.get("authority") == "bant_authority"
        assert mapping.get("need") == "bant_need"
        assert mapping.get("timeline") == "bant_timeline"

    def test_challenger_flow_phase_mapping(self, challenger_flow):
        """Challenger phase mapping should map to challenger_* states."""
        mapping = challenger_flow.phase_mapping
        assert mapping.get("teach") == "challenger_teach"
        assert mapping.get("tailor") == "challenger_tailor"
        assert mapping.get("take_control") == "challenger_close"

    def test_all_flows_have_greeting_state(self, all_flows):
        """All flows should have a greeting state."""
        for name, flow in all_flows.items():
            assert "greeting" in flow.states, f"Flow {name} missing greeting state"

    def test_bant_greeting_transitions_to_bant_states(self, bant_flow):
        """BANT flow's greeting should transition to bant_* states, not spin_* states."""
        greeting = bant_flow.states.get("greeting", {})
        transitions = greeting.get("transitions", {})

        # Check that transitions go to bant_budget, not spin_situation
        assert transitions.get("price_question") == "bant_budget"
        assert transitions.get("agreement") == "bant_budget"
        assert transitions.get("info_provided") == "bant_budget"

        # Verify no SPIN states in transitions
        for intent, target in transitions.items():
            if isinstance(target, str):
                assert "spin_" not in target, \
                    f"BANT greeting should not transition to SPIN state: {intent} -> {target}"

    def test_flow_variables_substituted(self, bant_flow):
        """Flow variables like {{entry_state}} should be substituted."""
        greeting = bant_flow.states.get("greeting", {})
        transitions = greeting.get("transitions", {})

        # Check that no unsubstituted variables remain
        for intent, target in transitions.items():
            if isinstance(target, str):
                assert "{{" not in target, \
                    f"Unsubstituted variable in transition: {intent} -> {target}"

# =============================================================================
# Tests: Phase Extraction
# =============================================================================

class TestPhaseExtraction:
    """Tests for extract_phases_from_dialogue with different flows."""

    def test_extract_spin_phases(self, spin_flow):
        """Should extract SPIN phases from dialogue with SPIN states."""
        dialogue = [
            {"turn": 1, "state": "greeting"},
            {"turn": 2, "state": "spin_situation"},
            {"turn": 3, "state": "spin_situation"},
            {"turn": 4, "state": "spin_problem"},
            {"turn": 5, "state": "spin_implication"},
            {"turn": 6, "state": "presentation"},
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=spin_flow)

        assert "situation" in phases
        assert "problem" in phases
        assert "implication" in phases
        assert "presentation" in phases

    def test_extract_bant_phases(self, bant_flow):
        """Should extract BANT phases from dialogue with BANT states."""
        dialogue = [
            {"turn": 1, "state": "greeting"},
            {"turn": 2, "state": "bant_budget"},
            {"turn": 3, "state": "bant_authority"},
            {"turn": 4, "state": "bant_need"},
            {"turn": 5, "state": "bant_timeline"},
            {"turn": 6, "state": "presentation"},
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=bant_flow)

        assert "budget" in phases
        assert "authority" in phases
        assert "need" in phases
        assert "timeline" in phases
        assert "presentation" in phases

    def test_extract_challenger_phases(self, challenger_flow):
        """Should extract Challenger phases from dialogue with Challenger states."""
        dialogue = [
            {"turn": 1, "state": "greeting"},
            {"turn": 2, "state": "challenger_teach"},
            {"turn": 3, "state": "challenger_tailor"},
            {"turn": 4, "state": "challenger_close"},
            {"turn": 5, "state": "presentation"},
        ]

        phases = extract_phases_from_dialogue(dialogue, flow_config=challenger_flow)

        assert "teach" in phases
        assert "tailor" in phases
        assert "take_control" in phases
        assert "presentation" in phases

    def test_legacy_spin_fallback_without_flow_config(self):
        """Without flow_config, should fall back to SPIN phase extraction."""
        dialogue = [
            {"turn": 1, "state": "spin_situation"},
            {"turn": 2, "state": "spin_problem"},
        ]

        phases = extract_phases_from_dialogue(dialogue)  # No flow_config

        assert "situation" in phases
        assert "problem" in phases

    def test_bant_states_not_extracted_with_spin_mapping(self):
        """BANT states should NOT be extracted when using legacy SPIN mapping."""
        dialogue = [
            {"turn": 1, "state": "bant_budget"},
            {"turn": 2, "state": "bant_authority"},
        ]

        phases = extract_phases_from_dialogue(dialogue)  # Legacy SPIN mapping

        # BANT states are not in SPIN mapping, so no phases should be extracted
        assert "budget" not in phases
        assert "authority" not in phases

    def test_custom_phase_mapping(self):
        """Should work with custom phase_mapping dict."""
        custom_mapping = {
            "custom_state_a": "phase_a",
            "custom_state_b": "phase_b",
        }

        dialogue = [
            {"turn": 1, "state": "custom_state_a"},
            {"turn": 2, "state": "custom_state_b"},
        ]

        phases = extract_phases_from_dialogue(dialogue, phase_mapping=custom_mapping)

        assert "phase_a" in phases
        assert "phase_b" in phases

# =============================================================================
# Tests: Phase Coverage Calculation
# =============================================================================

class TestPhaseCoverage:
    """Tests for calculate_spin_coverage with different flows."""

    def test_full_spin_coverage(self):
        """Full SPIN coverage should be 1.0."""
        phases = ["situation", "problem", "implication", "need_payoff", "presentation"]
        expected = ["situation", "problem", "implication", "need_payoff"]

        coverage = calculate_spin_coverage(phases, expected_phases=expected)
        assert coverage == 1.0

    def test_partial_spin_coverage(self):
        """Partial SPIN coverage should be proportional."""
        phases = ["situation", "problem"]
        expected = ["situation", "problem", "implication", "need_payoff"]

        # 2 phases + presentation added = 3 phases expected total (with presentation)
        # Actually: 2/5 phases covered (expected + presentation)
        coverage = calculate_spin_coverage(phases, expected_phases=expected)
        # 2 matched out of 5 expected (4 phases + presentation)
        assert coverage == pytest.approx(0.4, rel=0.01)

    def test_full_bant_coverage(self):
        """Full BANT coverage should be 1.0."""
        phases = ["budget", "authority", "need", "timeline", "presentation"]
        expected = ["budget", "authority", "need", "timeline"]

        coverage = calculate_spin_coverage(phases, expected_phases=expected)
        assert coverage == 1.0

    def test_full_challenger_coverage(self):
        """Full Challenger coverage should be 1.0."""
        phases = ["teach", "tailor", "take_control", "presentation"]
        expected = ["teach", "tailor", "take_control"]

        coverage = calculate_spin_coverage(phases, expected_phases=expected)
        assert coverage == 1.0

    def test_empty_phases_zero_coverage(self):
        """Empty phases should have 0 coverage."""
        phases = []
        expected = ["budget", "authority", "need", "timeline"]

        coverage = calculate_spin_coverage(phases, expected_phases=expected)
        assert coverage == 0.0

    def test_mismatched_phases_low_coverage(self):
        """Mismatched phases (SPIN in BANT flow) should have low coverage."""
        # SPIN phases used in dialogue
        spin_phases = ["situation", "problem", "implication"]
        # But expected BANT phases
        bant_expected = ["budget", "authority", "need", "timeline"]

        coverage = calculate_spin_coverage(spin_phases, expected_phases=bant_expected)
        # Only presentation might match if added
        assert coverage < 0.2

# =============================================================================
# Tests: Build Phase Mapping
# =============================================================================

class TestBuildPhaseMapping:
    """Tests for build_phase_mapping_from_flow helper."""

    def test_build_spin_mapping(self, spin_flow):
        """Build mapping from SPIN flow."""
        mapping = build_phase_mapping_from_flow(spin_flow)

        assert mapping["spin_situation"] == "situation"
        assert mapping["spin_problem"] == "problem"
        assert mapping["spin_implication"] == "implication"
        assert mapping["spin_need_payoff"] == "need_payoff"
        assert mapping["presentation"] == "presentation"

    def test_build_bant_mapping(self, bant_flow):
        """Build mapping from BANT flow."""
        mapping = build_phase_mapping_from_flow(bant_flow)

        assert mapping["bant_budget"] == "budget"
        assert mapping["bant_authority"] == "authority"
        assert mapping["bant_need"] == "need"
        assert mapping["bant_timeline"] == "timeline"
        assert mapping["presentation"] == "presentation"

    def test_build_challenger_mapping(self, challenger_flow):
        """Build mapping from Challenger flow."""
        mapping = build_phase_mapping_from_flow(challenger_flow)

        assert mapping["challenger_teach"] == "teach"
        assert mapping["challenger_tailor"] == "tailor"
        assert mapping["challenger_close"] == "take_control"
        assert mapping["presentation"] == "presentation"

# =============================================================================
# Tests: StateMachine Flow Integration
# =============================================================================

class TestStateMachineFlowIntegration:
    """Tests for StateMachine using correct flow configuration."""

    def test_state_machine_uses_flow_states(self, config_loader, bant_flow):
        """StateMachine should use states from the provided FlowConfig."""
        from src.state_machine import StateMachine

        config = config_loader.load()
        sm = StateMachine(config=config, flow=bant_flow)

        # Check that states_config comes from FlowConfig
        assert "bant_budget" in sm.states_config
        assert "bant_authority" in sm.states_config

        # SPIN states should NOT be in BANT flow
        assert "spin_situation" not in sm.states_config

    def test_state_machine_phase_order_from_flow(self, config_loader, bant_flow):
        """StateMachine phase_order should come from FlowConfig."""
        from src.state_machine import StateMachine

        config = config_loader.load()
        sm = StateMachine(config=config, flow=bant_flow)

        assert sm.phase_order == ["budget", "authority", "need", "timeline"]

    def test_state_machine_phase_states_from_flow(self, config_loader, bant_flow):
        """StateMachine phase_states should come from FlowConfig."""
        from src.state_machine import StateMachine

        config = config_loader.load()
        sm = StateMachine(config=config, flow=bant_flow)

        assert sm.phase_states["budget"] == "bant_budget"
        assert sm.phase_states["authority"] == "bant_authority"

    def test_greeting_transition_in_bant_flow(self, config_loader, bant_flow):
        """Greeting state transitions should go to BANT states."""
        from src.state_machine import StateMachine

        config = config_loader.load()
        sm = StateMachine(config=config, flow=bant_flow)

        # Check greeting transitions
        greeting_config = sm.states_config.get("greeting", {})
        transitions = greeting_config.get("transitions", {})

        # Should transition to bant_budget, not spin_situation
        assert transitions.get("agreement") == "bant_budget"
        assert transitions.get("price_question") == "bant_budget"

# =============================================================================
# Tests: End-to-End Flow Validation
# =============================================================================

class TestEndToEndFlowValidation:
    """End-to-end tests validating the complete flow chain."""

    @pytest.mark.parametrize("flow_name,expected_first_phase_state", [
        ("spin_selling", "spin_situation"),
        ("bant", "bant_budget"),
        ("challenger", "challenger_teach"),
    ])
    def test_flow_entry_state(self, config_loader, flow_name, expected_first_phase_state):
        """Each flow should have correct entry state after greeting."""
        flow = config_loader.load_flow(flow_name)

        # Check that greeting transitions to the correct first phase state
        greeting = flow.states.get("greeting", {})
        transitions = greeting.get("transitions", {})

        # At least one transition should go to the first phase state
        first_phase_targets = [
            t for t in transitions.values()
            if isinstance(t, str) and expected_first_phase_state in t
        ]
        assert len(first_phase_targets) > 0, \
            f"{flow_name} greeting should transition to {expected_first_phase_state}"

    def test_all_flows_phases_extractable(self, all_flows):
        """All flows should have extractable phases from dialogue."""
        for flow_name, flow in all_flows.items():
            # Create dialogue with flow's phase states
            dialogue = [{"turn": 1, "state": "greeting"}]
            for phase, state in flow.phase_mapping.items():
                dialogue.append({"turn": len(dialogue) + 1, "state": state})

            # Extract phases
            phases = extract_phases_from_dialogue(dialogue, flow_config=flow)

            # Should extract all expected phases
            for expected_phase in flow.phase_order:
                assert expected_phase in phases, \
                    f"Flow {flow_name}: Phase {expected_phase} not extracted"

    def test_flow_isolation(self, config_loader):
        """Loading one flow should not affect another flow."""
        spin = config_loader.load_flow("spin_selling")
        bant = config_loader.load_flow("bant")

        # Check that flows are independent
        assert spin.phase_order != bant.phase_order
        assert spin.states != bant.states

        # Check SPIN didn't leak into BANT
        assert "spin_situation" not in bant.states
        assert "bant_budget" not in spin.states

# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

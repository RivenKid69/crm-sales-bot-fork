#!/usr/bin/env python3
"""
Targeted blackboard trace runner for SIM #28 diagnosis.

Investigates: state=greeting, intent=question_sales_mgmt → action=compare_with_competitor

Tests two hypotheses:
  H1: intent=question_sales_mgmt  — what the report says
  H2: intent=comparison           — what FactQuestionSource would need to fire

Usage:
    python scripts/trace_blackboard_sim28.py

The script enables the blackboard.trace logger at DEBUG to capture every
proposal (source, type, value, priority) and the winning decision.
This is the definitive runtime answer to the root cause.
"""

import sys
import os
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

# ─── path setup ─────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─── Enable blackboard.trace BEFORE importing orchestrator ──────────────────
_trace_handler = logging.StreamHandler(sys.stdout)
_trace_handler.setLevel(logging.DEBUG)
_trace_handler.setFormatter(logging.Formatter("%(message)s"))
_trace_log = logging.getLogger("blackboard.trace")
_trace_log.setLevel(logging.DEBUG)
_trace_log.addHandler(_trace_handler)
_trace_log.propagate = False

# Suppress everything else
logging.getLogger().setLevel(logging.WARNING)
logging.getLogger("src").setLevel(logging.WARNING)

# ─── imports ────────────────────────────────────────────────────────────────
from src.blackboard.orchestrator import create_orchestrator
from src.blackboard.source_registry import SourceRegistry


# ─────────────────────────────────────────────────────────────────────────────
# Minimal Mock infrastructure (mirrors test_blackboard_orchestrator.py)
# ─────────────────────────────────────────────────────────────────────────────

class MockCircularFlow:
    goback_count = 0
    max_gobacks = 3

    def get_stats(self): return {"loops": 0, "max_loops": 3}
    def get_go_back_target(self, state, transitions): return transitions.get("go_back")
    def is_limit_reached(self): return False
    def get_remaining_gobacks(self): return 3
    def get_history(self): return []


class MockIntentTracker:
    def __init__(self, turn_number: int = 1):
        self._turn_number = turn_number
        self._intents: List[Any] = []
        self._prev_intent = None
        self._categories: Dict[str, int] = {}

    @property
    def turn_number(self): return self._turn_number
    @property
    def prev_intent(self): return self._prev_intent

    def record(self, intent, state):
        self._prev_intent = self._intents[-1] if self._intents else None
        self._intents.append(intent)

    def advance_turn(self): self._turn_number += 1
    def objection_consecutive(self): return 0
    def objection_total(self): return 0
    def total_count(self, intent): return sum(1 for i in self._intents if i == intent)
    def category_total(self, cat): return self._categories.get(cat, 0)
    def category_streak(self, cat): return 0
    def get_intents_by_category(self, cat): return []


class MockStateMachine:
    """Mock state machine with state=greeting (SIM #28 Turn 1 scenario)."""

    def __init__(self, state: str = "greeting"):
        self._state = state
        self._collected_data: Dict[str, Any] = {"persona": "busy"}
        self._current_phase = None
        self._last_action = None
        self._state_before_objection = None
        self.circular_flow = MockCircularFlow()
        self._intent_tracker = MockIntentTracker(turn_number=0)

    @property
    def state(self): return self._state
    @state.setter
    def state(self, v): self._state = v

    @property
    def collected_data(self): return self._collected_data

    @property
    def current_phase(self): return self._current_phase
    @current_phase.setter
    def current_phase(self, v): self._current_phase = v

    @property
    def last_action(self): return self._last_action
    @last_action.setter
    def last_action(self, v): self._last_action = v

    @property
    def state_before_objection(self): return self._state_before_objection
    @state_before_objection.setter
    def state_before_objection(self, v): self._state_before_objection = v

    def update_data(self, data): self._collected_data.update(data)
    def is_final(self, state=None): return (state or self._state) in ("closed", "rejected", "soft_close", "success")
    def transition_to(self, next_state, action=None, phase=None, source="", validate=True):
        self._state = next_state
        if phase: self._current_phase = phase
        if action: self._last_action = action
        return True
    def sync_phase_from_state(self): pass


# ─────────────────────────────────────────────────────────────────────────────
# Minimal ContextEnvelope (carries secondary_intents and repeated_question)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MockContextEnvelope:
    secondary_intents: List[str] = field(default_factory=list)
    repeated_question: Optional[str] = None
    frustration_level: int = 0
    is_stuck: bool = False
    has_oscillation: bool = False
    momentum_direction: str = "neutral"
    momentum: float = 0.0
    engagement_level: str = "medium"
    confidence_trend: str = "stable"
    total_objections: int = 0
    has_breakthrough: bool = False
    turns_since_breakthrough: Optional[int] = None
    guard_intervention: Optional[str] = None
    tone: Optional[str] = None
    unclear_count: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Run trace
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario(
    label: str,
    flow_config,
    intent: str,
    secondary_intents: Optional[List[str]] = None,
    repeated_question: Optional[str] = None,
    state: str = "greeting",
) -> None:
    """Run one blackboard scenario and print the trace."""
    print()
    print("=" * 72)
    print(f"SCENARIO: {label}")
    print(f"  state={state!r}  intent={intent!r}")
    if secondary_intents:
        print(f"  secondary_intents={secondary_intents}")
    if repeated_question:
        print(f"  repeated_question={repeated_question!r}")
    print("=" * 72)

    SourceRegistry.reset()

    sm = MockStateMachine(state=state)

    orchestrator = create_orchestrator(
        state_machine=sm,
        flow_config=flow_config,
        enable_debug_logging=False,
        enable_metrics=False,
    )

    envelope = MockContextEnvelope(
        secondary_intents=secondary_intents or [],
        repeated_question=repeated_question,
    )

    decision = orchestrator.process_turn(
        intent=intent,
        extracted_data={},
        context_envelope=envelope,
        user_message="Что продаётся лучше всего за последний месяц?",
    )

    print()
    print(f"  ✓ WINNING ACTION : {decision.action!r}")
    print(f"  ✓ NEXT STATE     : {decision.next_state!r}")
    print(f"  ✓ REASON CODES   : {decision.reason_codes}")


def main():
    print()
    print("╔" + "═" * 70 + "╗")
    print("║  BLACKBOARD TRACE — SIM #28 ROOT CAUSE INVESTIGATION            ║")
    print("╚" + "═" * 70 + "╝")
    print()
    print("Loading autonomous flow config...")

    try:
        from src.config_loader import ConfigLoader
        loader = ConfigLoader()
        loaded = loader.load("autonomous")
        flow_config = LoadedConfigAdapter(loaded)
        print(f"  ✓ Flow '{loaded.name}' loaded ({len(loaded.states)} states)")
    except Exception as e:
        print(f"  ✗ Failed to load config: {e}")
        print("  → Falling back to minimal mock config")
        flow_config = _make_mock_flow()

    # ─── Scenario 1: exactly what the report shows ───────────────────────────
    run_scenario(
        label="H1 — Report says: greeting + question_sales_mgmt",
        flow_config=flow_config,
        intent="question_sales_mgmt",
        state="greeting",
    )

    # ─── Scenario 2: what FactQuestionSource needs to produce compare_with_competitor
    run_scenario(
        label="H2 — If LLM misclassified as: greeting + comparison",
        flow_config=flow_config,
        intent="comparison",
        state="greeting",
    )

    # ─── Scenario 3: question_sales_mgmt with comparison as secondary intent ─
    run_scenario(
        label="H3 — question_sales_mgmt + secondary comparison",
        flow_config=flow_config,
        intent="question_sales_mgmt",
        secondary_intents=["comparison"],
        state="greeting",
    )

    print()
    print("=" * 72)
    print("DONE — See BLACKBOARD TRACE blocks above for source details")
    print("=" * 72)


class LoadedConfigAdapter:
    """
    Adapter that wraps LoadedConfig to satisfy the IFlowConfig protocol
    (adds missing methods that the orchestrator needs).
    """

    def __init__(self, loaded_config):
        self._lc = loaded_config

    @property
    def name(self):
        return getattr(self._lc, "name", "autonomous")

    @property
    def states(self):
        return self._lc.states

    @property
    def constants(self):
        return getattr(self._lc, "constants", {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "states": self._lc.states,
            "global_rules": getattr(self._lc, "global_rules", {}),
        }

    def get_state_on_enter_flags(self, state_name: str) -> Dict[str, Any]:
        return self._lc.get_state_on_enter_flags(state_name)

    @property
    def phase_mapping(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for sname, scfg in self._lc.states.items():
            if isinstance(scfg, dict):
                phase = scfg.get("phase") or scfg.get("spin_phase")
                if phase:
                    mapping[phase] = sname
        return mapping

    @property
    def state_to_phase(self) -> Dict[str, str]:
        result = {v: k for k, v in self.phase_mapping.items()}
        for sname, scfg in self._lc.states.items():
            if isinstance(scfg, dict):
                ph = scfg.get("phase") or scfg.get("spin_phase")
                if ph:
                    result[sname] = ph
        return result

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        return self.state_to_phase.get(state_name)

    def is_phase_state(self, state_name: str) -> bool:
        return self.get_phase_for_state(state_name) is not None


def _make_mock_flow():
    """Minimal mock flow config in case real config fails to load."""
    class _MinimalFlow:
        name = "autonomous"
        states = {
            "greeting": {
                "goal": "Поздороваться",
                "rules": {"greeting": "greet_back"},
                "transitions": {"any": "autonomous_discovery"},
            },
            "autonomous_discovery": {
                "goal": "Discover needs",
                "autonomous": True,
                "transitions": {},
            },
            "soft_close": {"is_final": True},
        }
        constants = {}

        def to_dict(self): return {"name": self.name, "states": self.states}
        def get_state_on_enter_flags(self, s): return {}

        @property
        def phase_mapping(self): return {}
        @property
        def state_to_phase(self): return {}
        def get_phase_for_state(self, s): return None
        def is_phase_state(self, s): return False

    return _MinimalFlow()


if __name__ == "__main__":
    main()

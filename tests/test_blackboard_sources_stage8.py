# tests/test_blackboard_sources_stage8.py

"""
Tests for Blackboard Stage 8: Knowledge Sources (Part 3).

These tests verify:
1. TransitionResolverSource - handles intent-based state transitions
2. EscalationSource - detects escalation triggers for human handoff
"""

import pytest
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock


# =============================================================================
# Mock Implementations for Testing
# =============================================================================

class MockStateMachine:
    """Mock StateMachine implementing IStateMachine protocol."""

    def __init__(self, state: str = "greeting", collected_data: Optional[Dict[str, Any]] = None):
        self._state = state
        self._collected_data = collected_data or {}
        self._current_phase = None
        self._last_action = None
        self._intent_tracker = None
        self._state_before_objection = None

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        self._state = value

    @property
    def collected_data(self) -> Dict[str, Any]:
        return self._collected_data

    @property
    def current_phase(self) -> Optional[str]:
        return self._current_phase

    @current_phase.setter
    def current_phase(self, value: Optional[str]) -> None:
        self._current_phase = value

    @property
    def last_action(self) -> Optional[str]:
        return self._last_action

    @last_action.setter
    def last_action(self, value: Optional[str]) -> None:
        self._last_action = value

    @property
    def state_before_objection(self) -> Optional[str]:
        return self._state_before_objection

    @state_before_objection.setter
    def state_before_objection(self, value: Optional[str]) -> None:
        self._state_before_objection = value

    def update_data(self, data: Dict[str, Any]) -> None:
        self._collected_data.update(data)

    def is_final(self) -> bool:
        return self._state in ("closed", "rejected")

    def sync_phase_from_state(self) -> None:
        pass


class MockIntentTracker:
    """Mock IntentTracker implementing IIntentTracker protocol."""

    def __init__(
        self,
        turn_number: int = 0,
        objection_consecutive: int = 0,
        objection_total: int = 0
    ):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents = []
        self._objection_consecutive = objection_consecutive
        self._objection_total = objection_total
        self._category_totals = {}
        self._intent_totals = {}

    @property
    def turn_number(self) -> int:
        return self._turn_number

    @property
    def prev_intent(self) -> Optional[str]:
        return self._prev_intent

    def record(self, intent: str, state: str) -> None:
        if self._intents:
            self._prev_intent = self._intents[-1][0]
        self._intents.append((intent, state))

        if "objection" in intent:
            self._objection_consecutive += 1
            self._objection_total += 1
        else:
            self._objection_consecutive = 0

    def advance_turn(self) -> None:
        self._turn_number += 1

    def objection_consecutive(self) -> int:
        return self._objection_consecutive

    def objection_total(self) -> int:
        return self._objection_total

    def total_count(self, intent: str) -> int:
        if intent in self._intent_totals:
            return self._intent_totals[intent]
        return sum(1 for i, _ in self._intents if i == intent)

    def category_total(self, category: str) -> int:
        return self._category_totals.get(category, 0)

    def set_intent_total(self, intent: str, count: int) -> None:
        """Set total count for testing."""
        self._intent_totals[intent] = count

    def set_category_total(self, category: str, count: int) -> None:
        """Set category total for testing."""
        self._category_totals[category] = count


class MockFlowConfig:
    """Mock FlowConfig implementing IFlowConfig protocol."""

    def __init__(
        self,
        states: Optional[Dict[str, Dict[str, Any]]] = None,
        entry_points: Optional[Dict[str, str]] = None,
    ):
        self._states = states or {
            "greeting": {"goal": "Greet user", "phase": None},
            "spin_situation": {
                "goal": "Gather situation",
                "phase": "situation",
                "required_data": ["company_name", "industry"],
                "transitions": {
                    "data_complete": "spin_problem",
                    "rejection": "soft_close",
                    "agreement": "spin_problem",
                },
                "rules": {
                    "greeting": "greet_back",
                    "unclear": "probe_situation",
                },
            },
            "spin_problem": {"goal": "Identify problems", "phase": "problem"},
            "soft_close": {"goal": "Soft close", "is_final": True},
            "human_handoff": {"goal": "Transfer to human", "is_final": True},
            "_limits": {"max_consecutive_objections": 3, "max_total_objections": 5},
        }
        self._entry_points = entry_points or {}

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        return self._states

    @property
    def entry_points(self) -> Dict[str, str]:
        return self._entry_points

    def to_dict(self) -> Dict[str, Any]:
        return {
            "states": self._states,
            "entry_points": self._entry_points,
        }
    @property
    def phase_mapping(self) -> Dict[str, str]:
        """Get phase -> state mapping."""
        mapping = {}
        for state_name, state_config in self._states.items():
            phase = state_config.get("phase") or state_config.get("spin_phase")
            if phase:
                mapping[phase] = state_name
        return mapping

    @property
    def state_to_phase(self) -> Dict[str, str]:
        """
        Get complete state -> phase mapping.

        This is the CANONICAL source of truth for state -> phase resolution.
        Includes both reverse mapping from phase_mapping AND explicit phases
        from state configs (explicit phases have higher priority).
        """
        # Start with reverse mapping from phase_mapping
        result = {v: k for k, v in self.phase_mapping.items()}

        # Override with explicit phases from state configs (higher priority)
        for state_name, state_config in self._states.items():
            explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
            if explicit_phase:
                result[state_name] = explicit_phase

        return result

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        """Get phase name for a state."""
        # Delegate to state_to_phase which contains the complete mapping
        return self.state_to_phase.get(state_name)

    def is_phase_state(self, state_name: str) -> bool:
        """Check if a state is a phase state."""
        return self.get_phase_for_state(state_name) is not None



class MockConditionRegistry:
    """Mock ConditionRegistry for testing TransitionResolverSource."""

    def __init__(self, conditions: Optional[Dict[str, bool]] = None):
        self._conditions = conditions or {}

    def evaluate(self, condition_name: str, ctx: Any, trace=None) -> bool:
        if condition_name in self._conditions:
            return self._conditions[condition_name]
        # Default: return True for unknown conditions
        return True

    def has(self, name: str) -> bool:
        return name in self._conditions


def create_blackboard(
    state: str = "greeting",
    collected_data: Optional[Dict[str, Any]] = None,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
    entry_points: Optional[Dict[str, str]] = None,
    intent: str = "greeting",
    extracted_data: Optional[Dict[str, Any]] = None,
    objection_consecutive: int = 0,
    objection_total: int = 0,
    intent_totals: Optional[Dict[str, int]] = None,
    category_totals: Optional[Dict[str, int]] = None,
):
    """Helper to create a blackboard with turn started."""
    from src.blackboard.blackboard import DialogueBlackboard

    sm = MockStateMachine(state=state, collected_data=collected_data or {})
    flow_config = MockFlowConfig(states=states, entry_points=entry_points)
    tracker = MockIntentTracker(
        objection_consecutive=objection_consecutive,
        objection_total=objection_total
    )

    # Set custom intent/category totals for testing
    if intent_totals:
        for intent_name, count in intent_totals.items():
            tracker.set_intent_total(intent_name, count)
    if category_totals:
        for category, count in category_totals.items():
            tracker.set_category_total(category, count)

    bb = DialogueBlackboard(
        state_machine=sm,
        flow_config=flow_config,
        intent_tracker=tracker,
    )
    bb.begin_turn(intent=intent, extracted_data=extracted_data or {})
    return bb


# =============================================================================
# Tests for TransitionResolverSource
# =============================================================================

class TestTransitionResolverSourceInit:
    """Test TransitionResolverSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        from src.blackboard.sources import TransitionResolverSource

        source = TransitionResolverSource()

        assert source.name == "TransitionResolverSource"
        assert source.enabled is True

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        from src.blackboard.sources import TransitionResolverSource

        source = TransitionResolverSource(name="CustomTransitionResolver")

        assert source.name == "CustomTransitionResolver"

    def test_init_with_custom_condition_registry(self):
        """Test initialization with custom condition registry."""
        from src.blackboard.sources import TransitionResolverSource

        custom_registry = MockConditionRegistry({"test_condition": True})
        source = TransitionResolverSource(condition_registry=custom_registry)

        assert source._condition_registry is custom_registry

    def test_excluded_triggers_defined(self):
        """Test that excluded triggers are defined."""
        from src.blackboard.sources import TransitionResolverSource

        expected = {"data_complete", "any"}
        assert TransitionResolverSource.EXCLUDED_TRIGGERS == expected


class TestTransitionResolverSourceShouldContribute:
    """Test TransitionResolverSource.should_contribute()."""

    def test_should_contribute_with_transitions(self):
        """Test should_contribute returns True when transitions defined."""
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "spin_situation": {
                "transitions": {"rejection": "soft_close"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="rejection")
        source = TransitionResolverSource()

        assert source.should_contribute(bb) is True

    def test_should_not_contribute_no_transitions(self):
        """Test should_contribute returns False when no transitions defined."""
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "spin_situation": {
                "rules": {"greeting": "greet_back"}
                # No transitions
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="greeting")
        source = TransitionResolverSource()

        assert source.should_contribute(bb) is False

    def test_should_not_contribute_when_disabled(self):
        """Test should_contribute returns False when source is disabled."""
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "spin_situation": {
                "transitions": {"rejection": "soft_close"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="rejection")
        source = TransitionResolverSource()
        source.disable()

        assert source.should_contribute(bb) is False


class TestTransitionResolverSourceContributeSimple:
    """Test TransitionResolverSource.contribute() with simple transitions."""

    def test_contribute_simple_string_transition(self):
        """Test simple string transition proposes transition."""
        from src.blackboard.sources import TransitionResolverSource
        from src.blackboard.enums import Priority, ProposalType

        states = {
            "spin_situation": {
                "transitions": {"rejection": "soft_close"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="rejection")
        source = TransitionResolverSource()

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].type == ProposalType.TRANSITION
        assert proposals[0].value == "soft_close"
        assert proposals[0].priority == Priority.HIGH  # rejection is high priority
        assert proposals[0].source_name == "TransitionResolverSource"
        assert proposals[0].reason_code == "intent_transition_rejection"

    def test_contribute_normal_priority_transition(self):
        """Test normal intent gets NORMAL priority."""
        from src.blackboard.sources import TransitionResolverSource
        from src.blackboard.enums import Priority

        states = {
            "spin_situation": {
                "transitions": {"agreement": "spin_problem"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="agreement")
        source = TransitionResolverSource()

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].priority == Priority.NORMAL  # Normal priority for agreement

    def test_contribute_no_matching_transition(self):
        """Test no proposal when intent has no transition defined."""
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "spin_situation": {
                "transitions": {"rejection": "soft_close"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="greeting")
        source = TransitionResolverSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_skips_data_complete(self):
        """Test that data_complete trigger is skipped (handled by DataCollectorSource)."""
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "spin_situation": {
                "transitions": {"data_complete": "spin_problem"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="data_complete")
        source = TransitionResolverSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_skips_any(self):
        """Test that 'any' trigger is skipped (handled separately)."""
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "spin_situation": {
                "transitions": {"any": "fallback_state"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="any")
        source = TransitionResolverSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0


class TestTransitionResolverSourceContributeConditional:
    """Test TransitionResolverSource.contribute() with conditional transitions."""

    def test_contribute_conditional_dict_true(self):
        """Test conditional dict transition when condition is true."""
        from src.blackboard.sources import TransitionResolverSource

        custom_registry = MockConditionRegistry({"has_pricing_data": True})
        states = {
            "spin_situation": {
                "transitions": {
                    "agreement": {"when": "has_pricing_data", "then": "proposal"}
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="agreement")
        source = TransitionResolverSource(condition_registry=custom_registry)

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "proposal"

    def test_contribute_conditional_dict_false(self):
        """Test conditional dict transition when condition is false."""
        from src.blackboard.sources import TransitionResolverSource

        custom_registry = MockConditionRegistry({"has_pricing_data": False})
        states = {
            "spin_situation": {
                "transitions": {
                    "agreement": {"when": "has_pricing_data", "then": "proposal"}
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="agreement")
        source = TransitionResolverSource(condition_registry=custom_registry)

        source.contribute(bb)

        # No proposal when condition is false
        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_conditional_list_first_match(self):
        """Test conditional list picks first matching condition."""
        from src.blackboard.sources import TransitionResolverSource

        custom_registry = MockConditionRegistry({
            "is_enterprise": True,
            "is_small_business": False
        })
        states = {
            "spin_situation": {
                "transitions": {
                    "agreement": [
                        {"when": "is_enterprise", "then": "enterprise_proposal"},
                        {"when": "is_small_business", "then": "standard_proposal"},
                        "default_proposal"
                    ]
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="agreement")
        source = TransitionResolverSource(condition_registry=custom_registry)

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "enterprise_proposal"

    def test_contribute_conditional_list_default_fallback(self):
        """Test conditional list falls back to default string."""
        from src.blackboard.sources import TransitionResolverSource

        custom_registry = MockConditionRegistry({
            "is_enterprise": False,
            "is_small_business": False
        })
        states = {
            "spin_situation": {
                "transitions": {
                    "agreement": [
                        {"when": "is_enterprise", "then": "enterprise_proposal"},
                        {"when": "is_small_business", "then": "standard_proposal"},
                        "default_proposal"
                    ]
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="agreement")
        source = TransitionResolverSource(condition_registry=custom_registry)

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "default_proposal"


class TestTransitionResolverSourceMetadata:
    """Test TransitionResolverSource metadata in proposals."""

    def test_metadata_includes_trigger_intent(self):
        """Test that metadata includes trigger intent."""
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "spin_situation": {
                "transitions": {"rejection": "soft_close"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="rejection")
        source = TransitionResolverSource()

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].metadata["trigger_intent"] == "rejection"

    def test_metadata_includes_transition_type(self):
        """Test that metadata includes transition type."""
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "spin_situation": {
                "transitions": {"rejection": "soft_close"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="rejection")
        source = TransitionResolverSource()

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].metadata["transition_type"] == "str"


class TestTransitionResolverSourceHighPriorityIntents:
    """Test TransitionResolverSource high priority intent handling."""

    def test_rejection_gets_high_priority(self):
        """Test rejection intent gets HIGH priority."""
        from src.blackboard.sources import TransitionResolverSource
        from src.blackboard.enums import Priority

        states = {"test": {"transitions": {"rejection": "soft_close"}}}
        bb = create_blackboard(state="test", states=states, intent="rejection")
        source = TransitionResolverSource()
        source.contribute(bb)

        assert bb.get_transition_proposals()[0].priority == Priority.HIGH

    def test_hard_no_gets_high_priority(self):
        """Test hard_no intent gets HIGH priority."""
        from src.blackboard.sources import TransitionResolverSource
        from src.blackboard.enums import Priority

        states = {"test": {"transitions": {"hard_no": "closed"}}}
        bb = create_blackboard(state="test", states=states, intent="hard_no")
        source = TransitionResolverSource()
        source.contribute(bb)

        assert bb.get_transition_proposals()[0].priority == Priority.HIGH

    def test_end_conversation_gets_high_priority(self):
        """Test end_conversation intent gets HIGH priority."""
        from src.blackboard.sources import TransitionResolverSource
        from src.blackboard.enums import Priority

        states = {"test": {"transitions": {"end_conversation": "closed"}}}
        bb = create_blackboard(state="test", states=states, intent="end_conversation")
        source = TransitionResolverSource()
        source.contribute(bb)

        assert bb.get_transition_proposals()[0].priority == Priority.HIGH


# =============================================================================
# Tests for EscalationSource
# =============================================================================

class TestEscalationSourceInit:
    """Test EscalationSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        from src.blackboard.sources import EscalationSource

        source = EscalationSource()

        assert source.name == "EscalationSource"
        assert source.enabled is True
        assert source._frustration_threshold == 3
        assert source._misunderstanding_threshold == 4
        assert source._high_value_threshold == 100

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        from src.blackboard.sources import EscalationSource

        source = EscalationSource(name="CustomEscalation")

        assert source.name == "CustomEscalation"

    def test_init_with_custom_thresholds(self):
        """Test initialization with custom thresholds."""
        from src.blackboard.sources import EscalationSource

        source = EscalationSource(
            frustration_threshold=5,
            misunderstanding_threshold=6,
            high_value_threshold=500
        )

        assert source._frustration_threshold == 5
        assert source._misunderstanding_threshold == 6
        assert source._high_value_threshold == 500

    def test_explicit_escalation_intents_defined(self):
        """Test that explicit escalation intents are defined."""
        from src.blackboard.sources import EscalationSource

        expected = {
            "request_human",
            "need_help",
        }
        assert EscalationSource.EXPLICIT_ESCALATION_INTENTS == expected

    def test_frustration_intents_defined(self):
        """Test that frustration intents are defined."""
        from src.blackboard.sources import EscalationSource

        expected = {
            "frustration_expression",
            "impatience_expression",
        }
        assert EscalationSource.FRUSTRATION_INTENTS == expected

    def test_sensitive_intents_defined(self):
        """Test that sensitive intents are defined."""
        from src.blackboard.sources import EscalationSource

        expected = {
            "legal_question",
            "compliance_question",
            "formal_complaint",
            "request_refund",
            "contract_dispute",
            "data_deletion",
            "gdpr_request",
        }
        assert EscalationSource.SENSITIVE_INTENTS == expected


class TestEscalationSourceShouldContribute:
    """Test EscalationSource.should_contribute()."""

    def test_should_contribute_explicit_escalation(self):
        """Test should_contribute returns True for explicit escalation."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="request_human")
        source = EscalationSource()

        assert source.should_contribute(bb) is True

    def test_should_contribute_sensitive_topic(self):
        """Test should_contribute returns True for sensitive topics."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="legal_question")
        source = EscalationSource()

        assert source.should_contribute(bb) is True

    def test_should_contribute_frustration(self):
        """Test should_contribute returns True for frustration intents."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="frustration_expression")
        source = EscalationSource()

        assert source.should_contribute(bb) is True

    def test_should_contribute_near_misunderstanding_threshold(self):
        """Test should_contribute returns True near misunderstanding threshold."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(
            intent="greeting",
            intent_totals={"unclear": 3}  # threshold-1 = 4-1 = 3
        )
        source = EscalationSource()

        assert source.should_contribute(bb) is True

    def test_should_not_contribute_normal_intent(self):
        """Test should_contribute returns False for normal intents."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="agreement")
        source = EscalationSource()

        assert source.should_contribute(bb) is False

    def test_should_not_contribute_when_disabled(self):
        """Test should_contribute returns False when source is disabled."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="request_human")
        source = EscalationSource()
        source.disable()

        assert source.should_contribute(bb) is False


class TestEscalationSourceContributeExplicit:
    """Test EscalationSource.contribute() for explicit escalation requests."""

    def test_contribute_explicit_request_proposes_escalation(self):
        """Test explicit request proposes escalation action and transition."""
        from src.blackboard.sources import EscalationSource
        from src.blackboard.enums import Priority, ProposalType

        # With entry_points.escalation defined -> uses human_handoff
        bb = create_blackboard(
            intent="request_human",
            entry_points={"escalation": "human_handoff"}
        )
        source = EscalationSource()

        source.contribute(bb)

        # Check action proposal
        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].type == ProposalType.ACTION
        assert action_proposals[0].value == "escalate_to_human"
        assert action_proposals[0].priority == Priority.CRITICAL
        assert action_proposals[0].combinable is False  # BLOCKING!
        assert action_proposals[0].source_name == "EscalationSource"
        assert action_proposals[0].reason_code == "escalation_explicit_request"

        # Check transition proposal
        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].type == ProposalType.TRANSITION
        assert transition_proposals[0].value == "human_handoff"
        assert transition_proposals[0].priority == Priority.CRITICAL

    def test_contribute_request_human(self):
        """Test request_human intent triggers escalation."""
        from src.blackboard.sources import EscalationSource
        from src.blackboard.enums import Priority

        bb = create_blackboard(intent="request_human")
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].value == "escalate_to_human"
        assert action_proposals[0].priority == Priority.CRITICAL


class TestEscalationSourceContributeSensitive:
    """Test EscalationSource.contribute() for sensitive topics."""

    def test_contribute_legal_question(self):
        """Test legal_question triggers escalation."""
        from src.blackboard.sources import EscalationSource
        from src.blackboard.enums import Priority

        bb = create_blackboard(intent="legal_question")
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].value == "escalate_to_human"
        assert action_proposals[0].priority == Priority.CRITICAL
        assert action_proposals[0].reason_code == "escalation_sensitive_topic"

    def test_contribute_gdpr_request(self):
        """Test gdpr_request triggers escalation."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="gdpr_request")
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].reason_code == "escalation_sensitive_topic"


class TestEscalationSourceContributeFrustration:
    """Test EscalationSource.contribute() for frustration threshold."""

    def test_contribute_frustration_below_threshold_no_escalation(self):
        """Test frustration below threshold doesn't trigger escalation."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(
            intent="frustration_expression",
            category_totals={"frustration": 2}  # Below threshold of 3
        )
        source = EscalationSource()

        source.contribute(bb)

        # No escalation below threshold
        assert len(bb.get_action_proposals()) == 0

    def test_contribute_frustration_at_threshold_escalates(self):
        """Test frustration at threshold triggers escalation."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(
            intent="frustration_expression",
            category_totals={"frustration": 3}  # At threshold
        )
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].value == "escalate_to_human"
        assert action_proposals[0].reason_code == "escalation_frustration_threshold"


class TestEscalationSourceContributeMisunderstanding:
    """Test EscalationSource.contribute() for misunderstanding threshold."""

    def test_contribute_misunderstanding_at_threshold_escalates(self):
        """Test misunderstanding at threshold triggers escalation."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(
            intent="greeting",  # Not a frustration intent
            intent_totals={"unclear": 4}  # At threshold
        )
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].reason_code == "escalation_misunderstanding_threshold"


class TestEscalationSourceContributeHighValue:
    """Test EscalationSource.contribute() for high-value leads."""

    def test_contribute_high_value_complex_question_escalates(self):
        """Test high-value lead with complex question triggers escalation."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(
            intent="enterprise_features",
            collected_data={"company_size": 500}  # Above threshold of 100
        )
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].reason_code == "escalation_high_value_complex"

    def test_contribute_high_value_simple_question_no_escalation(self):
        """Test high-value lead with simple question doesn't escalate."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(
            intent="agreement",  # Simple intent
            collected_data={"company_size": 500}
        )
        source = EscalationSource()

        source.contribute(bb)

        # No escalation for simple question
        assert len(bb.get_action_proposals()) == 0

    def test_contribute_low_value_complex_question_no_escalation(self):
        """Test low-value lead with complex question doesn't escalate."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(
            intent="enterprise_features",
            collected_data={"company_size": 50}  # Below threshold
        )
        source = EscalationSource()

        source.contribute(bb)

        # No escalation for small company
        assert len(bb.get_action_proposals()) == 0


class TestEscalationSourceMetadata:
    """Test EscalationSource metadata in proposals."""

    def test_metadata_includes_trigger(self):
        """Test that metadata includes trigger reason."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="request_human")
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert action_proposals[0].metadata["trigger"] == "explicit_request"

    def test_metadata_includes_intent(self):
        """Test that metadata includes intent."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="legal_question")
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert action_proposals[0].metadata["intent"] == "legal_question"

    def test_metadata_includes_turn_number(self):
        """Test that metadata includes turn number."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="request_human")
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert "turn_number" in action_proposals[0].metadata


class TestEscalationSourceCombinableFalse:
    """Test EscalationSource combinable=False behavior."""

    def test_escalation_action_is_blocking(self):
        """Test that escalation action has combinable=False."""
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="request_human")
        source = EscalationSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].combinable is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestSourcesStage8Integration:
    """Integration tests for Stage 8 sources working together."""

    def test_transition_resolver_with_intent_processor(self):
        """
        Test TransitionResolverSource works with IntentProcessorSource.
        Both can propose for the same intent.
        """
        from src.blackboard.sources import TransitionResolverSource, IntentProcessorSource

        states = {
            "spin_situation": {
                "transitions": {"rejection": "soft_close"},
                "rules": {"rejection": "handle_rejection"},
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="rejection")

        transition_source = TransitionResolverSource()
        intent_source = IntentProcessorSource()

        transition_source.contribute(bb)
        intent_source.contribute(bb)

        # TransitionResolverSource proposes transition
        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].value == "soft_close"

        # IntentProcessorSource proposes action
        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].value == "handle_rejection"

    def test_escalation_source_blocks_other_transitions(self):
        """
        Test EscalationSource blocking action should prevent
        other transitions from being combined.
        """
        from src.blackboard.sources import EscalationSource, TransitionResolverSource

        states = {
            "spin_situation": {
                "transitions": {"request_human": "some_state"}
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="request_human")

        escalation_source = EscalationSource()
        transition_source = TransitionResolverSource()

        escalation_source.contribute(bb)
        transition_source.contribute(bb)

        # EscalationSource proposes blocking action
        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].combinable is False

        # Both sources propose transitions (ConflictResolver will handle priority)
        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 2  # escalation and regular transition


# =============================================================================
# Package Import Tests
# =============================================================================

class TestStage8PackageImports:
    """Test package import functionality for Stage 8."""

    def test_import_transition_resolver_source(self):
        """Test importing TransitionResolverSource from package."""
        from src.blackboard.sources import TransitionResolverSource

        assert TransitionResolverSource is not None

    def test_import_escalation_source(self):
        """Test importing EscalationSource from package."""
        from src.blackboard.sources import EscalationSource

        assert EscalationSource is not None

    def test_sources_in_dunder_all(self):
        """Test that Stage 8 sources are in __all__."""
        import src.blackboard.sources as sources

        assert "TransitionResolverSource" in sources.__all__
        assert "EscalationSource" in sources.__all__


# =============================================================================
# Criteria Verification (from Architectural Plan)
# =============================================================================

class TestStage8CriteriaVerification:
    """
    Verification tests from the plan's CRITERION OF COMPLETION for Stage 8.
    """

    def test_criterion_import_transition_resolver_source(self):
        """
        Plan criterion: from src.blackboard.sources import TransitionResolverSource
        """
        from src.blackboard.sources import TransitionResolverSource

        assert TransitionResolverSource is not None

    def test_criterion_import_escalation_source(self):
        """
        Plan criterion: from src.blackboard.sources import EscalationSource
        """
        from src.blackboard.sources import EscalationSource

        assert EscalationSource is not None

    def test_criterion_transition_resolver_handles_intent_based(self):
        """
        Plan criterion: TransitionResolverSource handles intent-based transitions
        """
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "test": {"transitions": {"rejection": "soft_close"}}
        }
        bb = create_blackboard(state="test", states=states, intent="rejection")
        source = TransitionResolverSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "soft_close"

    def test_criterion_transition_resolver_skips_data_complete(self):
        """
        Plan criterion: TransitionResolverSource does NOT handle data_complete
        """
        from src.blackboard.sources import TransitionResolverSource

        states = {
            "test": {"transitions": {"data_complete": "next_state"}}
        }
        bb = create_blackboard(state="test", states=states, intent="data_complete")
        source = TransitionResolverSource()
        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_criterion_escalation_source_combinable_false(self):
        """
        Plan criterion (CRITICAL): EscalationSource.combinable = False (BLOCKING)
        """
        from src.blackboard.sources import EscalationSource

        bb = create_blackboard(intent="request_human")
        source = EscalationSource()
        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].combinable is False

    def test_criterion_escalation_proposes_human_handoff(self):
        """
        Plan criterion: EscalationSource proposes human_handoff transition
        when entry_points.escalation is defined.
        """
        from src.blackboard.sources import EscalationSource

        # With entry_points.escalation defined -> uses human_handoff
        bb = create_blackboard(
            intent="request_human",
            entry_points={"escalation": "human_handoff"}
        )
        source = EscalationSource()
        source.contribute(bb)

        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].value == "human_handoff"

    def test_criterion_escalation_explicit_request_critical_priority(self):
        """
        Plan criterion: Explicit escalation request -> CRITICAL priority
        """
        from src.blackboard.sources import EscalationSource
        from src.blackboard.enums import Priority

        bb = create_blackboard(intent="request_human")
        source = EscalationSource()
        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert action_proposals[0].priority == Priority.CRITICAL

    def test_criterion_escalation_sensitive_topic_critical_priority(self):
        """
        Plan criterion: Sensitive topic -> CRITICAL priority
        """
        from src.blackboard.sources import EscalationSource
        from src.blackboard.enums import Priority

        bb = create_blackboard(intent="legal_question")
        source = EscalationSource()
        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert action_proposals[0].priority == Priority.CRITICAL


# =============================================================================
# Tests for EscalationSource Flow-Aware Behavior
# =============================================================================

class TestEscalationSourceFlowAware:
    """Test EscalationSource flow-aware escalation state resolution."""

    def test_uses_entry_points_escalation_when_defined(self):
        """Uses entry_points.escalation when defined and state exists."""
        from src.blackboard.sources import EscalationSource

        states = {
            "greeting": {},
            "human_handoff": {"is_final": True},
            "soft_close": {"is_final": False},
        }
        entry_points = {"escalation": "human_handoff"}

        bb = create_blackboard(
            intent="request_human",
            states=states,
            entry_points=entry_points,
        )
        source = EscalationSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "human_handoff"

    def test_fallback_to_soft_close_when_no_escalation(self):
        """Falls back to soft_close when entry_points.escalation not defined."""
        from src.blackboard.sources import EscalationSource

        states = {
            "greeting": {},
            "soft_close": {"is_final": False},
            # NO human_handoff - simulates sales flow
        }
        entry_points = {"default": "greeting"}  # NO escalation defined

        bb = create_blackboard(
            intent="request_human",
            states=states,
            entry_points=entry_points,
        )
        source = EscalationSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "soft_close"

    def test_fallback_when_escalation_state_not_exists(self):
        """Falls back to soft_close when entry_points.escalation points to non-existent state."""
        from src.blackboard.sources import EscalationSource

        states = {
            "greeting": {},
            "soft_close": {"is_final": False},
            # NO human_handoff in states
        }
        entry_points = {"escalation": "human_handoff"}  # Points to non-existent state

        bb = create_blackboard(
            intent="request_human",
            states=states,
            entry_points=entry_points,
        )
        source = EscalationSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "soft_close"  # Fallback

    def test_metadata_includes_resolved_state(self):
        """Metadata includes resolved_state for debugging."""
        from src.blackboard.sources import EscalationSource

        states = {
            "greeting": {},
            "soft_close": {"is_final": False},
        }
        entry_points = {}  # No escalation defined

        bb = create_blackboard(
            intent="request_human",
            states=states,
            entry_points=entry_points,
        )
        source = EscalationSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].metadata.get("resolved_state") == "soft_close"

    def test_support_flow_uses_human_handoff(self):
        """Support flow correctly uses human_handoff via entry_points."""
        from src.blackboard.sources import EscalationSource

        # Mimics support_flow.yaml structure
        states = {
            "greeting": {},
            "issue_classifier": {},
            "human_handoff": {"is_final": True},
            "soft_close": {"is_final": False},
        }
        entry_points = {
            "default": "greeting",
            "escalation": "human_handoff",
        }

        bb = create_blackboard(
            intent="legal_question",  # Sensitive topic triggers escalation
            states=states,
            entry_points=entry_points,
        )
        source = EscalationSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].value == "human_handoff"

    def test_sales_flow_uses_soft_close(self):
        """Sales flow uses soft_close as fallback (no human_handoff)."""
        from src.blackboard.sources import EscalationSource

        # Mimics spin_selling flow structure - NO human_handoff
        states = {
            "greeting": {},
            "spin_situation": {},
            "spin_problem": {},
            "presentation": {},
            "soft_close": {"is_final": False},
            "success": {"is_final": True},
        }
        entry_points = {
            "default": "greeting",
            "hot_lead": "presentation",
            # NO escalation entry point
        }

        bb = create_blackboard(
            intent="gdpr_request",  # Sensitive topic triggers escalation
            states=states,
            entry_points=entry_points,
        )
        source = EscalationSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "soft_close"

    def test_custom_escalation_state(self):
        """Flow can define custom escalation state via entry_points."""
        from src.blackboard.sources import EscalationSource

        states = {
            "greeting": {},
            "custom_escalation": {"is_final": True, "goal": "Custom escalation"},
            "soft_close": {"is_final": False},
        }
        entry_points = {
            "escalation": "custom_escalation",
        }

        bb = create_blackboard(
            intent="request_human",
            states=states,
            entry_points=entry_points,
        )
        source = EscalationSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].value == "custom_escalation"

# tests/test_blackboard_sources_stage7.py

"""
Tests for Blackboard Stage 7: Knowledge Sources (Part 2).

These tests verify:
1. ObjectionGuardSource - monitors objection limits per persona
2. IntentProcessorSource - maps intents to actions via rules
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

    def update_data(self, data: Dict[str, Any]) -> None:
        self._collected_data.update(data)

    def is_final(self) -> bool:
        return self._state in ("closed", "rejected")


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
        self._turn_number += 1

        if "objection" in intent:
            self._objection_consecutive += 1
            self._objection_total += 1
        else:
            self._objection_consecutive = 0

    def objection_consecutive(self) -> int:
        return self._objection_consecutive

    def objection_total(self) -> int:
        return self._objection_total

    def total_count(self, intent: str) -> int:
        return sum(1 for i, _ in self._intents if i == intent)

    def category_total(self, category: str) -> int:
        return self._category_totals.get(category, 0)


class MockFlowConfig:
    """Mock FlowConfig implementing IFlowConfig protocol."""

    def __init__(self, states: Optional[Dict[str, Dict[str, Any]]] = None):
        self._states = states or {
            "greeting": {"goal": "Greet user", "phase": None},
            "spin_situation": {
                "goal": "Gather situation",
                "phase": "situation",
                "required_data": ["company_name", "industry"],
                "transitions": {"data_complete": "spin_problem"},
                "rules": {
                    "greeting": "greet_back",
                    "unclear": "probe_situation",
                },
            },
            "spin_problem": {"goal": "Identify problems", "phase": "problem"},
            "soft_close": {"goal": "Soft close", "is_final": True},
            "_limits": {"max_consecutive_objections": 3, "max_total_objections": 5},
        }

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        return self._states

    def to_dict(self) -> Dict[str, Any]:
        return {"states": self._states}
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
    """Mock ConditionRegistry for testing IntentProcessorSource."""

    def __init__(self, conditions: Optional[Dict[str, bool]] = None):
        self._conditions = conditions or {}

    def evaluate(self, condition_name: str, ctx: Any) -> bool:
        if condition_name in self._conditions:
            return self._conditions[condition_name]
        # Default: return True for unknown conditions
        return True

    def has(self, name: str) -> bool:
        return name in self._conditions


class MockRuleResolver:
    """Mock RuleResolver for testing."""

    def __init__(self):
        self.default_action = "continue_current_goal"

    def resolve_action(self, intent, state_rules, global_rules, ctx, state="", trace=None):
        if intent in state_rules:
            rule = state_rules[intent]
            if isinstance(rule, str):
                return rule
        return self.default_action


def create_blackboard(
    state: str = "greeting",
    collected_data: Optional[Dict[str, Any]] = None,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
    intent: str = "greeting",
    extracted_data: Optional[Dict[str, Any]] = None,
    objection_consecutive: int = 0,
    objection_total: int = 0,
):
    """Helper to create a blackboard with turn started."""
    from src.blackboard.blackboard import DialogueBlackboard

    sm = MockStateMachine(state=state, collected_data=collected_data or {})
    flow_config = MockFlowConfig(states=states)
    tracker = MockIntentTracker(
        objection_consecutive=objection_consecutive,
        objection_total=objection_total
    )

    bb = DialogueBlackboard(
        state_machine=sm,
        flow_config=flow_config,
        intent_tracker=tracker,
    )
    bb.begin_turn(intent=intent, extracted_data=extracted_data or {})
    return bb


# =============================================================================
# Tests for ObjectionGuardSource
# =============================================================================

class TestObjectionGuardSourceInit:
    """Test ObjectionGuardSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        from src.blackboard.sources import ObjectionGuardSource

        source = ObjectionGuardSource()

        assert source.name == "ObjectionGuardSource"
        assert source.enabled is True
        assert "objection_price" in source.objection_intents
        assert "objection_competitor" in source.objection_intents
        assert "objection_timing" in source.objection_intents

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        from src.blackboard.sources import ObjectionGuardSource

        source = ObjectionGuardSource(name="CustomObjectionGuard")

        assert source.name == "CustomObjectionGuard"

    def test_init_with_custom_persona_limits(self):
        """Test initialization with custom persona limits."""
        from src.blackboard.sources import ObjectionGuardSource

        custom_limits = {
            "aggressive": {"consecutive": 10, "total": 15},
            "default": {"consecutive": 5, "total": 10},
        }
        source = ObjectionGuardSource(persona_limits=custom_limits)

        assert source.persona_limits == custom_limits

    def test_init_with_custom_objection_intents(self):
        """Test initialization with custom objection intents."""
        from src.blackboard.sources import ObjectionGuardSource

        custom_intents = {"my_objection", "custom_objection"}
        source = ObjectionGuardSource(objection_intents=custom_intents)

        assert source.objection_intents == custom_intents
        assert "objection_price" not in source.objection_intents

    def test_default_persona_limits(self):
        """Test that default persona limits are correct."""
        from src.blackboard.sources import ObjectionGuardSource

        source = ObjectionGuardSource()

        assert source.persona_limits["aggressive"]["consecutive"] == 5
        assert source.persona_limits["aggressive"]["total"] == 8
        assert source.persona_limits["busy"]["consecutive"] == 2
        assert source.persona_limits["busy"]["total"] == 4
        assert source.persona_limits["default"]["consecutive"] == 3
        assert source.persona_limits["default"]["total"] == 5

    def test_default_objection_intents(self):
        """Test that default objection intents are comprehensive."""
        from src.blackboard.sources import ObjectionGuardSource

        source = ObjectionGuardSource()

        expected_intents = {
            "objection_price",
            "objection_competitor",
            "objection_timing",
            "objection_authority",
            "objection_need",
            "objection_trust",
            "objection_budget",
            "objection_features",
            "objection_complexity",
            "objection_support",
            "objection_integration",
            "objection_security",
            "objection_scalability",
            "objection_contract",
            "objection_implementation",
            "objection_training",
            "objection_roi",
            "objection_change",
            "objection_generic",
        }
        assert source.objection_intents == expected_intents


class TestObjectionGuardSourceShouldContribute:
    """Test ObjectionGuardSource.should_contribute()."""

    def test_should_contribute_objection_price(self):
        """Test should_contribute returns True for objection_price."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(intent="objection_price")
        source = ObjectionGuardSource()

        assert source.should_contribute(bb) is True

    def test_should_contribute_objection_timing(self):
        """Test should_contribute returns True for objection_timing."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(intent="objection_timing")
        source = ObjectionGuardSource()

        assert source.should_contribute(bb) is True

    def test_should_not_contribute_non_objection_intent(self):
        """Test should_contribute returns False for non-objection intents."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(intent="agreement")
        source = ObjectionGuardSource()

        assert source.should_contribute(bb) is False

    def test_should_not_contribute_when_disabled(self):
        """Test should_contribute returns False when source is disabled."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(intent="objection_price")
        source = ObjectionGuardSource()
        source.disable()

        assert source.should_contribute(bb) is False

    def test_should_contribute_custom_objection_intent(self):
        """Test should_contribute with custom objection intents."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(intent="my_custom_objection")
        source = ObjectionGuardSource(objection_intents={"my_custom_objection"})

        assert source.should_contribute(bb) is True


class TestObjectionGuardSourceContributeWithinLimits:
    """Test ObjectionGuardSource.contribute() when within limits."""

    def test_contribute_within_limits_no_proposals(self):
        """Test that no proposals when objection count is within limits."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=1,
            objection_total=1,
            collected_data={"persona": "default"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0
        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_at_limit_minus_one_no_proposals(self):
        """Test that no proposals when objection is one below limit."""
        from src.blackboard.sources import ObjectionGuardSource

        # Note: begin_turn calls tracker.record() which adds +1 to counters for objection intents
        # So we pass values 1 less than what we want after begin_turn
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=1,  # becomes 2 after begin_turn, limit is 3 for default
            objection_total=3,  # becomes 4 after begin_turn, limit is 5 for default
            collected_data={"persona": "default"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0
        assert len(bb.get_transition_proposals()) == 0


class TestObjectionGuardSourceContributeExceeded:
    """Test ObjectionGuardSource.contribute() when limits exceeded."""

    def test_contribute_consecutive_exceeded_proposes_action_and_transition(self):
        """Test that consecutive limit exceeded proposes blocking action and transition."""
        from src.blackboard.sources import ObjectionGuardSource
        from src.blackboard.enums import Priority, ProposalType

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,  # equals limit for default
            objection_total=3,
            collected_data={"persona": "default"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        # Check action proposal
        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].type == ProposalType.ACTION
        assert action_proposals[0].value == "objection_limit_reached"
        assert action_proposals[0].priority == Priority.CRITICAL
        assert action_proposals[0].combinable is True  # Allow transition to soft_close
        assert action_proposals[0].source_name == "ObjectionGuardSource"
        assert action_proposals[0].reason_code == "objection_limit_exceeded"

        # Check transition proposal
        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].type == ProposalType.TRANSITION
        assert transition_proposals[0].value == "soft_close"
        assert transition_proposals[0].priority == Priority.CRITICAL

    def test_contribute_total_exceeded_proposes_action_and_transition(self):
        """Test that total limit exceeded proposes blocking action and transition."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=1,
            objection_total=5,  # equals limit for default
            collected_data={"persona": "default"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].value == "objection_limit_reached"
        assert action_proposals[0].combinable is True  # Allow transition to soft_close

        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].value == "soft_close"

    def test_contribute_sets_objection_limit_final_flag(self):
        """Test that _objection_limit_final flag is proposed."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
            collected_data={"persona": "default"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        data_updates = bb.get_data_updates()
        assert "_objection_limit_final" in data_updates
        assert data_updates["_objection_limit_final"] is True

    def test_contribute_metadata_includes_counters(self):
        """Test that metadata includes objection counters and limits."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=4,
            collected_data={"persona": "default"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        metadata = action_proposals[0].metadata

        assert metadata["persona"] == "default"
        assert metadata["consecutive"] == 3
        assert metadata["total"] == 4
        assert metadata["max_consecutive"] == 3
        assert metadata["max_total"] == 5
        assert "consecutive=3>=3" in metadata["exceeded"]


class TestObjectionGuardSourcePersonaLimits:
    """Test ObjectionGuardSource persona-specific limits."""

    def test_aggressive_persona_higher_limits(self):
        """Test that aggressive persona has higher limits."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=4,  # would exceed default (3) but not aggressive (5)
            objection_total=7,  # would exceed default (5) but not aggressive (8)
            collected_data={"persona": "aggressive"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        # Should NOT propose anything - within aggressive limits
        assert len(bb.get_action_proposals()) == 0
        assert len(bb.get_transition_proposals()) == 0

    def test_busy_persona_lower_limits(self):
        """Test that busy persona has lower limits."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=2,  # equals busy limit (2)
            objection_total=2,
            collected_data={"persona": "busy"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        # Should propose - busy persona limit reached
        assert len(bb.get_action_proposals()) == 1
        assert bb.get_action_proposals()[0].value == "objection_limit_reached"

    def test_unknown_persona_uses_default(self):
        """Test that unknown persona falls back to default limits."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,  # equals default limit
            objection_total=3,
            collected_data={"persona": "unknown_persona"}
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        # Should use default limits
        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].metadata["max_consecutive"] == 3  # default

    def test_no_persona_uses_default(self):
        """Test that no persona in collected_data uses default limits."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
            collected_data={}  # No persona
        )
        source = ObjectionGuardSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1


class TestObjectionGuardSourceEnableDisable:
    """Test ObjectionGuardSource enable/disable functionality."""

    def test_enable_source(self):
        """Test enabling source."""
        from src.blackboard.sources import ObjectionGuardSource

        source = ObjectionGuardSource()
        source.disable()
        source.enable()

        assert source.enabled is True

    def test_disable_source(self):
        """Test disabling source."""
        from src.blackboard.sources import ObjectionGuardSource

        source = ObjectionGuardSource()
        source.disable()

        assert source.enabled is False

    def test_disabled_source_no_contribution(self):
        """Test that disabled source doesn't contribute even when limit exceeded."""
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=10,
            objection_total=10,
        )
        source = ObjectionGuardSource()
        source.disable()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0
        assert len(bb.get_transition_proposals()) == 0


# =============================================================================
# Tests for IntentProcessorSource
# =============================================================================

class TestIntentProcessorSourceInit:
    """Test IntentProcessorSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        from src.blackboard.sources import IntentProcessorSource

        source = IntentProcessorSource()

        assert source.name == "IntentProcessorSource"
        assert source.enabled is True
        assert source.rule_resolver is not None
        assert source.condition_registry is not None

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        from src.blackboard.sources import IntentProcessorSource

        source = IntentProcessorSource(name="CustomIntentProcessor")

        assert source.name == "CustomIntentProcessor"

    def test_init_with_custom_rule_resolver(self):
        """Test initialization with custom rule resolver."""
        from src.blackboard.sources import IntentProcessorSource

        custom_resolver = MockRuleResolver()
        source = IntentProcessorSource(rule_resolver=custom_resolver)

        assert source.rule_resolver is custom_resolver

    def test_init_with_custom_condition_registry(self):
        """Test initialization with custom condition registry."""
        from src.blackboard.sources import IntentProcessorSource

        custom_registry = MockConditionRegistry()
        source = IntentProcessorSource(condition_registry=custom_registry)

        assert source.condition_registry is custom_registry


class TestIntentProcessorSourceDedicatedIntents:
    """Test IntentProcessorSource skips dedicated source intents."""

    def test_dedicated_source_intents_defined(self):
        """Test that dedicated source intents are defined."""
        from src.blackboard.sources import IntentProcessorSource

        expected = {
            "price_question",
            "pricing_details",
            "cost_inquiry",
            "discount_request",
            "payment_terms",
            "pricing_comparison",
            "budget_question",
        }
        assert IntentProcessorSource.DEDICATED_SOURCE_INTENTS == expected


class TestIntentProcessorSourceShouldContribute:
    """Test IntentProcessorSource.should_contribute()."""

    def test_should_contribute_normal_intent(self):
        """Test should_contribute returns True for normal intents."""
        from src.blackboard.sources import IntentProcessorSource

        bb = create_blackboard(intent="greeting")
        source = IntentProcessorSource()

        assert source.should_contribute(bb) is True

    def test_should_not_contribute_price_question(self):
        """Test should_contribute returns False for price_question (dedicated source)."""
        from src.blackboard.sources import IntentProcessorSource

        bb = create_blackboard(intent="price_question")
        source = IntentProcessorSource()

        assert source.should_contribute(bb) is False

    def test_should_not_contribute_discount_request(self):
        """Test should_contribute returns False for discount_request (dedicated source)."""
        from src.blackboard.sources import IntentProcessorSource

        bb = create_blackboard(intent="discount_request")
        source = IntentProcessorSource()

        assert source.should_contribute(bb) is False

    def test_should_not_contribute_when_disabled(self):
        """Test should_contribute returns False when source is disabled."""
        from src.blackboard.sources import IntentProcessorSource

        bb = create_blackboard(intent="greeting")
        source = IntentProcessorSource()
        source.disable()

        assert source.should_contribute(bb) is False


class TestIntentProcessorSourceContributeSimpleRules:
    """Test IntentProcessorSource.contribute() with simple string rules."""

    def test_contribute_simple_rule_proposes_action(self):
        """Test that simple string rule proposes action."""
        from src.blackboard.sources import IntentProcessorSource
        from src.blackboard.enums import Priority, ProposalType

        states = {
            "spin_situation": {
                "rules": {
                    "greeting": "greet_back",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="greeting")
        source = IntentProcessorSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].type == ProposalType.ACTION
        assert action_proposals[0].value == "greet_back"
        assert action_proposals[0].priority == Priority.NORMAL
        assert action_proposals[0].combinable is True
        assert action_proposals[0].source_name == "IntentProcessorSource"
        assert action_proposals[0].reason_code == "rule_greeting"

    def test_contribute_no_rule_no_proposal(self):
        """Test that missing rule doesn't propose anything."""
        from src.blackboard.sources import IntentProcessorSource

        states = {
            "spin_situation": {
                "rules": {
                    "greeting": "greet_back",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="unknown_intent")
        source = IntentProcessorSource()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0


class TestIntentProcessorSourceContributeBlockingActions:
    """Test IntentProcessorSource blocking actions."""

    def test_handle_rejection_is_not_combinable(self):
        """Test that handle_rejection action is not combinable."""
        from src.blackboard.sources import IntentProcessorSource

        states = {
            "spin_situation": {
                "rules": {
                    "rejection": "handle_rejection",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="rejection")
        source = IntentProcessorSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].value == "handle_rejection"
        assert action_proposals[0].combinable is False

    def test_emergency_escalate_is_not_combinable(self):
        """Test that emergency_escalate action is not combinable."""
        from src.blackboard.sources import IntentProcessorSource

        states = {
            "spin_situation": {
                "rules": {
                    "emergency": "emergency_escalate",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="emergency")
        source = IntentProcessorSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].combinable is False

    def test_end_conversation_is_not_combinable(self):
        """Test that end_conversation action is not combinable."""
        from src.blackboard.sources import IntentProcessorSource

        states = {
            "spin_situation": {
                "rules": {
                    "goodbye": "end_conversation",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="goodbye")
        source = IntentProcessorSource()

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].combinable is False


class TestIntentProcessorSourceContributeMetadata:
    """Test IntentProcessorSource metadata in proposals."""

    def test_metadata_includes_intent(self):
        """Test that metadata includes the intent."""
        from src.blackboard.sources import IntentProcessorSource

        states = {
            "spin_situation": {
                "rules": {
                    "greeting": "greet_back",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="greeting")
        source = IntentProcessorSource()

        source.contribute(bb)

        metadata = bb.get_action_proposals()[0].metadata
        assert metadata["intent"] == "greeting"

    def test_metadata_includes_rule_type(self):
        """Test that metadata includes rule type."""
        from src.blackboard.sources import IntentProcessorSource

        states = {
            "spin_situation": {
                "rules": {
                    "greeting": "greet_back",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="greeting")
        source = IntentProcessorSource()

        source.contribute(bb)

        metadata = bb.get_action_proposals()[0].metadata
        assert metadata["rule_type"] == "str"


class TestIntentProcessorSourceEnableDisable:
    """Test IntentProcessorSource enable/disable functionality."""

    def test_enable_source(self):
        """Test enabling source."""
        from src.blackboard.sources import IntentProcessorSource

        source = IntentProcessorSource()
        source.disable()
        source.enable()

        assert source.enabled is True

    def test_disable_source(self):
        """Test disabling source."""
        from src.blackboard.sources import IntentProcessorSource

        source = IntentProcessorSource()
        source.disable()

        assert source.enabled is False

    def test_disabled_source_no_contribution(self):
        """Test that disabled source doesn't contribute."""
        from src.blackboard.sources import IntentProcessorSource

        states = {
            "spin_situation": {
                "rules": {
                    "greeting": "greet_back",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="greeting")
        source = IntentProcessorSource()
        source.disable()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestSourcesStage7Integration:
    """Integration tests for Stage 7 sources working together."""

    def test_objection_guard_has_critical_priority(self):
        """
        Test that ObjectionGuardSource creates CRITICAL priority action.

        When objection limit is exceeded, we want:
        - ObjectionGuardSource: objection_limit_reached (Priority.CRITICAL, combinable=True)
        - The CRITICAL priority ensures this action wins in conflict resolution
        - combinable=True allows the transition to soft_close to happen
        """
        from src.blackboard.sources import ObjectionGuardSource, IntentProcessorSource
        from src.blackboard.enums import Priority

        states = {
            "spin_situation": {
                "rules": {
                    "objection_price": "handle_price_objection",
                }
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
            collected_data={"persona": "default"}
        )

        objection_source = ObjectionGuardSource()
        intent_source = IntentProcessorSource()

        # Both sources contribute
        objection_source.contribute(bb)
        intent_source.contribute(bb)

        action_proposals = bb.get_action_proposals()

        # Should have 2 proposals
        assert len(action_proposals) == 2

        # Find the CRITICAL priority one (objection_limit_reached)
        critical_proposals = [p for p in action_proposals if p.priority == Priority.CRITICAL]
        assert len(critical_proposals) == 1
        assert critical_proposals[0].value == "objection_limit_reached"
        # combinable=True to allow soft_close transition
        assert critical_proposals[0].combinable is True

    def test_intent_processor_with_data_collector(self):
        """
        Test IntentProcessorSource works with DataCollectorSource.
        """
        from src.blackboard.sources import IntentProcessorSource, DataCollectorSource

        states = {
            "spin_situation": {
                "required_data": ["company_name"],
                "transitions": {"data_complete": "spin_problem"},
                "rules": {
                    "agreement": "acknowledge",
                }
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="agreement",
            collected_data={"company_name": "ACME"},
        )

        intent_source = IntentProcessorSource()
        data_source = DataCollectorSource()

        intent_source.contribute(bb)
        data_source.contribute(bb)

        # Should have action from IntentProcessor and transition from DataCollector
        action_proposals = bb.get_action_proposals()
        transition_proposals = bb.get_transition_proposals()

        assert len(action_proposals) == 1
        assert action_proposals[0].value == "acknowledge"
        assert action_proposals[0].combinable is True

        assert len(transition_proposals) == 1
        assert transition_proposals[0].value == "spin_problem"


# =============================================================================
# Package Import Tests
# =============================================================================

class TestStage7PackageImports:
    """Test package import functionality for Stage 7."""

    def test_import_objection_guard_source(self):
        """Test importing ObjectionGuardSource from package."""
        from src.blackboard.sources import ObjectionGuardSource

        assert ObjectionGuardSource is not None

    def test_import_intent_processor_source(self):
        """Test importing IntentProcessorSource from package."""
        from src.blackboard.sources import IntentProcessorSource

        assert IntentProcessorSource is not None

    def test_sources_in_dunder_all(self):
        """Test that Stage 7 sources are in __all__."""
        import src.blackboard.sources as sources

        assert "ObjectionGuardSource" in sources.__all__
        assert "IntentProcessorSource" in sources.__all__


# =============================================================================
# Criteria Verification (from Architectural Plan)
# =============================================================================

class TestStage7CriteriaVerification:
    """
    Verification tests from the plan's CRITERION OF COMPLETION for Stage 7.
    """

    def test_criterion_import_objection_guard_source(self):
        """
        Plan criterion: from src.blackboard.sources import ObjectionGuardSource
        """
        from src.blackboard.sources import ObjectionGuardSource

        assert ObjectionGuardSource is not None

    def test_criterion_import_intent_processor_source(self):
        """
        Plan criterion: from src.blackboard.sources import IntentProcessorSource
        """
        from src.blackboard.sources import IntentProcessorSource

        assert IntentProcessorSource is not None

    def test_criterion_objection_guard_sets_objection_limit_final(self):
        """
        Plan criterion (CRITICAL): ObjectionGuardSource должен устанавливать _objection_limit_final
        """
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
            collected_data={"persona": "default"}
        )
        source = ObjectionGuardSource()
        source.contribute(bb)

        data_updates = bb.get_data_updates()
        assert "_objection_limit_final" in data_updates
        assert data_updates["_objection_limit_final"] is True

    def test_criterion_objection_guard_critical_priority(self):
        """
        Plan criterion: ObjectionGuardSource uses CRITICAL priority and combinable=True.

        Design note: combinable=True allows the soft_close transition to happen.
        CRITICAL priority ensures this action wins over other proposals.
        """
        from src.blackboard.sources import ObjectionGuardSource
        from src.blackboard.enums import Priority

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
        )
        source = ObjectionGuardSource()
        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].priority == Priority.CRITICAL
        assert action_proposals[0].combinable is True

    def test_criterion_objection_guard_proposes_soft_close(self):
        """
        Plan criterion: ObjectionGuardSource proposes soft_close transition
        """
        from src.blackboard.sources import ObjectionGuardSource

        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
        )
        source = ObjectionGuardSource()
        source.contribute(bb)

        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].value == "soft_close"

    def test_criterion_intent_processor_maps_intents(self):
        """
        Plan criterion: IntentProcessorSource maps intents to actions
        """
        from src.blackboard.sources import IntentProcessorSource

        states = {
            "spin_situation": {
                "rules": {
                    "unclear": "probe_situation",
                }
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="unclear")
        source = IntentProcessorSource()
        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].value == "probe_situation"

    def test_criterion_intent_processor_skips_price_intents(self):
        """
        Plan criterion: IntentProcessorSource does NOT handle price questions
        """
        from src.blackboard.sources import IntentProcessorSource

        bb = create_blackboard(intent="price_question")
        source = IntentProcessorSource()

        # should_contribute should return False
        assert source.should_contribute(bb) is False

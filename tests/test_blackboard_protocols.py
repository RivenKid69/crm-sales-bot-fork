# tests/test_blackboard_protocols.py

"""
Tests for Blackboard Stage 1: Protocols and Enums.

These tests verify:
1. Priority and ProposalType enums work correctly
2. Protocol definitions are valid
3. Concrete implementations properly implement required protocols
4. TenantConfig implementation works correctly
"""

import pytest
from typing import Dict, Any, Optional


class TestPriorityEnum:
    """Test Priority enum functionality."""

    def test_priority_values(self):
        """Verify Priority enum values are correct."""
        from src.blackboard.enums import Priority

        assert Priority.CRITICAL.value == 0
        assert Priority.HIGH.value == 1
        assert Priority.NORMAL.value == 2
        assert Priority.LOW.value == 3

    def test_priority_ordering(self):
        """Verify Priority comparison works (lower value = higher priority)."""
        from src.blackboard.enums import Priority

        # CRITICAL has highest priority (lowest value)
        assert Priority.CRITICAL < Priority.HIGH
        assert Priority.HIGH < Priority.NORMAL
        assert Priority.NORMAL < Priority.LOW

        # Reverse checks
        assert Priority.LOW > Priority.NORMAL
        assert Priority.NORMAL > Priority.HIGH
        assert Priority.HIGH > Priority.CRITICAL

    def test_priority_equality(self):
        """Verify Priority equality works."""
        from src.blackboard.enums import Priority

        assert Priority.CRITICAL == Priority.CRITICAL
        assert Priority.HIGH == Priority.HIGH
        assert not (Priority.CRITICAL == Priority.HIGH)

    def test_priority_comparison_operators(self):
        """Test all comparison operators."""
        from src.blackboard.enums import Priority

        # Less than or equal
        assert Priority.CRITICAL <= Priority.CRITICAL
        assert Priority.CRITICAL <= Priority.HIGH

        # Greater than or equal
        assert Priority.LOW >= Priority.LOW
        assert Priority.LOW >= Priority.NORMAL

    def test_priority_is_intenum(self):
        """Verify Priority is IntEnum for sorting."""
        from src.blackboard.enums import Priority
        from enum import IntEnum

        assert issubclass(Priority, IntEnum)

        # Can be sorted
        priorities = [Priority.LOW, Priority.CRITICAL, Priority.NORMAL, Priority.HIGH]
        sorted_priorities = sorted(priorities)
        assert sorted_priorities == [
            Priority.CRITICAL,
            Priority.HIGH,
            Priority.NORMAL,
            Priority.LOW,
        ]


class TestProposalTypeEnum:
    """Test ProposalType enum functionality."""

    def test_proposal_type_values_exist(self):
        """Verify all ProposalType values exist."""
        from src.blackboard.enums import ProposalType

        assert hasattr(ProposalType, "ACTION")
        assert hasattr(ProposalType, "TRANSITION")

    def test_proposal_type_uniqueness(self):
        """Verify all ProposalType values are unique."""
        from src.blackboard.enums import ProposalType

        values = [pt.value for pt in ProposalType]
        assert len(values) == len(set(values)), "ProposalType values must be unique"

    def test_proposal_type_iteration(self):
        """Verify ProposalType can be iterated."""
        from src.blackboard.enums import ProposalType

        types = list(ProposalType)
        assert len(types) == 2
        assert ProposalType.ACTION in types
        assert ProposalType.TRANSITION in types


class TestTenantConfig:
    """Test TenantConfig implementation."""

    def test_default_tenant_exists(self):
        """Verify DEFAULT_TENANT is available."""
        from src.blackboard.protocols import DEFAULT_TENANT

        assert DEFAULT_TENANT is not None
        assert DEFAULT_TENANT.tenant_id == "default"

    def test_default_tenant_default_values(self):
        """Verify DEFAULT_TENANT has correct default values."""
        from src.blackboard.protocols import DEFAULT_TENANT

        assert DEFAULT_TENANT.bot_name == "Assistant"
        assert DEFAULT_TENANT.tone == "professional"
        assert DEFAULT_TENANT.features == {}
        assert DEFAULT_TENANT.persona_limits_override is None

    def test_tenant_config_creation(self):
        """Test creating custom tenant config."""
        from src.blackboard.protocols import TenantConfig

        tenant = TenantConfig(
            tenant_id="acme_corp",
            bot_name="ACME Assistant",
            tone="friendly",
            features={"escalation": True, "price_questions": False},
            persona_limits_override={
                "aggressive": {"consecutive": 10, "total": 15}
            },
        )

        assert tenant.tenant_id == "acme_corp"
        assert tenant.bot_name == "ACME Assistant"
        assert tenant.tone == "friendly"
        assert tenant.features["escalation"] is True
        assert tenant.features["price_questions"] is False
        assert tenant.persona_limits_override["aggressive"]["consecutive"] == 10
        assert tenant.persona_limits_override["aggressive"]["total"] == 15

    def test_tenant_config_default_features(self):
        """Test that features defaults to empty dict."""
        from src.blackboard.protocols import TenantConfig

        tenant = TenantConfig(tenant_id="test")
        assert tenant.features == {}
        assert tenant.persona_limits_override is None

    def test_tenant_config_minimal(self):
        """Test creating tenant with minimal arguments."""
        from src.blackboard.protocols import TenantConfig

        tenant = TenantConfig(tenant_id="minimal")
        assert tenant.tenant_id == "minimal"
        assert tenant.bot_name == "Assistant"
        assert tenant.tone == "professional"

    def test_tenant_implements_protocol(self):
        """Verify TenantConfig implements ITenantConfig protocol."""
        from src.blackboard.protocols import TenantConfig, ITenantConfig

        tenant = TenantConfig(tenant_id="test")
        assert isinstance(tenant, ITenantConfig)


class TestProtocolCompliance:
    """Test that concrete classes implement protocols correctly."""

    def test_state_machine_implements_protocol(self):
        """Verify StateMachine implements IStateMachine protocol."""
        from src.blackboard.protocols import IStateMachine
        from src.state_machine import StateMachine

        # Create StateMachine instance
        sm = StateMachine()

        # Runtime check using isinstance with runtime_checkable protocol
        assert isinstance(sm, IStateMachine), (
            "StateMachine must implement IStateMachine protocol"
        )

    def test_state_machine_has_required_properties(self):
        """Verify StateMachine has all required properties."""
        from src.state_machine import StateMachine

        sm = StateMachine()

        # Check properties exist and are accessible
        assert hasattr(sm, "state")
        assert hasattr(sm, "collected_data")
        assert hasattr(sm, "is_final")

        # Check they return correct types
        assert isinstance(sm.state, str)
        assert isinstance(sm.collected_data, dict)
        assert isinstance(sm.is_final(), bool)

    def test_intent_tracker_implements_protocol(self):
        """Verify IntentTracker implements IIntentTracker protocol."""
        from src.blackboard.protocols import IIntentTracker
        from src.intent_tracker import IntentTracker

        tracker = IntentTracker()
        assert isinstance(tracker, IIntentTracker), (
            "IntentTracker must implement IIntentTracker protocol"
        )

    def test_intent_tracker_has_required_methods(self):
        """Verify IntentTracker has all required methods."""
        from src.intent_tracker import IntentTracker

        tracker = IntentTracker()

        # Check properties
        assert hasattr(tracker, "turn_number")
        assert hasattr(tracker, "prev_intent")

        # Check methods
        assert callable(getattr(tracker, "record", None))
        assert callable(getattr(tracker, "objection_consecutive", None))
        assert callable(getattr(tracker, "objection_total", None))
        assert callable(getattr(tracker, "total_count", None))
        assert callable(getattr(tracker, "category_total", None))

    def test_flow_config_implements_protocol(self):
        """Verify FlowConfig implements IFlowConfig protocol."""
        from src.blackboard.protocols import IFlowConfig
        from src.config_loader import FlowConfig

        config = FlowConfig(name="test_flow", states={})
        assert isinstance(config, IFlowConfig), (
            "FlowConfig must implement IFlowConfig protocol"
        )

    def test_flow_config_has_required_properties(self):
        """Verify FlowConfig has all required properties."""
        from src.config_loader import FlowConfig

        config = FlowConfig(name="test_flow", states={"greeting": {}})

        # Check property
        assert hasattr(config, "states")
        assert isinstance(config.states, dict)

        # Check method
        assert callable(getattr(config, "to_dict", None))

        # Verify to_dict works
        config_dict = config.to_dict()
        assert "states" in config_dict
        assert "greeting" in config_dict["states"]


class TestMockImplementations:
    """Test that mock implementations work with protocols."""

    def test_mock_state_machine_implements_protocol(self):
        """
        Demonstrate how to create a mock that implements IStateMachine.

        This is useful for unit testing without real StateMachine.
        """
        from src.blackboard.protocols import IStateMachine

        class MockStateMachine:
            def __init__(self):
                self._state = "greeting"
                self._collected_data = {}
                self._current_phase = None
                self._last_action = None
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
                return self._state == "closed"

            def transition_to(
                self,
                next_state: str,
                action: Optional[str] = None,
                phase: Optional[str] = None,
                source: str = "unknown",
                validate: bool = True,
            ) -> bool:
                self._state = next_state
                self._current_phase = phase
                if action is not None:
                    self._last_action = action
                return True

            def sync_phase_from_state(self) -> None:
                pass

        mock_sm = MockStateMachine()
        assert isinstance(mock_sm, IStateMachine)

        # Verify functionality
        assert mock_sm.state == "greeting"
        mock_sm.state = "collecting"
        assert mock_sm.state == "collecting"

        mock_sm.update_data({"key": "value"})
        assert mock_sm.collected_data == {"key": "value"}

        assert not mock_sm.is_final()
        mock_sm.state = "closed"
        assert mock_sm.is_final()

    def test_mock_intent_tracker_implements_protocol(self):
        """Test mock IntentTracker implementation."""
        from src.blackboard.protocols import IIntentTracker

        class MockIntentTracker:
            def __init__(self):
                self._turn_number = 1
                self._prev_intent = None
                self._intents = []

            @property
            def turn_number(self) -> int:
                return self._turn_number

            @property
            def prev_intent(self) -> Optional[str]:
                return self._prev_intent

            @property
            def last_intent(self) -> Optional[str]:
                return self._intents[-1][0] if self._intents else None

            @property
            def last_state(self) -> Optional[str]:
                return self._intents[-1][1] if self._intents else None

            @property
            def history_length(self) -> int:
                return len(self._intents)

            def record(self, intent: str, state: str) -> None:
                self._prev_intent = intent
                self._intents.append((intent, state))

            def advance_turn(self) -> None:
                self._turn_number += 1

            def objection_consecutive(self) -> int:
                return 0

            def objection_total(self) -> int:
                return 0

            def total_count(self, intent: str) -> int:
                return sum(1 for i, _ in self._intents if i == intent)

            def category_total(self, category: str) -> int:
                return 0

            def streak_count(self, intent: str) -> int:
                return 0

            def category_streak(self, category: str) -> int:
                return 0

            def get_intents_by_category(self, category: str) -> list:
                return []

            def get_recent_intents(self, limit: int = 5) -> list:
                return [i for i, _ in self._intents[-limit:]]

        mock_tracker = MockIntentTracker()
        assert isinstance(mock_tracker, IIntentTracker)

        # Verify functionality
        assert mock_tracker.turn_number == 1
        assert mock_tracker.prev_intent is None

        mock_tracker.record("greeting", "greeting_state")
        mock_tracker.advance_turn()
        assert mock_tracker.turn_number == 2
        assert mock_tracker.prev_intent == "greeting"
        assert mock_tracker.total_count("greeting") == 1

    def test_mock_flow_config_implements_protocol(self):
        """Test mock FlowConfig implementation."""
        from src.blackboard.protocols import IFlowConfig

        class MockFlowConfig:
            def __init__(self, states: Dict[str, Dict[str, Any]]):
                self._states = states

            @property
            def states(self) -> Dict[str, Dict[str, Any]]:
                return self._states

            def to_dict(self) -> Dict[str, Any]:
                return {"states": self._states}

            @property
            def phase_mapping(self) -> Dict[str, str]:
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
                Includes reverse mapping AND explicit phases from state configs.
                """
                # Start with reverse mapping from phase_mapping
                result = {v: k for k, v in self.phase_mapping.items()}

                # Override with explicit phases from state configs
                for state_name, state_config in self._states.items():
                    explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
                    if explicit_phase:
                        result[state_name] = explicit_phase

                return result

            def get_phase_for_state(self, state_name: str) -> Optional[str]:
                # Delegate to state_to_phase which contains the complete mapping
                return self.state_to_phase.get(state_name)

            def is_phase_state(self, state_name: str) -> bool:
                return self.get_phase_for_state(state_name) is not None

        mock_config = MockFlowConfig(states={"greeting": {"goal": "Greet user"}})
        assert isinstance(mock_config, IFlowConfig)

        # Verify functionality
        assert "greeting" in mock_config.states
        assert mock_config.states["greeting"]["goal"] == "Greet user"
        assert mock_config.to_dict() == {"states": {"greeting": {"goal": "Greet user"}}}


class TestBlackboardPackageImports:
    """Test that blackboard package exports work correctly."""

    def test_import_priority_from_package(self):
        """Verify Priority can be imported from src.blackboard."""
        from src.blackboard import Priority

        assert Priority.CRITICAL.value == 0

    def test_import_proposal_type_from_package(self):
        """Verify ProposalType can be imported from src.blackboard."""
        from src.blackboard import ProposalType

        assert hasattr(ProposalType, "ACTION")

    def test_import_protocols_from_package(self):
        """Verify all protocols can be imported from src.blackboard."""
        from src.blackboard import (
            IStateMachine,
            IIntentTracker,
            IFlowConfig,
            IContextEnvelope,
            ITenantConfig,
            TenantConfig,
            DEFAULT_TENANT,
        )

        assert IStateMachine is not None
        assert IIntentTracker is not None
        assert IFlowConfig is not None
        assert IContextEnvelope is not None
        assert ITenantConfig is not None
        assert TenantConfig is not None
        assert DEFAULT_TENANT is not None

    def test_all_exports_in_dunder_all(self):
        """Verify __all__ contains expected exports."""
        import src.blackboard as bb

        expected = [
            "Priority",
            "ProposalType",
            "IStateMachine",
            "IIntentTracker",
            "IFlowConfig",
            "IContextEnvelope",
            "ITenantConfig",
            "TenantConfig",
            "DEFAULT_TENANT",
        ]

        for name in expected:
            assert name in bb.__all__, f"{name} should be in __all__"


class TestCriteriaVerification:
    """
    Verification tests from the plan's CRITERION OF COMPLETION for Stage 1.

    These are the exact checks specified in the architectural plan.
    """

    def test_criterion_priority_import(self):
        """
        Plan criterion: python -c "from src.blackboard import Priority, ProposalType"
        """
        from src.blackboard import Priority, ProposalType

        # Additional verification
        assert Priority.CRITICAL < Priority.LOW
        assert ProposalType.ACTION != ProposalType.TRANSITION

    def test_criterion_protocols_import(self):
        """
        Plan criterion: python -c "from src.blackboard.protocols import IStateMachine, TenantConfig"
        """
        from src.blackboard.protocols import IStateMachine, TenantConfig

        # Additional verification
        assert callable(getattr(IStateMachine, "__init__", None)) or True  # Protocol
        tenant = TenantConfig(tenant_id="test")
        assert tenant.tenant_id == "test"

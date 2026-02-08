# tests/test_protocols.py

"""
Tests for Protocol compliance (Hexagonal Architecture).

These tests verify that concrete implementations properly implement
the required protocols, ensuring Dependency Inversion principle.
"""

import pytest
from typing import Dict, Any, Optional

from src.blackboard.protocols import (
    IStateMachine,
    IIntentTracker,
    IFlowConfig,
    ITenantConfig,
    TenantConfig,
    DEFAULT_TENANT,
)


class TestProtocolCompliance:
    """Test that concrete classes implement protocols correctly."""

    def test_state_machine_implements_protocol(self):
        """Verify StateMachine implements IStateMachine protocol."""
        from src.state_machine import StateMachine

        # Runtime check using isinstance with runtime_checkable protocol
        sm = StateMachine()
        assert isinstance(sm, IStateMachine), (
            "StateMachine must implement IStateMachine protocol"
        )

    def test_intent_tracker_implements_protocol(self):
        """Verify IntentTracker implements IIntentTracker protocol."""
        from src.intent_tracker import IntentTracker

        tracker = IntentTracker()
        assert isinstance(tracker, IIntentTracker), (
            "IntentTracker must implement IIntentTracker protocol"
        )

    def test_flow_config_implements_protocol(self):
        """Verify FlowConfig implements IFlowConfig protocol."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        flow = loader.load_flow("spin_selling")
        assert isinstance(flow, IFlowConfig), (
            "FlowConfig must implement IFlowConfig protocol"
        )


class TestTenantConfig:
    """Test TenantConfig implementation."""

    def test_default_tenant_exists(self):
        """Verify DEFAULT_TENANT is available."""
        assert DEFAULT_TENANT is not None
        assert DEFAULT_TENANT.tenant_id == "default"

    def test_tenant_config_creation(self):
        """Test creating custom tenant config."""
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

    def test_tenant_config_default_features(self):
        """Test that features defaults to empty dict."""
        tenant = TenantConfig(tenant_id="test")
        assert tenant.features == {}

    def test_tenant_implements_protocol(self):
        """Verify TenantConfig implements ITenantConfig protocol."""
        tenant = TenantConfig(tenant_id="test")
        assert isinstance(tenant, ITenantConfig)

    def test_tenant_config_default_values(self):
        """Test default values for TenantConfig."""
        tenant = TenantConfig(tenant_id="minimal")

        assert tenant.tenant_id == "minimal"
        assert tenant.bot_name == "Assistant"  # default
        assert tenant.tone == "professional"  # default
        assert tenant.features == {}  # default
        assert tenant.persona_limits_override is None  # default


class TestMockImplementations:
    """Test that mock implementations work with protocols."""

    def test_mock_state_machine_for_testing(self):
        """
        Demonstrate how to create a mock that implements IStateMachine.

        This is useful for unit testing without real StateMachine.
        """
        class MockIntentTracker:
            @property
            def turn_number(self) -> int:
                return 1

            @property
            def prev_intent(self) -> Optional[str]:
                return None

            def record(self, intent: str, state: str) -> None:
                pass

            def advance_turn(self) -> None:
                pass

            def objection_consecutive(self) -> int:
                return 0

            def objection_total(self) -> int:
                return 0

            def total_count(self, intent: str) -> int:
                return 0

            def category_total(self, category: str) -> int:
                return 0

        class MockStateMachine:
            def __init__(self):
                self._state = "greeting"
                self._collected_data = {}
                self._intent_tracker = MockIntentTracker()
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
                for key, value in data.items():
                    if value:
                        self._collected_data[key] = value

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

        # Use mock in DialogueBlackboard
        from src.blackboard.blackboard import DialogueBlackboard
        from src.blackboard.protocols import DEFAULT_TENANT

        class MockFlowConfig:
            @property
            def states(self) -> Dict[str, Dict[str, Any]]:
                return {"greeting": {"goal": "Test"}}

            def to_dict(self) -> Dict[str, Any]:
                return {"states": self.states}

            @property
            def phase_mapping(self) -> Dict[str, str]:
                return {}

            @property
            def state_to_phase(self) -> Dict[str, str]:
                return {}

            def get_phase_for_state(self, state_name: str) -> Optional[str]:
                return None

            def is_phase_state(self, state_name: str) -> bool:
                return False

        bb = DialogueBlackboard(
            state_machine=mock_sm,
            flow_config=MockFlowConfig(),
            tenant_config=DEFAULT_TENANT,
        )
        assert bb.tenant_id == "default"

    def test_mock_intent_tracker_for_testing(self):
        """
        Demonstrate how to create a mock that implements IIntentTracker.
        """
        class MockIntentTracker:
            def __init__(self):
                self._turn = 0
                self._prev_intent = None
                self._intents = []
                self._states = []

            @property
            def turn_number(self) -> int:
                return self._turn

            @property
            def prev_intent(self) -> Optional[str]:
                return self._prev_intent

            @property
            def last_intent(self) -> Optional[str]:
                return self._intents[-1] if self._intents else None

            @property
            def last_state(self) -> Optional[str]:
                return self._states[-1] if self._states else None

            @property
            def history_length(self) -> int:
                return len(self._intents)

            def record(self, intent: str, state: str) -> None:
                self._prev_intent = self._intents[-1] if self._intents else None
                self._intents.append(intent)
                self._states.append(state)

            def advance_turn(self) -> None:
                self._turn += 1

            def objection_consecutive(self) -> int:
                return 0

            def objection_total(self) -> int:
                return 0

            def total_count(self, intent: str) -> int:
                return self._intents.count(intent)

            def category_total(self, category: str) -> int:
                return 0

            def streak_count(self, intent: str) -> int:
                return 0

            def category_streak(self, category: str) -> int:
                return 0

            def get_intents_by_category(self, category: str) -> list:
                return []

            def get_recent_intents(self, limit: int = 5) -> list:
                return self._intents[-limit:]

        mock_tracker = MockIntentTracker()
        assert isinstance(mock_tracker, IIntentTracker)

        # Test recording
        mock_tracker.record("greeting", "greeting")
        mock_tracker.advance_turn()
        assert mock_tracker.turn_number == 1
        assert mock_tracker.total_count("greeting") == 1

        mock_tracker.record("price_question", "spin_situation")
        mock_tracker.advance_turn()
        assert mock_tracker.turn_number == 2
        assert mock_tracker.prev_intent == "greeting"

    def test_mock_flow_config_for_testing(self):
        """
        Demonstrate how to create a mock that implements IFlowConfig.
        """
        class MockFlowConfig:
            def __init__(self, states: Dict[str, Dict[str, Any]] = None):
                self._states = states or {}

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

        mock_config = MockFlowConfig({
            "greeting": {
                "goal": "Welcome user",
                "transitions": {"any": "spin_situation"},
            },
            "spin_situation": {
                "goal": "Gather situation data",
                "phase": "situation",
                "required_data": ["company_size"],
            },
        })

        assert isinstance(mock_config, IFlowConfig)
        assert "greeting" in mock_config.states
        assert mock_config.states["spin_situation"]["phase"] == "situation"


class TestProtocolAttributes:
    """Test that protocol implementations have required attributes."""

    def test_state_machine_has_required_properties(self):
        """Verify StateMachine has all required properties from IStateMachine."""
        from src.state_machine import StateMachine

        sm = StateMachine()

        # Test readable properties
        assert hasattr(sm, 'state')
        assert hasattr(sm, 'collected_data')
        assert hasattr(sm, 'current_phase')
        assert hasattr(sm, 'last_action')

        # Test writable properties
        sm.state = "test_state"
        assert sm.state == "test_state"

        sm.current_phase = "situation"
        assert sm.current_phase == "situation"

        sm.last_action = "test_action"
        assert sm.last_action == "test_action"

        # Test methods
        assert callable(getattr(sm, 'update_data', None))
        assert callable(getattr(sm, 'is_final', None))

    def test_intent_tracker_has_required_methods(self):
        """Verify IntentTracker has all required methods from IIntentTracker."""
        from src.intent_tracker import IntentTracker

        tracker = IntentTracker()

        # Test properties
        assert hasattr(tracker, 'turn_number')
        assert hasattr(tracker, 'prev_intent')

        # Test methods
        assert callable(getattr(tracker, 'record', None))
        assert callable(getattr(tracker, 'objection_consecutive', None))
        assert callable(getattr(tracker, 'objection_total', None))
        assert callable(getattr(tracker, 'total_count', None))
        assert callable(getattr(tracker, 'category_total', None))

    def test_intent_tracker_record_updates_turn(self):
        """Verify advance_turn() increments turn number (decoupled from record)."""
        from src.intent_tracker import IntentTracker

        tracker = IntentTracker()
        assert tracker.turn_number == 0

        tracker.record("greeting", "greeting")
        tracker.advance_turn()
        assert tracker.turn_number == 1

        tracker.record("info_provided", "spin_situation")
        tracker.advance_turn()
        assert tracker.turn_number == 2

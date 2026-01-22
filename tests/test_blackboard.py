# tests/test_blackboard.py

"""
Tests for DialogueBlackboard class.

Tests cover:
- begin_turn initialization
- Context snapshot management
- Proposal layer (actions and transitions)
- Decision layer (commit and retrieval)
- Multi-tenancy support
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.models import Proposal, ResolvedDecision, ContextSnapshot
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.protocols import TenantConfig, DEFAULT_TENANT


class TestDialogueBlackboard:
    """Test suite for DialogueBlackboard class."""

    @pytest.fixture
    def mock_state_machine(self):
        """Create a mock state machine."""
        sm = Mock()
        sm.state = "spin_situation"
        sm.collected_data = {"company_size": "50"}
        # Create intent_tracker mock (StateMachine uses 'intent_tracker' without underscore)
        tracker = Mock()
        tracker.turn_number = 5
        tracker.prev_intent = "greeting"
        tracker.objection_consecutive.return_value = 0
        tracker.objection_total.return_value = 0
        sm.intent_tracker = tracker
        # Also set _intent_tracker for backward compatibility
        sm._intent_tracker = tracker
        return sm

    @pytest.fixture
    def mock_flow_config(self):
        """Create a mock flow config."""
        config = Mock()
        config.states = {
            "spin_situation": {
                "goal": "Understand situation",
                "phase": "situation",
                "required_data": ["company_size"],
                "transitions": {
                    "data_complete": "spin_problem",
                    "rejection": "soft_close",
                },
                "rules": {
                    "unclear": "probe_situation",
                },
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
            },
            "soft_close": {
                "goal": "Graceful exit",
                "is_final": True,
            },
        }
        config.to_dict.return_value = {
            "states": config.states,
            "persona_limits": {
                "aggressive": {"consecutive": 5, "total": 8},
                "default": {"consecutive": 3, "total": 5},
            }
        }
        return config

    @pytest.fixture
    def blackboard(self, mock_state_machine, mock_flow_config):
        """Create a blackboard instance."""
        return DialogueBlackboard(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

    # === begin_turn tests ===

    def test_begin_turn_initializes_context(self, blackboard, mock_state_machine):
        """begin_turn should create a ContextSnapshot."""
        blackboard.begin_turn(
            intent="price_question",
            extracted_data={"pain_point": "no analytics"},
            context_envelope=None,
        )

        ctx = blackboard.get_context()

        assert ctx.state == "spin_situation"
        assert ctx.current_intent == "price_question"
        assert ctx.collected_data["company_size"] == "50"
        assert ctx.collected_data["pain_point"] == "no analytics"

    def test_begin_turn_records_intent(self, blackboard, mock_state_machine):
        """begin_turn should record intent in tracker."""
        blackboard.begin_turn(
            intent="price_question",
            extracted_data={},
            context_envelope=None,
        )

        # StateMachine uses 'intent_tracker' (without underscore)
        mock_state_machine.intent_tracker.record.assert_called_once_with(
            "price_question", "spin_situation"
        )

    def test_begin_turn_clears_previous_proposals(self, blackboard):
        """begin_turn should clear previous proposals."""
        # Add some proposals
        blackboard.begin_turn("intent1", {}, None)
        blackboard.propose_action("action1", Priority.HIGH)
        blackboard.propose_transition("state1", Priority.NORMAL)

        assert len(blackboard.get_proposals()) == 2

        # Begin new turn
        blackboard.begin_turn("intent2", {}, None)

        assert len(blackboard.get_proposals()) == 0

    def test_begin_turn_merges_extracted_data(self, blackboard, mock_state_machine):
        """begin_turn should merge new data with existing."""
        mock_state_machine.collected_data = {"field1": "value1"}

        blackboard.begin_turn(
            intent="test",
            extracted_data={"field2": "value2"},
            context_envelope=None,
        )

        ctx = blackboard.get_context()
        assert ctx.collected_data["field1"] == "value1"
        assert ctx.collected_data["field2"] == "value2"

    def test_begin_turn_does_not_overwrite_with_empty(self, blackboard, mock_state_machine):
        """begin_turn should not overwrite with empty values."""
        mock_state_machine.collected_data = {"field1": "original"}

        blackboard.begin_turn(
            intent="test",
            extracted_data={"field1": "", "field2": None},
            context_envelope=None,
        )

        ctx = blackboard.get_context()
        assert ctx.collected_data["field1"] == "original"
        # field2 with None should not overwrite
        assert ctx.collected_data.get("field2") is None or "field2" not in ctx.collected_data

    # === get_context tests ===

    def test_get_context_before_begin_turn_raises(self, blackboard):
        """get_context should raise if called before begin_turn."""
        with pytest.raises(RuntimeError, match="before begin_turn"):
            blackboard.get_context()

    def test_get_context_returns_immutable_snapshot(self, blackboard):
        """get_context should return frozen dataclass."""
        blackboard.begin_turn("test", {}, None)
        ctx = blackboard.get_context()

        # ContextSnapshot is frozen, should not allow modification
        with pytest.raises(AttributeError):
            ctx.state = "new_state"

    # === propose_action tests ===

    def test_propose_action_adds_to_proposals(self, blackboard):
        """propose_action should add action proposal."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_action(
            action="answer_with_pricing",
            priority=Priority.HIGH,
            combinable=True,
            reason_code="price_question",
            source_name="TestSource",
        )

        proposals = blackboard.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].type == ProposalType.ACTION
        assert proposals[0].value == "answer_with_pricing"
        assert proposals[0].priority == Priority.HIGH
        assert proposals[0].combinable == True
        assert proposals[0].reason_code == "price_question"
        assert proposals[0].source_name == "TestSource"

    def test_propose_action_default_combinable_true(self, blackboard):
        """propose_action should default combinable to True."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_action("action", Priority.NORMAL)

        proposals = blackboard.get_action_proposals()
        assert proposals[0].combinable == True

    def test_propose_action_blocking(self, blackboard):
        """propose_action with combinable=False creates blocking action."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_action(
            action="handle_rejection",
            priority=Priority.CRITICAL,
            combinable=False,
            reason_code="rejection",
            source_name="TestSource",
        )

        proposals = blackboard.get_action_proposals()
        assert proposals[0].combinable == False

    # === propose_transition tests ===

    def test_propose_transition_adds_to_proposals(self, blackboard):
        """propose_transition should add transition proposal."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_transition(
            next_state="spin_problem",
            priority=Priority.NORMAL,
            reason_code="data_complete",
            source_name="TestSource",
        )

        proposals = blackboard.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].type == ProposalType.TRANSITION
        assert proposals[0].value == "spin_problem"
        assert proposals[0].priority == Priority.NORMAL

    def test_propose_transition_always_combinable(self, blackboard):
        """Transitions should always be combinable."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_transition("state", Priority.HIGH)

        proposals = blackboard.get_transition_proposals()
        assert proposals[0].combinable == True

    # === get_proposals tests ===

    def test_get_proposals_returns_all(self, blackboard):
        """get_proposals should return actions and transitions."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_action("action1", Priority.HIGH)
        blackboard.propose_action("action2", Priority.LOW)
        blackboard.propose_transition("state1", Priority.NORMAL)

        all_proposals = blackboard.get_proposals()
        assert len(all_proposals) == 3

    def test_get_action_proposals_filters(self, blackboard):
        """get_action_proposals should return only actions."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_action("action1", Priority.HIGH)
        blackboard.propose_transition("state1", Priority.NORMAL)

        action_proposals = blackboard.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].type == ProposalType.ACTION

    def test_get_transition_proposals_filters(self, blackboard):
        """get_transition_proposals should return only transitions."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_action("action1", Priority.HIGH)
        blackboard.propose_transition("state1", Priority.NORMAL)

        transition_proposals = blackboard.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].type == ProposalType.TRANSITION

    # === commit_decision tests ===

    def test_commit_decision_stores_decision(self, blackboard):
        """commit_decision should store the decision."""
        blackboard.begin_turn("test", {}, None)

        decision = ResolvedDecision(
            action="answer_with_pricing",
            next_state="spin_problem",
            reason_codes=["price_question", "data_complete"],
        )

        blackboard.commit_decision(decision)

        stored = blackboard.get_decision()
        assert stored.action == "answer_with_pricing"
        assert stored.next_state == "spin_problem"
        assert "price_question" in stored.reason_codes

    def test_commit_decision_applies_data_updates(self, blackboard, mock_state_machine):
        """commit_decision should apply data updates to state machine."""
        blackboard.begin_turn("test", {}, None)

        decision = ResolvedDecision(
            action="test",
            next_state="test",
            data_updates={"new_field": "new_value"},
        )

        blackboard.commit_decision(decision)

        assert mock_state_machine.collected_data["new_field"] == "new_value"

    def test_commit_decision_applies_flags(self, blackboard, mock_state_machine):
        """commit_decision should store flags to set."""
        blackboard.begin_turn("test", {}, None)

        decision = ResolvedDecision(
            action="test",
            next_state="test",
            flags_to_set={"flag1": True, "flag2": "value"},
        )

        blackboard.commit_decision(decision)

        flags = blackboard.get_flags_to_set()
        assert flags["flag1"] == True
        assert flags["flag2"] == "value"

    # === data_updates and flags tests ===

    def test_propose_data_update(self, blackboard):
        """propose_data_update should add to data updates."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_data_update("company_name", "Acme Corp", source_name="Extractor")

        updates = blackboard.get_data_updates()
        assert updates["company_name"] == "Acme Corp"

    def test_propose_flag_set(self, blackboard):
        """propose_flag_set should add to flags."""
        blackboard.begin_turn("test", {}, None)

        blackboard.propose_flag_set("escalation_requested", True, source_name="Escalation")

        flags = blackboard.get_flags_to_set()
        assert flags["escalation_requested"] == True


class TestContextSnapshot:
    """Test suite for ContextSnapshot helper methods."""

    @pytest.fixture
    def context_snapshot(self):
        """Create a ContextSnapshot for testing."""
        mock_tracker = Mock()
        mock_tracker.prev_intent = "previous"
        mock_tracker.objection_consecutive.return_value = 2
        mock_tracker.objection_total.return_value = 5

        return ContextSnapshot(
            state="spin_situation",
            collected_data={"company_size": "50", "pain_point": ""},
            current_intent="price_question",
            intent_tracker=mock_tracker,
            context_envelope=None,
            turn_number=10,
            persona="default",
            state_config={
                "required_data": ["company_size", "industry"],
                "optional_data": ["pain_point"],
                "transitions": {
                    "data_complete": "spin_problem",
                    "rejection": "soft_close",
                },
                "phase": "situation",
            },
            flow_config={},
        )

    def test_last_intent_property(self, context_snapshot):
        """last_intent should return prev_intent from tracker."""
        assert context_snapshot.last_intent == "previous"

    def test_objection_consecutive_property(self, context_snapshot):
        """objection_consecutive should delegate to tracker."""
        assert context_snapshot.objection_consecutive == 2

    def test_objection_total_property(self, context_snapshot):
        """objection_total should delegate to tracker."""
        assert context_snapshot.objection_total == 5

    def test_required_data_property(self, context_snapshot):
        """required_data should return from state_config."""
        assert context_snapshot.required_data == ["company_size", "industry"]

    def test_get_missing_required_data(self, context_snapshot):
        """get_missing_required_data should return uncollected fields."""
        missing = context_snapshot.get_missing_required_data()
        assert "industry" in missing
        assert "company_size" not in missing  # Already collected

    def test_has_all_required_data_false(self, context_snapshot):
        """has_all_required_data should return False if missing."""
        assert context_snapshot.has_all_required_data() == False

    def test_has_all_required_data_true(self):
        """has_all_required_data should return True when all data collected."""
        mock_tracker = Mock()
        mock_tracker.prev_intent = None
        mock_tracker.objection_consecutive.return_value = 0
        mock_tracker.objection_total.return_value = 0

        ctx = ContextSnapshot(
            state="spin_situation",
            collected_data={"company_size": "50", "industry": "tech"},
            current_intent="test",
            intent_tracker=mock_tracker,
            context_envelope=None,
            turn_number=1,
            persona="default",
            state_config={
                "required_data": ["company_size", "industry"],
            },
            flow_config={},
        )

        assert ctx.has_all_required_data() == True

    def test_get_transition(self, context_snapshot):
        """get_transition should return target state."""
        assert context_snapshot.get_transition("data_complete") == "spin_problem"
        assert context_snapshot.get_transition("rejection") == "soft_close"
        assert context_snapshot.get_transition("nonexistent") is None

    def test_current_phase_property(self, context_snapshot):
        """current_phase should return phase from state_config."""
        assert context_snapshot.current_phase == "situation"

    def test_optional_data_fields_property(self, context_snapshot):
        """optional_data_fields should return from state_config."""
        assert context_snapshot.optional_data_fields == ["pain_point"]


class TestMultiTenancy:
    """Test multi-tenancy support in DialogueBlackboard."""

    @pytest.fixture
    def mock_state_machine(self):
        """Create a mock state machine."""
        sm = Mock()
        sm.state = "greeting"
        sm.collected_data = {}
        sm._intent_tracker = Mock()
        sm._intent_tracker.turn_number = 1
        sm._intent_tracker.prev_intent = None
        sm._intent_tracker.objection_consecutive.return_value = 0
        sm._intent_tracker.objection_total.return_value = 0
        return sm

    @pytest.fixture
    def mock_flow_config(self):
        """Create a mock flow config."""
        config = Mock()
        config.states = {"greeting": {"goal": "Greet user"}}
        config.to_dict.return_value = {
            "states": config.states,
            "persona_limits": {
                "aggressive": {"consecutive": 5, "total": 8},
                "default": {"consecutive": 3, "total": 5},
            }
        }
        return config

    def test_default_tenant_when_not_provided(self, mock_state_machine, mock_flow_config):
        """Blackboard should use DEFAULT_TENANT when none provided."""
        bb = DialogueBlackboard(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )
        assert bb.tenant_id == "default"

    def test_custom_tenant_config(self, mock_state_machine, mock_flow_config):
        """Blackboard should use provided tenant config."""
        tenant = TenantConfig(
            tenant_id="acme_corp",
            bot_name="ACME Bot",
            tone="friendly",
        )
        bb = DialogueBlackboard(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            tenant_config=tenant,
        )
        assert bb.tenant_id == "acme_corp"
        assert bb.tenant_config.bot_name == "ACME Bot"

    def test_tenant_in_context_snapshot(self, mock_state_machine, mock_flow_config):
        """ContextSnapshot should include tenant information."""
        tenant = TenantConfig(tenant_id="test_tenant")
        bb = DialogueBlackboard(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            tenant_config=tenant,
        )
        bb.begin_turn("greeting", {})
        ctx = bb.get_context()

        assert ctx.tenant_id == "test_tenant"
        assert ctx.tenant_config is not None

    def test_tenant_persona_limit_override(self, mock_state_machine, mock_flow_config):
        """Tenant can override persona limits."""
        # Tenant with custom limits for aggressive persona
        tenant = TenantConfig(
            tenant_id="enterprise",
            persona_limits_override={
                "aggressive": {"consecutive": 10, "total": 20},
            }
        )
        bb = DialogueBlackboard(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            tenant_config=tenant,
        )
        bb.begin_turn("greeting", {})
        ctx = bb.get_context()

        # Tenant override should take precedence
        assert ctx.get_persona_limit("aggressive", "consecutive") == 10
        assert ctx.get_persona_limit("aggressive", "total") == 20

        # Non-overridden persona falls back to global
        assert ctx.get_persona_limit("default", "consecutive") == 3

    def test_tenant_feature_flags(self, mock_state_machine, mock_flow_config):
        """Tenant can have custom feature flags."""
        tenant = TenantConfig(
            tenant_id="basic_tier",
            features={
                "escalation": False,  # Disabled for this tenant
                "price_questions": True,
            }
        )
        bb = DialogueBlackboard(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            tenant_config=tenant,
        )
        bb.begin_turn("greeting", {})
        ctx = bb.get_context()

        assert ctx.is_tenant_feature_enabled("escalation") is False
        assert ctx.is_tenant_feature_enabled("price_questions") is True
        # Unknown features default to True
        assert ctx.is_tenant_feature_enabled("unknown_feature") is True


class TestBlackboardProperties:
    """Test Blackboard properties and utility methods."""

    @pytest.fixture
    def mock_state_machine(self):
        """Create a mock state machine."""
        sm = Mock()
        sm.state = "spin_situation"
        sm.collected_data = {"field1": "value1"}
        sm._intent_tracker = Mock()
        sm._intent_tracker.turn_number = 3
        sm._intent_tracker.prev_intent = "greeting"
        sm._intent_tracker.objection_consecutive.return_value = 0
        sm._intent_tracker.objection_total.return_value = 0
        return sm

    @pytest.fixture
    def mock_flow_config(self):
        """Create a mock flow config."""
        config = Mock()
        config.states = {"spin_situation": {"goal": "Test"}}
        config.to_dict.return_value = {"states": config.states}
        return config

    @pytest.fixture
    def blackboard(self, mock_state_machine, mock_flow_config):
        """Create a blackboard instance."""
        return DialogueBlackboard(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

    def test_current_intent_property(self, blackboard):
        """current_intent should return intent from current turn."""
        blackboard.begin_turn("price_question", {}, None)
        assert blackboard.current_intent == "price_question"

    def test_current_intent_before_begin_raises(self, blackboard):
        """current_intent should raise before begin_turn."""
        with pytest.raises(RuntimeError):
            _ = blackboard.current_intent

    def test_current_state_property(self, blackboard, mock_state_machine):
        """current_state should return state machine state."""
        assert blackboard.current_state == "spin_situation"

    def test_collected_data_property(self, blackboard):
        """collected_data should return context collected_data."""
        blackboard.begin_turn("test", {"field2": "value2"}, None)
        assert blackboard.collected_data["field1"] == "value1"
        assert blackboard.collected_data["field2"] == "value2"

    def test_get_turn_summary(self, blackboard):
        """get_turn_summary should return turn information."""
        blackboard.begin_turn("test", {}, None)
        blackboard.propose_action("action1", Priority.HIGH)
        blackboard.propose_transition("state1", Priority.NORMAL)

        summary = blackboard.get_turn_summary()

        assert summary["intent"] == "test"
        assert summary["state"] == "spin_situation"
        assert summary["action_proposals_count"] == 1
        assert summary["transition_proposals_count"] == 1
        assert "turn_duration_ms" in summary

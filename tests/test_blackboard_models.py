# tests/test_blackboard_models.py

"""
Tests for Blackboard Stage 2: Data Models.

These tests verify:
1. Proposal dataclass - creation, validation, __repr__
2. ResolvedDecision dataclass - creation, to_dict, to_sm_result
3. ContextSnapshot dataclass - immutability, properties, methods
"""

import pytest
from datetime import datetime
from typing import Dict, Any, Optional
from unittest.mock import Mock, MagicMock

# =============================================================================
# Test Proposal Dataclass
# =============================================================================

class TestProposal:
    """Test Proposal dataclass functionality."""

    def test_proposal_creation_basic(self):
        """Test basic Proposal creation with required fields."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="answer_question",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST_001",
        )

        assert proposal.type == ProposalType.ACTION
        assert proposal.value == "answer_question"
        assert proposal.priority == Priority.NORMAL
        assert proposal.source_name == "TestSource"
        assert proposal.reason_code == "TEST_001"
        assert proposal.combinable is True  # Default
        assert proposal.metadata == {}  # Default
        assert isinstance(proposal.created_at, datetime)

    def test_proposal_creation_with_all_fields(self):
        """Test Proposal creation with all fields."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        custom_time = datetime(2024, 1, 1, 12, 0, 0)
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="reject",
            priority=Priority.CRITICAL,
            source_name="ObjectionGuard",
            reason_code="OBJ_LIMIT",
            combinable=False,
            metadata={"consecutive": 3, "total": 5},
            created_at=custom_time,
        )

        assert proposal.combinable is False
        assert proposal.metadata == {"consecutive": 3, "total": 5}
        assert proposal.created_at == custom_time

    def test_proposal_types(self):
        """Test all proposal types can be created."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        # ACTION type
        action = Proposal(
            type=ProposalType.ACTION,
            value="handle_objection",
            priority=Priority.HIGH,
            source_name="TestSource",
            reason_code="TEST",
        )
        assert action.type == ProposalType.ACTION
        assert action.validate() == []

        # TRANSITION type
        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="next_state",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )
        assert transition.type == ProposalType.TRANSITION
        assert transition.validate() == []

    def test_proposal_validate_success(self):
        """Test that valid proposal passes validation."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST_001",
        )

        errors = proposal.validate()
        assert errors == []

    def test_proposal_validate_none_value(self):
        """Test validation catches None value."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value=None,
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = proposal.validate()
        assert "Proposal value cannot be None." in errors

    def test_proposal_validate_empty_reason_code(self):
        """Test validation catches empty reason_code."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="",
        )

        errors = proposal.validate()
        assert "Proposal must have a non-empty reason_code." in errors

        # Also test whitespace-only reason_code
        proposal2 = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="   ",
        )
        errors2 = proposal2.validate()
        assert "Proposal must have a non-empty reason_code." in errors2

    def test_proposal_validate_empty_source_name(self):
        """Test validation catches empty source_name."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="",
            reason_code="TEST",
        )

        errors = proposal.validate()
        assert "Proposal must have a non-empty source_name." in errors

    def test_proposal_validate_action_value_type(self):
        """Test validation catches non-string ACTION value."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value=123,  # Should be string
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = proposal.validate()
        assert any("ACTION value must be string" in e for e in errors)

    def test_proposal_validate_transition_value_type(self):
        """Test validation catches non-string TRANSITION value."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value={"state": "next"},  # Should be string
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = proposal.validate()
        assert any("TRANSITION value must be string" in e for e in errors)

    def test_proposal_validate_transition_combinable_false(self):
        """Test validation catches TRANSITION with combinable=False."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value="next_state",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
            combinable=False,
        )

        errors = proposal.validate()
        assert "TRANSITION proposals cannot have combinable=False" in errors

    def test_proposal_validate_multiple_errors(self):
        """Test validation can return multiple errors."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value=None,  # Error: None value
            priority=Priority.NORMAL,
            source_name="",  # Error: empty source_name
            reason_code="",  # Error: empty reason_code
        )

        errors = proposal.validate()
        assert len(errors) >= 3

    def test_proposal_repr_action(self):
        """Test __repr__ for ACTION proposal."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.HIGH,
            source_name="TestSource",
            reason_code="TEST_001",
            combinable=True,
        )

        repr_str = repr(proposal)
        assert "Proposal(ACTION" in repr_str
        assert "'answer'" in repr_str
        assert "HIGH" in repr_str
        assert "source='TestSource'" in repr_str
        assert "reason='TEST_001'" in repr_str
        assert "combinable=True" in repr_str

    def test_proposal_repr_action_non_combinable(self):
        """Test __repr__ for non-combinable ACTION proposal."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="reject",
            priority=Priority.CRITICAL,
            source_name="ObjectionGuard",
            reason_code="OBJ_LIMIT",
            combinable=False,
        )

        repr_str = repr(proposal)
        assert "combinable=False" in repr_str

    def test_proposal_repr_transition(self):
        """Test __repr__ for TRANSITION proposal (no combinable field)."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value="next_state",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        repr_str = repr(proposal)
        assert "Proposal(TRANSITION" in repr_str
        assert "combinable" not in repr_str

# =============================================================================
# Test ResolvedDecision Dataclass
# =============================================================================

class TestResolvedDecision:
    """Test ResolvedDecision dataclass functionality."""

    def test_resolved_decision_creation_basic(self):
        """Test basic ResolvedDecision creation."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="answer_question",
            next_state="spin_problem",
        )

        assert decision.action == "answer_question"
        assert decision.next_state == "spin_problem"
        assert decision.reason_codes == []
        assert decision.rejected_proposals == []
        assert decision.resolution_trace == {}
        assert decision.data_updates == {}
        assert decision.flags_to_set == {}
        # Compatibility fields defaults
        assert decision.prev_state == ""
        assert decision.goal == ""
        assert decision.collected_data == {}
        assert decision.missing_data == []
        assert decision.optional_data == []
        assert decision.is_final is False
        assert decision.spin_phase is None
        assert decision.prev_phase is None
        assert decision.circular_flow == {}
        assert decision.objection_flow == {}

    def test_resolved_decision_creation_full(self):
        """Test ResolvedDecision with all fields."""
        from src.blackboard.models import ResolvedDecision, Proposal
        from src.blackboard.enums import Priority, ProposalType

        rejected = Proposal(
            type=ProposalType.TRANSITION,
            value="other_state",
            priority=Priority.LOW,
            source_name="SomeSource",
            reason_code="REJECTED",
        )

        decision = ResolvedDecision(
            action="handle_objection",
            next_state="presentation",
            reason_codes=["OBJ_PRICE", "OBJ_HANDLE_001"],
            rejected_proposals=[rejected],
            resolution_trace={"winner": "ObjectionHandler", "strategy": "empathy"},
            data_updates={"last_objection": "price"},
            flags_to_set={"_objection_handled": True},
            prev_state="spin_need_payoff",
            goal="Обработать возражение",
            collected_data={"company_size": "small"},
            missing_data=["contact_phone"],
            optional_data=["company_name"],
            is_final=False,
            spin_phase="need_payoff",
            prev_phase="implication",
            circular_flow={"gobacks": 1},
            objection_flow={"total": 2, "consecutive": 1},
        )

        assert decision.action == "handle_objection"
        assert decision.next_state == "presentation"
        assert "OBJ_PRICE" in decision.reason_codes
        assert len(decision.rejected_proposals) == 1
        assert decision.data_updates["last_objection"] == "price"
        assert decision.prev_state == "spin_need_payoff"
        assert decision.goal == "Обработать возражение"
        assert decision.spin_phase == "need_payoff"
        assert decision.prev_phase == "implication"

    def test_resolved_decision_to_dict(self):
        """Test to_dict() method."""
        from src.blackboard.models import ResolvedDecision, Proposal
        from src.blackboard.enums import Priority, ProposalType

        rejected = Proposal(
            type=ProposalType.ACTION,
            value="other_action",
            priority=Priority.LOW,
            source_name="Other",
            reason_code="OTHER",
        )

        decision = ResolvedDecision(
            action="answer",
            next_state="next",
            reason_codes=["REASON_1", "REASON_2"],
            rejected_proposals=[rejected],
            resolution_trace={"step": "final"},
            data_updates={"key": "value"},
            flags_to_set={"flag": True},
            prev_state="prev",
            goal="Test goal",
            is_final=True,
            spin_phase="problem",
        )

        d = decision.to_dict()

        assert d["action"] == "answer"
        assert d["next_state"] == "next"
        assert d["reason_codes"] == ["REASON_1", "REASON_2"]
        assert d["rejected_proposals_count"] == 1
        assert len(d["rejected_proposals"]) == 1
        assert d["resolution_trace"] == {"step": "final"}
        assert d["data_updates"] == {"key": "value"}
        assert d["flags_to_set"] == {"flag": True}
        assert d["prev_state"] == "prev"
        assert d["goal"] == "Test goal"
        assert d["is_final"] is True
        assert d["spin_phase"] == "problem"

    def test_resolved_decision_to_sm_result(self):
        """Test to_sm_result() method for bot.py compatibility."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="collect_data",
            next_state="spin_situation",
            reason_codes=["DATA_COLLECT"],
            resolution_trace={"source": "DataCollector"},
            prev_state="greeting",
            goal="Собрать информацию о компании",
            collected_data={"industry": "IT"},
            missing_data=["company_size", "employees_count"],
            optional_data=["website"],
            is_final=False,
            spin_phase="situation",
            prev_phase=None,
            circular_flow={"gobacks": 0},
            objection_flow={"total": 0},
        )

        sm_result = decision.to_sm_result()

        # Core fields
        assert sm_result["action"] == "collect_data"
        assert sm_result["next_state"] == "spin_situation"

        # Compatibility fields
        assert sm_result["prev_state"] == "greeting"
        assert sm_result["goal"] == "Собрать информацию о компании"
        assert sm_result["collected_data"] == {"industry": "IT"}
        assert sm_result["missing_data"] == ["company_size", "employees_count"]
        assert sm_result["optional_data"] == ["website"]
        assert sm_result["is_final"] is False
        assert sm_result["spin_phase"] == "situation"
        assert sm_result["prev_phase"] is None
        assert sm_result["circular_flow"] == {"gobacks": 0}
        assert sm_result["objection_flow"] == {"total": 0}

        # New Blackboard fields
        assert sm_result["reason_codes"] == ["DATA_COLLECT"]
        assert sm_result["resolution_trace"] == {"source": "DataCollector"}
        assert sm_result["trace"] == {"source": "DataCollector"}

    def test_resolved_decision_to_sm_result_without_trace(self):
        """Test to_sm_result() without resolution_trace doesn't add trace key."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="continue",
            next_state="current",
            resolution_trace={},  # Empty trace
        )

        sm_result = decision.to_sm_result()

        # Empty trace should not add trace key
        assert "trace" not in sm_result or sm_result.get("trace") == {}

    def test_resolved_decision_repr(self):
        """Test __repr__ method."""
        from src.blackboard.models import ResolvedDecision, Proposal
        from src.blackboard.enums import Priority, ProposalType

        rejected1 = Proposal(
            type=ProposalType.ACTION,
            value="x",
            priority=Priority.LOW,
            source_name="X",
            reason_code="X",
        )
        rejected2 = Proposal(
            type=ProposalType.ACTION,
            value="y",
            priority=Priority.LOW,
            source_name="Y",
            reason_code="Y",
        )

        decision = ResolvedDecision(
            action="final_action",
            next_state="final_state",
            reason_codes=["R1", "R2"],
            rejected_proposals=[rejected1, rejected2],
        )

        repr_str = repr(decision)
        assert "ResolvedDecision" in repr_str
        assert "action='final_action'" in repr_str
        assert "next_state='final_state'" in repr_str
        assert "reasons=['R1', 'R2']" in repr_str
        assert "rejected=2" in repr_str

# =============================================================================
# Test ContextSnapshot Dataclass
# =============================================================================

class TestContextSnapshot:
    """Test ContextSnapshot dataclass functionality."""

    @pytest.fixture
    def mock_intent_tracker(self):
        """Create mock IntentTracker."""
        tracker = Mock()
        tracker.prev_intent = "agreement"
        tracker.objection_consecutive.return_value = 2
        tracker.objection_total.return_value = 5
        return tracker

    @pytest.fixture
    def mock_context_envelope(self):
        """Create mock ContextEnvelope."""
        envelope = Mock()
        envelope.to_dict.return_value = {"key": "value"}
        return envelope

    @pytest.fixture
    def sample_state_config(self):
        """Sample state configuration."""
        return {
            "goal": "Выявить проблемы клиента",
            "phase": "problem",
            "required_data": ["company_size", "industry"],
            "optional_data": ["website", "address"],
            "transitions": {
                "problem_revealed": "spin_implication",
                "data_complete": "spin_implication",
            },
            "rules": {
                "objection_price": {"action": "handle_objection"},
                "question_features": {"action": "answer_features"},
            },
        }

    @pytest.fixture
    def sample_flow_config(self):
        """Sample flow configuration."""
        return {
            "persona_limits": {
                "aggressive": {"consecutive": 2, "total": 5},
                "busy": {"consecutive": 3, "total": 7},
            },
        }

    def test_context_snapshot_creation(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test basic ContextSnapshot creation."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="spin_problem",
            collected_data={"company_size": "medium"},
            current_intent="problem_revealed",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=5,
            persona="professional",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.state == "spin_problem"
        assert snapshot.collected_data == {"company_size": "medium"}
        assert snapshot.current_intent == "problem_revealed"
        assert snapshot.turn_number == 5
        assert snapshot.persona == "professional"
        assert snapshot.tenant_id == "default"  # Default value
        assert snapshot.tenant_config is None  # Default value

    def test_context_snapshot_immutable(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test that ContextSnapshot is immutable (frozen=True)."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="spin_problem",
            collected_data={"key": "value"},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        # Attempt to modify should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError in dataclasses
            snapshot.state = "new_state"

    def test_context_snapshot_last_intent(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test last_intent property."""
        from src.blackboard.models import ContextSnapshot

        mock_intent_tracker.prev_intent = "previous_intent"

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="current",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.last_intent == "previous_intent"

    def test_context_snapshot_objection_consecutive(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test objection_consecutive property."""
        from src.blackboard.models import ContextSnapshot

        mock_intent_tracker.objection_consecutive.return_value = 3

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="objection_price",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.objection_consecutive == 3

    def test_context_snapshot_objection_total(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test objection_total property."""
        from src.blackboard.models import ContextSnapshot

        mock_intent_tracker.objection_total.return_value = 7

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.objection_total == 7

    def test_context_snapshot_required_data(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test required_data property."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.required_data == ["company_size", "industry"]

    def test_context_snapshot_optional_data_fields(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test optional_data_fields property."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.optional_data_fields == ["website", "address"]

    def test_context_snapshot_current_phase(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test current_phase property."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="spin_problem",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.current_phase == "problem"

    def test_context_snapshot_get_missing_required_data(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test get_missing_required_data method."""
        from src.blackboard.models import ContextSnapshot

        # Only company_size collected, industry is missing
        snapshot = ContextSnapshot(
            state="test",
            collected_data={"company_size": "large"},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        missing = snapshot.get_missing_required_data()
        assert "industry" in missing
        assert "company_size" not in missing

    def test_context_snapshot_get_missing_required_data_empty_value(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test get_missing_required_data treats empty values as missing."""
        from src.blackboard.models import ContextSnapshot

        # company_size has empty value
        snapshot = ContextSnapshot(
            state="test",
            collected_data={"company_size": "", "industry": "IT"},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        missing = snapshot.get_missing_required_data()
        assert "company_size" in missing  # Empty string is falsy
        assert "industry" not in missing

    def test_context_snapshot_has_all_required_data_true(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test has_all_required_data returns True when all data collected."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="test",
            collected_data={"company_size": "medium", "industry": "Finance"},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.has_all_required_data() is True

    def test_context_snapshot_has_all_required_data_false(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test has_all_required_data returns False when data missing."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="test",
            collected_data={"company_size": "medium"},  # industry missing
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.has_all_required_data() is False

    def test_context_snapshot_get_transition(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test get_transition method."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="spin_problem",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.get_transition("problem_revealed") == "spin_implication"
        assert snapshot.get_transition("data_complete") == "spin_implication"
        assert snapshot.get_transition("nonexistent") is None

    def test_context_snapshot_get_rule(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test get_rule method."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="spin_problem",
            collected_data={},
            current_intent="objection_price",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        rule = snapshot.get_rule("objection_price")
        assert rule == {"action": "handle_objection"}

        assert snapshot.get_rule("nonexistent") is None

    def test_context_snapshot_get_persona_limit_from_flow_config(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test get_persona_limit returns limit from flow_config."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="aggressive",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.get_persona_limit("aggressive", "consecutive") == 2
        assert snapshot.get_persona_limit("aggressive", "total") == 5
        assert snapshot.get_persona_limit("busy", "consecutive") == 3
        assert snapshot.get_persona_limit("nonexistent", "total") is None

    def test_context_snapshot_get_persona_limit_with_tenant_override(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test get_persona_limit with tenant config override."""
        from src.blackboard.models import ContextSnapshot
        from src.blackboard.protocols import TenantConfig

        tenant_config = TenantConfig(
            tenant_id="test_tenant",
            persona_limits_override={
                "aggressive": {"consecutive": 10, "total": 20},  # Override
            },
        )

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="aggressive",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
            tenant_id="test_tenant",
            tenant_config=tenant_config,
        )

        # Should return tenant override values
        assert snapshot.get_persona_limit("aggressive", "consecutive") == 10
        assert snapshot.get_persona_limit("aggressive", "total") == 20

        # Busy should still come from flow_config (no override)
        assert snapshot.get_persona_limit("busy", "consecutive") == 3

    def test_context_snapshot_is_tenant_feature_enabled_default(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test is_tenant_feature_enabled returns True by default."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.is_tenant_feature_enabled("any_feature") is True

    def test_context_snapshot_is_tenant_feature_enabled_with_config(
        self, mock_intent_tracker, mock_context_envelope, sample_state_config, sample_flow_config
    ):
        """Test is_tenant_feature_enabled with tenant config."""
        from src.blackboard.models import ContextSnapshot
        from src.blackboard.protocols import TenantConfig

        tenant_config = TenantConfig(
            tenant_id="test_tenant",
            features={
                "escalation": True,
                "price_questions": False,
            },
        )

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="test",
            intent_tracker=mock_intent_tracker,
            context_envelope=mock_context_envelope,
            turn_number=1,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
            tenant_id="test_tenant",
            tenant_config=tenant_config,
        )

        assert snapshot.is_tenant_feature_enabled("escalation") is True
        assert snapshot.is_tenant_feature_enabled("price_questions") is False
        # Unknown features default to True
        assert snapshot.is_tenant_feature_enabled("unknown_feature") is True

    def test_context_snapshot_with_none_context_envelope(
        self, mock_intent_tracker, sample_state_config, sample_flow_config
    ):
        """Test ContextSnapshot works with None context_envelope."""
        from src.blackboard.models import ContextSnapshot

        snapshot = ContextSnapshot(
            state="greeting",
            collected_data={},
            current_intent="greeting",
            intent_tracker=mock_intent_tracker,
            context_envelope=None,  # Can be None
            turn_number=0,
            persona="default",
            state_config=sample_state_config,
            flow_config=sample_flow_config,
        )

        assert snapshot.context_envelope is None

# =============================================================================
# Test Package Imports
# =============================================================================

class TestBlackboardModelsImports:
    """Test that models can be imported from blackboard package."""

    def test_import_proposal_from_package(self):
        """Verify Proposal can be imported from src.blackboard."""
        from src.blackboard import Proposal

        assert Proposal is not None

    def test_import_resolved_decision_from_package(self):
        """Verify ResolvedDecision can be imported from src.blackboard."""
        from src.blackboard import ResolvedDecision

        assert ResolvedDecision is not None

    def test_import_context_snapshot_from_package(self):
        """Verify ContextSnapshot can be imported from src.blackboard."""
        from src.blackboard import ContextSnapshot

        assert ContextSnapshot is not None

    def test_all_models_in_dunder_all(self):
        """Verify __all__ contains model exports."""
        import src.blackboard as bb

        assert "Proposal" in bb.__all__
        assert "ResolvedDecision" in bb.__all__
        assert "ContextSnapshot" in bb.__all__

# =============================================================================
# Criteria Verification (from Architectural Plan)
# =============================================================================

class TestStage2CriteriaVerification:
    """
    Verification tests from the plan's CRITERION OF COMPLETION for Stage 2.
    """

    def test_criterion_proposal_import(self):
        """
        Plan criterion: from src.blackboard.models import Proposal, ResolvedDecision, ContextSnapshot
        """
        from src.blackboard.models import Proposal, ResolvedDecision, ContextSnapshot

        assert Proposal is not None
        assert ResolvedDecision is not None
        assert ContextSnapshot is not None

    def test_criterion_proposal_validate_returns_empty_list(self):
        """
        Plan criterion: Proposal.validate() returns empty list for valid proposal.
        """
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        p = Proposal(
            type=ProposalType.ACTION,
            value="test_action",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST_001",
        )

        assert p.validate() == []

    def test_criterion_resolved_decision_to_sm_result(self):
        """
        Plan criterion: ResolvedDecision.to_sm_result() returns dict compatible with bot.py.
        """
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="test",
            next_state="next",
            prev_state="prev",
            goal="Test goal",
            collected_data={"key": "value"},
            missing_data=["field1"],
            is_final=False,
            spin_phase="situation",
        )

        sm_result = decision.to_sm_result()

        # Must have all fields expected by bot.py
        assert "action" in sm_result
        assert "next_state" in sm_result
        assert "prev_state" in sm_result
        assert "goal" in sm_result
        assert "collected_data" in sm_result
        assert "missing_data" in sm_result
        assert "is_final" in sm_result
        assert "spin_phase" in sm_result

    def test_criterion_context_snapshot_immutable(self):
        """
        Plan criterion: ContextSnapshot is frozen (immutable).
        """
        from src.blackboard.models import ContextSnapshot
        from dataclasses import FrozenInstanceError

        tracker = Mock()
        tracker.prev_intent = None
        tracker.objection_consecutive.return_value = 0
        tracker.objection_total.return_value = 0

        snapshot = ContextSnapshot(
            state="test",
            collected_data={},
            current_intent="test",
            intent_tracker=tracker,
            context_envelope=None,
            turn_number=1,
            persona="default",
            state_config={},
            flow_config={},
        )

        # Attempt to modify should raise error
        with pytest.raises((FrozenInstanceError, AttributeError)):
            snapshot.state = "modified"

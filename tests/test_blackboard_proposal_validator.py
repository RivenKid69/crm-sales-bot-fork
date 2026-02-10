# tests/test_blackboard_proposal_validator.py

"""
Tests for Blackboard Stage 4: ProposalValidator.

These tests verify:
1. ValidationError dataclass - creation, __repr__
2. ProposalValidator - validation of proposals before conflict resolution
3. Validation of action names, state names, reason codes
4. Strict mode behavior
5. Error and warning filtering
"""

import pytest
from datetime import datetime

from src.blackboard.models import Proposal
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.proposal_validator import ValidationError, ProposalValidator

# =============================================================================
# Test ValidationError Dataclass
# =============================================================================

class TestValidationError:
    """Test ValidationError dataclass functionality."""

    def test_validation_error_creation_basic(self):
        """Test basic ValidationError creation with required fields."""
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test_action",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST_001",
        )

        error = ValidationError(
            proposal=proposal,
            error_code="INVALID_ACTION",
            message="Unknown action: 'test_action'",
        )

        assert error.proposal == proposal
        assert error.error_code == "INVALID_ACTION"
        assert error.message == "Unknown action: 'test_action'"
        assert error.severity == "error"  # Default

    def test_validation_error_with_warning_severity(self):
        """Test ValidationError with warning severity."""
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test_action",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="UNDOCUMENTED_CODE",
        )

        error = ValidationError(
            proposal=proposal,
            error_code="UNDOCUMENTED_REASON_CODE",
            message="Undocumented reason code: 'UNDOCUMENTED_CODE'",
            severity="warning",
        )

        assert error.severity == "warning"

    def test_validation_error_repr(self):
        """Test __repr__ method."""
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        error = ValidationError(
            proposal=proposal,
            error_code="TEST_ERROR",
            message="Test message",
        )

        repr_str = repr(error)
        assert "ValidationError" in repr_str
        assert "TEST_ERROR" in repr_str
        assert "Test message" in repr_str

# =============================================================================
# Test ProposalValidator Initialization
# =============================================================================

class TestProposalValidatorInit:
    """Test ProposalValidator initialization."""

    def test_init_default(self):
        """Test default initialization."""
        validator = ProposalValidator()

        assert validator._valid_actions is None
        assert validator._valid_states is None
        assert validator._valid_reason_codes is None
        assert validator._strict_mode is False

    def test_init_with_valid_actions(self):
        """Test initialization with valid_actions set."""
        valid_actions = {"action1", "action2", "action3"}
        validator = ProposalValidator(valid_actions=valid_actions)

        assert validator._valid_actions == valid_actions

    def test_init_with_valid_states(self):
        """Test initialization with valid_states set."""
        valid_states = {"state1", "state2", "state3"}
        validator = ProposalValidator(valid_states=valid_states)

        assert validator._valid_states == valid_states

    def test_init_with_valid_reason_codes(self):
        """Test initialization with valid_reason_codes set."""
        valid_codes = {"CODE_001", "CODE_002"}
        validator = ProposalValidator(valid_reason_codes=valid_codes)

        assert validator._valid_reason_codes == valid_codes

    def test_init_strict_mode(self):
        """Test initialization with strict_mode."""
        validator = ProposalValidator(strict_mode=True)

        assert validator._strict_mode is True

    def test_init_all_parameters(self):
        """Test initialization with all parameters."""
        validator = ProposalValidator(
            valid_actions={"a1", "a2"},
            valid_states={"s1", "s2"},
            valid_reason_codes={"c1", "c2"},
            strict_mode=True,
        )

        assert validator._valid_actions == {"a1", "a2"}
        assert validator._valid_states == {"s1", "s2"}
        assert validator._valid_reason_codes == {"c1", "c2"}
        assert validator._strict_mode is True

# =============================================================================
# Test ProposalValidator.validate() - Basic Validation
# =============================================================================

class TestProposalValidatorValidate:
    """Test ProposalValidator.validate() method."""

    def test_validate_empty_list(self):
        """Test validation of empty proposal list."""
        validator = ProposalValidator()
        errors = validator.validate([])

        assert errors == []

    def test_validate_valid_proposal(self):
        """Test that valid proposal passes validation."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST_001",
        )

        errors = validator.validate([proposal])
        assert errors == []

    def test_validate_multiple_valid_proposals(self):
        """Test validation of multiple valid proposals."""
        validator = ProposalValidator()

        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="action1",
                priority=Priority.NORMAL,
                source_name="Source1",
                reason_code="CODE_001",
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="next_state",
                priority=Priority.LOW,
                source_name="Source2",
                reason_code="CODE_002",
            ),
        ]

        errors = validator.validate(proposals)
        assert errors == []

# =============================================================================
# Test ProposalValidator - Structure Validation
# =============================================================================

class TestProposalValidatorStructure:
    """Test structure validation (from Proposal.validate())."""

    def test_validate_none_value(self):
        """Test validation catches None value."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value=None,
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert len(errors) >= 1
        assert any(e.error_code == "INVALID_STRUCTURE" for e in errors)
        assert any("None" in e.message for e in errors)

    def test_validate_empty_reason_code(self):
        """Test validation catches empty reason_code."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="",
        )

        errors = validator.validate([proposal])
        assert any(e.error_code == "INVALID_STRUCTURE" for e in errors)
        assert any("reason_code" in e.message for e in errors)

    def test_validate_empty_source_name(self):
        """Test validation catches empty source_name."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert any(e.error_code == "INVALID_STRUCTURE" for e in errors)
        assert any("source_name" in e.message for e in errors)

    def test_validate_wrong_action_value_type(self):
        """Test validation catches non-string ACTION value."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value=123,  # Should be string
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert any(e.error_code == "INVALID_STRUCTURE" for e in errors)
        assert any("ACTION value must be string" in e.message for e in errors)

    def test_validate_wrong_transition_value_type(self):
        """Test validation catches non-string TRANSITION value."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value={"state": "next"},  # Should be string
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert any(e.error_code == "INVALID_STRUCTURE" for e in errors)
        assert any("TRANSITION value must be string" in e.message for e in errors)

# =============================================================================
# Test ProposalValidator - Action Name Validation
# =============================================================================

class TestProposalValidatorActions:
    """Test action name validation."""

    def test_validate_action_in_valid_set(self):
        """Test that valid action passes validation."""
        validator = ProposalValidator(
            valid_actions={"answer", "handle_objection", "reject"}
        )

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "INVALID_ACTION" for e in errors)

    def test_validate_action_not_in_valid_set_warning(self):
        """Test that unknown action produces warning in non-strict mode."""
        validator = ProposalValidator(
            valid_actions={"answer", "handle_objection", "reject"},
            strict_mode=False,
        )

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="unknown_action",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        invalid_action_errors = [e for e in errors if e.error_code == "INVALID_ACTION"]
        assert len(invalid_action_errors) == 1
        assert invalid_action_errors[0].severity == "warning"

    def test_validate_action_not_in_valid_set_error_strict(self):
        """Test that unknown action produces error in strict mode."""
        validator = ProposalValidator(
            valid_actions={"answer", "handle_objection", "reject"},
            strict_mode=True,
        )

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="unknown_action",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        invalid_action_errors = [e for e in errors if e.error_code == "INVALID_ACTION"]
        assert len(invalid_action_errors) == 1
        assert invalid_action_errors[0].severity == "error"

    def test_validate_action_skip_when_no_valid_actions(self):
        """Test that action validation is skipped when valid_actions is None."""
        validator = ProposalValidator(valid_actions=None)

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="any_action_name",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "INVALID_ACTION" for e in errors)

    def test_validate_action_only_for_action_type(self):
        """Test that action validation only applies to ACTION type."""
        validator = ProposalValidator(
            valid_actions={"answer"}
        )

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="not_an_action",  # Not in valid_actions, but it's a TRANSITION
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([transition])
        assert not any(e.error_code == "INVALID_ACTION" for e in errors)

# =============================================================================
# Test ProposalValidator - State Name Validation
# =============================================================================

class TestProposalValidatorStates:
    """Test state name validation."""

    def test_validate_state_in_valid_set(self):
        """Test that valid state passes validation."""
        validator = ProposalValidator(
            valid_states={"greeting", "spin_situation", "spin_problem", "presentation"}
        )

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value="spin_problem",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "INVALID_STATE" for e in errors)

    def test_validate_state_not_in_valid_set_error(self):
        """Test that unknown state produces error (always, not just strict)."""
        validator = ProposalValidator(
            valid_states={"greeting", "spin_situation"},
            strict_mode=False,  # Even in non-strict mode, invalid state is error
        )

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value="nonexistent_state",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        invalid_state_errors = [e for e in errors if e.error_code == "INVALID_STATE"]
        assert len(invalid_state_errors) == 1
        assert invalid_state_errors[0].severity == "error"

    def test_validate_state_skip_when_no_valid_states(self):
        """Test that state validation is skipped when valid_states is None."""
        validator = ProposalValidator(valid_states=None)

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value="any_state_name",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "INVALID_STATE" for e in errors)

    def test_validate_state_only_for_transition_type(self):
        """Test that state validation only applies to TRANSITION type."""
        validator = ProposalValidator(
            valid_states={"greeting"}
        )

        action = Proposal(
            type=ProposalType.ACTION,
            value="not_a_state",  # Not in valid_states, but it's an ACTION
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([action])
        assert not any(e.error_code == "INVALID_STATE" for e in errors)

# =============================================================================
# Test ProposalValidator - Reason Code Validation
# =============================================================================

class TestProposalValidatorReasonCodes:
    """Test reason code validation."""

    def test_validate_reason_code_in_valid_set(self):
        """Test that valid reason code passes validation."""
        validator = ProposalValidator(
            valid_reason_codes={"INTENT_001", "OBJ_PRICE", "DATA_COMPLETE"}
        )

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="INTENT_001",
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "UNDOCUMENTED_REASON_CODE" for e in errors)

    def test_validate_reason_code_not_in_valid_set_warning(self):
        """Test that undocumented reason code produces warning."""
        validator = ProposalValidator(
            valid_reason_codes={"INTENT_001", "OBJ_PRICE"}
        )

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="UNDOCUMENTED_CODE",
        )

        errors = validator.validate([proposal])
        undocumented_errors = [e for e in errors if e.error_code == "UNDOCUMENTED_REASON_CODE"]
        assert len(undocumented_errors) == 1
        assert undocumented_errors[0].severity == "warning"

    def test_validate_reason_code_skip_when_no_valid_codes(self):
        """Test that reason code validation is skipped when valid_reason_codes is None."""
        validator = ProposalValidator(valid_reason_codes=None)

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="ANY_CODE",
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "UNDOCUMENTED_REASON_CODE" for e in errors)

# =============================================================================
# Test ProposalValidator - Combinable Flag Validation
# =============================================================================

class TestProposalValidatorCombinable:
    """Test combinable flag validation."""

    def test_validate_transition_with_combinable_false_error(self):
        """Test that TRANSITION with combinable=False produces error."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value="next_state",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
            combinable=False,  # Invalid for TRANSITION
        )

        errors = validator.validate([proposal])
        # This comes from both Proposal.validate() and ProposalValidator
        combinable_errors = [e for e in errors if "combinable" in e.message.lower()]
        assert len(combinable_errors) >= 1
        assert any(e.severity == "error" for e in combinable_errors)

    def test_validate_action_with_combinable_false_valid(self):
        """Test that ACTION with combinable=False is valid."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="reject",
            priority=Priority.CRITICAL,
            source_name="TestSource",
            reason_code="TEST",
            combinable=False,  # Valid for blocking actions
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "INVALID_COMBINABLE" for e in errors)

# =============================================================================
# Test ProposalValidator - Priority Validation for Blocking Actions
# =============================================================================

class TestProposalValidatorPriority:
    """Test priority validation for blocking actions."""

    def test_validate_blocking_action_with_low_priority_warning(self):
        """Test that blocking action with LOW priority produces warning."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="block_action",
            priority=Priority.LOW,
            source_name="TestSource",
            reason_code="TEST",
            combinable=False,  # Blocking action
        )

        errors = validator.validate([proposal])
        priority_warnings = [e for e in errors if e.error_code == "BLOCKING_LOW_PRIORITY"]
        assert len(priority_warnings) == 1
        assert priority_warnings[0].severity == "warning"

    def test_validate_blocking_action_with_high_priority_valid(self):
        """Test that blocking action with HIGH priority is valid."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="reject",
            priority=Priority.CRITICAL,
            source_name="TestSource",
            reason_code="TEST",
            combinable=False,
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "BLOCKING_LOW_PRIORITY" for e in errors)

    def test_validate_combinable_action_with_low_priority_valid(self):
        """Test that combinable action with LOW priority is valid."""
        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="continue",
            priority=Priority.LOW,
            source_name="TestSource",
            reason_code="TEST",
            combinable=True,  # Not blocking
        )

        errors = validator.validate([proposal])
        assert not any(e.error_code == "BLOCKING_LOW_PRIORITY" for e in errors)

# =============================================================================
# Test ProposalValidator - Helper Methods
# =============================================================================

class TestProposalValidatorHelpers:
    """Test helper methods."""

    @pytest.fixture
    def mixed_validation_results(self):
        """Create mixed validation results with errors and warnings."""
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        return [
            ValidationError(proposal, "ERROR_1", "Error 1", severity="error"),
            ValidationError(proposal, "WARNING_1", "Warning 1", severity="warning"),
            ValidationError(proposal, "ERROR_2", "Error 2", severity="error"),
            ValidationError(proposal, "WARNING_2", "Warning 2", severity="warning"),
        ]

    def test_get_errors_only(self, mixed_validation_results):
        """Test get_errors_only filters correctly."""
        validator = ProposalValidator()
        errors_only = validator.get_errors_only(mixed_validation_results)

        assert len(errors_only) == 2
        assert all(e.severity == "error" for e in errors_only)
        assert any(e.error_code == "ERROR_1" for e in errors_only)
        assert any(e.error_code == "ERROR_2" for e in errors_only)

    def test_get_warnings_only(self, mixed_validation_results):
        """Test get_warnings_only filters correctly."""
        validator = ProposalValidator()
        warnings_only = validator.get_warnings_only(mixed_validation_results)

        assert len(warnings_only) == 2
        assert all(e.severity == "warning" for e in warnings_only)
        assert any(e.error_code == "WARNING_1" for e in warnings_only)
        assert any(e.error_code == "WARNING_2" for e in warnings_only)

    def test_has_blocking_errors_true(self, mixed_validation_results):
        """Test has_blocking_errors returns True when errors exist."""
        validator = ProposalValidator()
        assert validator.has_blocking_errors(mixed_validation_results) is True

    def test_has_blocking_errors_false_only_warnings(self):
        """Test has_blocking_errors returns False when only warnings."""
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        warnings_only = [
            ValidationError(proposal, "WARNING_1", "Warning 1", severity="warning"),
            ValidationError(proposal, "WARNING_2", "Warning 2", severity="warning"),
        ]

        validator = ProposalValidator()
        assert validator.has_blocking_errors(warnings_only) is False

    def test_has_blocking_errors_false_empty(self):
        """Test has_blocking_errors returns False for empty list."""
        validator = ProposalValidator()
        assert validator.has_blocking_errors([]) is False

# =============================================================================
# Test ProposalValidator - Complex Scenarios
# =============================================================================

class TestProposalValidatorComplexScenarios:
    """Test complex validation scenarios."""

    def test_validate_mixed_proposals(self):
        """Test validation of mixed proposal types."""
        validator = ProposalValidator(
            valid_actions={"answer", "handle_objection"},
            valid_states={"greeting", "spin_situation", "spin_problem"},
            valid_reason_codes={"INTENT_001", "DATA_COMPLETE"},
        )

        proposals = [
            # Valid action
            Proposal(
                type=ProposalType.ACTION,
                value="answer",
                priority=Priority.NORMAL,
                source_name="Source1",
                reason_code="INTENT_001",
            ),
            # Invalid action (warning)
            Proposal(
                type=ProposalType.ACTION,
                value="unknown_action",
                priority=Priority.HIGH,
                source_name="Source2",
                reason_code="INTENT_001",
            ),
            # Valid transition
            Proposal(
                type=ProposalType.TRANSITION,
                value="spin_problem",
                priority=Priority.NORMAL,
                source_name="Source3",
                reason_code="DATA_COMPLETE",
            ),
            # Invalid state (error)
            Proposal(
                type=ProposalType.TRANSITION,
                value="invalid_state",
                priority=Priority.NORMAL,
                source_name="Source4",
                reason_code="DATA_COMPLETE",
            ),
        ]

        errors = validator.validate(proposals)

        # Should have warning for unknown action
        action_warnings = [e for e in errors if e.error_code == "INVALID_ACTION"]
        assert len(action_warnings) == 1
        assert action_warnings[0].severity == "warning"

        # Should have error for invalid state
        state_errors = [e for e in errors if e.error_code == "INVALID_STATE"]
        assert len(state_errors) == 1
        assert state_errors[0].severity == "error"

    def test_validate_proposal_with_multiple_issues(self):
        """Test validation of proposal with multiple issues."""
        validator = ProposalValidator(
            valid_actions={"answer"},
            valid_reason_codes={"KNOWN_CODE"},
            strict_mode=True,
        )

        # Proposal with unknown action AND unknown reason code
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="unknown_action",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="UNKNOWN_CODE",
        )

        errors = validator.validate([proposal])

        # Should have error for invalid action (strict mode)
        assert any(e.error_code == "INVALID_ACTION" for e in errors)
        # Should have warning for undocumented reason code
        assert any(e.error_code == "UNDOCUMENTED_REASON_CODE" for e in errors)

# =============================================================================
# Test Package Imports
# =============================================================================

class TestProposalValidatorImports:
    """Test that ProposalValidator can be imported from blackboard package."""

    def test_import_validation_error_from_package(self):
        """Verify ValidationError can be imported from src.blackboard."""
        from src.blackboard import ValidationError

        assert ValidationError is not None

    def test_import_proposal_validator_from_package(self):
        """Verify ProposalValidator can be imported from src.blackboard."""
        from src.blackboard import ProposalValidator

        assert ProposalValidator is not None

    def test_all_exports_in_dunder_all(self):
        """Verify __all__ contains validator exports."""
        import src.blackboard as bb

        assert "ValidationError" in bb.__all__
        assert "ProposalValidator" in bb.__all__

# =============================================================================
# Criteria Verification (from Architectural Plan Stage 4)
# =============================================================================

class TestStage4ValidatorCriteriaVerification:
    """
    Verification tests from the plan's CRITERION OF COMPLETION for Stage 4.
    """

    def test_criterion_validator_import(self):
        """
        Plan criterion: from src.blackboard import ProposalValidator, ValidationError
        """
        from src.blackboard import ProposalValidator, ValidationError

        assert ProposalValidator is not None
        assert ValidationError is not None

    def test_criterion_validator_returns_empty_for_valid(self):
        """
        Plan criterion: Validator returns empty list for valid proposals.
        """
        from src.blackboard import ProposalValidator, Proposal, Priority, ProposalType

        validator = ProposalValidator()
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST_001",
        )

        errors = validator.validate([proposal])
        assert errors == []

    def test_criterion_validator_catches_invalid_action(self):
        """
        Plan criterion: Validator catches invalid action names.
        """
        from src.blackboard import ProposalValidator, Proposal, Priority, ProposalType

        validator = ProposalValidator(
            valid_actions={"known_action"},
            strict_mode=True,
        )

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="unknown_action",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert any(e.error_code == "INVALID_ACTION" for e in errors)

    def test_criterion_validator_catches_invalid_state(self):
        """
        Plan criterion: Validator catches invalid state names.
        """
        from src.blackboard import ProposalValidator, Proposal, Priority, ProposalType

        validator = ProposalValidator(
            valid_states={"known_state"},
        )

        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value="unknown_state",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([proposal])
        assert any(e.error_code == "INVALID_STATE" for e in errors)

    def test_criterion_has_blocking_errors_method(self):
        """
        Plan criterion: has_blocking_errors() returns True when errors exist.
        """
        from src.blackboard import ProposalValidator, ValidationError, Proposal, Priority, ProposalType

        validator = ProposalValidator()

        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        error = ValidationError(proposal, "TEST_ERROR", "Test", severity="error")
        warning = ValidationError(proposal, "TEST_WARNING", "Test", severity="warning")

        assert validator.has_blocking_errors([error]) is True
        assert validator.has_blocking_errors([warning]) is False
        assert validator.has_blocking_errors([]) is False

# =============================================================================
# Test Valid Actions SSOT (Single Source of Truth via generator.get_valid_actions)
# =============================================================================

class TestValidActionsSSOT:
    """
    Tests that generator.get_valid_actions() is the SSOT for action validity
    and that ProposalValidator correctly uses it to catch invalid actions.
    """

    def test_generator_get_valid_actions_returns_nonempty_set(self):
        """generator.get_valid_actions() returns non-empty set."""
        from unittest.mock import MagicMock
        from src.generator import ResponseGenerator

        mock_llm = MagicMock()
        gen = ResponseGenerator(mock_llm)
        actions = gen.get_valid_actions()

        assert isinstance(actions, set)
        assert len(actions) > 0

    def test_generator_valid_actions_covers_prompt_templates(self):
        """PROMPT_TEMPLATES keys are in the set."""
        from unittest.mock import MagicMock
        from src.generator import ResponseGenerator
        from src.config import PROMPT_TEMPLATES

        mock_llm = MagicMock()
        gen = ResponseGenerator(mock_llm)
        actions = gen.get_valid_actions()

        for key in PROMPT_TEMPLATES:
            assert key in actions, f"PROMPT_TEMPLATES key '{key}' missing from get_valid_actions()"

    def test_generator_valid_actions_covers_flow_templates(self):
        """FlowConfig template keys are in the set when flow is loaded."""
        from unittest.mock import MagicMock
        from src.generator import ResponseGenerator
        from src.config_loader import ConfigLoader

        mock_llm = MagicMock()
        loader = ConfigLoader()
        flow = loader.load_flow("spin_selling")
        gen = ResponseGenerator(mock_llm, flow=flow)
        actions = gen.get_valid_actions()

        if hasattr(flow, 'templates') and flow.templates:
            for key in flow.templates:
                assert key in actions, f"FlowConfig template key '{key}' missing from get_valid_actions()"

    def test_validator_with_valid_actions_catches_typo(self):
        """ProposalValidator(valid_actions=...) catches 'continu_current_goal' typo."""
        from unittest.mock import MagicMock
        from src.generator import ResponseGenerator

        mock_llm = MagicMock()
        gen = ResponseGenerator(mock_llm)
        valid_actions = gen.get_valid_actions()

        validator = ProposalValidator(
            valid_actions=valid_actions,
            strict_mode=True,
        )

        typo_proposal = Proposal(
            type=ProposalType.ACTION,
            value="continu_current_goal",  # Typo: missing 'e'
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        errors = validator.validate([typo_proposal])
        invalid_action_errors = [e for e in errors if e.error_code == "INVALID_ACTION"]
        assert len(invalid_action_errors) == 1
        assert invalid_action_errors[0].severity == "error"

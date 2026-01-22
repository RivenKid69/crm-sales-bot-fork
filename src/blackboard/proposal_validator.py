# src/blackboard/proposal_validator.py

"""
ProposalValidator for Dialogue Blackboard System.

This module provides validation of proposals before conflict resolution.
Validates proposal structure, action names, state names, and reason codes.
"""

from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass
import logging

from .models import Proposal
from .enums import Priority, ProposalType

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """
    Represents a validation error for a proposal.

    Attributes:
        proposal: The proposal that failed validation
        error_code: Machine-readable error code
        message: Human-readable error message
        severity: "error" (blocks resolution) or "warning" (logged only)
    """
    proposal: Proposal
    error_code: str
    message: str
    severity: str = "error"  # "error" or "warning"

    def __repr__(self):
        return f"ValidationError({self.error_code}: {self.message})"


class ProposalValidator:
    """
    Validates proposals before conflict resolution.

    Responsibilities:
        - Validate proposal structure (required fields, types)
        - Validate action names against allowed actions
        - Validate state names against defined states
        - Validate reason codes against documented codes
        - Log warnings for non-critical issues

    Validation is critical for:
        - Catching configuration errors early
        - Ensuring auditability (valid reason codes)
        - Preventing runtime errors in ConflictResolver
    """

    def __init__(
        self,
        valid_actions: Optional[Set[str]] = None,
        valid_states: Optional[Set[str]] = None,
        valid_reason_codes: Optional[Set[str]] = None,
        strict_mode: bool = False
    ):
        """
        Initialize the validator.

        Args:
            valid_actions: Set of valid action names. If None, action validation is skipped.
            valid_states: Set of valid state names. If None, state validation is skipped.
            valid_reason_codes: Set of documented reason codes. If None, logs warning only.
            strict_mode: If True, treat warnings as errors.
        """
        self._valid_actions = valid_actions
        self._valid_states = valid_states
        self._valid_reason_codes = valid_reason_codes
        self._strict_mode = strict_mode

    def validate(self, proposals: List[Proposal]) -> List[ValidationError]:
        """
        Validate a list of proposals.

        Args:
            proposals: List of proposals to validate

        Returns:
            List of ValidationError objects (empty if all valid)
        """
        errors: List[ValidationError] = []

        for proposal in proposals:
            errors.extend(self._validate_proposal(proposal))

        # Log validation results
        error_count = sum(1 for e in errors if e.severity == "error")
        warning_count = sum(1 for e in errors if e.severity == "warning")

        if error_count > 0:
            logger.error(f"Proposal validation failed: {error_count} errors, {warning_count} warnings")
        elif warning_count > 0:
            logger.warning(f"Proposal validation: {warning_count} warnings")
        else:
            logger.debug(f"Proposal validation passed: {len(proposals)} proposals valid")

        return errors

    def _validate_proposal(self, proposal: Proposal) -> List[ValidationError]:
        """Validate a single proposal."""
        errors: List[ValidationError] = []

        # 1. Basic structure validation (from Proposal.validate())
        structure_errors = proposal.validate()
        for error_msg in structure_errors:
            errors.append(ValidationError(
                proposal=proposal,
                error_code="INVALID_STRUCTURE",
                message=error_msg,
                severity="error"
            ))

        # 2. Validate action names
        if proposal.type == ProposalType.ACTION and self._valid_actions is not None:
            if proposal.value not in self._valid_actions:
                errors.append(ValidationError(
                    proposal=proposal,
                    error_code="INVALID_ACTION",
                    message=f"Unknown action: '{proposal.value}'. Valid actions: {sorted(self._valid_actions)[:10]}...",
                    severity="warning" if not self._strict_mode else "error"
                ))

        # 3. Validate state names
        if proposal.type == ProposalType.TRANSITION and self._valid_states is not None:
            if proposal.value not in self._valid_states:
                errors.append(ValidationError(
                    proposal=proposal,
                    error_code="INVALID_STATE",
                    message=f"Unknown state: '{proposal.value}'. Valid states: {sorted(self._valid_states)[:10]}...",
                    severity="error"  # Invalid state is always an error
                ))

        # 4. Validate reason codes
        if self._valid_reason_codes is not None:
            if proposal.reason_code not in self._valid_reason_codes:
                errors.append(ValidationError(
                    proposal=proposal,
                    error_code="UNDOCUMENTED_REASON_CODE",
                    message=f"Undocumented reason code: '{proposal.reason_code}'",
                    severity="warning"  # Undocumented is a warning, not error
                ))

        # 5. Validate combinable flag consistency
        if proposal.type == ProposalType.TRANSITION and not proposal.combinable:
            errors.append(ValidationError(
                proposal=proposal,
                error_code="INVALID_COMBINABLE",
                message="TRANSITION proposals cannot have combinable=False",
                severity="error"
            ))

        # 6. Validate priority for blocking actions
        if proposal.type == ProposalType.ACTION and not proposal.combinable:
            if proposal.priority == Priority.LOW:
                errors.append(ValidationError(
                    proposal=proposal,
                    error_code="BLOCKING_LOW_PRIORITY",
                    message="Blocking actions (combinable=False) should not have LOW priority",
                    severity="warning"
                ))

        return errors

    def get_errors_only(self, validation_results: List[ValidationError]) -> List[ValidationError]:
        """Filter to get only errors (not warnings)."""
        return [e for e in validation_results if e.severity == "error"]

    def get_warnings_only(self, validation_results: List[ValidationError]) -> List[ValidationError]:
        """Filter to get only warnings (not errors)."""
        return [e for e in validation_results if e.severity == "warning"]

    def has_blocking_errors(self, validation_results: List[ValidationError]) -> bool:
        """Check if there are any blocking errors."""
        return any(e.severity == "error" for e in validation_results)

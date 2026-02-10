"""Decision-level transition sanitization for runtime safety."""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Set


INVALID_NEXT_STATE_REASON = "invalid_next_state_sanitized"


@dataclass(frozen=True)
class SanitizedTransitionResult:
    """Outcome of transition target sanitization."""

    requested_state: Optional[str]
    effective_state: str
    is_valid: bool
    sanitized: bool
    reason_code: Optional[str]
    diagnostic: Dict[str, Any]


class DecisionSanitizer:
    """Pure sanitizer for decision/transition targets.

    The sanitizer is intentionally side-effect free. Callers are responsible
    for applying the effective state to runtime objects.
    """

    def sanitize_target(
        self,
        requested_state: Optional[str],
        current_state: str,
        valid_states: Optional[Set[str]],
        source: str,
    ) -> SanitizedTransitionResult:
        """Sanitize a single transition target."""
        if not requested_state:
            diagnostic = {
                "requested_state": requested_state,
                "effective_state": current_state,
                "source": source,
                "sanitized_reason": None,
            }
            return SanitizedTransitionResult(
                requested_state=requested_state,
                effective_state=current_state,
                is_valid=True,
                sanitized=False,
                reason_code=None,
                diagnostic=diagnostic,
            )

        if not valid_states:
            diagnostic = {
                "requested_state": requested_state,
                "effective_state": requested_state,
                "source": source,
                "sanitized_reason": None,
            }
            return SanitizedTransitionResult(
                requested_state=requested_state,
                effective_state=requested_state,
                is_valid=True,
                sanitized=False,
                reason_code=None,
                diagnostic=diagnostic,
            )

        is_valid = requested_state in valid_states
        effective_state = requested_state if is_valid else current_state
        sanitized = not is_valid
        sanitized_reason = INVALID_NEXT_STATE_REASON if sanitized else None

        diagnostic = {
            "requested_state": requested_state,
            "effective_state": effective_state,
            "source": source,
            "sanitized_reason": sanitized_reason,
        }

        return SanitizedTransitionResult(
            requested_state=requested_state,
            effective_state=effective_state,
            is_valid=is_valid,
            sanitized=sanitized,
            reason_code=sanitized_reason,
            diagnostic=diagnostic,
        )

    def sanitize_decision(
        self,
        decision: Any,
        current_state: str,
        valid_states: Optional[Set[str]],
        source: str,
    ) -> SanitizedTransitionResult:
        """Sanitize decision.next_state without mutating the decision object."""
        requested_state = getattr(decision, "next_state", None)
        return self.sanitize_target(
            requested_state=requested_state,
            current_state=current_state,
            valid_states=valid_states,
            source=source,
        )

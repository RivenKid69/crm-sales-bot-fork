# src/blackboard/knowledge_source.py

"""
Knowledge Source Base Class for Dialogue Blackboard System.

Knowledge Sources are independent modules that contribute proposals
to the Blackboard. Each source has a specific responsibility and
should not know about other sources.
"""

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class KnowledgeSource(ABC):
    """
    Abstract base class for Knowledge Sources.

    Knowledge Sources are independent modules that contribute proposals
    to the Blackboard. Each source has a specific responsibility and
    should not know about other sources.

    Lifecycle:
        1. should_contribute(bb) - Quick check if source should run
        2. contribute(bb) - Make proposals to the blackboard

    Guidelines for implementing Knowledge Sources:
        - Single Responsibility: Each source should have ONE clear purpose
        - No Side Effects: Sources should only propose, never modify state directly
        - Idempotent: Multiple calls with same context should produce same proposals
        - Fast: should_contribute() must be O(1), contribute() should be efficient
    """

    def __init__(self, name: Optional[str] = None):
        """
        Initialize the knowledge source.

        Args:
            name: Optional name for the source (defaults to class name)
        """
        self._name = name or self.__class__.__name__
        self._enabled = True

    @property
    def name(self) -> str:
        """Get the source name."""
        return self._name

    @property
    def enabled(self) -> bool:
        """Check if source is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable the source."""
        self._enabled = True

    def disable(self) -> None:
        """Disable the source."""
        self._enabled = False

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check whether this source should contribute.

        This method is called before contribute() and should be FAST (O(1)).
        Use it to avoid expensive computation when the source is not relevant.

        Default implementation returns True (always contribute).
        Override this method for performance optimization.

        Args:
            blackboard: The dialogue blackboard

        Returns:
            True if contribute() should be called, False to skip
        """
        return self._enabled

    @abstractmethod
    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Contribute proposals to the blackboard.

        This method should:
        1. Read context from blackboard.get_context()
        2. Evaluate conditions based on context
        3. Call blackboard.propose_action() / propose_transition() as needed

        Args:
            blackboard: The dialogue blackboard to contribute to
        """
        pass

    def _log_contribution(
        self,
        action: Optional[str] = None,
        transition: Optional[str] = None,
        reason: str = ""
    ) -> None:
        """Helper to log contributions."""
        if action:
            logger.debug(f"[{self._name}] Proposing action: {action} ({reason})")
        if transition:
            logger.debug(f"[{self._name}] Proposing transition: {transition} ({reason})")
        if not action and not transition:
            logger.debug(f"[{self._name}] No proposals ({reason})")

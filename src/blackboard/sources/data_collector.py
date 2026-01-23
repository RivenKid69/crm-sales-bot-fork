# src/blackboard/sources/data_collector.py

"""
Data Collector Knowledge Source for Dialogue Blackboard System.

This source monitors data collection progress and proposes transitions
when all required data for the current state has been collected.
"""

from typing import List, Optional, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class DataCollectorSource(KnowledgeSource):
    """
    Knowledge Source for monitoring data collection progress.

    Responsibility:
        - Check if required data for current state is complete
        - Propose data_complete transition when all required data is collected
        - DOES NOT handle intent-based transitions (that's TransitionResolverSource)

    This is a critical source that ensures automatic phase progression
    when users provide required information (even in combination with other intents).

    Clear boundary with TransitionResolverSource:
        - DataCollectorSource: data_complete transitions ONLY
        - TransitionResolverSource: intent-based transitions ONLY
    """

    def __init__(self, name: str = "DataCollectorSource"):
        """
        Initialize the data collector source.

        Args:
            name: Source name for logging
        """
        super().__init__(name)

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: does current state have required_data?

        Skip if:
        - Source is disabled
        - State has no required_data defined
        - State is final

        Args:
            blackboard: The dialogue blackboard

        Returns:
            True if source should contribute, False to skip
        """
        if not self._enabled:
            return False

        ctx = blackboard.get_context()

        # Skip if state is final
        if ctx.state_config.get("is_final", False):
            return False

        # Skip if no required_data defined
        required = ctx.state_config.get("required_data", [])
        if not required:
            return False

        return True

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Check data completeness and propose transition if complete.

        Algorithm:
        1. Get required_data from state config
        2. Check each field in collected_data
        3. If all required fields present -> propose data_complete transition

        NOTE: Eventual Consistency by Design
        -------------------------------------
        This source reads from ctx.collected_data which is a FROZEN SNAPSHOT
        created at the beginning of the turn (blackboard.begin_turn()).

        If another source proposes DATA_UPDATE in the same turn, those updates
        are NOT visible here. This is intentional, not a bug:

        1. Snapshot Isolation: All sources see the SAME consistent view of data.
           This prevents race conditions and non-deterministic behavior.

        2. Atomic Updates: DATA_UPDATE proposals are collected during the turn
           and applied atomically in commit_decision() (blackboard.py:456-461).

        3. Next Turn Visibility: Updated data is visible in the next turn's
           snapshot. This is standard eventual consistency.

        Timeline:
          Turn N: Source A proposes DATA_UPDATE("field", value)
                  DataCollectorSource sees old snapshot (no "field")
                  → data_complete NOT triggered
          Turn N+1: New snapshot includes "field"
                    DataCollectorSource sees updated data
                    → data_complete triggered if all fields present

        This pattern (Snapshot + Deferred Apply) is similar to Event Sourcing
        and database MVCC. It ensures deterministic, reproducible behavior.

        Args:
            blackboard: The dialogue blackboard to contribute to
        """
        ctx = blackboard.get_context()

        required_fields = ctx.required_data
        collected = ctx.collected_data

        # Find missing fields
        missing_fields = self._get_missing_fields(required_fields, collected)

        if missing_fields:
            # Not all data collected yet
            self._log_contribution(
                reason=f"Missing required data: {missing_fields}"
            )
            return

        # All required data is present!
        # Check if there's a data_complete transition defined
        data_complete_target = ctx.get_transition("data_complete")

        if not data_complete_target:
            # No data_complete transition defined for this state
            self._log_contribution(
                reason="Data complete but no transition defined"
            )
            return

        # Propose the transition
        blackboard.propose_transition(
            next_state=data_complete_target,
            priority=Priority.NORMAL,
            reason_code="data_complete",
            source_name=self.name,
            metadata={
                "required_fields": required_fields,
                "collected_fields": list(collected.keys()),
            }
        )

        self._log_contribution(
            transition=data_complete_target,
            reason=f"All required data collected: {required_fields}"
        )

    def _get_missing_fields(
        self,
        required_fields: List[str],
        collected: dict
    ) -> List[str]:
        """
        Get list of missing required fields.

        A field is considered missing if:
        - Not present in collected_data
        - Value is None
        - Value is empty string
        - Value is empty list

        Args:
            required_fields: List of required field names
            collected: Collected data dictionary

        Returns:
            List of missing field names
        """
        missing = []
        for field in required_fields:
            value = collected.get(field)
            if self._is_empty_value(value):
                missing.append(field)
        return missing

    def _is_empty_value(self, value) -> bool:
        """
        Check if a value is considered empty.

        Args:
            value: The value to check

        Returns:
            True if value is empty (None, "", [], {}), False otherwise
        """
        if value is None:
            return True
        if value == "":
            return True
        if value == []:
            return True
        if value == {}:
            return True
        return False

    def get_data_status(self, blackboard: 'DialogueBlackboard') -> dict:
        """
        Get detailed data collection status.

        Utility method for debugging and logging.

        Args:
            blackboard: The dialogue blackboard

        Returns:
            Dict with status information
        """
        ctx = blackboard.get_context()
        required = ctx.required_data
        optional = ctx.optional_data_fields
        collected = ctx.collected_data

        missing_required = self._get_missing_fields(required, collected)
        missing_optional = self._get_missing_fields(optional, collected)

        return {
            "required_fields": required,
            "optional_fields": optional,
            "collected_fields": list(collected.keys()),
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "is_complete": len(missing_required) == 0,
            "completion_percentage": (
                (len(required) - len(missing_required)) / len(required) * 100
                if required else 100.0
            ),
        }

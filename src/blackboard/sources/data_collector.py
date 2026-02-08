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

        ==========================================================================
        NOT A BUG: Eventual Consistency by Design (Snapshot Isolation)
        ==========================================================================

        REPORTED CONCERN:
          "data_complete triggers on NEXT turn, not same turn when data extracted"

        WHY THIS IS CORRECT (architectural decision):

        This source reads from ctx.collected_data which is a FROZEN SNAPSHOT
        created at the beginning of the turn (blackboard.begin_turn()).

        If another source calls propose_data_update() in the same turn, those updates
        are NOT visible here. This is INTENTIONAL, not a bug:

        1. SNAPSHOT ISOLATION:
           - All sources see the SAME consistent view of data
           - Prevents race conditions and non-deterministic behavior
           - Source A cannot affect Source B's decisions mid-turn

        2. ATOMIC UPDATES:
           - Data updates are collected during the turn
           - Applied atomically by Orchestrator._apply_side_effects()
           - Either all updates apply or none (transactional semantics)

        3. NEXT TURN VISIBILITY:
           - Updated data is visible in the next turn's snapshot
           - This is standard eventual consistency (like database MVCC)

        4. WHY NOT IMMEDIATE VISIBILITY:
           - Would create ORDER DEPENDENCY between sources
           - Source execution order would affect results
           - Testing would become non-deterministic
           - Debugging would be extremely difficult

        TIMELINE EXAMPLE:
          Turn N:   User says "Мы компания Acme, проблема с CRM"
                    extracted_data = {company_name: "Acme", situation_data: "..."}
                    Snapshot created BEFORE extracted_data written
                    DataCollectorSource sees old snapshot (missing fields)
                    → data_complete NOT triggered (correct!)
                    → commit_decision() writes data to collected_data

          Turn N+1: User says anything (even "да" or "хорошо")
                    New snapshot includes company_name + situation_data
                    DataCollectorSource sees complete data
                    → data_complete triggered → transition to next phase

        ARCHITECTURAL PATTERN:
        This is similar to Event Sourcing and database MVCC (Multi-Version
        Concurrency Control). It ensures deterministic, reproducible behavior.
        Each turn is a "transaction" with consistent read snapshot.

        ALTERNATIVE CONSIDERED:
        "Apply extracted_data before creating snapshot" would:
        - Break snapshot isolation guarantees
        - Make source order matter (fragile design)
        - Cause subtle bugs when sources interact
        ==========================================================================

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

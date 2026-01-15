"""
Branch Router - маршрутизация интентов между параллельными ветками.

Отвечает за:
- Выбор активной ветки для обработки интента
- Round-robin между ветками
- Приоритизация веток по срочности/релевантности
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
import logging

from src.dag.models import (
    DAGExecutionContext,
    DAGBranch,
    BranchStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class BranchRouteResult:
    """Результат маршрутизации интента к ветке."""
    branch_id: Optional[str] = None
    state: Optional[str] = None
    reason: str = ""
    all_waiting: bool = False


class BranchRouter:
    """
    Маршрутизатор для параллельных веток.

    Отвечает за:
    - Выбор активной ветки для обработки интента
    - Round-robin между ветками
    - Приоритизация веток по срочности

    Usage:
        router = BranchRouter(dag_ctx)

        # Get next branch to process
        result = router.route_intent(intent, branch_handlers)

        if result.branch_id:
            # Process intent in this branch
            pass
    """

    def __init__(
        self,
        dag_ctx: DAGExecutionContext,
        strategy: str = "round_robin",
    ):
        """
        Initialize branch router.

        Args:
            dag_ctx: DAG execution context
            strategy: Routing strategy ("round_robin", "priority", "first_match")
        """
        self.dag_ctx = dag_ctx
        self.strategy = strategy
        self._current_branch_idx = 0
        self._branch_priorities: Dict[str, int] = {}

    @property
    def active_branches(self) -> List[DAGBranch]:
        """Get list of active branches."""
        return [
            b for b in self.dag_ctx.active_branches.values()
            if b.status == BranchStatus.ACTIVE
        ]

    def set_branch_priority(self, branch_id: str, priority: int) -> None:
        """
        Set priority for a branch (higher = more priority).

        Args:
            branch_id: Branch identifier
            priority: Priority level (higher = processed first)
        """
        self._branch_priorities[branch_id] = priority

    def route_intent(
        self,
        intent: str,
        branch_handlers: Optional[Dict[str, List[str]]] = None,
    ) -> BranchRouteResult:
        """
        Route an intent to the appropriate branch.

        Args:
            intent: Intent to route
            branch_handlers: Optional mapping of branch_id -> list of intents it handles

        Returns:
            BranchRouteResult with selected branch info
        """
        active = self.active_branches
        if not active:
            return BranchRouteResult(
                reason="no_active_branches",
                all_waiting=True,
            )

        # Strategy 1: Check if any branch explicitly handles this intent
        if branch_handlers:
            for branch_id, handled_intents in branch_handlers.items():
                if intent in handled_intents:
                    branch = self.dag_ctx.active_branches.get(branch_id)
                    if branch and branch.status == BranchStatus.ACTIVE:
                        return BranchRouteResult(
                            branch_id=branch_id,
                            state=branch.current_state,
                            reason="explicit_handler",
                        )

        # Strategy 2: Use configured strategy
        if self.strategy == "priority":
            return self._route_by_priority(active)
        elif self.strategy == "first_match":
            return self._route_first_active(active)
        else:  # round_robin (default)
            return self._route_round_robin(active)

    def _route_round_robin(self, active: List[DAGBranch]) -> BranchRouteResult:
        """Route using round-robin strategy."""
        if not active:
            return BranchRouteResult(reason="no_active_branches")

        idx = self._current_branch_idx % len(active)
        self._current_branch_idx += 1

        branch = active[idx]
        return BranchRouteResult(
            branch_id=branch.branch_id,
            state=branch.current_state,
            reason="round_robin",
        )

    def _route_by_priority(self, active: List[DAGBranch]) -> BranchRouteResult:
        """Route to highest priority branch."""
        if not active:
            return BranchRouteResult(reason="no_active_branches")

        # Sort by priority (descending)
        sorted_branches = sorted(
            active,
            key=lambda b: self._branch_priorities.get(b.branch_id, 0),
            reverse=True,
        )

        branch = sorted_branches[0]
        return BranchRouteResult(
            branch_id=branch.branch_id,
            state=branch.current_state,
            reason="priority",
        )

    def _route_first_active(self, active: List[DAGBranch]) -> BranchRouteResult:
        """Route to first active branch."""
        if not active:
            return BranchRouteResult(reason="no_active_branches")

        branch = active[0]
        return BranchRouteResult(
            branch_id=branch.branch_id,
            state=branch.current_state,
            reason="first_active",
        )

    def get_branch_state(self, branch_id: str) -> Optional[str]:
        """Get current state of a branch."""
        return self.dag_ctx.get_branch_state(branch_id)

    def update_branch_state(self, branch_id: str, new_state: str) -> bool:
        """Update state of a branch."""
        return self.dag_ctx.update_branch_state(branch_id, new_state)

    def complete_branch(self, branch_id: str, result: Any = None) -> bool:
        """Mark a branch as completed."""
        return self.dag_ctx.complete_branch(branch_id, result)

    def get_pending_branches(self) -> List[str]:
        """Get list of branches still waiting for completion."""
        return [
            b.branch_id
            for b in self.dag_ctx.active_branches.values()
            if b.status == BranchStatus.ACTIVE
        ]

    def get_completed_branches(self) -> List[str]:
        """Get list of completed branches."""
        return [
            b.branch_id
            for b in self.dag_ctx.active_branches.values()
            if b.status == BranchStatus.COMPLETED
        ] + [
            b.branch_id
            for b in self.dag_ctx.completed_branches.values()
            if b.status == BranchStatus.COMPLETED
        ]

    def all_branches_complete(self) -> bool:
        """Check if all branches are complete."""
        return self.dag_ctx.all_branches_complete

    def broadcast_intent(
        self,
        intent: str,
        handler_callback,
    ) -> Dict[str, Any]:
        """
        Broadcast an intent to all active branches.

        Useful for intents that should be processed by all branches
        (e.g., "cancel", "reset").

        Args:
            intent: Intent to broadcast
            handler_callback: Function(branch_id, state, intent) -> result

        Returns:
            Dict mapping branch_id -> result
        """
        results = {}
        for branch in self.active_branches:
            try:
                result = handler_callback(
                    branch.branch_id,
                    branch.current_state,
                    intent,
                )
                results[branch.branch_id] = result
            except Exception as e:
                logger.error(
                    f"Error broadcasting intent to branch {branch.branch_id}: {e}"
                )
                results[branch.branch_id] = {"error": str(e)}

        return results


class IntentBranchMapping:
    """
    Mapping of intents to branches.

    Defines which intents should be handled by which branches,
    allowing for explicit routing without round-robin.
    """

    def __init__(self):
        self._mapping: Dict[str, Set[str]] = {}  # intent -> set of branch_ids
        self._branch_intents: Dict[str, Set[str]] = {}  # branch_id -> set of intents

    def register(self, branch_id: str, intents: List[str]) -> None:
        """
        Register intents for a branch.

        Args:
            branch_id: Branch identifier
            intents: List of intents this branch handles
        """
        if branch_id not in self._branch_intents:
            self._branch_intents[branch_id] = set()

        for intent in intents:
            self._branch_intents[branch_id].add(intent)

            if intent not in self._mapping:
                self._mapping[intent] = set()
            self._mapping[intent].add(branch_id)

    def get_branches_for_intent(self, intent: str) -> List[str]:
        """Get branches that handle an intent."""
        return list(self._mapping.get(intent, set()))

    def get_intents_for_branch(self, branch_id: str) -> List[str]:
        """Get intents handled by a branch."""
        return list(self._branch_intents.get(branch_id, set()))

    def to_dict(self) -> Dict[str, List[str]]:
        """Convert to dict format for BranchRouter."""
        return {
            branch_id: list(intents)
            for branch_id, intents in self._branch_intents.items()
        }

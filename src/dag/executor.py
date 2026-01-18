"""
DAG Executor - выполнение DAG узлов.

Отвечает за:
- Обработку CHOICE nodes (условное ветвление XOR)
- Управление FORK/JOIN (параллельные ветки)
- Координацию PARALLEL regions
- Event sourcing для отладки и replay
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
import logging

from src.dag.models import (
    NodeType,
    BranchStatus,
    JoinCondition,
    DAGBranch,
    DAGEvent,
    DAGExecutionContext,
    DAGNodeConfig,
)

if TYPE_CHECKING:
    from src.config_loader import FlowConfig
    from src.conditions.state_machine.context import EvaluatorContext
    from src.conditions.state_machine.registry import ConditionRegistry

logger = logging.getLogger(__name__)


@dataclass
class DAGExecutionResult:
    """
    Результат выполнения DAG узла.

    Attributes:
        is_dag: Был ли это DAG узел (False = обычный simple state)
        action: Действие для выполнения
        primary_state: Основное состояние после обработки
        next_states: Список следующих состояний (для fork)
        active_branches: Список активных веток
        aggregated_data: Агрегированные данные из завершённых веток
        dag_event: Событие для логирования
        should_continue: Нужно ли продолжать обработку в текущей ветке
    """
    is_dag: bool = False
    action: str = "continue"
    primary_state: str = ""
    next_states: List[str] = field(default_factory=list)
    active_branches: List[str] = field(default_factory=list)
    aggregated_data: Dict[str, Any] = field(default_factory=dict)
    dag_event: Optional[Dict[str, Any]] = None
    should_continue: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "is_dag": self.is_dag,
            "action": self.action,
            "primary_state": self.primary_state,
            "next_states": self.next_states,
            "active_branches": self.active_branches,
            "aggregated_data": self.aggregated_data,
            "dag_event": self.dag_event,
            "should_continue": self.should_continue,
        }


class DAGExecutor:
    """
    Исполнитель DAG переходов.

    Обрабатывает DAG узлы (choice, fork, join, parallel) и возвращает
    результат выполнения для интеграции со StateMachine.

    Usage:
        executor = DAGExecutor(flow_config, condition_registry)
        result = executor.execute_node(node_id, intent, ctx, dag_ctx)

        if result.is_dag:
            # Handle DAG transition
            pass
        else:
            # Regular state, use standard processing
            pass
    """

    def __init__(
        self,
        flow_config: "FlowConfig",
        condition_registry: Optional["ConditionRegistry"] = None,
    ):
        """
        Initialize DAG executor.

        Args:
            flow_config: Flow configuration with states
            condition_registry: Registry for evaluating conditions
        """
        self.flow = flow_config
        self._registry = condition_registry

    @property
    def registry(self) -> "ConditionRegistry":
        """Get condition registry (lazy import if not provided)."""
        if self._registry is None:
            from src.conditions.state_machine.registry import sm_registry
            self._registry = sm_registry
        return self._registry

    def execute_node(
        self,
        node_id: str,
        intent: str,
        ctx: "EvaluatorContext",
        dag_ctx: DAGExecutionContext,
    ) -> DAGExecutionResult:
        """
        Execute a DAG node.

        Args:
            node_id: State/node identifier
            intent: Current intent being processed
            ctx: Evaluator context with collected data
            dag_ctx: DAG execution context

        Returns:
            DAGExecutionResult with action and state info
        """
        # Check if this is a DAG node
        if not self.flow.is_dag_state(node_id):
            return DAGExecutionResult(
                is_dag=False,
                primary_state=node_id,
            )

        node = self.flow.get_dag_node(node_id)
        if not node:
            return DAGExecutionResult(
                is_dag=False,
                primary_state=node_id,
            )

        # Dispatch by node type
        handlers = {
            NodeType.CHOICE: self._execute_choice,
            NodeType.FORK: self._execute_fork,
            NodeType.JOIN: self._execute_join,
            NodeType.PARALLEL: self._execute_parallel,
        }

        handler = handlers.get(node.node_type)
        if handler:
            try:
                return handler(node, intent, ctx, dag_ctx)
            except Exception as e:
                logger.error(f"Error executing DAG node {node_id}: {e}")
                return DAGExecutionResult(
                    is_dag=True,
                    action="dag_error",
                    primary_state=node_id,
                    dag_event={
                        "type": "DAG_ERROR",
                        "node": node_id,
                        "error": str(e),
                    },
                )

        # Unknown node type - treat as simple
        return DAGExecutionResult(
            is_dag=False,
            primary_state=node_id,
        )

    def _execute_choice(
        self,
        node: DAGNodeConfig,
        intent: str,
        ctx: "EvaluatorContext",
        dag_ctx: DAGExecutionContext,
    ) -> DAGExecutionResult:
        """
        Execute CHOICE node (XOR branching).

        Evaluates conditions in order and takes the first matching path.
        If no condition matches, uses the default path.

        Args:
            node: CHOICE node configuration
            intent: Current intent
            ctx: Evaluator context
            dag_ctx: DAG context

        Returns:
            Result with chosen path
        """
        logger.debug(f"Executing CHOICE node: {node.node_id}")

        # Evaluate each choice in order
        for choice in node.choices:
            condition = choice.get("condition")
            next_state = choice.get("next")

            if not condition or not next_state:
                continue

            try:
                if self.registry.evaluate(condition, ctx):
                    logger.debug(
                        f"CHOICE {node.node_id}: condition '{condition}' matched, "
                        f"going to '{next_state}'"
                    )

                    dag_ctx.add_event(
                        DAGEvent.CHOICE_TAKEN,
                        node.node_id,
                        condition=condition,
                        next=next_state,
                        intent=intent,
                    )

                    return DAGExecutionResult(
                        is_dag=True,
                        action="choice_branch",
                        primary_state=next_state,
                        dag_event={
                            "type": DAGEvent.CHOICE_TAKEN,
                            "node": node.node_id,
                            "condition": condition,
                            "next": next_state,
                        },
                    )
            except Exception as e:
                logger.warning(
                    f"Error evaluating condition '{condition}': {e}"
                )
                continue

        # No condition matched - use default
        default_state = node.default_choice
        if default_state:
            logger.debug(
                f"CHOICE {node.node_id}: no condition matched, "
                f"using default '{default_state}'"
            )

            dag_ctx.add_event(
                DAGEvent.CHOICE_DEFAULT,
                node.node_id,
                next=default_state,
                intent=intent,
            )

            return DAGExecutionResult(
                is_dag=True,
                action="choice_default",
                primary_state=default_state,
                dag_event={
                    "type": DAGEvent.CHOICE_DEFAULT,
                    "node": node.node_id,
                    "next": default_state,
                },
            )

        # No default - error
        logger.error(f"CHOICE {node.node_id}: no condition matched and no default")
        raise ValueError(
            f"No matching choice and no default in CHOICE node '{node.node_id}'"
        )

    def _execute_fork(
        self,
        node: DAGNodeConfig,
        intent: str,
        ctx: "EvaluatorContext",
        dag_ctx: DAGExecutionContext,
    ) -> DAGExecutionResult:
        """
        Execute FORK node (parallel branching).

        Creates multiple parallel branches that can be processed independently.

        Args:
            node: FORK node configuration
            intent: Current intent
            ctx: Evaluator context
            dag_ctx: DAG context

        Returns:
            Result with created branches
        """
        logger.debug(f"Executing FORK node: {node.node_id}")

        branches = {}
        activated = []
        skipped = []

        for branch_config in node.branches:
            branch_id = branch_config.get("id")
            start_at = branch_config.get("start_at")

            if not branch_id or not start_at:
                logger.warning(f"Invalid branch config in FORK {node.node_id}")
                continue

            # Check branch condition (if any)
            condition = branch_config.get("condition")
            if condition:
                try:
                    if not self.registry.evaluate(condition, ctx):
                        logger.debug(
                            f"FORK {node.node_id}: skipping branch '{branch_id}' "
                            f"(condition '{condition}' not met)"
                        )
                        branches[branch_id] = DAGBranch(
                            branch_id=branch_id,
                            start_state=start_at,
                            status=BranchStatus.SKIPPED,
                        )
                        skipped.append(branch_id)
                        continue
                except Exception as e:
                    logger.warning(
                        f"Error evaluating branch condition '{condition}': {e}"
                    )
                    # On error, skip the branch
                    branches[branch_id] = DAGBranch(
                        branch_id=branch_id,
                        start_state=start_at,
                        status=BranchStatus.SKIPPED,
                    )
                    skipped.append(branch_id)
                    continue

            # Activate branch
            branch = DAGBranch(
                branch_id=branch_id,
                start_state=start_at,
            )
            branch.activate()
            branches[branch_id] = branch
            activated.append(branch_id)

            dag_ctx.add_event(
                DAGEvent.BRANCH_ACTIVATED,
                node.node_id,
                branch_id=branch_id,
                start_state=start_at,
            )

        # Start the fork
        dag_ctx.start_fork(node.node_id, branches)

        # Determine primary state (first active branch)
        first_active = next(
            (b for b in branches.values() if b.status == BranchStatus.ACTIVE),
            None
        )
        primary_state = (
            first_active.current_state
            if first_active
            else node.join_at or node.node_id
        )

        logger.info(
            f"FORK {node.node_id}: started with {len(activated)} active branches, "
            f"{len(skipped)} skipped"
        )

        return DAGExecutionResult(
            is_dag=True,
            action="fork_started",
            primary_state=primary_state,
            next_states=[b.start_state for b in branches.values() if b.status == BranchStatus.ACTIVE],
            active_branches=activated,
            dag_event={
                "type": DAGEvent.FORK_STARTED,
                "node": node.node_id,
                "branches": activated,
                "skipped": skipped,
                "join_at": node.join_at,
            },
        )

    def _execute_join(
        self,
        node: DAGNodeConfig,
        intent: str,
        ctx: "EvaluatorContext",
        dag_ctx: DAGExecutionContext,
    ) -> DAGExecutionResult:
        """
        Execute JOIN node (branch convergence).

        Waits for branches to complete based on join_condition,
        then aggregates results.

        Args:
            node: JOIN node configuration
            intent: Current intent
            ctx: Evaluator context
            dag_ctx: DAG context

        Returns:
            Result with join status
        """
        logger.debug(f"Executing JOIN node: {node.node_id}")

        expected = set(node.expects_branches)
        join_condition = node.join_condition

        # Count completed branches
        completed = set()
        for b_id in expected:
            branch = dag_ctx.get_branch(b_id)
            if branch and branch.status in (BranchStatus.COMPLETED, BranchStatus.SKIPPED):
                completed.add(b_id)

        # Check join condition
        ready_to_join = self._check_join_condition(
            join_condition, completed, expected
        )

        if not ready_to_join:
            logger.debug(
                f"JOIN {node.node_id}: waiting for branches "
                f"({len(completed)}/{len(expected)} complete)"
            )

            dag_ctx.add_event(
                DAGEvent.JOIN_WAITING,
                node.node_id,
                completed=list(completed),
                expected=list(expected),
                condition=join_condition.value,
            )

            return DAGExecutionResult(
                is_dag=True,
                action="join_waiting",
                primary_state=node.node_id,
                should_continue=False,
                dag_event={
                    "type": DAGEvent.JOIN_WAITING,
                    "node": node.node_id,
                    "completed": list(completed),
                    "expected": list(expected),
                },
            )

        # Ready to join - aggregate data
        aggregated_data = {}
        for b_id in completed:
            branch = dag_ctx.get_branch(b_id)
            if branch and branch.status == BranchStatus.COMPLETED:
                aggregated_data[b_id] = branch.collected_data.copy()

        # Complete the fork
        dag_ctx.complete_fork(dag_ctx.current_fork or "")

        dag_ctx.add_event(
            DAGEvent.JOIN_COMPLETE,
            node.node_id,
            completed=list(completed),
            aggregated_keys=list(aggregated_data.keys()),
        )

        logger.info(
            f"JOIN {node.node_id}: completed with {len(completed)} branches"
        )

        # Execute on_join action if defined
        action = node.on_join_action or "join_complete"

        return DAGExecutionResult(
            is_dag=True,
            action=action,
            primary_state=node.node_id,
            aggregated_data=aggregated_data,
            dag_event={
                "type": DAGEvent.JOIN_COMPLETE,
                "node": node.node_id,
                "branches": list(completed),
            },
        )

    def _check_join_condition(
        self,
        condition: JoinCondition,
        completed: set,
        expected: set,
    ) -> bool:
        """
        Check if join condition is satisfied.

        Args:
            condition: Join condition type
            completed: Set of completed branch IDs
            expected: Set of expected branch IDs

        Returns:
            True if join should proceed
        """
        if condition == JoinCondition.ALL_COMPLETE:
            return completed >= expected

        elif condition == JoinCondition.ANY_COMPLETE:
            return len(completed & expected) > 0

        elif condition == JoinCondition.MAJORITY:
            # Use >= for "simple majority" (50%+), more intuitive for even branch counts
            # For 2 branches: 1 is majority (50%)
            # For 4 branches: 2 is majority (50%)
            return len(completed & expected) >= len(expected) / 2

        elif condition == JoinCondition.N_OF_M:
            # N_OF_M requires additional config, default to majority
            return len(completed & expected) >= len(expected) / 2

        return False

    def _execute_parallel(
        self,
        node: DAGNodeConfig,
        intent: str,
        ctx: "EvaluatorContext",
        dag_ctx: DAGExecutionContext,
    ) -> DAGExecutionResult:
        """
        Execute PARALLEL node (compound state with parallel regions).

        All regions are active simultaneously, each processing intents
        independently.

        Note: Full parallel region support is complex and may be
        implemented in a future phase.

        Args:
            node: PARALLEL node configuration
            intent: Current intent
            ctx: Evaluator context
            dag_ctx: DAG context

        Returns:
            Result for parallel state
        """
        logger.debug(f"Executing PARALLEL node: {node.node_id}")

        # For now, treat as a fork with automatic regions
        regions = node.regions
        if not regions:
            logger.warning(f"PARALLEL {node.node_id}: no regions defined")
            return DAGExecutionResult(
                is_dag=True,
                action="parallel_empty",
                primary_state=node.node_id,
            )

        # Create branches for each region
        branches = {}
        for region_id, region_config in regions.items():
            initial_state = region_config.get("initial")
            if initial_state:
                branch = DAGBranch(
                    branch_id=region_id,
                    start_state=initial_state,
                )
                branch.activate()
                branches[region_id] = branch

        dag_ctx.start_fork(f"{node.node_id}_parallel", branches)

        # Primary state is from the main region (first one)
        first_region = next(iter(regions.keys()), None)
        primary_state = (
            regions[first_region].get("initial", node.node_id)
            if first_region
            else node.node_id
        )

        return DAGExecutionResult(
            is_dag=True,
            action="parallel_started",
            primary_state=primary_state,
            active_branches=list(branches.keys()),
            dag_event={
                "type": "PARALLEL_STARTED",
                "node": node.node_id,
                "regions": list(regions.keys()),
            },
        )

    # =========================================================================
    # Branch Management Helpers
    # =========================================================================

    def complete_branch(
        self,
        branch_id: str,
        dag_ctx: DAGExecutionContext,
        result: Any = None,
    ) -> bool:
        """
        Mark a branch as completed.

        Args:
            branch_id: Branch to complete
            dag_ctx: DAG context
            result: Optional result data

        Returns:
            True if branch was completed
        """
        return dag_ctx.complete_branch(branch_id, result)

    def update_branch_state(
        self,
        branch_id: str,
        new_state: str,
        dag_ctx: DAGExecutionContext,
    ) -> bool:
        """
        Update the current state of a branch.

        Args:
            branch_id: Branch to update
            new_state: New state
            dag_ctx: DAG context

        Returns:
            True if branch was updated
        """
        return dag_ctx.update_branch_state(branch_id, new_state)

    def is_branch_complete_signal(self, state: str) -> bool:
        """
        Check if a state is a branch completion signal.

        Convention: states ending with '_complete' or '_branch_complete'
        signal that the branch should be marked as complete.

        Args:
            state: State to check

        Returns:
            True if this is a completion signal
        """
        return state in ("_complete", "_branch_complete") or state.endswith("_complete")

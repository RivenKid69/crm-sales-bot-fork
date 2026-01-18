"""
Sync Points - управление точками синхронизации параллельных веток.

Отвечает за:
- Регистрацию sync points
- Отслеживание прибытия веток в sync points
- Проверку условий синхронизации
- Callback'и при достижении синхронизации
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional, Callable, Any
from enum import Enum
import logging
import time

from src.dag.models import DAGExecutionContext, BranchStatus

logger = logging.getLogger(__name__)


class SyncStrategy(Enum):
    """Стратегии синхронизации."""
    ALL_COMPLETE = "all_complete"    # Все ветки должны завершиться
    ANY_COMPLETE = "any_complete"    # Достаточно одной
    MAJORITY = "majority"            # Больше половины
    N_OF_M = "n_of_m"               # N из M веток
    TIMEOUT = "timeout"             # По таймауту (fallback)


@dataclass
class SyncPoint:
    """
    Точка синхронизации для параллельных веток.

    Attributes:
        sync_id: Уникальный идентификатор sync point
        strategy: Стратегия синхронизации
        expected_branches: Ожидаемые ветки
        n_required: Для N_OF_M - количество требуемых веток
        timeout_ms: Таймаут в миллисекундах (0 = без таймаута)
        on_sync: Callback при достижении синхронизации
        created_at: Время создания
    """
    sync_id: str
    strategy: SyncStrategy
    expected_branches: Set[str]
    n_required: int = 0
    timeout_ms: int = 0
    on_sync: Optional[Callable] = None
    created_at: float = field(default_factory=time.time)

    def is_timed_out(self) -> bool:
        """Check if sync point has timed out."""
        if self.timeout_ms <= 0:
            return False
        elapsed = (time.time() - self.created_at) * 1000
        return elapsed > self.timeout_ms


@dataclass
class SyncResult:
    """Result of sync check."""
    is_synced: bool
    completed_branches: Set[str]
    pending_branches: Set[str]
    timed_out: bool = False
    reason: str = ""


class SyncPointManager:
    """
    Управление точками синхронизации.

    Отслеживает когда все необходимые ветки достигли sync point
    и вызывает callback'и при синхронизации.

    Usage:
        manager = SyncPointManager()

        # Register sync point
        manager.register(
            sync_id="qualification_complete",
            expected_branches=["budget", "timeline", "authority"],
            strategy=SyncStrategy.ALL_COMPLETE,
            on_sync=lambda ctx, branches: aggregate_results(ctx, branches)
        )

        # Mark branch arrival
        result = manager.arrive("qualification_complete", "budget", dag_ctx)

        if result.is_synced:
            # All branches arrived, proceed
            pass
    """

    def __init__(self):
        self.sync_points: Dict[str, SyncPoint] = {}
        self.arrived: Dict[str, Set[str]] = {}  # sync_id -> branches arrived
        self.branch_data: Dict[str, Dict[str, Any]] = {}  # sync_id -> branch_id -> data

    def register(
        self,
        sync_id: str,
        expected_branches: List[str],
        strategy: SyncStrategy = SyncStrategy.ALL_COMPLETE,
        n_required: int = 0,
        timeout_ms: int = 0,
        on_sync: Optional[Callable] = None,
    ) -> SyncPoint:
        """
        Register a sync point.

        Args:
            sync_id: Unique identifier for this sync point
            expected_branches: List of branch IDs expected to arrive
            strategy: Synchronization strategy
            n_required: For N_OF_M strategy, number of branches required
            timeout_ms: Timeout in milliseconds (0 = no timeout)
            on_sync: Callback when sync is achieved

        Returns:
            Created SyncPoint
        """
        sync_point = SyncPoint(
            sync_id=sync_id,
            strategy=strategy,
            expected_branches=set(expected_branches),
            n_required=n_required,
            timeout_ms=timeout_ms,
            on_sync=on_sync,
        )

        self.sync_points[sync_id] = sync_point
        self.arrived[sync_id] = set()
        self.branch_data[sync_id] = {}

        # Warn about MAJORITY with 2 branches (equivalent to ALL_COMPLETE)
        if strategy == SyncStrategy.MAJORITY and len(expected_branches) == 2:
            logger.warning(
                f"Sync point '{sync_id}' uses MAJORITY strategy with 2 branches. "
                f"This is equivalent to ALL_COMPLETE (requires both branches). "
                f"Consider using ALL_COMPLETE explicitly or adding more branches."
            )

        logger.debug(
            f"Registered sync point '{sync_id}' with strategy {strategy.value}, "
            f"expecting {len(expected_branches)} branches"
        )

        return sync_point

    def arrive(
        self,
        sync_id: str,
        branch_id: str,
        dag_ctx: DAGExecutionContext,
        data: Optional[Dict[str, Any]] = None,
    ) -> SyncResult:
        """
        Mark a branch as arrived at sync point.

        Args:
            sync_id: Sync point identifier
            branch_id: Branch that arrived
            dag_ctx: DAG execution context
            data: Optional data from this branch

        Returns:
            SyncResult indicating sync status
        """
        if sync_id not in self.sync_points:
            logger.warning(f"Unknown sync point: {sync_id}")
            return SyncResult(
                is_synced=False,
                completed_branches=set(),
                pending_branches=set(),
                reason="unknown_sync_point",
            )

        sync_point = self.sync_points[sync_id]

        # Store branch data
        if data:
            self.branch_data[sync_id][branch_id] = data

        # Mark arrival
        self.arrived[sync_id].add(branch_id)

        logger.debug(
            f"Branch '{branch_id}' arrived at sync point '{sync_id}' "
            f"({len(self.arrived[sync_id])}/{len(sync_point.expected_branches)})"
        )

        # Check if synced
        result = self._check_sync(sync_point, dag_ctx)

        if result.is_synced:
            # Execute callback if defined
            if sync_point.on_sync:
                try:
                    sync_point.on_sync(dag_ctx, self.arrived[sync_id])
                except Exception as e:
                    logger.error(f"Error in sync callback for '{sync_id}': {e}")

            logger.info(f"Sync point '{sync_id}' completed")

        return result

    def _check_sync(
        self,
        sync_point: SyncPoint,
        dag_ctx: DAGExecutionContext,
    ) -> SyncResult:
        """Check if sync condition is met."""
        arrived = self.arrived[sync_point.sync_id]
        expected = sync_point.expected_branches

        # Check timeout
        if sync_point.is_timed_out():
            return SyncResult(
                is_synced=True,  # Proceed anyway
                completed_branches=arrived,
                pending_branches=expected - arrived,
                timed_out=True,
                reason="timeout",
            )

        # Check strategy
        is_synced = self._evaluate_strategy(
            sync_point.strategy,
            arrived,
            expected,
            sync_point.n_required,
        )

        return SyncResult(
            is_synced=is_synced,
            completed_branches=arrived,
            pending_branches=expected - arrived,
            reason=sync_point.strategy.value if is_synced else "waiting",
        )

    def _evaluate_strategy(
        self,
        strategy: SyncStrategy,
        arrived: Set[str],
        expected: Set[str],
        n_required: int,
    ) -> bool:
        """
        Evaluate sync strategy.

        Note on MAJORITY strategy:
            Uses strict > (greater than) len/2, meaning:
            - 2 branches: requires 2 (>1) - equivalent to ALL_COMPLETE
            - 3 branches: requires 2 (>1.5)
            - 4 branches: requires 3 (>2)
            This ensures a true majority (more than half, not just half).
        """
        intersection = arrived & expected

        if strategy == SyncStrategy.ALL_COMPLETE:
            return intersection >= expected

        elif strategy == SyncStrategy.ANY_COMPLETE:
            return len(intersection) > 0

        elif strategy == SyncStrategy.MAJORITY:
            # Strict majority: more than half must complete
            return len(intersection) > len(expected) / 2

        elif strategy == SyncStrategy.N_OF_M:
            return len(intersection) >= n_required

        elif strategy == SyncStrategy.TIMEOUT:
            # Always returns False, actual timeout check is separate
            return False

        return False

    def check_status(self, sync_id: str) -> Optional[SyncResult]:
        """
        Check current status of a sync point without marking arrival.

        Args:
            sync_id: Sync point identifier

        Returns:
            SyncResult or None if sync point doesn't exist
        """
        if sync_id not in self.sync_points:
            return None

        sync_point = self.sync_points[sync_id]
        arrived = self.arrived[sync_id]
        expected = sync_point.expected_branches

        is_synced = self._evaluate_strategy(
            sync_point.strategy,
            arrived,
            expected,
            sync_point.n_required,
        )

        return SyncResult(
            is_synced=is_synced,
            completed_branches=arrived.copy(),
            pending_branches=expected - arrived,
            timed_out=sync_point.is_timed_out(),
            reason=sync_point.strategy.value if is_synced else "waiting",
        )

    def get_branch_data(self, sync_id: str) -> Dict[str, Any]:
        """Get collected data from all arrived branches."""
        return self.branch_data.get(sync_id, {}).copy()

    def reset(self, sync_id: str) -> None:
        """Reset a sync point for reuse."""
        if sync_id in self.arrived:
            self.arrived[sync_id] = set()
        if sync_id in self.branch_data:
            self.branch_data[sync_id] = {}

        # Reset creation time for timeout
        if sync_id in self.sync_points:
            self.sync_points[sync_id].created_at = time.time()

        logger.debug(f"Reset sync point '{sync_id}'")

    def remove(self, sync_id: str) -> None:
        """Remove a sync point."""
        self.sync_points.pop(sync_id, None)
        self.arrived.pop(sync_id, None)
        self.branch_data.pop(sync_id, None)

        logger.debug(f"Removed sync point '{sync_id}'")

    def clear_all(self) -> None:
        """Clear all sync points."""
        self.sync_points.clear()
        self.arrived.clear()
        self.branch_data.clear()

    def get_all_pending(self) -> Dict[str, Set[str]]:
        """Get all pending branches for all sync points."""
        result = {}
        for sync_id, sync_point in self.sync_points.items():
            arrived = self.arrived.get(sync_id, set())
            pending = sync_point.expected_branches - arrived
            if pending:
                result[sync_id] = pending
        return result

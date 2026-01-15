"""
DAG State Machine Module.

Поддержка DAG (Directed Acyclic Graph) переходов для стейт-машины.

Позволяет создавать:
- Условные ветвления (CHOICE)
- Параллельные потоки (FORK/JOIN)
- Compound states (PARALLEL)
- History states для прерванных диалогов

Usage:
    from src.dag import (
        DAGExecutionContext,
        DAGBranch,
        NodeType,
        BranchStatus,
    )

    # Создать контекст выполнения
    dag_ctx = DAGExecutionContext(primary_state="greeting")

    # Начать fork
    branches = {
        "branch_a": DAGBranch("branch_a", "state_a"),
        "branch_b": DAGBranch("branch_b", "state_b"),
    }
    dag_ctx.start_fork("my_fork", branches)

    # Проверить статус
    if dag_ctx.is_dag_mode:
        print(f"Active branches: {dag_ctx.active_branch_ids}")
"""

from src.dag.models import (
    # Enums
    NodeType,
    BranchStatus,
    JoinCondition,
    HistoryType,
    # Models
    DAGBranch,
    DAGEvent,
    DAGExecutionContext,
    DAGNodeConfig,
)
from src.dag.executor import DAGExecutor, DAGExecutionResult
from src.dag.branch_router import BranchRouter, BranchRouteResult, IntentBranchMapping
from src.dag.sync_points import SyncPointManager, SyncStrategy, SyncPoint, SyncResult
from src.dag.history import HistoryManager, HistoryType, HistoryEntry, ConversationFlowTracker

__all__ = [
    # Enums
    "NodeType",
    "BranchStatus",
    "JoinCondition",
    "HistoryType",
    # Models
    "DAGBranch",
    "DAGEvent",
    "DAGExecutionContext",
    "DAGNodeConfig",
    # Executor
    "DAGExecutor",
    "DAGExecutionResult",
    # Branch Router
    "BranchRouter",
    "BranchRouteResult",
    "IntentBranchMapping",
    # Sync Points
    "SyncPointManager",
    "SyncStrategy",
    "SyncPoint",
    "SyncResult",
    # History
    "HistoryManager",
    "HistoryType",
    "HistoryEntry",
    "ConversationFlowTracker",
]

__version__ = "1.0.0"

"""
Tests for DAG State Machine.

Tests cover:
- DAG models (DAGBranch, DAGExecutionContext, DAGNodeConfig)
- DAG executor (CHOICE, FORK, JOIN)
- Branch router
- Sync points
- History manager
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from src.dag.models import (
    NodeType,
    BranchStatus,
    JoinCondition,
    HistoryType,
    DAGBranch,
    DAGEvent,
    DAGExecutionContext,
    DAGNodeConfig,
)
from src.dag.executor import DAGExecutor, DAGExecutionResult
from src.dag.branch_router import BranchRouter, BranchRouteResult, IntentBranchMapping
from src.dag.sync_points import SyncPointManager, SyncStrategy, SyncResult
from src.dag.history import HistoryManager, HistoryEntry, ConversationFlowTracker

# =============================================================================
# DAG Models Tests
# =============================================================================

class TestDAGBranch:
    """Tests for DAGBranch model."""

    def test_branch_creation(self):
        """Test basic branch creation."""
        branch = DAGBranch(
            branch_id="test_branch",
            start_state="collect_data",
        )

        assert branch.branch_id == "test_branch"
        assert branch.start_state == "collect_data"
        assert branch.status == BranchStatus.PENDING
        assert branch.current_state is None
        assert not branch.is_terminal

    def test_branch_activation(self):
        """Test branch activation."""
        branch = DAGBranch(
            branch_id="test_branch",
            start_state="collect_data",
        )

        branch.activate()

        assert branch.status == BranchStatus.ACTIVE
        assert branch.current_state == "collect_data"
        assert not branch.is_terminal

    def test_branch_completion(self):
        """Test branch completion."""
        branch = DAGBranch(
            branch_id="test_branch",
            start_state="collect_data",
        )
        branch.activate()

        branch.complete(result={"data": "collected"})

        assert branch.status == BranchStatus.COMPLETED
        assert branch.result == {"data": "collected"}
        assert branch.is_terminal
        assert branch.completed_at is not None

    def test_branch_skip(self):
        """Test branch skipping."""
        branch = DAGBranch(
            branch_id="test_branch",
            start_state="collect_data",
        )

        branch.skip()

        assert branch.status == BranchStatus.SKIPPED
        assert branch.is_terminal

    def test_branch_serialization(self):
        """Test branch serialization and deserialization."""
        branch = DAGBranch(
            branch_id="test_branch",
            start_state="collect_data",
            collected_data={"key": "value"},
        )
        branch.activate()

        data = branch.to_dict()
        restored = DAGBranch.from_dict(data)

        assert restored.branch_id == branch.branch_id
        assert restored.start_state == branch.start_state
        assert restored.status == branch.status
        assert restored.collected_data == branch.collected_data

class TestDAGExecutionContext:
    """Tests for DAGExecutionContext."""

    def test_context_creation(self):
        """Test basic context creation."""
        ctx = DAGExecutionContext(primary_state="greeting")

        assert ctx.primary_state == "greeting"
        assert not ctx.is_dag_mode
        assert ctx.all_branches_complete
        assert len(ctx.active_branches) == 0

    def test_start_fork(self):
        """Test starting a fork."""
        ctx = DAGExecutionContext(primary_state="greeting")

        branches = {
            "branch_a": DAGBranch("branch_a", "state_a"),
            "branch_b": DAGBranch("branch_b", "state_b"),
        }
        ctx.start_fork("my_fork", branches)

        assert ctx.is_dag_mode
        assert "my_fork" in ctx.fork_stack
        assert len(ctx.active_branches) == 2
        assert "branch_a" in ctx.active_branches
        assert len(ctx.events) > 0

    def test_complete_fork(self):
        """Test completing a fork."""
        ctx = DAGExecutionContext(primary_state="greeting")

        branches = {
            "branch_a": DAGBranch("branch_a", "state_a"),
            "branch_b": DAGBranch("branch_b", "state_b"),
        }
        for b in branches.values():
            b.activate()
            b.complete()

        ctx.start_fork("my_fork", branches)
        completed = ctx.complete_fork("my_fork")

        assert "my_fork" not in ctx.fork_stack
        assert len(completed) == 2

    def test_history_save_restore(self):
        """Test history save and restore."""
        ctx = DAGExecutionContext(primary_state="greeting")

        ctx.save_history("booking_flow", "collect_date", HistoryType.SHALLOW)
        state = ctx.restore_history("booking_flow", HistoryType.SHALLOW)

        assert state == "collect_date"

    def test_deep_history(self):
        """Test deep history."""
        ctx = DAGExecutionContext(primary_state="greeting")

        ctx.save_history("flow", "state_1", HistoryType.DEEP)
        ctx.save_history("flow", "state_2", HistoryType.DEEP)
        ctx.save_history("flow", "state_3", HistoryType.DEEP)

        assert len(ctx.deep_history["flow"]) == 3
        assert ctx.restore_history("flow", HistoryType.DEEP) == "state_3"

    def test_branch_data_update(self):
        """Test updating branch data."""
        ctx = DAGExecutionContext(primary_state="greeting")

        branch = DAGBranch("test", "start")
        branch.activate()
        ctx.active_branches["test"] = branch

        ctx.update_branch_data("test", {"key": "value"})

        assert ctx.active_branches["test"].collected_data == {"key": "value"}

    def test_serialization(self):
        """Test context serialization."""
        ctx = DAGExecutionContext(primary_state="greeting")
        ctx.start_fork("fork", {"b": DAGBranch("b", "s")})

        data = ctx.to_dict()
        restored = DAGExecutionContext.from_dict(data)

        assert restored.primary_state == ctx.primary_state
        assert "b" in restored.active_branches

class TestDAGNodeConfig:
    """Tests for DAGNodeConfig."""

    def test_simple_node(self):
        """Test simple node creation."""
        node = DAGNodeConfig.from_state_config(
            "greeting",
            {"goal": "Greet user", "type": "simple"},
        )

        assert node.node_id == "greeting"
        assert node.node_type == NodeType.SIMPLE
        assert not node.is_dag_node

    def test_choice_node(self):
        """Test CHOICE node creation."""
        node = DAGNodeConfig.from_state_config(
            "router",
            {
                "type": "choice",
                "goal": "Route by lead type",
                "choices": [
                    {"condition": "is_enterprise", "next": "enterprise_flow"},
                    {"condition": "is_smb", "next": "smb_flow"},
                ],
                "default": "standard_flow",
            },
        )

        assert node.node_type == NodeType.CHOICE
        assert node.is_dag_node
        assert len(node.choices) == 2
        assert node.default_choice == "standard_flow"

    def test_fork_node(self):
        """Test FORK node creation."""
        node = DAGNodeConfig.from_state_config(
            "parallel_qual",
            {
                "type": "fork",
                "goal": "Parallel qualification",
                "branches": [
                    {"id": "budget", "start_at": "collect_budget"},
                    {"id": "timeline", "start_at": "collect_timeline"},
                ],
                "join_at": "qualification_complete",
                "join_condition": "all_complete",
            },
        )

        assert node.node_type == NodeType.FORK
        assert len(node.branches) == 2
        assert node.join_at == "qualification_complete"
        assert node.join_condition == JoinCondition.ALL_COMPLETE

    def test_join_node(self):
        """Test JOIN node creation."""
        node = DAGNodeConfig.from_state_config(
            "qual_complete",
            {
                "type": "join",
                "goal": "Complete qualification",
                "expects_branches": ["budget", "timeline"],
                "on_join": {"action": "aggregate_results"},
            },
        )

        assert node.node_type == NodeType.JOIN
        assert node.expects_branches == ["budget", "timeline"]
        assert node.on_join_action == "aggregate_results"

# =============================================================================
# DAG Executor Tests
# =============================================================================

class TestDAGExecutor:
    """Tests for DAGExecutor."""

    @pytest.fixture
    def mock_flow_config(self):
        """Create mock flow config."""
        flow = MagicMock()
        flow.is_dag_state.return_value = True
        return flow

    @pytest.fixture
    def mock_ctx(self):
        """Create mock evaluator context."""
        ctx = MagicMock()
        ctx.collected_data = {}
        return ctx

    def test_execute_non_dag_node(self, mock_flow_config, mock_ctx):
        """Test execution of non-DAG node."""
        mock_flow_config.is_dag_state.return_value = False

        executor = DAGExecutor(mock_flow_config)
        dag_ctx = DAGExecutionContext(primary_state="simple_state")

        result = executor.execute_node("simple_state", "intent", mock_ctx, dag_ctx)

        assert not result.is_dag
        assert result.primary_state == "simple_state"

    def test_execute_choice_matching_condition(self, mock_flow_config, mock_ctx):
        """Test CHOICE node with matching condition."""
        choice_node = DAGNodeConfig.from_state_config(
            "router",
            {
                "type": "choice",
                "choices": [
                    {"condition": "is_enterprise", "next": "enterprise_flow"},
                ],
                "default": "standard_flow",
            },
        )
        mock_flow_config.get_dag_node.return_value = choice_node

        executor = DAGExecutor(mock_flow_config)
        # Mock registry to return True for condition
        executor._registry = MagicMock()
        executor._registry.evaluate.return_value = True

        dag_ctx = DAGExecutionContext(primary_state="router")

        result = executor.execute_node("router", "intent", mock_ctx, dag_ctx)

        assert result.is_dag
        assert result.action == "choice_branch"
        assert result.primary_state == "enterprise_flow"

    def test_execute_choice_default(self, mock_flow_config, mock_ctx):
        """Test CHOICE node using default."""
        choice_node = DAGNodeConfig.from_state_config(
            "router",
            {
                "type": "choice",
                "choices": [
                    {"condition": "is_enterprise", "next": "enterprise_flow"},
                ],
                "default": "standard_flow",
            },
        )
        mock_flow_config.get_dag_node.return_value = choice_node

        executor = DAGExecutor(mock_flow_config)
        executor._registry = MagicMock()
        executor._registry.evaluate.return_value = False  # No condition matches

        dag_ctx = DAGExecutionContext(primary_state="router")

        result = executor.execute_node("router", "intent", mock_ctx, dag_ctx)

        assert result.is_dag
        assert result.action == "choice_default"
        assert result.primary_state == "standard_flow"

    def test_execute_fork(self, mock_flow_config, mock_ctx):
        """Test FORK node execution."""
        fork_node = DAGNodeConfig.from_state_config(
            "parallel_qual",
            {
                "type": "fork",
                "branches": [
                    {"id": "budget", "start_at": "collect_budget"},
                    {"id": "timeline", "start_at": "collect_timeline"},
                ],
                "join_at": "qual_complete",
            },
        )
        mock_flow_config.get_dag_node.return_value = fork_node

        executor = DAGExecutor(mock_flow_config)
        dag_ctx = DAGExecutionContext(primary_state="parallel_qual")

        result = executor.execute_node("parallel_qual", "start", mock_ctx, dag_ctx)

        assert result.is_dag
        assert result.action == "fork_started"
        assert len(result.active_branches) == 2
        assert "budget" in result.active_branches
        assert "timeline" in result.active_branches
        assert len(dag_ctx.active_branches) == 2

    def test_execute_join_waiting(self, mock_flow_config, mock_ctx):
        """Test JOIN node waiting for branches."""
        join_node = DAGNodeConfig.from_state_config(
            "qual_complete",
            {
                "type": "join",
                "expects_branches": ["budget", "timeline"],
                "join_condition": "all_complete",
            },
        )
        mock_flow_config.get_dag_node.return_value = join_node

        executor = DAGExecutor(mock_flow_config)

        dag_ctx = DAGExecutionContext(primary_state="qual_complete")
        # Only one branch completed
        dag_ctx.active_branches["budget"] = DAGBranch("budget", "s1")
        dag_ctx.active_branches["budget"].complete()
        dag_ctx.active_branches["timeline"] = DAGBranch("timeline", "s2")
        dag_ctx.active_branches["timeline"].activate()  # Still active

        result = executor.execute_node("qual_complete", "check", mock_ctx, dag_ctx)

        assert result.is_dag
        assert result.action == "join_waiting"
        assert not result.should_continue

    def test_execute_join_complete(self, mock_flow_config, mock_ctx):
        """Test JOIN node completing."""
        join_node = DAGNodeConfig.from_state_config(
            "qual_complete",
            {
                "type": "join",
                "expects_branches": ["budget", "timeline"],
                "join_condition": "all_complete",
            },
        )
        mock_flow_config.get_dag_node.return_value = join_node

        executor = DAGExecutor(mock_flow_config)

        dag_ctx = DAGExecutionContext(primary_state="qual_complete")
        dag_ctx.fork_stack.append("parent_fork")

        # Both branches completed
        budget = DAGBranch("budget", "s1")
        budget.complete()
        budget.collected_data = {"budget": 10000}

        timeline = DAGBranch("timeline", "s2")
        timeline.complete()
        timeline.collected_data = {"timeline": "Q1"}

        dag_ctx.active_branches["budget"] = budget
        dag_ctx.active_branches["timeline"] = timeline

        result = executor.execute_node("qual_complete", "check", mock_ctx, dag_ctx)

        assert result.is_dag
        assert result.action == "join_complete"
        assert "budget" in result.aggregated_data
        assert "timeline" in result.aggregated_data

# =============================================================================
# Branch Router Tests
# =============================================================================

class TestBranchRouter:
    """Tests for BranchRouter."""

    def test_round_robin_routing(self):
        """Test round-robin branch routing."""
        dag_ctx = DAGExecutionContext(primary_state="fork")

        b1 = DAGBranch("branch_1", "state_1")
        b1.activate()
        b2 = DAGBranch("branch_2", "state_2")
        b2.activate()

        dag_ctx.active_branches["branch_1"] = b1
        dag_ctx.active_branches["branch_2"] = b2

        router = BranchRouter(dag_ctx)

        # First call
        result1 = router.route_intent("intent_1")
        # Second call
        result2 = router.route_intent("intent_2")

        assert result1.branch_id != result2.branch_id or len(router.active_branches) == 1

    def test_explicit_handler_routing(self):
        """Test routing with explicit handler mapping."""
        dag_ctx = DAGExecutionContext(primary_state="fork")

        b1 = DAGBranch("budget_branch", "collect_budget")
        b1.activate()
        dag_ctx.active_branches["budget_branch"] = b1

        router = BranchRouter(dag_ctx)

        handlers = {"budget_branch": ["budget_question", "price_inquiry"]}
        result = router.route_intent("budget_question", handlers)

        assert result.branch_id == "budget_branch"
        assert result.reason == "explicit_handler"

    def test_no_active_branches(self):
        """Test routing with no active branches."""
        dag_ctx = DAGExecutionContext(primary_state="fork")

        router = BranchRouter(dag_ctx)
        result = router.route_intent("intent")

        assert result.branch_id is None
        assert result.all_waiting

class TestIntentBranchMapping:
    """Tests for IntentBranchMapping."""

    def test_register_and_lookup(self):
        """Test registering and looking up mappings."""
        mapping = IntentBranchMapping()

        mapping.register("budget_branch", ["budget_question", "price_inquiry"])
        mapping.register("timeline_branch", ["timeline_question", "urgency"])

        assert "budget_branch" in mapping.get_branches_for_intent("budget_question")
        assert "timeline_branch" in mapping.get_branches_for_intent("timeline_question")
        assert mapping.get_branches_for_intent("unknown") == []

# =============================================================================
# Sync Points Tests
# =============================================================================

class TestSyncPointManager:
    """Tests for SyncPointManager."""

    def test_register_sync_point(self):
        """Test registering a sync point."""
        manager = SyncPointManager()

        sync_point = manager.register(
            sync_id="qual_complete",
            expected_branches=["budget", "timeline", "authority"],
            strategy=SyncStrategy.ALL_COMPLETE,
        )

        assert sync_point.sync_id == "qual_complete"
        assert len(sync_point.expected_branches) == 3

    def test_arrive_all_complete(self):
        """Test arriving with ALL_COMPLETE strategy."""
        manager = SyncPointManager()
        dag_ctx = DAGExecutionContext(primary_state="test")

        manager.register(
            sync_id="qual_complete",
            expected_branches=["budget", "timeline"],
            strategy=SyncStrategy.ALL_COMPLETE,
        )

        # First arrival - not synced
        result1 = manager.arrive("qual_complete", "budget", dag_ctx)
        assert not result1.is_synced

        # Second arrival - synced
        result2 = manager.arrive("qual_complete", "timeline", dag_ctx)
        assert result2.is_synced
        assert result2.completed_branches == {"budget", "timeline"}

    def test_arrive_any_complete(self):
        """Test arriving with ANY_COMPLETE strategy."""
        manager = SyncPointManager()
        dag_ctx = DAGExecutionContext(primary_state="test")

        manager.register(
            sync_id="first_response",
            expected_branches=["fast", "slow"],
            strategy=SyncStrategy.ANY_COMPLETE,
        )

        # First arrival - already synced
        result = manager.arrive("first_response", "fast", dag_ctx)
        assert result.is_synced

    def test_callback_execution(self):
        """Test callback execution on sync."""
        manager = SyncPointManager()
        dag_ctx = DAGExecutionContext(primary_state="test")

        callback_called = []

        def on_sync(ctx, branches):
            callback_called.append(list(branches))

        manager.register(
            sync_id="test_sync",
            expected_branches=["a"],
            strategy=SyncStrategy.ALL_COMPLETE,
            on_sync=on_sync,
        )

        manager.arrive("test_sync", "a", dag_ctx)

        assert len(callback_called) == 1
        assert "a" in callback_called[0]

# =============================================================================
# History Manager Tests
# =============================================================================

class TestHistoryManager:
    """Tests for HistoryManager."""

    def test_save_and_restore_shallow(self):
        """Test shallow history save and restore."""
        manager = HistoryManager()

        manager.save("booking_flow", "collect_date")
        state = manager.restore("booking_flow")

        assert state == "collect_date"

    def test_save_and_restore_deep(self):
        """Test deep history save and restore."""
        manager = HistoryManager()

        manager.save("flow", "state_1", HistoryType.DEEP)
        manager.save("flow", "state_2", HistoryType.DEEP)
        manager.save("flow", "state_3", HistoryType.DEEP)

        # Restore gets last state
        state = manager.restore("flow", HistoryType.DEEP)
        assert state == "state_3"

        # Pop removes from history
        state = manager.restore("flow", HistoryType.DEEP, pop=True)
        assert state == "state_3"

        # Next restore gets previous
        state = manager.restore("flow", HistoryType.DEEP)
        assert state == "state_2"

    def test_restore_with_data(self):
        """Test restoring state with data."""
        manager = HistoryManager()

        manager.save("flow", "state", data={"step": 3, "input": "test"})
        result = manager.restore_with_data("flow")

        assert result is not None
        state, data = result
        assert state == "state"
        assert data["step"] == 3

    def test_interrupted_flag(self):
        """Test interrupted flag."""
        manager = HistoryManager()

        assert not manager.is_interrupted("flow")

        manager.save("flow", "state")
        assert manager.is_interrupted("flow")

        manager.clear_interrupted("flow")
        assert not manager.is_interrupted("flow")

    def test_clear_region(self):
        """Test clearing region history."""
        manager = HistoryManager()

        manager.save("flow", "state", HistoryType.DEEP)
        manager.save("flow", "state2", HistoryType.DEEP)

        manager.clear_region("flow")

        assert not manager.has_history("flow")

class TestConversationFlowTracker:
    """Tests for ConversationFlowTracker."""

    def test_flow_interruption_and_resume(self):
        """Test interrupting and resuming a flow."""
        tracker = ConversationFlowTracker()

        # Start booking flow
        tracker.start_flow("booking", "collect_date")

        # Interrupt to ask about prices
        tracker.interrupt_flow("collect_date", data={"step": 1})

        # Resume
        result = tracker.resume_flow()

        assert result is not None
        flow_id, state, data = result
        assert flow_id == "booking"
        assert state == "collect_date"
        assert data["step"] == 1

# =============================================================================
# Integration Tests
# =============================================================================

class TestDAGIntegration:
    """Integration tests for DAG state machine."""

    def test_full_fork_join_flow(self):
        """Test complete fork -> branches -> join flow."""
        dag_ctx = DAGExecutionContext(primary_state="start")

        # Start fork
        branches = {
            "budget": DAGBranch("budget", "collect_budget"),
            "timeline": DAGBranch("timeline", "collect_timeline"),
        }
        dag_ctx.start_fork("qualification", branches)

        assert dag_ctx.is_dag_mode
        assert len(dag_ctx.active_branches) == 2

        # Process budget branch
        dag_ctx.active_branches["budget"].activate()
        dag_ctx.active_branches["budget"].collected_data["budget"] = 50000
        dag_ctx.active_branches["budget"].complete()

        # Process timeline branch
        dag_ctx.active_branches["timeline"].activate()
        dag_ctx.active_branches["timeline"].collected_data["timeline"] = "Q2"
        dag_ctx.active_branches["timeline"].complete()

        # All branches complete
        assert dag_ctx.all_branches_complete

        # Complete fork
        completed = dag_ctx.complete_fork("qualification")

        assert len(completed) == 2
        assert "qualification" not in dag_ctx.fork_stack

        # Check aggregated data
        aggregated = dag_ctx.get_aggregated_data()
        assert "budget" in aggregated
        assert aggregated["budget"]["budget"] == 50000

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

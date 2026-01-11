"""
Evaluation Trace and Trace Collector for conditional rules system.

This module provides observability into condition evaluation, allowing
debugging of "why was this action/state selected" in simulations and
during development.

Part of Phase 1: Foundation (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Resolution(str, Enum):
    """
    How a rule was resolved.

    - SIMPLE: Simple string rule, no conditions
    - CONDITION_MATCHED: A conditional rule matched
    - DEFAULT: Fell through all conditions to default
    - FALLBACK: No rule found, using fallback
    - NONE: No resolution (e.g., stayed in current state)
    """
    SIMPLE = "simple"
    CONDITION_MATCHED = "condition_matched"
    DEFAULT = "default"
    FALLBACK = "fallback"
    NONE = "none"


@dataclass
class ConditionEntry:
    """
    Record of a single condition evaluation.

    Attributes:
        condition_name: Name of the evaluated condition
        result: Boolean result of the evaluation
        relevant_fields: Fields from collected_data that were checked
        field_values: Actual values of relevant fields at evaluation time
        elapsed_ms: Time taken to evaluate the condition in milliseconds
        timestamp: When the evaluation occurred
    """
    condition_name: str
    result: bool
    relevant_fields: Set[str] = field(default_factory=set)
    field_values: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "condition": self.condition_name,
            "result": self.result,
            "relevant_fields": list(self.relevant_fields),
            "field_values": self.field_values,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "timestamp": self.timestamp.isoformat()
        }

    def to_compact_string(self) -> str:
        """Convert to compact string representation."""
        result_str = "PASS" if self.result else "FAIL"
        values_str = ""
        if self.field_values:
            values_str = f" ({', '.join(f'{k}={v}' for k, v in self.field_values.items())})"
        return f"  {self.condition_name}: {result_str}{values_str}"


@dataclass
class EvaluationTrace:
    """
    Trace of condition evaluations for a single rule resolution.

    Captures all conditions checked, which one matched (if any),
    and the final result. Used for debugging and simulation reports.

    Attributes:
        rule_name: Name of the rule being resolved (e.g., intent name)
        intent: The intent that triggered this evaluation
        state: The state where evaluation happened
        domain: Which domain this trace belongs to (e.g., "state_machine")
        entries: List of condition evaluations in order
        final_action: The final action/state selected
        resolution: How the rule was resolved
        matched_condition: Name of the condition that matched (if any)
        start_time: When evaluation started
        end_time: When evaluation completed
    """
    rule_name: str
    intent: str = ""
    state: str = ""
    domain: str = ""
    entries: List[ConditionEntry] = field(default_factory=list)
    final_action: Optional[str] = None
    resolution: Resolution = Resolution.NONE
    matched_condition: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def record(
        self,
        condition_name: str,
        result: bool,
        ctx: Any,
        relevant_fields: Set[str] = None,
        elapsed_ms: float = 0.0
    ) -> None:
        """
        Record a condition evaluation.

        Args:
            condition_name: Name of the condition
            result: Whether the condition passed
            ctx: Context used for evaluation (to extract field values)
            relevant_fields: Fields checked by this condition
            elapsed_ms: Time taken for evaluation
        """
        # Extract relevant field values from context
        field_values = {}
        fields = relevant_fields or set()
        if hasattr(ctx, 'collected_data') and fields:
            for field_name in fields:
                if field_name in ctx.collected_data:
                    field_values[field_name] = ctx.collected_data[field_name]

        entry = ConditionEntry(
            condition_name=condition_name,
            result=result,
            relevant_fields=fields,
            field_values=field_values,
            elapsed_ms=elapsed_ms
        )
        self.entries.append(entry)

    def set_result(
        self,
        final_action: str,
        resolution: Resolution,
        matched_condition: Optional[str] = None
    ) -> None:
        """
        Set the final result of rule resolution.

        Args:
            final_action: The action/state selected
            resolution: How the rule was resolved
            matched_condition: Name of the matching condition (if any)
        """
        self.final_action = final_action
        self.resolution = resolution
        self.matched_condition = matched_condition
        self.end_time = datetime.now()

    @property
    def conditions_checked(self) -> int:
        """Number of conditions that were evaluated."""
        return len(self.entries)

    @property
    def conditions_passed(self) -> int:
        """Number of conditions that passed."""
        return sum(1 for e in self.entries if e.result)

    @property
    def total_elapsed_ms(self) -> float:
        """Total time spent evaluating conditions."""
        return sum(e.elapsed_ms for e in self.entries)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert trace to dictionary representation.

        Suitable for JSON serialization and storage.
        """
        return {
            "rule_name": self.rule_name,
            "intent": self.intent,
            "state": self.state,
            "domain": self.domain,
            "resolution": self.resolution.value,
            "final_action": self.final_action,
            "matched_condition": self.matched_condition,
            "conditions_checked": self.conditions_checked,
            "conditions_passed": self.conditions_passed,
            "total_elapsed_ms": round(self.total_elapsed_ms, 3),
            "entries": [e.to_dict() for e in self.entries],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None
        }

    def to_compact_string(self) -> str:
        """
        Convert to compact string for simulation reports.

        Format:
        [RULE] rule_name -> final_action (resolution)
          condition1: PASS (field=value)
          condition2: FAIL

        Example:
        [RULE] price_question -> answer_with_facts (condition_matched)
          has_pricing_data: PASS (company_size=10)
        """
        lines = []

        # Header line
        action_str = self.final_action or "N/A"
        resolution_str = self.resolution.value
        matched_str = ""
        if self.matched_condition:
            matched_str = f" via {self.matched_condition}"

        lines.append(
            f"[RULE] {self.rule_name} -> {action_str} ({resolution_str}{matched_str})"
        )

        # Condition entries
        for entry in self.entries:
            lines.append(entry.to_compact_string())

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"EvaluationTrace(rule={self.rule_name!r}, "
            f"resolution={self.resolution.value}, "
            f"action={self.final_action!r}, "
            f"checked={self.conditions_checked})"
        )


@dataclass
class TraceSummary:
    """
    Summary statistics for a collection of traces.

    Attributes:
        total_traces: Total number of traces
        by_resolution: Count by resolution type
        by_domain: Count by domain
        total_conditions_checked: Total conditions evaluated
        total_elapsed_ms: Total time spent on evaluations
        matched_conditions: Count by matched condition name
    """
    total_traces: int = 0
    by_resolution: Dict[str, int] = field(default_factory=dict)
    by_domain: Dict[str, int] = field(default_factory=dict)
    total_conditions_checked: int = 0
    total_elapsed_ms: float = 0.0
    matched_conditions: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "total_traces": self.total_traces,
            "by_resolution": self.by_resolution,
            "by_domain": self.by_domain,
            "total_conditions_checked": self.total_conditions_checked,
            "total_elapsed_ms": round(self.total_elapsed_ms, 3),
            "avg_conditions_per_trace": (
                round(self.total_conditions_checked / self.total_traces, 2)
                if self.total_traces > 0 else 0
            ),
            "matched_conditions": self.matched_conditions
        }


class TraceCollector:
    """
    Collector for evaluation traces across a batch of simulations.

    Aggregates traces and provides summary statistics for analysis.

    Example:
        collector = TraceCollector()

        # During simulation
        trace = collector.create_trace("price_question", "price_question", "spin")
        registry.evaluate("has_pricing_data", ctx, trace)
        trace.set_result("answer_with_facts", Resolution.CONDITION_MATCHED, "has_pricing_data")

        # After simulation
        summary = collector.get_summary()
    """

    def __init__(self):
        """Initialize a new trace collector."""
        self._traces: List[EvaluationTrace] = []
        self._created_at = datetime.now()

    def create_trace(
        self,
        rule_name: str,
        intent: str = "",
        state: str = "",
        domain: str = ""
    ) -> EvaluationTrace:
        """
        Create a new trace and add it to the collection.

        Args:
            rule_name: Name of the rule being resolved
            intent: Intent that triggered evaluation
            state: Current state
            domain: Domain name (e.g., "state_machine")

        Returns:
            New EvaluationTrace instance
        """
        trace = EvaluationTrace(
            rule_name=rule_name,
            intent=intent,
            state=state,
            domain=domain
        )
        self._traces.append(trace)
        return trace

    def add_trace(self, trace: EvaluationTrace) -> None:
        """
        Add an existing trace to the collection.

        Args:
            trace: The trace to add
        """
        self._traces.append(trace)

    def get_traces(self) -> List[EvaluationTrace]:
        """Get all collected traces."""
        return list(self._traces)

    def get_traces_by_domain(self, domain: str) -> List[EvaluationTrace]:
        """Get traces filtered by domain."""
        return [t for t in self._traces if t.domain == domain]

    def get_traces_by_resolution(
        self,
        resolution: Resolution
    ) -> List[EvaluationTrace]:
        """Get traces filtered by resolution type."""
        return [t for t in self._traces if t.resolution == resolution]

    def get_summary(self) -> TraceSummary:
        """
        Get summary statistics for all traces.

        Returns:
            TraceSummary with aggregated statistics
        """
        summary = TraceSummary(total_traces=len(self._traces))

        for trace in self._traces:
            # Count by resolution
            res_key = trace.resolution.value
            summary.by_resolution[res_key] = (
                summary.by_resolution.get(res_key, 0) + 1
            )

            # Count by domain
            if trace.domain:
                summary.by_domain[trace.domain] = (
                    summary.by_domain.get(trace.domain, 0) + 1
                )

            # Aggregate metrics
            summary.total_conditions_checked += trace.conditions_checked
            summary.total_elapsed_ms += trace.total_elapsed_ms

            # Count matched conditions
            if trace.matched_condition:
                summary.matched_conditions[trace.matched_condition] = (
                    summary.matched_conditions.get(trace.matched_condition, 0) + 1
                )

        return summary

    def clear(self) -> None:
        """Clear all collected traces."""
        self._traces.clear()

    def __len__(self) -> int:
        """Return number of collected traces."""
        return len(self._traces)

    def __iter__(self):
        """Iterate over traces."""
        return iter(self._traces)

    def __repr__(self) -> str:
        return f"TraceCollector(traces={len(self._traces)})"

"""
E2E Evaluator for Sales Technique Testing.

Evaluates simulation results against expected outcomes and calculates scores.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulator.runner import SimulationResult
    from src.simulator.e2e_scenarios import E2EScenario


@dataclass
class E2EResult:
    """
    Result of evaluating one e2e scenario.

    Attributes:
        scenario_id: ID of the scenario (01-20)
        scenario_name: Human-readable name
        flow_name: Flow that was tested
        passed: Whether the scenario passed
        score: Overall score (0.0 - 1.0)
        outcome: Actual outcome achieved
        expected_outcome: Expected outcome
        phases_reached: Phases actually reached during simulation
        expected_phases: Phases that were expected
        turns: Number of dialogue turns
        duration_seconds: Time taken for simulation
        errors: Any errors encountered
        details: Detailed breakdown of scoring
        dialogue: Full dialogue history
        decision_traces: Decision traces from bot
        client_traces: Client agent traces
        rule_traces: Conditional rule traces
    """
    scenario_id: str
    scenario_name: str
    flow_name: str
    passed: bool
    score: float
    outcome: str
    expected_outcome: str
    phases_reached: List[str]
    expected_phases: List[str]
    turns: int
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    dialogue: List[Dict[str, Any]] = field(default_factory=list)
    decision_traces: List[Dict[str, Any]] = field(default_factory=list)
    client_traces: List[Dict[str, Any]] = field(default_factory=list)
    rule_traces: List[Dict[str, Any]] = field(default_factory=list)
    kb_questions_used: int = 0
    kb_topics_covered: List[str] = field(default_factory=list)


class E2EEvaluator:
    """
    Evaluator for e2e test results.

    Calculates weighted scores based on:
    - Outcome match (40%)
    - Phase coverage (30%)
    - Turns efficiency (15%)
    - Error penalty (15%)
    """

    # Scoring weights
    WEIGHTS = {
        'outcome_match': 0.40,
        'phases_coverage': 0.30,
        'turns_efficiency': 0.15,
        'error_penalty': 0.15,
    }

    # Ideal turn ranges for different outcomes
    IDEAL_TURNS = {
        'success': (8, 15),
        'soft_close': (6, 12),
        'rejection': (3, 8),
        'error': (0, 0),
    }

    # Acceptable alternative outcomes
    ACCEPTABLE_ALTERNATIVES = {
        'success': ['soft_close'],  # soft_close is acceptable if expected success
        'soft_close': ['success'],  # success is even better
    }

    def evaluate(
        self,
        result: "SimulationResult",
        scenario: "E2EScenario"
    ) -> E2EResult:
        """
        Evaluate a simulation result against its scenario.

        Args:
            result: SimulationResult from the simulation
            scenario: E2EScenario that was being tested

        Returns:
            E2EResult with scores and details
        """
        scores = {}
        details = {}

        # 1. Outcome Match (40%)
        outcome_score, outcome_details = self._evaluate_outcome(
            result.outcome,
            scenario.expected_outcome
        )
        scores['outcome_match'] = outcome_score
        details['outcome'] = outcome_details

        # 2. Phase Coverage (30%)
        phases_score, phases_details = self._evaluate_phases(
            result.phases_reached,
            scenario.phases
        )
        scores['phases_coverage'] = phases_score
        details['phases'] = phases_details

        # 3. Turns Efficiency (15%)
        turns_score, turns_details = self._evaluate_turns(
            result.turns,
            scenario.expected_outcome
        )
        scores['turns_efficiency'] = turns_score
        details['turns'] = turns_details

        # 4. Error Penalty (15%)
        error_score, error_details = self._evaluate_errors(result.errors)
        scores['error_penalty'] = error_score
        details['errors'] = error_details

        # Calculate total score
        total_score = sum(
            self.WEIGHTS[k] * scores[k]
            for k in self.WEIGHTS
        )

        # Determine pass/fail
        # Pass if: outcome matches exactly OR score >= 0.7
        exact_match = result.outcome == scenario.expected_outcome
        acceptable_alternative = result.outcome in self.ACCEPTABLE_ALTERNATIVES.get(
            scenario.expected_outcome, []
        )
        passed = exact_match or acceptable_alternative or total_score >= 0.7

        return E2EResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            flow_name=scenario.flow,
            passed=passed,
            score=total_score,
            outcome=result.outcome,
            expected_outcome=scenario.expected_outcome,
            phases_reached=result.phases_reached,
            expected_phases=scenario.phases,
            turns=result.turns,
            duration_seconds=result.duration_seconds,
            errors=result.errors,
            details={
                'scores': scores,
                'weights': self.WEIGHTS,
                **details
            },
            dialogue=result.dialogue,
            decision_traces=result.decision_traces,
            client_traces=result.client_traces,
            rule_traces=result.rule_traces,
            kb_questions_used=getattr(result, 'kb_questions_used', 0),
            kb_topics_covered=getattr(result, 'kb_topics_covered', []),
        )

    def _evaluate_outcome(
        self,
        actual: str,
        expected: str
    ) -> tuple[float, Dict[str, Any]]:
        """
        Evaluate outcome match.

        Returns:
            (score, details) tuple
        """
        details = {
            'actual': actual,
            'expected': expected,
        }

        if actual == expected:
            return 1.0, {**details, 'match': 'exact'}

        # Check acceptable alternatives
        if actual in self.ACCEPTABLE_ALTERNATIVES.get(expected, []):
            return 0.8, {**details, 'match': 'acceptable_alternative'}

        # Partial credit for related outcomes
        if actual == 'soft_close' and expected == 'success':
            return 0.6, {**details, 'match': 'partial_soft_close'}
        if actual == 'success' and expected == 'soft_close':
            return 0.9, {**details, 'match': 'better_than_expected'}

        # Error outcome
        if actual == 'error':
            return 0.0, {**details, 'match': 'error'}

        # No match
        return 0.2, {**details, 'match': 'mismatch'}

    def _evaluate_phases(
        self,
        reached: List[str],
        expected: List[str]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Evaluate phase coverage.

        Returns:
            (score, details) tuple
        """
        if not expected:
            # No phases expected, give full score
            return 1.0, {'coverage': 1.0, 'reached': reached, 'expected': expected}

        reached_set = set(reached)
        expected_set = set(expected)

        # Calculate coverage
        matched = reached_set & expected_set
        coverage = len(matched) / len(expected_set) if expected_set else 1.0

        # Bonus for reaching phases in order
        order_bonus = 0.0
        if reached and expected:
            # Check if first few expected phases were reached in order
            in_order = 0
            for i, phase in enumerate(expected):
                if i < len(reached) and phase in reached[:i+2]:
                    in_order += 1
                else:
                    break
            order_bonus = (in_order / len(expected)) * 0.2  # Up to 20% bonus

        score = min(1.0, coverage + order_bonus)

        return score, {
            'coverage': coverage,
            'reached': list(reached),
            'expected': expected,
            'matched': list(matched),
            'order_bonus': order_bonus
        }

    def _evaluate_turns(
        self,
        turns: int,
        expected_outcome: str
    ) -> tuple[float, Dict[str, Any]]:
        """
        Evaluate turns efficiency.

        Returns:
            (score, details) tuple
        """
        ideal_range = self.IDEAL_TURNS.get(expected_outcome, (5, 15))
        min_turns, max_turns = ideal_range

        details = {
            'turns': turns,
            'ideal_range': ideal_range,
        }

        if min_turns <= turns <= max_turns:
            # Perfect - within ideal range
            return 1.0, {**details, 'assessment': 'ideal'}

        if turns < min_turns:
            # Too fast - might have missed things
            ratio = turns / min_turns if min_turns > 0 else 0
            return max(0.3, ratio), {**details, 'assessment': 'too_fast'}

        if turns > max_turns:
            # Too slow - inefficient
            overage = turns - max_turns
            penalty = min(0.5, overage * 0.1)  # 10% per turn over, max 50%
            return max(0.5, 1.0 - penalty), {**details, 'assessment': 'too_slow'}

        return 0.7, {**details, 'assessment': 'unknown'}

    def _evaluate_errors(
        self,
        errors: List[str]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Evaluate error penalty.

        Returns:
            (score, details) tuple where score is 1.0 for no errors
        """
        if not errors:
            return 1.0, {'error_count': 0, 'errors': []}

        # Penalty per error
        error_count = len(errors)
        penalty = min(1.0, error_count * 0.25)  # 25% per error, max 100%

        return max(0.0, 1.0 - penalty), {
            'error_count': error_count,
            'errors': errors[:5],  # Limit to first 5
            'penalty': penalty
        }


def evaluate_batch(
    results: List["SimulationResult"],
    scenarios: List["E2EScenario"]
) -> List[E2EResult]:
    """
    Evaluate a batch of results against scenarios.

    Matches results to scenarios by flow_name or index.
    """
    evaluator = E2EEvaluator()
    e2e_results = []

    # Create flow -> scenario mapping
    scenario_by_flow = {s.flow: s for s in scenarios}

    for result in results:
        # Find matching scenario
        scenario = scenario_by_flow.get(result.flow_name)
        if scenario:
            e2e_result = evaluator.evaluate(result, scenario)
            e2e_results.append(e2e_result)

    return e2e_results


# Export
__all__ = [
    "E2EResult",
    "E2EEvaluator",
    "evaluate_batch",
]

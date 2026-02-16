"""
Regression tests for simulator lead scoring pipeline.

Covers:
- feature flag defaults/groups for lead_scoring
- runner transport of score + temperature from bot API
- metrics aggregation by YAML-defined temperatures
- report layer consuming only AggregatedMetrics payload
"""

from pathlib import Path
from unittest.mock import Mock

from src.feature_flags import FeatureFlags
from src.simulator.metrics import AggregatedMetrics, MetricsCollector
from src.simulator.report import ReportGenerator
from src.simulator.runner import SimulationResult, SimulationRunner
from src.yaml_config.constants import LEAD_TEMPERATURE_THRESHOLDS


def _make_result(
    simulation_id: int,
    temperature: str,
    score: float,
    outcome: str = "success",
) -> SimulationResult:
    return SimulationResult(
        simulation_id=simulation_id,
        persona="happy_path",
        outcome=outcome,
        turns=1,
        duration_seconds=0.5,
        dialogue=[],
        final_lead_score=score,
        final_lead_temperature=temperature,
    )


def test_lead_scoring_enabled_by_default():
    ff = FeatureFlags()
    assert FeatureFlags.DEFAULTS["lead_scoring"] is True
    assert ff.is_enabled("lead_scoring") is True


def test_lead_scoring_in_safe_group():
    assert "lead_scoring" in FeatureFlags.GROUPS["safe"]
    assert "lead_scoring" not in FeatureFlags.GROUPS["risky"]


def test_simulation_result_carries_temperature(monkeypatch):
    import src.simulator.runner as runner_module
    import src.bot as bot_module

    class FakeStateMachine:
        collected_data = {"phone": "+70000000000"}

    class FakeBot:
        def __init__(self, *args, **kwargs):
            self.state_machine = FakeStateMachine()
            self._called = False

        def process(self, _client_message):
            self._called = True
            return {
                "response": "OK",
                "state": "soft_close",
                "intent": "fallback_close",
                "action": "soft_close",
                "is_final": True,
                "visited_states": ["soft_close"],
                "initial_state": "greeting",
            }

        def get_lead_score(self):
            return {"score": 88.0, "temperature": "very_hot"}

    class FakeClientAgent:
        def __init__(self, *_args, **_kwargs):
            pass

        def start_conversation(self):
            return "Привет"

        def should_continue(self):
            return False

        def respond(self, _bot_text):
            return "Ок"

        def get_last_trace(self):
            return None

        def is_budget_exhausted(self):
            return False

        def get_summary(self):
            return {"objections": 0, "kb_questions_used": 0, "kb_topics_covered": []}

    monkeypatch.setattr(runner_module, "ClientAgent", FakeClientAgent)
    monkeypatch.setattr(bot_module, "SalesBot", FakeBot)

    result = SimulationRunner(bot_llm=Mock(), client_llm=Mock(), verbose=False).run_single("happy_path")

    assert result.final_lead_score == 88.0
    assert result.final_lead_temperature == "very_hot"


def test_metrics_aggregates_by_yaml_temperatures():
    assert LEAD_TEMPERATURE_THRESHOLDS, "LEAD_TEMPERATURE_THRESHOLDS must be defined in YAML"
    temperatures = list(LEAD_TEMPERATURE_THRESHOLDS.keys())

    results = [_make_result(i, temp, score=10.0 * (i + 1)) for i, temp in enumerate(temperatures)]
    results.append(_make_result(999, temperatures[0], score=99.0))

    aggregated = MetricsCollector().aggregate(results)
    assert list(aggregated.lead_temperature_stats.keys()) == temperatures

    expected_counts = {temp: 0 for temp in temperatures}
    for result in results:
        expected_counts[result.final_lead_temperature] += 1

    for temp in temperatures:
        assert aggregated.lead_temperature_stats[temp]["count"] == expected_counts[temp]


def test_aggregated_metrics_includes_ranges():
    temperatures = list(LEAD_TEMPERATURE_THRESHOLDS.keys())
    results = [_make_result(i, temp, score=25.0) for i, temp in enumerate(temperatures)]

    aggregated = MetricsCollector().aggregate(results)

    for temp in temperatures:
        assert aggregated.lead_temperature_stats[temp]["range"] == LEAD_TEMPERATURE_THRESHOLDS[temp]


def test_report_reads_only_from_aggregated_metrics():
    content = Path("src/simulator/report.py").read_text(encoding="utf-8")
    forbidden_imports = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("from src.") or line.strip().startswith("import src.")
    ]
    assert not forbidden_imports

    lead_stats = {
        temp: {"count": idx + 1, "range": LEAD_TEMPERATURE_THRESHOLDS[temp]}
        for idx, temp in enumerate(LEAD_TEMPERATURE_THRESHOLDS.keys())
    }
    metrics = AggregatedMetrics(avg_lead_score=61.5, lead_temperature_stats=lead_stats)

    section = ReportGenerator()._section_lead_scoring(metrics)
    assert "Средний lead score: 61.5" in section
    for temp, stats in lead_stats.items():
        low, high = stats["range"]
        label = temp.replace("_", " ").title()
        assert f"{label} leads ({low}-{high}): {stats['count']}" in section

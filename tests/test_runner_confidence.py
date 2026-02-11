"""Tests for runner confidence contract (trace -> mirror -> default)."""

from src.simulator.runner import SimulationRunner


def test_runner_confidence_prefers_decision_trace_value():
    bot_result = {
        "confidence": 0.2,
        "decision_trace": {"classification": {"confidence": 0.91}},
    }
    assert SimulationRunner._resolve_turn_confidence(bot_result) == 0.91


def test_runner_confidence_falls_back_to_top_level_mirror():
    bot_result = {"confidence": 0.67, "decision_trace": {}}
    assert SimulationRunner._resolve_turn_confidence(bot_result) == 0.67


def test_runner_confidence_defaults_to_zero():
    assert SimulationRunner._resolve_turn_confidence({}) == 0.0

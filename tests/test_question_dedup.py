"""
Comprehensive tests for QuestionDeduplicationEngine.

Tests cover:
1. Configuration loading
2. Question filtering by collected_data
3. Instruction generation
4. Phase-specific questions
5. Edge cases and error handling
6. Metrics tracking
7. Integration scenarios
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from question_dedup import (
    QuestionDeduplicationEngine,
    QuestionDedupConfig,
    QuestionDedupMetrics,
    QuestionGenerationResult,
    question_dedup_engine,
    get_available_questions,
    get_prompt_context,
    get_do_not_ask_instruction,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def engine():
    """Fresh engine instance for each test."""
    return QuestionDeduplicationEngine()


@pytest.fixture
def collected_data_full():
    """Collected data with all situation fields."""
    return {
        "company_size": 10,
        "current_tools": "Excel",
        "business_type": "розница",
    }


@pytest.fixture
def collected_data_partial():
    """Collected data with only some fields."""
    return {
        "company_size": 10,
    }


@pytest.fixture
def collected_data_empty():
    """Empty collected data."""
    return {}


# =============================================================================
# CONFIGURATION LOADING TESTS
# =============================================================================


class TestConfigLoading:
    """Tests for configuration loading."""

    def test_config_loads_successfully(self, engine):
        """Config should load from YAML file."""
        assert engine._config is not None
        assert isinstance(engine._config, QuestionDedupConfig)

    def test_config_has_data_fields(self, engine):
        """Config should have data_fields defined."""
        assert engine._config.data_fields
        assert "company_size" in engine._config.data_fields
        assert "current_tools" in engine._config.data_fields
        assert "pain_point" in engine._config.data_fields

    def test_config_has_phase_questions(self, engine):
        """Config should have phase_questions defined."""
        assert engine._config.phase_questions
        assert "situation" in engine._config.phase_questions
        assert "problem" in engine._config.phase_questions
        assert "implication" in engine._config.phase_questions
        assert "need_payoff" in engine._config.phase_questions

    def test_field_to_questions_index_built(self, engine):
        """Field to questions index should be built."""
        assert engine._field_to_questions
        assert "company_size" in engine._field_to_questions
        assert len(engine._field_to_questions["company_size"]) > 0

    def test_fallback_config_on_missing_file(self):
        """Should use fallback config if file missing."""
        engine = QuestionDeduplicationEngine(
            config_path=Path("/nonexistent/path.yaml")
        )
        assert engine._config is not None
        # Fallback still works
        result = engine.get_available_questions("situation", {})
        assert result.available_questions


# =============================================================================
# QUESTION FILTERING TESTS
# =============================================================================


class TestQuestionFiltering:
    """Tests for question filtering by collected_data."""

    def test_no_filtering_when_nothing_collected(self, engine, collected_data_empty):
        """All questions available when nothing collected."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data=collected_data_empty,
        )
        assert result.filtered_count == 0
        assert len(result.available_questions) > 0
        assert not result.all_data_collected

    def test_filters_company_size_when_collected(self, engine, collected_data_partial):
        """Questions about company_size filtered when it's collected."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data=collected_data_partial,
        )
        assert "company_size" in result.do_not_ask_fields
        assert result.filtered_count >= 1

        # Available questions should NOT contain company_size questions
        for q in result.available_questions:
            assert "сколько человек" not in q.lower() or "команд" not in q.lower()

    def test_filters_all_fields_when_all_collected(self, engine, collected_data_full):
        """All questions filtered when all data collected."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data=collected_data_full,
        )
        assert result.all_data_collected
        assert result.filtered_count == 3  # company_size, current_tools, business_type

    def test_missing_data_parameter_used(self, engine):
        """Should use missing_data parameter if provided."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={"company_size": 10},
            missing_data=["current_tools"],  # Explicitly specify missing
        )
        # Should generate questions only for current_tools
        assert len(result.available_questions) >= 1

    def test_filters_current_tools_when_collected(self, engine):
        """Questions about current_tools filtered when it's collected."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={"current_tools": "Excel"},
        )
        assert "current_tools" in result.do_not_ask_fields

        # Available questions should NOT ask about current tools
        for q in result.available_questions:
            assert "чем пользуетесь" not in q.lower() and "excel" not in q.lower()


# =============================================================================
# INSTRUCTION GENERATION TESTS
# =============================================================================


class TestInstructionGeneration:
    """Tests for instruction generation."""

    def test_do_not_ask_instruction_empty_when_nothing_collected(self, engine):
        """do_not_ask instruction should be empty when nothing collected."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={},
        )
        assert result.do_not_ask_instruction == ""

    def test_do_not_ask_instruction_lists_collected_fields(self, engine):
        """do_not_ask instruction should list collected fields."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={"company_size": 10, "current_tools": "Excel"},
        )
        instruction = result.do_not_ask_instruction
        assert "company_size" in instruction.lower() or "размер" in instruction.lower()
        assert "current_tools" in instruction.lower() or "инструмент" in instruction.lower()

    def test_available_questions_instruction_format(self, engine):
        """available_questions instruction should have proper format."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={},
        )
        instruction = result.available_questions_instruction
        assert "вопрос" in instruction.lower() or "выбери" in instruction.lower()

    def test_all_collected_instruction_when_complete(self, engine, collected_data_full):
        """Should show 'all collected' instruction when phase complete."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data=collected_data_full,
        )
        instruction = result.available_questions_instruction
        assert "собран" in instruction.lower() or "следующ" in instruction.lower()


# =============================================================================
# PHASE-SPECIFIC TESTS
# =============================================================================


class TestPhaseSpecificQuestions:
    """Tests for phase-specific question generation."""

    def test_situation_phase_questions(self, engine):
        """Situation phase should have situation-specific questions."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={},
        )
        questions_text = " ".join(result.available_questions).lower()
        # Should contain situation questions
        assert any([
            "сколько" in questions_text,
            "учёт" in questions_text,
            "бизнес" in questions_text,
        ])

    def test_problem_phase_questions(self, engine):
        """Problem phase should have problem-specific questions."""
        result = engine.get_available_questions(
            phase="problem",
            collected_data={"company_size": 10, "current_tools": "Excel"},
        )
        questions_text = " ".join(result.available_questions).lower()
        # Should contain problem questions
        assert any([
            "сложност" in questions_text,
            "проблем" in questions_text,
            "головн" in questions_text,
            "боль" in questions_text.replace("больше", ""),
        ])

    def test_implication_phase_questions(self, engine):
        """Implication phase should have implication-specific questions."""
        result = engine.get_available_questions(
            phase="implication",
            collected_data={"pain_point": "теряем клиентов"},
        )
        questions_text = " ".join(result.available_questions).lower()
        # Should contain implication questions
        assert any([
            "сколько" in questions_text,
            "влия" in questions_text,
            "теря" in questions_text,
            "врем" in questions_text,
        ])

    def test_need_payoff_phase_questions(self, engine):
        """Need-payoff phase should have need-payoff-specific questions."""
        result = engine.get_available_questions(
            phase="need_payoff",
            collected_data={"pain_point": "теряем клиентов", "pain_impact": "5 клиентов в месяц"},
        )
        questions_text = " ".join(result.available_questions).lower()
        # Should contain need-payoff questions
        assert any([
            "если бы" in questions_text,
            "измени" in questions_text,
            "упрост" in questions_text,
        ])


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_values_not_considered_collected(self, engine):
        """Empty string and None should not be considered as collected."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={"company_size": "", "current_tools": None},
        )
        # Should not filter empty values
        assert "company_size" not in result.do_not_ask_fields
        assert "current_tools" not in result.do_not_ask_fields

    def test_zero_value_not_considered_collected(self, engine):
        """Zero should not be considered as collected for numeric fields."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={"company_size": 0},
        )
        assert "company_size" not in result.do_not_ask_fields

    def test_unknown_phase_uses_fallback(self, engine):
        """Unknown phase should use fallback questions."""
        result = engine.get_available_questions(
            phase="unknown_phase",
            collected_data={},
        )
        # Should still return something (fallback)
        assert result is not None

    def test_variable_substitution_in_questions(self, engine):
        """Variables like {current_tools} should be substituted."""
        result = engine.get_available_questions(
            phase="problem",
            collected_data={"current_tools": "Excel"},
            missing_data=["pain_point"],
        )
        # If there's a question template with {current_tools}, it should be substituted
        for q in result.available_questions:
            assert "{current_tools}" not in q


# =============================================================================
# METRICS TESTS
# =============================================================================


class TestMetrics:
    """Tests for metrics tracking."""

    def test_metrics_initialized(self, engine):
        """Metrics should be initialized."""
        assert engine._metrics is not None
        assert isinstance(engine._metrics, QuestionDedupMetrics)

    def test_metrics_track_requests(self, engine):
        """Metrics should track total requests."""
        initial = engine._metrics.total_requests
        engine.get_available_questions("situation", {})
        engine.get_available_questions("problem", {})
        assert engine._metrics.total_requests == initial + 2

    def test_metrics_track_filtered_questions(self, engine, collected_data_full):
        """Metrics should track filtered questions."""
        engine.reset_metrics()
        engine.get_available_questions("situation", collected_data_full)
        assert engine._metrics.questions_filtered > 0

    def test_metrics_track_phases_with_all_data(self, engine, collected_data_full):
        """Metrics should track phases with all data collected."""
        engine.reset_metrics()
        engine.get_available_questions("situation", collected_data_full)
        assert engine._metrics.phases_with_all_data == 1

    def test_metrics_to_dict(self, engine):
        """Metrics should convert to dict."""
        engine.get_available_questions("situation", {})
        metrics_dict = engine.get_metrics()
        assert "total_requests" in metrics_dict
        assert "questions_filtered" in metrics_dict
        assert "filtering_rate" in metrics_dict


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration tests with convenience functions."""

    def test_get_available_questions_function(self):
        """get_available_questions convenience function should work."""
        result = get_available_questions("situation", {"company_size": 10})
        assert isinstance(result, QuestionGenerationResult)
        assert "company_size" in result.do_not_ask_fields

    def test_get_prompt_context_function(self):
        """get_prompt_context convenience function should work."""
        context = get_prompt_context(
            phase="situation",
            collected_data={"company_size": 10},
        )
        assert "available_questions" in context
        assert "do_not_ask" in context
        assert "missing_data_questions" in context

    def test_get_do_not_ask_instruction_function(self):
        """get_do_not_ask_instruction convenience function should work."""
        instruction = get_do_not_ask_instruction({"company_size": 10})
        assert isinstance(instruction, str)

    def test_singleton_instance_works(self):
        """Singleton instance should work correctly."""
        result = question_dedup_engine.get_available_questions(
            "situation", {"company_size": 10}
        )
        assert result is not None

    def test_result_to_prompt_variables(self, engine):
        """QuestionGenerationResult.to_prompt_variables should work."""
        result = engine.get_available_questions(
            phase="situation",
            collected_data={"company_size": 10},
        )
        variables = result.to_prompt_variables()
        assert "available_questions" in variables
        assert "do_not_ask" in variables
        assert "missing_data_questions" in variables
        assert "collected_fields_list" in variables


# =============================================================================
# REGRESSION TESTS - THE ORIGINAL PROBLEM
# =============================================================================


class TestRegressionOriginalProblem:
    """
    Regression tests for the original problem:
    "Бот переспрашивает уже отвеченное"

    Example from issue:
    Turn 2: Client: "ручной, неудобно, тратим время" (answered about tools)
    Turn 5: Bot: "Чем сейчас пользуетесь для учёта клиентов?" (re-asked!)
    """

    def test_current_tools_filtered_after_answer(self, engine):
        """
        When client says "ручной" (current_tools), bot should NOT ask about tools.
        """
        # Client answered about tools
        collected_data = {"current_tools": "ручной"}

        result = engine.get_available_questions(
            phase="situation",
            collected_data=collected_data,
        )

        # current_tools should be in do_not_ask
        assert "current_tools" in result.do_not_ask_fields

        # None of the available questions should ask about tools
        for q in result.available_questions:
            q_lower = q.lower()
            assert "чем пользуетесь" not in q_lower
            assert "как ведёте учёт" not in q_lower
            assert "excel" not in q_lower
            assert "1с" not in q_lower

    def test_company_size_filtered_after_answer(self, engine):
        """
        When client says "нас 10 человек", bot should NOT ask about team size.
        """
        collected_data = {"company_size": 10}

        result = engine.get_available_questions(
            phase="situation",
            collected_data=collected_data,
        )

        # company_size should be in do_not_ask
        assert "company_size" in result.do_not_ask_fields

        # None of the available questions should ask about size
        for q in result.available_questions:
            q_lower = q.lower()
            # Avoid false positives - only check specific patterns
            if "человек" in q_lower:
                assert "сколько" not in q_lower

    def test_pain_point_filtered_after_answer(self, engine):
        """
        When client says "теряем клиентов", bot should NOT ask about pain again.
        """
        collected_data = {
            "company_size": 10,
            "current_tools": "Excel",
            "pain_point": "теряем клиентов",
        }

        result = engine.get_available_questions(
            phase="problem",
            collected_data=collected_data,
        )

        # pain_point should be in do_not_ask
        assert "pain_point" in result.do_not_ask_fields

    def test_full_scenario_situation_to_problem(self, engine):
        """
        Full scenario: situation phase with partial data → problem phase.
        """
        # Turn 1: Got company_size
        collected_turn1 = {"company_size": 10}
        result1 = engine.get_available_questions("situation", collected_turn1)
        assert "company_size" in result1.do_not_ask_fields
        assert len(result1.available_questions) > 0  # Still have questions about tools, business

        # Turn 2: Got current_tools
        collected_turn2 = {"company_size": 10, "current_tools": "ручной"}
        result2 = engine.get_available_questions("situation", collected_turn2)
        assert "company_size" in result2.do_not_ask_fields
        assert "current_tools" in result2.do_not_ask_fields

        # Turn 3: Got business_type - all situation data collected
        collected_turn3 = {
            "company_size": 10,
            "current_tools": "ручной",
            "business_type": "розница",
        }
        result3 = engine.get_available_questions("situation", collected_turn3)
        assert result3.all_data_collected

        # Turn 4: Problem phase - should ask about pain, not situation
        result4 = engine.get_available_questions("problem", collected_turn3)
        # Should NOT ask about already collected situation data
        for q in result4.available_questions:
            q_lower = q.lower()
            # Should not ask situation questions
            assert "сколько человек" not in q_lower or "теряете" in q_lower  # "сколько теряете" is ok


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================


class TestPerformance:
    """Performance tests."""

    def test_many_calls_performance(self, engine):
        """Engine should handle many calls efficiently."""
        import time

        start = time.time()
        for _ in range(100):
            engine.get_available_questions(
                "situation",
                {"company_size": 10, "current_tools": "Excel"},
            )
        elapsed = time.time() - start

        # Should complete 100 calls in under 1 second
        assert elapsed < 1.0, f"100 calls took {elapsed:.2f}s, expected <1s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

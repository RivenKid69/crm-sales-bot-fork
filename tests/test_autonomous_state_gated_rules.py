from unittest.mock import MagicMock

from src.generator import ResponseGenerator


def _make_generator():
    gen = ResponseGenerator.__new__(ResponseGenerator)
    gen._flow = None
    gen._enhanced_pipeline = None
    return gen


class TestAutonomousStateGatedRules:
    def test_interruption_rule_in_non_closing_autonomous_state(self):
        gen = _make_generator()

        rules = gen._build_state_gated_rules(
            state="autonomous_discovery",
            intent="agreement",
            user_message="Да, но сколько стоит внедрение?",
            history=[],
            collected={},
            secondary_intents=["question_pricing"],
        )

        assert "INTERRUPTION" in rules
        assert "сначала дай прямой ответ" in rules.lower()

    def test_comparison_and_logic_rules_are_added(self):
        gen = _make_generator()

        rules = gen._build_state_gated_rules(
            state="autonomous_presentation",
            intent="comparison",
            user_message="Сравни с iiko: чем отличается и если интеграция сложная, то как влияет на запуск?",
            history=[],
            collected={},
            secondary_intents=[],
        )

        assert "СРАВНЕНИЕ" in rules
        assert "ЛОГИЧЕСКАЯ СВЯЗЬ" in rules

    def test_no_interruption_rule_in_autonomous_closing(self):
        gen = _make_generator()

        rules = gen._build_state_gated_rules(
            state="autonomous_closing",
            intent="question_features",
            user_message="А есть API?",
            history=[],
            collected={},
            secondary_intents=["question_integrations"],
        )

        assert "INTERRUPTION" not in rules


class TestInterruptQuestionSuppression:
    def test_suppress_followup_question_for_question_intent(self):
        assert ResponseGenerator._should_suppress_followup_question_for_interrupt(
            state="autonomous_discovery",
            intent="question_integrations",
            user_message="Есть интеграция с Kaspi?",
            secondary_intents=[],
        ) is True

    def test_suppress_followup_question_for_logic_marker(self):
        assert ResponseGenerator._should_suppress_followup_question_for_interrupt(
            state="autonomous_presentation",
            intent="agreement",
            user_message="Если у нас 5 точек, то как влияет это на внедрение?",
            secondary_intents=[],
        ) is True

    def test_do_not_suppress_in_closing(self):
        assert ResponseGenerator._should_suppress_followup_question_for_interrupt(
            state="autonomous_closing",
            intent="question_integrations",
            user_message="Есть API?",
            secondary_intents=["question_features"],
        ) is False

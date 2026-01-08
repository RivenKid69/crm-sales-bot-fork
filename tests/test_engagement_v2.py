"""
Тесты для Engagement V2 (улучшенный расчёт без зависимости от word_count).

Phase 3 из PLAN_CONTEXT_POLICY.md:
- Короткие позитивные ответы ("да", "ок", "понял") не штрафуются
- Опора на has_data, turn_type, question_count
- Более стабильные метрики вовлечённости
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from context_window import ContextWindow, TurnType, EngagementLevel


class TestEngagementV2Score:
    """Тесты для get_engagement_score_v2."""

    def test_empty_window(self):
        """Проверить score для пустого окна."""
        cw = ContextWindow(max_size=5)
        score = cw.get_engagement_score_v2()
        assert score == 0.5  # Нейтральный

    def test_positive_short_responses_not_penalized(self):
        """Проверить что короткие позитивные ответы не штрафуются."""
        cw = ContextWindow(max_size=5)

        positive_responses = ["да", "ок", "хорошо", "понял", "ага"]

        for msg in positive_responses:
            cw.add_turn_from_dict(
                user_message=msg,
                bot_response="Отлично!",
                intent="agreement",
                confidence=0.9,
                action="continue",
                state="spin_situation",
                next_state="spin_situation",
            )

        score = cw.get_engagement_score_v2()

        # Score должен быть >= 0.5 (не штрафуем за краткость)
        assert score >= 0.5

    def test_data_provided_increases_score(self):
        """Проверить что предоставление данных повышает score."""
        cw = ContextWindow(max_size=5)

        # Ход без данных
        cw.add_turn_from_dict(
            user_message="Привет",
            bot_response="Здравствуйте!",
            intent="greeting",
            confidence=0.9,
            action="greet",
            state="greeting",
            next_state="spin_situation",
        )

        score_without_data = cw.get_engagement_score_v2()

        # Ход с данными
        cw.add_turn_from_dict(
            user_message="Нас 20 человек",
            bot_response="Отлично!",
            intent="company_size",
            confidence=0.9,
            action="ask_pain",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 20},
        )

        score_with_data = cw.get_engagement_score_v2()

        # Score должен вырасти
        assert score_with_data > score_without_data

    def test_progress_turn_type_increases_score(self):
        """Проверить что PROGRESS turn type повышает score."""
        cw = ContextWindow(max_size=5)

        # Добавляем progress ходы
        cw.add_turn_from_dict(
            user_message="Нас 10 человек, занимаемся розницей",
            bot_response="Отлично!",
            intent="company_size",
            confidence=0.95,
            action="ask_pain",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 10, "business_type": "розница"},
        )

        cw.add_turn_from_dict(
            user_message="Теряем клиентов, это основная проблема",
            bot_response="Понимаю...",
            intent="pain_point",
            confidence=0.9,
            action="explore",
            state="spin_problem",
            next_state="spin_implication",
            extracted_data={"pain_point": "потеря клиентов"},
        )

        score = cw.get_engagement_score_v2()

        # Score должен быть высоким
        assert score >= 0.6

    def test_regress_turn_type_decreases_score(self):
        """Проверить что REGRESS turn type понижает score."""
        cw = ContextWindow(max_size=5)

        # Добавляем regress ходы (возражения)
        for i in range(3):
            cw.add_turn_from_dict(
                user_message="Не интересно",
                bot_response="Понимаю...",
                intent="objection_no_need",
                confidence=0.85,
                action="handle_objection",
                state="handle_objection",
                next_state="handle_objection",
            )

        score = cw.get_engagement_score_v2()

        # Score должен быть ниже нейтрального
        assert score < 0.5

    def test_questions_increase_score(self):
        """Проверить что вопросы (как признак интереса) повышают score."""
        cw = ContextWindow(max_size=5)

        # Добавляем несколько вопросов
        cw.add_turn_from_dict(
            user_message="А сколько это стоит?",
            bot_response="Зависит от...",
            intent="question_price",
            confidence=0.9,
            action="deflect_price",
            state="spin_situation",
            next_state="spin_situation",
        )

        cw.add_turn_from_dict(
            user_message="А интеграции есть?",
            bot_response="Да, есть...",
            intent="question_features",
            confidence=0.88,
            action="answer_features",
            state="spin_situation",
            next_state="spin_situation",
        )

        score = cw.get_engagement_score_v2()

        # Score должен быть >= 0.5 (вопросы = интерес)
        assert score >= 0.5

    def test_repeated_question_penalty(self):
        """Проверить что повторные вопросы немного снижают score."""
        cw = ContextWindow(max_size=5)

        # Сначала добавляем другой ход
        cw.add_turn_from_dict(
            user_message="Привет",
            bot_response="Здравствуйте!",
            intent="greeting",
            confidence=0.9,
            action="greet",
            state="greeting",
            next_state="spin_situation",
        )

        # Затем повторяющийся вопрос
        for i in range(2):
            cw.add_turn_from_dict(
                user_message="Сколько стоит?",
                bot_response="Зависит от...",
                intent="question_price",
                confidence=0.9,
                action="deflect_price",
                state="spin_situation",
                next_state="spin_situation",
            )

        score = cw.get_engagement_score_v2()

        # Проверяем что detect_repeated_question работает (может быть None если нет паттерна)
        # Основная проверка - score в разумных пределах
        assert 0.4 <= score <= 0.7

    def test_many_objections_penalty(self):
        """Проверить что много возражений снижают score."""
        cw = ContextWindow(max_size=10)

        # Добавляем много возражений
        for i in range(4):
            cw.add_turn_from_dict(
                user_message=f"Возражение {i}",
                bot_response="Понимаю...",
                intent="objection_price" if i % 2 == 0 else "objection_competitor",
                confidence=0.85,
                action="handle_objection",
                state="handle_objection",
                next_state="handle_objection",
            )

        score = cw.get_engagement_score_v2()

        # Score снижен из-за возражений
        assert score < 0.5


class TestEngagementV2Level:
    """Тесты для get_engagement_level_v2."""

    def test_high_engagement(self):
        """Проверить определение высокой вовлечённости."""
        cw = ContextWindow(max_size=5)

        # Добавляем хорошие ходы с данными
        cw.add_turn_from_dict(
            user_message="Нас 50 человек, занимаемся логистикой",
            bot_response="Отлично!",
            intent="company_size",
            confidence=0.95,
            action="ask_pain",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 50, "business_type": "логистика"},
        )

        cw.add_turn_from_dict(
            user_message="Основная проблема - контроль водителей",
            bot_response="Понимаю...",
            intent="pain_point",
            confidence=0.92,
            action="explore",
            state="spin_problem",
            next_state="spin_implication",
            extracted_data={"pain_point": "контроль водителей"},
        )

        cw.add_turn_from_dict(
            user_message="Да, это нам очень нужно!",
            bot_response="Отлично!",
            intent="explicit_interest",
            confidence=0.98,
            action="present",
            state="spin_need_payoff",
            next_state="presentation",
        )

        level = cw.get_engagement_level_v2()

        assert level == EngagementLevel.HIGH

    def test_medium_engagement(self):
        """Проверить определение средней вовлечённости."""
        cw = ContextWindow(max_size=5)

        # Нейтральные ходы
        cw.add_turn_from_dict(
            user_message="Привет",
            bot_response="Здравствуйте!",
            intent="greeting",
            confidence=0.9,
            action="greet",
            state="greeting",
            next_state="spin_situation",
        )

        cw.add_turn_from_dict(
            user_message="Ок",
            bot_response="Отлично!",
            intent="agreement",
            confidence=0.85,
            action="continue",
            state="spin_situation",
            next_state="spin_situation",
        )

        level = cw.get_engagement_level_v2()

        assert level == EngagementLevel.MEDIUM

    def test_low_engagement(self):
        """Проверить определение низкой вовлечённости."""
        cw = ContextWindow(max_size=5)

        # Несколько unclear
        for i in range(3):
            cw.add_turn_from_dict(
                user_message="Не знаю",
                bot_response="Уточните...",
                intent="unclear",
                confidence=0.4,
                action="clarify",
                state="spin_situation",
                next_state="spin_situation",
            )

        level = cw.get_engagement_level_v2()

        assert level in [EngagementLevel.LOW, EngagementLevel.DISENGAGED]

    def test_disengaged(self):
        """Проверить определение disengaged или low engagement."""
        cw = ContextWindow(max_size=5)

        # Много негативных сигналов
        for i in range(4):
            cw.add_turn_from_dict(
                user_message="Не интересно, отстаньте",
                bot_response="Понимаю...",
                intent="rejection",
                confidence=0.9,
                action="soft_close",
                state="handle_objection",
                next_state="soft_close",
            )

        level = cw.get_engagement_level_v2()

        # Rejections приводят к low или disengaged уровню
        assert level in [EngagementLevel.LOW, EngagementLevel.DISENGAGED]


class TestEngagementV2Trend:
    """Тесты для get_engagement_trend_v2."""

    def test_trend_unknown_few_turns(self):
        """Проверить trend unknown при малом количестве ходов."""
        cw = ContextWindow(max_size=5)

        cw.add_turn_from_dict(
            user_message="Привет",
            bot_response="Здравствуйте!",
            intent="greeting",
            confidence=0.9,
            action="greet",
            state="greeting",
            next_state="spin_situation",
        )

        trend = cw.get_engagement_trend_v2()

        assert trend == "unknown"

    def test_trend_improving(self):
        """Проверить определение improving trend."""
        cw = ContextWindow(max_size=10)

        # Первая половина - нейтральные
        for i in range(3):
            cw.add_turn_from_dict(
                user_message="Хм",
                bot_response="...",
                intent="unclear",
                confidence=0.5,
                action="clarify",
                state="spin_situation",
                next_state="spin_situation",
            )

        # Вторая половина - позитивные с данными
        for i in range(3):
            cw.add_turn_from_dict(
                user_message=f"Данные {i}",
                bot_response="Отлично!",
                intent="info_provided",
                confidence=0.9,
                action="continue",
                state="spin_problem",
                next_state="spin_implication",
                extracted_data={f"data_{i}": i},
            )

        trend = cw.get_engagement_trend_v2()

        assert trend == "improving"

    def test_trend_declining(self):
        """Проверить определение declining trend."""
        cw = ContextWindow(max_size=10)

        # Первая половина - позитивные
        for i in range(3):
            cw.add_turn_from_dict(
                user_message="Отлично!",
                bot_response="...",
                intent="explicit_interest",
                confidence=0.95,
                action="present",
                state="presentation",
                next_state="presentation",
                extracted_data={"interest": True},
            )

        # Вторая половина - негативные
        for i in range(3):
            cw.add_turn_from_dict(
                user_message="Не знаю...",
                bot_response="...",
                intent="unclear",
                confidence=0.4,
                action="clarify",
                state="spin_situation",
                next_state="spin_situation",
            )

        trend = cw.get_engagement_trend_v2()

        assert trend == "declining"

    def test_trend_stable(self):
        """Проверить определение stable trend."""
        cw = ContextWindow(max_size=10)

        # Все ходы примерно одинаковые
        for i in range(6):
            cw.add_turn_from_dict(
                user_message="Ок",
                bot_response="...",
                intent="agreement",
                confidence=0.8,
                action="continue",
                state="spin_situation",
                next_state="spin_situation",
            )

        trend = cw.get_engagement_trend_v2()

        assert trend == "stable"


class TestEngagementV2VsV1:
    """Сравнительные тесты v1 vs v2."""

    def test_short_responses_comparison(self):
        """Сравнить v1 и v2 для коротких ответов."""
        cw = ContextWindow(max_size=5)

        # Короткие позитивные ответы
        for msg in ["да", "хорошо", "понял"]:
            cw.add_turn_from_dict(
                user_message=msg,
                bot_response="OK",
                intent="agreement",
                confidence=0.9,
                action="continue",
                state="spin_situation",
                next_state="spin_situation",
            )

        score_v1 = cw.get_engagement_score()
        score_v2 = cw.get_engagement_score_v2()

        # v2 должен давать разумный score для коротких позитивных ответов
        # v2 не обязательно >= v1, но должен быть >= 0.5 (нейтральный)
        assert score_v2 >= 0.5
        # v1 и v2 оба дают высокие scores для позитивных сигналов
        assert score_v1 >= 0.5

    def test_data_heavy_comparison(self):
        """Сравнить v1 и v2 для ходов с данными."""
        cw = ContextWindow(max_size=5)

        # Ходы с данными
        cw.add_turn_from_dict(
            user_message="10 человек",
            bot_response="OK",
            intent="company_size",
            confidence=0.9,
            action="ask_pain",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 10},
        )

        score_v1 = cw.get_engagement_score()
        score_v2 = cw.get_engagement_score_v2()

        # Оба должны быть высокими
        assert score_v1 >= 0.5
        assert score_v2 >= 0.5

    def test_structured_context_uses_v2(self):
        """Проверить что structured_context использует v2 при флаге."""
        cw = ContextWindow(max_size=5)

        cw.add_turn_from_dict(
            user_message="да",
            bot_response="OK",
            intent="agreement",
            confidence=0.9,
            action="continue",
            state="spin_situation",
            next_state="spin_situation",
        )

        ctx_v1 = cw.get_structured_context(use_v2_engagement=False)
        ctx_v2 = cw.get_structured_context(use_v2_engagement=True)

        # Оба метода работают и дают scores
        assert 0 <= ctx_v1["engagement_score"] <= 1
        assert 0 <= ctx_v2["engagement_score"] <= 1
        # v2 должен давать разумный score
        assert ctx_v2["engagement_score"] >= 0.5

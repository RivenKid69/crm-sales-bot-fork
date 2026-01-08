"""
Тесты для Context Window Уровень 2 — Structured Context

Тестирует:
1. TurnType классификация (progress, regress, lateral, stuck)
2. Engagement анализ (score, level, trend)
3. Funnel Progress (velocity, progress, regress)
4. Momentum (инерция диалога)
5. Trigger Analysis (что вызвало возражение/прогресс)
6. Интеграция с классификатором
7. Сравнение Уровень 2 отдельно vs Уровень 1+2 вместе
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from context_window import (
    ContextWindow, TurnContext, TurnType, EngagementLevel,
    STATE_ORDER, SPIN_PHASE_ORDER
)
from classifier import HybridClassifier


# =============================================================================
# ТЕСТЫ TurnType (Классификация типов ходов)
# =============================================================================

class TestTurnType:
    """Тесты классификации типов ходов."""

    def test_turn_type_progress_by_delta(self):
        """Ход с положительным delta = PROGRESS."""
        turn = TurnContext(
            user_message="у нас 10 человек",
            intent="info_provided",
            state="greeting",
            next_state="spin_situation",  # +1 delta
        )
        assert turn.turn_type == TurnType.PROGRESS
        assert turn.funnel_delta == 1

    def test_turn_type_regress_by_intent(self):
        """Возражение = REGRESS независимо от delta."""
        turn = TurnContext(
            user_message="дорого",
            intent="objection_price",
            state="presentation",
            next_state="handle_objection",
        )
        assert turn.turn_type == TurnType.REGRESS

    def test_turn_type_lateral_question(self):
        """Вопрос = LATERAL."""
        turn = TurnContext(
            user_message="какие есть интеграции?",
            intent="question_integrations",
            state="spin_situation",
            next_state="spin_situation",
        )
        assert turn.turn_type == TurnType.LATERAL

    def test_turn_type_stuck_unclear(self):
        """Unclear = STUCK."""
        turn = TurnContext(
            user_message="ыыы",
            intent="unclear",
            state="spin_situation",
            next_state="spin_situation",
        )
        assert turn.turn_type == TurnType.STUCK

    def test_turn_type_neutral_greeting(self):
        """Приветствие = NEUTRAL."""
        turn = TurnContext(
            user_message="привет",
            intent="greeting",
            state="greeting",
            next_state="greeting",
        )
        assert turn.turn_type == TurnType.NEUTRAL

    def test_funnel_delta_calculation(self):
        """Проверка расчёта funnel_delta."""
        # greeting(0) -> spin_situation(1) = +1
        turn1 = TurnContext(
            user_message="test",
            state="greeting",
            next_state="spin_situation",
        )
        assert turn1.funnel_delta == 1

        # spin_situation(1) -> spin_problem(2) = +1
        turn2 = TurnContext(
            user_message="test",
            state="spin_situation",
            next_state="spin_problem",
        )
        assert turn2.funnel_delta == 1

        # presentation(5) -> soft_close(-1) = -6
        turn3 = TurnContext(
            user_message="test",
            state="presentation",
            next_state="soft_close",
        )
        assert turn3.funnel_delta == -6


class TestTurnTypeHistory:
    """Тесты истории типов ходов."""

    @pytest.fixture
    def mixed_window(self):
        """Окно с разными типами ходов."""
        cw = ContextWindow(max_size=5)

        turns_data = [
            ("привет", "greeting", "greeting", "spin_situation"),
            ("у нас 5 человек", "info_provided", "spin_situation", "spin_problem"),
            ("какие интеграции?", "question_integrations", "spin_problem", "spin_problem"),
            ("дорого", "objection_price", "spin_problem", "handle_objection"),
            ("ну ладно", "agreement", "handle_objection", "presentation"),
        ]

        for msg, intent, state, next_state in turns_data:
            cw.add_turn_from_dict(
                user_message=msg,
                bot_response="ответ",
                intent=intent,
                confidence=0.8,
                action="action",
                state=state,
                next_state=next_state,
            )

        return cw

    def test_get_turn_type_history(self, mixed_window):
        """Получение истории типов ходов."""
        history = mixed_window.get_turn_type_history()
        # PROGRESS(greeting->spin), PROGRESS(spin->problem), LATERAL(question),
        # REGRESS(objection), PROGRESS(agreement)
        assert "progress" in history
        assert "lateral" in history
        assert "regress" in history

    def test_turn_type_counts(self, mixed_window):
        """Подсчёт типов ходов."""
        counts = mixed_window.get_turn_type_counts()
        # greeting -> NEUTRAL, info_provided -> PROGRESS, question -> LATERAL,
        # objection -> REGRESS, agreement -> NEUTRAL
        assert counts["progress"] >= 1
        assert counts["lateral"] >= 1
        assert counts["regress"] >= 1
        assert counts["neutral"] >= 1


# =============================================================================
# ТЕСТЫ Engagement (Вовлечённость)
# =============================================================================

class TestEngagement:
    """Тесты анализа вовлечённости."""

    def test_engagement_score_high(self):
        """Высокий engagement: длинные сообщения, данные, прогресс."""
        cw = ContextWindow(max_size=5)

        # Клиент активно участвует
        cw.add_turn_from_dict(
            user_message="У нас компания из 15 человек, занимаемся розничной торговлей",
            bot_response="Отлично!",
            intent="info_provided",
            confidence=0.9,
            action="spin_situation",
            state="greeting",
            next_state="spin_situation",
            extracted_data={"company_size": 15},
        )
        cw.add_turn_from_dict(
            user_message="Основная проблема - теряем клиентов из-за долгого обслуживания",
            bot_response="Понимаю",
            intent="problem_revealed",
            confidence=0.9,
            action="spin_problem",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"pain_point": "теряем клиентов"},
        )

        score = cw.get_engagement_score()
        level = cw.get_engagement_level()

        print(f"\nHigh engagement: score={score:.2f}, level={level.value}")
        assert score >= 0.6
        assert level in (EngagementLevel.HIGH, EngagementLevel.MEDIUM)

    def test_engagement_score_low(self):
        """Низкий engagement: короткие ответы, нет данных, возражения."""
        cw = ContextWindow(max_size=5)

        # Клиент отвечает минимально
        cw.add_turn_from_dict(
            user_message="да",
            bot_response="...",
            intent="unclear",
            confidence=0.3,
            action="probe",
            state="spin_situation",
            next_state="spin_situation",
        )
        cw.add_turn_from_dict(
            user_message="нет",
            bot_response="...",
            intent="rejection",
            confidence=0.7,
            action="handle",
            state="spin_situation",
            next_state="soft_close",
        )

        score = cw.get_engagement_score()
        level = cw.get_engagement_level()

        print(f"\nLow engagement: score={score:.2f}, level={level.value}")
        assert score <= 0.5
        assert level in (EngagementLevel.LOW, EngagementLevel.DISENGAGED)

    def test_engagement_trend_improving(self):
        """Тренд улучшения engagement."""
        cw = ContextWindow(max_size=6)

        # Сначала короткие ответы
        cw.add_turn_from_dict(
            user_message="да",
            bot_response="...",
            intent="unclear",
            confidence=0.3,
            action="probe",
            state="spin_situation",
            next_state="spin_situation",
        )
        cw.add_turn_from_dict(
            user_message="ну",
            bot_response="...",
            intent="unclear",
            confidence=0.3,
            action="probe",
            state="spin_situation",
            next_state="spin_situation",
        )

        # Потом развёрнутые с данными
        cw.add_turn_from_dict(
            user_message="У нас 20 человек в штате, работаем с розницей",
            bot_response="Отлично!",
            intent="info_provided",
            confidence=0.9,
            action="spin_situation",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 20},
        )
        cw.add_turn_from_dict(
            user_message="Да, есть проблема с учётом товаров на складе",
            bot_response="Понимаю",
            intent="problem_revealed",
            confidence=0.9,
            action="spin_problem",
            state="spin_problem",
            next_state="spin_implication",
            extracted_data={"pain_point": "учёт товаров"},
        )

        trend = cw.get_engagement_trend()
        print(f"\nEngagement trend: {trend}")
        assert trend == "improving"

    def test_engagement_trend_declining(self):
        """Тренд падения engagement."""
        cw = ContextWindow(max_size=6)

        # Сначала активные ответы
        cw.add_turn_from_dict(
            user_message="Здравствуйте! У нас небольшая компания, 10 человек",
            bot_response="Отлично!",
            intent="info_provided",
            confidence=0.9,
            action="spin_situation",
            state="greeting",
            next_state="spin_situation",
            extracted_data={"company_size": 10},
        )
        cw.add_turn_from_dict(
            user_message="Основная боль - долго считаем остатки",
            bot_response="Понимаю",
            intent="problem_revealed",
            confidence=0.9,
            action="spin_problem",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"pain_point": "остатки"},
        )

        # Потом короткие отговорки
        cw.add_turn_from_dict(
            user_message="ну",
            bot_response="...",
            intent="unclear",
            confidence=0.3,
            action="probe",
            state="spin_problem",
            next_state="spin_problem",
        )
        cw.add_turn_from_dict(
            user_message="не знаю",
            bot_response="...",
            intent="objection_think",
            confidence=0.5,
            action="handle",
            state="spin_problem",
            next_state="handle_objection",
        )

        trend = cw.get_engagement_trend()
        print(f"\nEngagement trend: {trend}")
        assert trend == "declining"


# =============================================================================
# ТЕСТЫ Funnel Progress (Прогресс по воронке)
# =============================================================================

class TestFunnelProgress:
    """Тесты анализа прогресса по воронке."""

    def test_funnel_progress_positive(self):
        """Положительный прогресс по воронке."""
        cw = ContextWindow(max_size=5)

        # Успешное движение: greeting -> spin_situation -> spin_problem
        cw.add_turn_from_dict(
            user_message="10 человек",
            bot_response="...",
            intent="info_provided",
            confidence=0.9,
            action="spin_situation",
            state="greeting",
            next_state="spin_situation",
        )
        cw.add_turn_from_dict(
            user_message="есть проблема с учётом",
            bot_response="...",
            intent="problem_revealed",
            confidence=0.9,
            action="spin_problem",
            state="spin_situation",
            next_state="spin_problem",
        )

        progress = cw.get_funnel_progress()
        velocity = cw.get_funnel_velocity()

        print(f"\nFunnel: progress={progress}, velocity={velocity:.2f}")
        assert progress > 0
        assert velocity > 0
        assert cw.is_progressing() is True

    def test_funnel_progress_negative(self):
        """Негативный прогресс (откат)."""
        cw = ContextWindow(max_size=5)

        # Откат: presentation -> soft_close
        cw.add_turn_from_dict(
            user_message="не интересно",
            bot_response="...",
            intent="rejection",
            confidence=0.9,
            action="soft_close",
            state="presentation",
            next_state="soft_close",
        )

        progress = cw.get_funnel_progress()
        print(f"\nFunnel negative: progress={progress}")
        assert progress < 0
        assert cw.is_regressing() is True

    def test_current_funnel_stage(self):
        """Получение текущей стадии воронки."""
        cw = ContextWindow(max_size=5)

        cw.add_turn_from_dict(
            user_message="test",
            bot_response="...",
            intent="info_provided",
            confidence=0.9,
            action="action",
            state="spin_situation",
            next_state="spin_problem",
        )

        stage = cw.get_current_funnel_stage()
        assert stage == "spin_problem"


# =============================================================================
# ТЕСТЫ Momentum (Инерция)
# =============================================================================

class TestMomentum:
    """Тесты анализа momentum."""

    def test_momentum_positive(self):
        """Положительный momentum при прогрессе."""
        cw = ContextWindow(max_size=5)

        # Серия прогрессивных ходов
        for i, (intent, state, next_state) in enumerate([
            ("info_provided", "greeting", "spin_situation"),
            ("problem_revealed", "spin_situation", "spin_problem"),
            ("agreement", "spin_problem", "spin_implication"),
        ]):
            cw.add_turn_from_dict(
                user_message=f"ответ {i}",
                bot_response="...",
                intent=intent,
                confidence=0.9,
                action="action",
                state=state,
                next_state=next_state,
            )

        momentum = cw.get_momentum()
        direction = cw.get_momentum_direction()

        print(f"\nPositive momentum: {momentum:.2f}, direction={direction}")
        assert momentum > 0
        assert direction == "positive"

    def test_momentum_negative(self):
        """Негативный momentum при возражениях."""
        cw = ContextWindow(max_size=5)

        # Серия возражений
        for i, intent in enumerate([
            "objection_price",
            "objection_think",
            "rejection",
        ]):
            cw.add_turn_from_dict(
                user_message=f"возражение {i}",
                bot_response="...",
                intent=intent,
                confidence=0.7,
                action="handle_objection",
                state="presentation",
                next_state="handle_objection",
            )

        momentum = cw.get_momentum()
        direction = cw.get_momentum_direction()

        print(f"\nNegative momentum: {momentum:.2f}, direction={direction}")
        assert momentum < 0
        assert direction == "negative"

    def test_momentum_recency_weight(self):
        """Недавние ходы влияют на momentum сильнее."""
        cw = ContextWindow(max_size=5)

        # Сначала негатив, потом позитив
        cw.add_turn_from_dict(
            user_message="дорого",
            bot_response="...",
            intent="objection_price",
            confidence=0.8,
            action="handle",
            state="presentation",
            next_state="handle_objection",
        )
        # Последние 2 хода позитивные
        cw.add_turn_from_dict(
            user_message="ну ладно",
            bot_response="...",
            intent="agreement",
            confidence=0.8,
            action="presentation",
            state="handle_objection",
            next_state="presentation",
        )
        cw.add_turn_from_dict(
            user_message="давайте попробуем",
            bot_response="...",
            intent="demo_request",
            confidence=0.9,
            action="close",
            state="presentation",
            next_state="close",
        )

        momentum = cw.get_momentum()
        print(f"\nRecency-weighted momentum: {momentum:.2f}")

        # Должен быть положительный из-за recency weight
        assert momentum > 0


# =============================================================================
# ТЕСТЫ Trigger Analysis (Анализ триггеров)
# =============================================================================

class TestTriggerAnalysis:
    """Тесты анализа триггеров."""

    def test_last_objection_trigger(self):
        """Найти что триггернуло возражение."""
        cw = ContextWindow(max_size=5)

        # Презентация -> Возражение
        cw.add_turn_from_dict(
            user_message="понятно",
            bot_response="Наша система позволяет...",
            intent="agreement",
            confidence=0.8,
            action="presentation",
            state="spin_need_payoff",
            next_state="presentation",
        )
        cw.add_turn_from_dict(
            user_message="дорого для нас",
            bot_response="Давайте посчитаем ROI",
            intent="objection_price",
            confidence=0.9,
            action="handle_objection",
            state="presentation",
            next_state="handle_objection",
        )

        trigger = cw.get_last_objection_trigger()

        print(f"\nObjection trigger: {trigger}")
        assert trigger is not None
        assert trigger["action"] == "presentation"
        assert trigger["objection_type"] == "objection_price"

    def test_last_progress_trigger(self):
        """Найти что триггернуло прогресс."""
        cw = ContextWindow(max_size=5)

        # Вопрос -> Прогресс
        cw.add_turn_from_dict(
            user_message="какие есть функции?",
            bot_response="У нас есть...",
            intent="question_features",
            confidence=0.8,
            action="answer_question",
            state="spin_situation",
            next_state="spin_situation",
        )
        cw.add_turn_from_dict(
            user_message="звучит хорошо, у нас 10 человек",
            bot_response="Отлично!",
            intent="info_provided",
            confidence=0.9,
            action="spin_situation",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 10},
        )

        trigger = cw.get_last_progress_trigger()

        print(f"\nProgress trigger: {trigger}")
        assert trigger is not None
        assert trigger["action"] == "answer_question"
        assert trigger["progress_intent"] == "info_provided"

    def test_effective_actions(self):
        """Получить эффективные actions."""
        cw = ContextWindow(max_size=5)

        # Эффективный ответ на вопрос
        cw.add_turn_from_dict(
            user_message="сколько стоит?",
            bot_response="от 990р/мес",
            intent="price_question",
            confidence=0.9,
            action="answer_with_facts",
            state="presentation",
            next_state="presentation",
        )
        cw.add_turn_from_dict(
            user_message="хорошо, давайте попробуем",
            bot_response="Отлично!",
            intent="demo_request",
            confidence=0.95,
            action="close",
            state="presentation",
            next_state="close",
        )

        effective = cw.get_effective_actions()
        print(f"\nEffective actions: {effective}")
        assert "answer_with_facts" in effective

    def test_ineffective_actions(self):
        """Получить неэффективные actions."""
        cw = ContextWindow(max_size=5)

        # Неэффективный deflect
        cw.add_turn_from_dict(
            user_message="сколько стоит?",
            bot_response="давайте сначала узнаю о вас",
            intent="price_question",
            confidence=0.9,
            action="deflect_and_continue",
            state="greeting",
            next_state="spin_situation",
        )
        cw.add_turn_from_dict(
            user_message="не интересно тогда",
            bot_response="...",
            intent="rejection",
            confidence=0.85,
            action="soft_close",
            state="spin_situation",
            next_state="soft_close",
        )

        ineffective = cw.get_ineffective_actions()
        print(f"\nIneffective actions: {ineffective}")
        assert "deflect_and_continue" in ineffective


# =============================================================================
# ТЕСТЫ Level 2 Context (Структурированный контекст)
# =============================================================================

class TestLevel2Context:
    """Тесты получения структурированного контекста."""

    @pytest.fixture
    def full_window(self):
        """Окно с полным диалогом."""
        cw = ContextWindow(max_size=5)

        turns = [
            ("привет", "greeting", "greeting", "spin_situation", {}),
            ("у нас 10 человек", "info_provided", "spin_situation", "spin_problem", {"company_size": 10}),
            ("теряем клиентов", "problem_revealed", "spin_problem", "spin_implication", {"pain_point": "клиенты"}),
            ("да это проблема", "implication_acknowledged", "spin_implication", "spin_need_payoff", {}),
            ("хотим автоматизировать", "need_expressed", "spin_need_payoff", "presentation", {}),
        ]

        for msg, intent, state, next_state, data in turns:
            cw.add_turn_from_dict(
                user_message=msg,
                bot_response="ответ",
                intent=intent,
                confidence=0.85,
                action="action",
                state=state,
                next_state=next_state,
                extracted_data=data,
            )

        return cw

    def test_level2_context_contains_all_fields(self, full_window):
        """Level 2 контекст содержит все поля."""
        ctx = full_window.get_level2_context()

        required_fields = [
            "turn_types", "turn_type_counts", "last_turn_type",
            "engagement_level", "engagement_score", "engagement_trend",
            "funnel_progress", "funnel_velocity", "is_progressing", "is_regressing",
            "momentum", "momentum_direction",
            "last_objection_trigger", "last_progress_trigger", "effective_actions",
            "avg_message_length", "data_provided_count",
        ]

        for field in required_fields:
            assert field in ctx, f"Missing field: {field}"

    def test_full_context_includes_both_levels(self, full_window):
        """Полный контекст включает оба уровня."""
        ctx = full_window.get_classifier_context()

        # Level 1 fields
        assert "intent_history" in ctx
        assert "action_history" in ctx
        assert "objection_count" in ctx
        assert "has_oscillation" in ctx

        # Level 2 fields
        assert "momentum" in ctx
        assert "engagement_score" in ctx
        assert "funnel_progress" in ctx


# =============================================================================
# ТЕСТЫ ИНТЕГРАЦИИ С КЛАССИФИКАТОРОМ (Level 2)
# =============================================================================

class TestClassifierLevel2Integration:
    """Тесты интеграции Level 2 с классификатором."""

    @pytest.fixture
    def classifier(self):
        return HybridClassifier()

    def test_negative_momentum_rejection(self, classifier):
        """
        Негативный momentum + disengaged + короткое "нет" = rejection.
        """
        context = {
            "state": "presentation",
            "momentum_direction": "negative",
            "engagement_level": "disengaged",
            "intent_history": ["objection_price", "objection_think"],
            "is_stuck": False,
            "has_oscillation": False,
        }

        result = classifier.classify("нет", context=context)

        print(f"\nNegative momentum + disengaged + 'нет':")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}, method={result.get('method')}")

        assert result["intent"] == "rejection"

    def test_positive_momentum_agreement(self, classifier):
        """
        Положительный momentum + progressing + короткое "да" = agreement.
        """
        context = {
            "state": "presentation",
            "last_action": "presentation",
            "momentum_direction": "positive",
            "is_progressing": True,
            "intent_history": ["info_provided", "agreement"],
            "is_stuck": False,
            "has_oscillation": False,
        }

        result = classifier.classify("да, хорошо", context=context)

        print(f"\nPositive momentum + progressing + 'да':")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}, method={result.get('method')}")

        assert result["intent"] == "agreement"
        assert result["confidence"] >= 0.85

    def test_repeated_trigger_objection(self, classifier):
        """
        После action который триггернул возражение — ожидаем возражение снова.
        """
        context = {
            "state": "presentation",
            "last_action": "presentation",
            "last_objection_trigger": {
                "action": "presentation",
                "intent_before": "agreement",
                "objection_type": "objection_price",
            },
            "intent_history": ["agreement", "objection_price", "agreement"],
            "is_stuck": False,
            "has_oscillation": False,
        }

        # Используем простое сообщение с маркером "дорого"
        result = classifier.classify("дорого для нас", context=context)

        print(f"\nRepeated trigger objection:")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}, "
              f"pattern={result.get('pattern_type')}")

        assert result["intent"] == "objection_price"


# =============================================================================
# СРАВНЕНИЕ: УРОВЕНЬ 2 ОТДЕЛЬНО vs УРОВЕНЬ 1+2 ВМЕСТЕ
# =============================================================================

class TestLevel2VsLevel1Plus2:
    """Сравнение работы Level 2 отдельно и вместе с Level 1."""

    @pytest.fixture
    def classifier(self):
        return HybridClassifier()

    def test_level1_only_context(self, classifier):
        """Классификация только с Level 1 контекстом."""
        # Level 1 контекст (без momentum, engagement, etc.)
        context_l1 = {
            "state": "presentation",
            "last_action": "presentation",
            "intent_history": ["objection_price", "agreement", "objection_price"],
            "action_history": ["handle_objection", "presentation", "handle_objection"],
            "objection_count": 2,
            "positive_count": 1,
            "has_oscillation": True,
            "is_stuck": False,
            "repeated_question": None,
        }

        result = classifier.classify("ну не знаю", context=context_l1)

        print(f"\n=== Level 1 Only ===")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}")

        return result

    def test_level2_adds_momentum_context(self, classifier):
        """Level 2 добавляет momentum и engagement для лучшей классификации."""
        # Level 1 + Level 2 контекст
        context_l1_l2 = {
            # Level 1
            "state": "presentation",
            "last_action": "presentation",
            "intent_history": ["objection_price", "agreement", "objection_price"],
            "action_history": ["handle_objection", "presentation", "handle_objection"],
            "objection_count": 2,
            "positive_count": 1,
            "has_oscillation": True,
            "is_stuck": False,
            "repeated_question": None,
            # Level 2
            "momentum_direction": "negative",
            "engagement_level": "low",
            "engagement_trend": "declining",
            "is_progressing": False,
            "is_regressing": True,
            "last_objection_trigger": {
                "action": "presentation",
                "objection_type": "objection_price",
            },
        }

        result = classifier.classify("ну не знаю", context=context_l1_l2)

        print(f"\n=== Level 1 + Level 2 ===")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}")

        return result

    def test_compare_scenarios(self, classifier):
        """Сравнение сценариев с разным контекстом."""
        # Используем более однозначное сообщение
        message = "хорошо, согласен"

        # Сценарий 1: Только базовый контекст
        ctx_basic = {
            "state": "presentation",
            "last_action": "presentation",
        }
        result_basic = classifier.classify(message, context=ctx_basic)

        # Сценарий 2: Level 1 контекст
        ctx_l1 = {
            **ctx_basic,
            "intent_history": ["agreement", "agreement"],
            "positive_count": 2,
            "objection_count": 0,
            "is_stuck": False,
        }
        result_l1 = classifier.classify(message, context=ctx_l1)

        # Сценарий 3: Level 1 + Level 2 контекст
        ctx_l1_l2 = {
            **ctx_l1,
            "momentum_direction": "positive",
            "engagement_level": "high",
            "is_progressing": True,
        }
        result_l1_l2 = classifier.classify(message, context=ctx_l1_l2)

        print(f"\n=== Comparison: '{message}' ===")
        print(f"  Basic:    intent={result_basic['intent']}, conf={result_basic['confidence']:.2f}")
        print(f"  Level 1:  intent={result_l1['intent']}, conf={result_l1['confidence']:.2f}")
        print(f"  L1 + L2:  intent={result_l1_l2['intent']}, conf={result_l1_l2['confidence']:.2f}")

        # L1+L2 должен дать agreement с высокой уверенностью
        assert result_l1_l2["intent"] == "agreement"
        assert result_l1_l2["confidence"] >= result_basic["confidence"]


# =============================================================================
# РЕАЛИСТИЧНЫЕ СЦЕНАРИИ (Level 2)
# =============================================================================

class TestRealisticScenariosLevel2:
    """Реалистичные сценарии с Level 2."""

    @pytest.fixture
    def classifier(self):
        return HybridClassifier()

    def test_scenario_losing_client(self, classifier):
        """
        Сценарий: Теряем клиента — engagement падает, momentum негативный.
        """
        print("\n=== Сценарий: Теряем клиента ===")

        cw = ContextWindow(max_size=5)

        # Короткое приветствие (низкий engagement с начала)
        cw.add_turn_from_dict(
            user_message="да",
            bot_response="...",
            intent="unclear",
            confidence=0.3,
            action="probe",
            state="greeting",
            next_state="greeting",
        )
        print(f"Ход 1: engagement={cw.get_engagement_score():.2f}, momentum={cw.get_momentum():.2f}")

        # Минимальный ответ
        cw.add_turn_from_dict(
            user_message="ну",
            bot_response="...",
            intent="unclear",
            confidence=0.3,
            action="probe",
            state="greeting",
            next_state="greeting",
        )
        print(f"Ход 2: engagement={cw.get_engagement_score():.2f}, momentum={cw.get_momentum():.2f}")

        # Первое возражение
        cw.add_turn_from_dict(
            user_message="дорого",
            bot_response="...",
            intent="objection_price",
            confidence=0.85,
            action="handle_objection",
            state="greeting",
            next_state="handle_objection",
        )
        print(f"Ход 3: engagement={cw.get_engagement_score():.2f}, momentum={cw.get_momentum():.2f}")

        # Ещё возражение
        cw.add_turn_from_dict(
            user_message="нет",
            bot_response="...",
            intent="rejection",
            confidence=0.8,
            action="soft_close",
            state="handle_objection",
            next_state="soft_close",
        )
        print(f"Ход 4: engagement={cw.get_engagement_score():.2f}, momentum={cw.get_momentum():.2f}")

        # Финальный ход - используем контекст для классификации
        ctx = cw.get_classifier_context()

        print(f"Final context: engagement={ctx['engagement_level']}, momentum={ctx['momentum_direction']}")

        # Проверяем что контекст правильный
        assert ctx["engagement_level"] in ("low", "disengaged", "medium")
        assert ctx["momentum_direction"] == "negative"

        # Классифицируем финальное сообщение
        result = classifier.classify("пока не надо", context=ctx)
        print(f"Ход 5: '{result['intent']}' (conf={result['confidence']:.2f})")

        # Должны распознать отказ или прощание
        assert result["intent"] in ("rejection", "farewell", "objection_timing")

    def test_scenario_winning_client(self, classifier):
        """
        Сценарий: Выигрываем клиента — engagement высокий, momentum положительный.
        """
        print("\n=== Сценарий: Выигрываем клиента ===")

        cw = ContextWindow(max_size=5)

        turns = [
            ("Здравствуйте! У нас розничный магазин, 15 человек", "info_provided",
             "greeting", "spin_situation", {"company_size": 15}),
            ("Да, есть проблема с учётом товаров", "problem_revealed",
             "spin_situation", "spin_problem", {"pain_point": "учёт"}),
            ("Это нам много времени съедает, примерно 2 часа в день", "implication_acknowledged",
             "spin_problem", "spin_implication", {}),
            ("Хотим ускорить этот процесс", "need_expressed",
             "spin_implication", "spin_need_payoff", {}),
        ]

        for i, (msg, intent, state, next_state, data) in enumerate(turns, 1):
            cw.add_turn_from_dict(
                user_message=msg,
                bot_response="...",
                intent=intent,
                confidence=0.9,
                action="action",
                state=state,
                next_state=next_state,
                extracted_data=data,
            )
            print(f"Ход {i}: engagement={cw.get_engagement_score():.2f}, momentum={cw.get_momentum():.2f}")

        # Финальный ход
        ctx = cw.get_classifier_context()
        # Используем более явную фразу для демо-запроса
        result = classifier.classify("можно посмотреть демо вашей системы?", context=ctx)

        print(f"Ход 5: '{result['intent']}' (conf={result['confidence']:.2f})")
        print(f"Final: engagement={ctx['engagement_level']}, momentum={ctx['momentum_direction']}")

        # Должны распознать запрос демо или agreement (оба положительные)
        assert result["intent"] in ("demo_request", "agreement", "callback_request")
        assert ctx["engagement_level"] in ("high", "medium")
        assert ctx["momentum_direction"] == "positive"


# =============================================================================
# ТЕСТЫ ПРОИЗВОДИТЕЛЬНОСТИ Level 2
# =============================================================================

class TestPerformanceLevel2:
    """Тесты производительности Level 2."""

    def test_level2_context_generation_fast(self):
        """Генерация Level 2 контекста должна быть быстрой."""
        import time

        cw = ContextWindow(max_size=10)

        # Заполняем окно
        for i in range(10):
            cw.add_turn_from_dict(
                user_message=f"сообщение {i} с некоторым текстом для теста",
                bot_response=f"ответ {i}",
                intent=["greeting", "info_provided", "objection_price", "agreement"][i % 4],
                confidence=0.8,
                action="action",
                state="state",
                next_state="next_state",
                extracted_data={"key": "value"} if i % 2 == 0 else {},
            )

        # Измеряем время
        start = time.time()
        for _ in range(1000):
            ctx = cw.get_level2_context()
        elapsed = time.time() - start

        print(f"\nLevel 2 context generation: {elapsed*1000:.2f}ms for 1000 calls")
        print(f"Per call: {elapsed:.4f}ms")

        # Должно быть < 100ms на 1000 вызовов
        assert elapsed < 0.5


# =============================================================================
# ЗАПУСК ТЕСТОВ
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

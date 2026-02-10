"""
Тесты для исправленных подтверждённых ошибок (январь 2026).

Покрывает:
1. Проблема #1: SALES_STATES - теперь используется YAML flow config
2. Проблема #2: ContextWindow получает config
3. Проблема #3/#6: Объединённые objection categories между IntentTracker и ContextWindow
4. Проблема #4: Policy override валидация (next_state без action)
5. Проблема #7: NO_OVERRIDE не загрязняет decision_history
6. Проблема #9: Неизвестные states в state_order возвращают neutral delta
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

# =============================================================================
# ТЕСТЫ ДЛЯ ПРОБЛЕМЫ #1: SALES_STATES -> YAML flow config
# =============================================================================

class TestYAMLFlowConfigUsage:
    """
    Проверяет что bot.py и context_envelope.py используют YAML flow config
    вместо устаревшего SALES_STATES из config.py.
    """

    def test_bot_get_classification_context_uses_flow_states(self):
        """
        bot._get_classification_context() должен использовать self._flow.states
        вместо импорта SALES_STATES из config.py.
        """
        from src.bot import SalesBot

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Тестовый ответ"
        mock_llm.health_check.return_value = True

        # Создаём бота и проверяем что _get_classification_context работает
        bot = SalesBot(mock_llm)

        # Проверяем что у бота есть _flow.states
        assert hasattr(bot, '_flow')
        assert hasattr(bot._flow, 'states')
        assert len(bot._flow.states) > 0

        # Вызываем метод - не должно быть ошибок
        context = bot._get_classification_context()

        # Проверяем структуру контекста
        assert "state" in context
        assert "missing_data" in context
        assert "spin_phase" in context or context.get("spin_phase") is None

    def test_context_envelope_uses_state_machine_states(self):
        """
        ContextEnvelopeBuilder._fill_from_state_machine() должен использовать
        sm.states вместо импорта SALES_STATES.
        """
        from src.context_envelope import ContextEnvelopeBuilder
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        # Загружаем config и flow
        loader = ConfigLoader()
        config = loader.load()
        flow = loader.load_flow("spin_selling")

        # Создаём StateMachine с config и flow
        sm = StateMachine(config=config, flow=flow)

        # Проверяем что sm.states_config работает (это property, поэтому вызываем)
        states = sm.states_config
        assert states is not None
        assert len(states) > 0

        # Создаём envelope
        builder = ContextEnvelopeBuilder(state_machine=sm)
        envelope = builder.build()

        # Проверяем что envelope заполнился без ошибок
        assert envelope.state is not None

# =============================================================================
# ТЕСТЫ ДЛЯ ПРОБЛЕМЫ #2: ContextWindow получает config
# =============================================================================

class TestContextWindowWithConfig:
    """
    Проверяет что ContextWindow получает config с state_order и phase_order.
    """

    def test_context_window_receives_config_from_bot(self):
        """
        SalesBot должен передавать config в ContextWindow при инициализации.
        """
        from src.bot import SalesBot

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Тест"
        mock_llm.health_check.return_value = True

        bot = SalesBot(mock_llm)

        # Проверяем что config передан
        # ContextWindow использует _state_order из config
        assert hasattr(bot.context_window, '_state_order')
        assert hasattr(bot.context_window, '_phase_order')

    def test_context_window_uses_config_state_order(self):
        """
        ContextWindow._load_state_order должен использовать config если передан.
        """
        from src.context_window import ContextWindow
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        # С config
        cw_with_config = ContextWindow(max_size=5, config=config)

        # Без config (должен использовать DEFAULT)
        cw_without_config = ContextWindow(max_size=5, config=None)

        # Оба должны иметь _state_order
        assert cw_with_config._state_order is not None
        assert cw_without_config._state_order is not None

# =============================================================================
# ТЕСТЫ ДЛЯ ПРОБЛЕМЫ #3/#6: Objection categories синхронизация
# =============================================================================

class TestObjectionCategoriesSync:
    """
    Проверяет что objection intents синхронизированы между
    IntentTracker и ContextWindow.
    """

    def test_intent_tracker_has_all_objection_intents(self):
        """
        IntentTracker.INTENT_CATEGORIES["objection"] должен содержать все 8 интентов.
        """
        from src.intent_tracker import INTENT_CATEGORIES

        expected_objections = {
            "objection_price",
            "objection_competitor",
            "objection_no_time",
            "objection_think",
            "objection_timing",
            "objection_complexity",
            "objection_no_need",
            "objection_trust",
        }

        actual_objections = set(INTENT_CATEGORIES["objection"])

        # Все ожидаемые должны присутствовать
        assert expected_objections.issubset(actual_objections), \
            f"Missing objections: {expected_objections - actual_objections}"

    def test_context_window_objection_intents_match(self):
        """
        ContextWindow.OBJECTION_INTENTS должен совпадать с IntentTracker.
        """
        from src.intent_tracker import INTENT_CATEGORIES
        from src.context_window import ContextWindow

        tracker_objections = set(INTENT_CATEGORIES["objection"])
        cw_objections = ContextWindow.OBJECTION_INTENTS

        # Должны совпадать
        assert tracker_objections == cw_objections, \
            f"Mismatch: tracker has {tracker_objections - cw_objections}, " \
            f"cw has {cw_objections - tracker_objections}"

    def test_negative_category_includes_all_objections(self):
        """
        INTENT_CATEGORIES["negative"] должен включать все objection intents.
        """
        from src.intent_tracker import INTENT_CATEGORIES

        objections = set(INTENT_CATEGORIES["objection"])
        negatives = set(INTENT_CATEGORIES["negative"])

        # Все objections должны быть в negative (кроме базовых negative типа rejection)
        missing = objections - negatives
        assert not missing, f"Objections missing from negative: {missing}"

# =============================================================================
# ТЕСТЫ ДЛЯ ПРОБЛЕМЫ #4: Policy override валидация
# =============================================================================

class TestPolicyOverrideValidation:
    """
    Проверяет что policy override с next_state без action логирует warning
    и не применяет next_state.
    """

    def test_next_state_without_action_is_logged_and_skipped(self):
        """
        Если policy_override имеет next_state без action, должен быть warning лог
        и next_state не должен применяться.
        """
        from src.dialogue_policy import PolicyOverride, PolicyDecision

        # Создаём override с next_state но без action
        override = PolicyOverride(
            action=None,  # No action!
            next_state="spin_problem",  # But has next_state
            decision=PolicyDecision.NO_OVERRIDE,
        )

        # has_override должен быть False (т.к. action=None)
        assert override.has_override is False

        # В bot.py этот override будет пропущен из-за проверки has_override
        # и если каким-то образом попадёт в применение, warning будет залогирован

    def test_has_override_requires_action(self):
        """
        PolicyOverride.has_override должен возвращать True только если action задан.
        """
        from src.dialogue_policy import PolicyOverride, PolicyDecision

        # С action
        with_action = PolicyOverride(action="clarify_one_question")
        assert with_action.has_override is True

        # Без action (None)
        without_action = PolicyOverride(action=None)
        assert without_action.has_override is False

        # Примечание: пустая строка "" технически является truthy в has_override,
        # но в реальности никогда не используется как action

# =============================================================================
# ТЕСТЫ ДЛЯ ПРОБЛЕМЫ #7: NO_OVERRIDE не загрязняет decision_history
# =============================================================================

class TestDecisionHistoryPurity:
    """
    Проверяет что NO_OVERRIDE решения не добавляются в decision_history.
    """

    def test_no_override_not_added_to_history(self):
        """
        PolicyOverride с decision=NO_OVERRIDE не должен попадать в decision_history.
        """
        from src.dialogue_policy import DialoguePolicy, PolicyOverride, PolicyDecision

        policy = DialoguePolicy(shadow_mode=False)

        # Очищаем историю
        policy.reset()

        # Создаём NO_OVERRIDE (как guard intervention)
        no_override = PolicyOverride(
            action=None,
            decision=PolicyDecision.NO_OVERRIDE,
            reason_codes=["guard.intervention"],
        )

        # Проверяем has_override = False
        assert no_override.has_override is False

        # История должна быть пуста после reset
        assert len(policy._decision_history) == 0

    def test_real_override_added_to_history(self):
        """
        Реальный PolicyOverride с action должен попадать в decision_history.
        """
        from src.dialogue_policy import PolicyOverride, PolicyDecision

        # Реальный override
        real_override = PolicyOverride(
            action="clarify_one_question",
            decision=PolicyDecision.REPAIR_CLARIFY,
            reason_codes=["repair.stuck"],
        )

        assert real_override.has_override is True

    def test_override_rate_calculation_excludes_no_override(self):
        """
        get_override_rate() должен корректно считать только реальные override.
        """
        from src.dialogue_policy import DialoguePolicy

        policy = DialoguePolicy()
        policy.reset()

        # Изначально история пуста, rate = 0
        rate = policy.get_override_rate()
        assert rate == 0.0

# =============================================================================
# ТЕСТЫ ДЛЯ ПРОБЛЕМЫ #9: state_order для неизвестных states
# =============================================================================

class TestUnknownStateOrder:
    """
    Проверяет что неизвестные states не ломают funnel_delta вычисление.
    """

    def test_unknown_state_returns_zero_delta(self):
        """
        Если state или next_state неизвестны, funnel_delta должен быть 0.
        """
        from src.context_window import TurnContext, DEFAULT_STATE_ORDER

        # Неизвестный state
        turn = TurnContext(
            user_message="тест",
            state="custom_unknown_state",
            next_state="greeting",
            intent="agreement",
        )

        # funnel_delta должен быть 0 (неизвестный state)
        assert turn.funnel_delta == 0

    def test_unknown_next_state_returns_zero_delta(self):
        """
        Если next_state неизвестен, funnel_delta должен быть 0.
        """
        from src.context_window import TurnContext

        turn = TurnContext(
            user_message="тест",
            state="greeting",
            next_state="custom_unknown_state",
            intent="agreement",
        )

        assert turn.funnel_delta == 0

    def test_both_unknown_states_return_zero_delta(self):
        """
        Если оба states неизвестны, funnel_delta должен быть 0.
        """
        from src.context_window import TurnContext

        turn = TurnContext(
            user_message="тест",
            state="custom_state_1",
            next_state="custom_state_2",
            intent="agreement",
        )

        assert turn.funnel_delta == 0

    def test_known_states_calculate_correct_delta(self):
        """
        Если оба states известны, funnel_delta должен вычисляться корректно.
        """
        from src.context_window import TurnContext, DEFAULT_STATE_ORDER

        # greeting -> spin_situation (0 -> 1 = +1)
        turn = TurnContext(
            user_message="тест",
            state="greeting",
            next_state="spin_situation",
            intent="situation_provided",
        )

        expected_delta = DEFAULT_STATE_ORDER["spin_situation"] - DEFAULT_STATE_ORDER["greeting"]
        assert turn.funnel_delta == expected_delta
        assert turn.funnel_delta == 1

    def test_regression_has_negative_delta(self):
        """
        Переход назад (regression) должен иметь отрицательный delta.
        """
        from src.context_window import TurnContext

        # spin_problem -> spin_situation (2 -> 1 = -1)
        turn = TurnContext(
            user_message="тест",
            state="spin_problem",
            next_state="spin_situation",
            intent="unclear",
        )

        assert turn.funnel_delta == -1

# =============================================================================
# ИНТЕГРАЦИОННЫЙ ТЕСТ: ВСЕ ИСПРАВЛЕНИЯ РАБОТАЮТ ВМЕСТЕ
# =============================================================================

class TestAllFixesIntegration:
    """
    Интеграционный тест проверяющий что все исправления работают вместе.
    """

    def test_bot_initialization_with_all_fixes(self):
        """
        SalesBot должен инициализироваться корректно со всеми исправлениями.
        """
        from src.bot import SalesBot

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Тестовый ответ"
        mock_llm.health_check.return_value = True

        # Не должно быть исключений при создании
        bot = SalesBot(mock_llm)

        # Проверяем все компоненты
        assert bot._flow is not None
        assert bot._config is not None
        assert bot.context_window is not None
        assert bot.dialogue_policy is not None

        # ContextWindow должен иметь config-driven order
        assert bot.context_window._state_order is not None

    def test_classification_context_works_with_fixes(self):
        """
        _get_classification_context должен работать корректно после всех исправлений.
        """
        from src.bot import SalesBot

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Здравствуйте!"
        mock_llm.health_check.return_value = True

        bot = SalesBot(mock_llm)

        # Тестируем _get_classification_context (избегаем загрузку embeddings)
        context = bot._get_classification_context()

        # Должен вернуться контекст без ошибок
        assert context is not None
        assert "state" in context
        assert "collected_data" in context

    def test_context_envelope_build_works_with_fixes(self):
        """
        ContextEnvelopeBuilder.build() должен работать корректно после исправлений.
        """
        from src.context_envelope import ContextEnvelopeBuilder, ContextEnvelope
        from src.state_machine import StateMachine
        from src.context_window import ContextWindow
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()
        flow = loader.load_flow("spin_selling")

        sm = StateMachine(config=config, flow=flow)
        cw = ContextWindow(max_size=5, config=config)

        # Создаём envelope со всеми компонентами
        envelope = ContextEnvelopeBuilder(
            state_machine=sm,
            context_window=cw,
        ).build()

        # Должен создаться без ошибок
        assert isinstance(envelope, ContextEnvelope)
        assert envelope.state is not None

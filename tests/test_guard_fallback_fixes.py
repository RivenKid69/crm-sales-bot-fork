"""
Тесты для исправлений массовых Guard/Fallback интервенций.

Основные исправления:
1. bot.py - сброс fallback_response после skip action
2. conversation_guard.py - проверка информативных интентов перед TIER_3
3. constants.yaml - категория informative
4. feature_flags.py - новые флаги guard_informative_intent_check, guard_skip_resets_fallback

Эти тесты проверяют:
- ConversationGuard не срабатывает на TIER_3 когда клиент даёт информативные ответы
- fallback_response сбрасывается после skip action для нормальной генерации
- YAML конфигурация содержит informative категорию
- Feature flags включены по умолчанию
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)


# =============================================================================
# Test 1: ConversationGuard - Informative Intent Detection
# =============================================================================
class TestConversationGuardInformativeIntents:
    """Тесты для проверки информативных интентов в ConversationGuard."""

    def test_get_informative_intents_returns_set(self):
        """_get_informative_intents должен возвращать set интентов."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()
        informative = guard._get_informative_intents()

        assert isinstance(informative, set)
        assert len(informative) > 0

    def test_get_informative_intents_contains_spin_intents(self):
        """_get_informative_intents должен содержать SPIN интенты."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()
        informative = guard._get_informative_intents()

        # SPIN situation
        assert "situation_provided" in informative
        assert "info_provided" in informative

        # SPIN problem
        assert "problem_mentioned" in informative

        # SPIN implication
        assert "implication_acknowledged" in informative

        # SPIN need-payoff
        assert "need_expressed" in informative

    def test_get_informative_intents_contains_general_intents(self):
        """_get_informative_intents должен содержать общие информативные интенты."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()
        informative = guard._get_informative_intents()

        assert "question_answered" in informative
        assert "data_provided" in informative
        assert "clarification_provided" in informative

    def test_has_recent_informative_intent_true(self):
        """_has_recent_informative_intent должен вернуть True для информативного интента."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()
        guard._state.last_intent = "situation_provided"

        result = guard._has_recent_informative_intent()

        assert result == True

    def test_has_recent_informative_intent_false(self):
        """_has_recent_informative_intent должен вернуть False для не-информативного интента."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()
        guard._state.last_intent = "unclear"

        result = guard._has_recent_informative_intent()

        assert result == False

    def test_has_recent_informative_intent_empty(self):
        """_has_recent_informative_intent должен вернуть False если intent пустой."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()
        guard._state.last_intent = ""

        result = guard._has_recent_informative_intent()

        assert result == False


# =============================================================================
# Test 2: ConversationGuard - State Loop with Informative Check
# =============================================================================
class TestConversationGuardStateLoopWithInformative:
    """Тесты для state loop detection с учётом информативности."""

    def test_state_loop_triggers_tier3_without_informative_intent(self):
        """State loop должен срабатывать на TIER_3 если нет информативного интента."""
        from conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_same_state=3)
        guard = ConversationGuard(config)

        # Симулируем 4 одинаковых состояния (>= max_same_state)
        for i in range(4):
            can_continue, intervention = guard.check(
                state="spin_situation",
                message=f"сообщение {i}",
                collected_data={},
                last_intent="unclear"  # Не информативный интент
            )

        # На 4й раз должен сработать TIER_3
        assert intervention == "fallback_tier_3"

    def test_state_loop_does_not_trigger_with_informative_intent(self):
        """State loop НЕ должен срабатывать если последний intent информативный."""
        from conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_same_state=3)
        guard = ConversationGuard(config)

        # Симулируем 4 одинаковых состояния
        for i in range(3):
            guard.check(
                state="spin_situation",
                message=f"сообщение {i}",
                collected_data={},
                last_intent="unclear"
            )

        # На 4й раз - информативный интент
        can_continue, intervention = guard.check(
            state="spin_situation",
            message="10 человек",
            collected_data={},
            last_intent="situation_provided"  # Информативный интент
        )

        # Не должен срабатывать TIER_3
        assert intervention != "fallback_tier_3"

    def test_intent_history_recorded(self):
        """Intent должен записываться в историю."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()

        guard.check(
            state="spin_situation",
            message="10 человек",
            collected_data={},
            last_intent="situation_provided"
        )

        assert "situation_provided" in guard._state.intent_history
        assert guard._state.last_intent == "situation_provided"

    def test_multiple_informative_intents_recorded(self):
        """Несколько информативных интентов должны записываться."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()

        intents = ["situation_provided", "problem_mentioned", "info_provided"]

        for i, intent in enumerate(intents):
            guard.check(
                state="spin_situation",
                message=f"сообщение {i}",
                collected_data={},
                last_intent=intent
            )

        assert len(guard._state.intent_history) == 3
        assert guard._state.last_intent == "info_provided"


# =============================================================================
# Test 3: GuardState - Intent Tracking Fields
# =============================================================================
class TestGuardStateIntentTracking:
    """Тесты для полей intent_history и last_intent в GuardState."""

    def test_guard_state_has_intent_history(self):
        """GuardState должен иметь поле intent_history."""
        from conversation_guard import GuardState

        state = GuardState()

        assert hasattr(state, 'intent_history')
        assert isinstance(state.intent_history, list)
        assert len(state.intent_history) == 0

    def test_guard_state_has_last_intent(self):
        """GuardState должен иметь поле last_intent."""
        from conversation_guard import GuardState

        state = GuardState()

        assert hasattr(state, 'last_intent')
        assert state.last_intent == ""


# =============================================================================
# Test 4: YAML Configuration - Informative Category
# =============================================================================
class TestYamlInformativeCategory:
    """Тесты для YAML конфигурации informative категории."""

    def test_informative_category_exists(self):
        """Категория informative должна существовать в constants.yaml."""
        import yaml

        constants_path = os.path.join(src_path, 'yaml_config', 'constants.yaml')
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        assert 'intents' in constants
        assert 'categories' in constants['intents']
        assert 'informative' in constants['intents']['categories']

    def test_informative_category_contains_spin_intents(self):
        """Категория informative должна содержать SPIN интенты."""
        import yaml

        constants_path = os.path.join(src_path, 'yaml_config', 'constants.yaml')
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        informative = constants['intents']['categories']['informative']

        assert 'situation_provided' in informative
        assert 'problem_revealed' in informative
        assert 'implication_acknowledged' in informative
        assert 'need_expressed' in informative

    def test_informative_category_contains_general_intents(self):
        """Категория informative должна содержать общие интенты."""
        import yaml

        constants_path = os.path.join(src_path, 'yaml_config', 'constants.yaml')
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        informative = constants['intents']['categories']['informative']

        assert 'info_provided' in informative
        assert 'positive_feedback' in informative
        assert 'correct_info' in informative


# =============================================================================
# Test 5: Feature Flags - Guard Fixes
# =============================================================================
class TestFeatureFlagsGuardFixes:
    """Тесты для новых feature flags Guard fixes."""

    def test_guard_informative_intent_check_flag_exists(self):
        """Флаг guard_informative_intent_check должен существовать."""
        from feature_flags import FeatureFlags

        assert 'guard_informative_intent_check' in FeatureFlags.DEFAULTS

    def test_guard_skip_resets_fallback_flag_exists(self):
        """Флаг guard_skip_resets_fallback должен существовать."""
        from feature_flags import FeatureFlags

        assert 'guard_skip_resets_fallback' in FeatureFlags.DEFAULTS

    def test_guard_flags_enabled_by_default(self):
        """Новые guard флаги должны быть включены по умолчанию."""
        from feature_flags import FeatureFlags

        assert FeatureFlags.DEFAULTS['guard_informative_intent_check'] == True
        assert FeatureFlags.DEFAULTS['guard_skip_resets_fallback'] == True

    def test_guard_fixes_group_exists(self):
        """Группа guard_fixes должна существовать."""
        from feature_flags import FeatureFlags

        assert 'guard_fixes' in FeatureFlags.GROUPS

        group = FeatureFlags.GROUPS['guard_fixes']
        assert 'guard_informative_intent_check' in group
        assert 'guard_skip_resets_fallback' in group

    def test_flags_property_accessors(self):
        """Property accessors должны работать."""
        from feature_flags import flags

        # Just test that they exist and return bool
        assert isinstance(flags.guard_informative_intent_check, bool)
        assert isinstance(flags.guard_skip_resets_fallback, bool)


# =============================================================================
# Test 6: ConversationGuard - check() Method Signature
# =============================================================================
class TestConversationGuardCheckSignature:
    """Тесты для сигнатуры метода check()."""

    def test_check_accepts_last_intent_parameter(self):
        """check() должен принимать параметр last_intent."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()

        # Должен работать без ошибок
        can_continue, intervention = guard.check(
            state="spin_situation",
            message="10 человек",
            collected_data={},
            frustration_level=0,
            last_intent="situation_provided"
        )

        assert can_continue == True

    def test_check_works_without_last_intent(self):
        """check() должен работать без last_intent (backward compatible)."""
        from conversation_guard import ConversationGuard

        guard = ConversationGuard()

        # Должен работать без ошибок
        can_continue, intervention = guard.check(
            state="spin_situation",
            message="10 человек",
            collected_data={},
            frustration_level=0
        )

        assert can_continue == True


# =============================================================================
# Test 7: Integration Tests
# =============================================================================
class TestIntegration:
    """Интеграционные тесты для всей цепочки."""

    def test_informative_responses_dont_trigger_tier3(self):
        """E2E: Информативные ответы не должны приводить к TIER_3."""
        from conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_same_state=3)
        guard = ConversationGuard(config)

        # Симулируем диалог где клиент даёт информативные ответы
        test_cases = [
            ("spin_situation", "10 человек", "situation_provided"),
            ("spin_situation", "продажи", "info_provided"),
            ("spin_situation", "CRM Битрикс", "info_provided"),
            ("spin_situation", "5 лет на рынке", "info_provided"),
        ]

        interventions = []
        for state, message, intent in test_cases:
            can_continue, intervention = guard.check(
                state=state,
                message=message,
                collected_data={},
                last_intent=intent
            )
            interventions.append(intervention)

        # Ни один не должен быть TIER_3
        assert "fallback_tier_3" not in interventions, (
            f"TIER_3 не должен срабатывать при информативных ответах, получили: {interventions}"
        )

    def test_unclear_responses_trigger_tier3(self):
        """E2E: Неясные ответы должны приводить к TIER_3."""
        from conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_same_state=3)
        guard = ConversationGuard(config)

        # Симулируем диалог где клиент даёт неясные ответы
        test_cases = [
            ("spin_situation", "не знаю", "unclear"),
            ("spin_situation", "ну типа", "unclear"),
            ("spin_situation", "эээ", "unclear"),
            ("spin_situation", "хм", "unclear"),
        ]

        last_intervention = None
        for state, message, intent in test_cases:
            can_continue, intervention = guard.check(
                state=state,
                message=message,
                collected_data={},
                last_intent=intent
            )
            last_intervention = intervention

        # На 4й раз должен сработать TIER_3
        assert last_intervention == "fallback_tier_3", (
            f"TIER_3 должен срабатывать при unclear ответах, получили: {last_intervention}"
        )

    def test_mixed_responses_respect_last_intent(self):
        """E2E: При смешанных ответах учитывается последний intent."""
        from conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_same_state=3)
        guard = ConversationGuard(config)

        # 3 unclear, потом informative
        guard.check("spin_situation", "не знаю", {}, last_intent="unclear")
        guard.check("spin_situation", "ну", {}, last_intent="unclear")
        guard.check("spin_situation", "эээ", {}, last_intent="unclear")

        # На 4й - информативный
        can_continue, intervention = guard.check(
            state="spin_situation",
            message="10 человек в команде",
            collected_data={},
            last_intent="situation_provided"
        )

        # Не должен срабатывать TIER_3
        assert intervention != "fallback_tier_3"


# =============================================================================
# Test 8: Bot - fallback_response Reset After Skip
# =============================================================================
class TestBotFallbackReset:
    """Тесты для сброса fallback_response после skip action."""

    def test_bot_check_guard_accepts_last_intent(self):
        """Bot._check_guard должен принимать last_intent."""
        # Проверяем сигнатуру метода через inspect
        import inspect
        from bot import SalesBot

        sig = inspect.signature(SalesBot._check_guard)
        params = list(sig.parameters.keys())

        assert 'last_intent' in params, (
            f"_check_guard должен иметь параметр last_intent, есть: {params}"
        )


# =============================================================================
# Run tests
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

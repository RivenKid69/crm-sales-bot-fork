"""
Тесты для исправлений багов:
- Баг 2: Игнорирование вопросов о цене
- Баг 3: Повторяющиеся ответы бота

Эти тесты проверяют архитектурные изменения:
1. YAML конфигурация - intent categories для price_related
2. Generator - deduplication и regenerate_with_diversity
3. State Machine - ПРИОРИТЕТ 2.5 для price_related
4. DialoguePolicy - price question overlay
5. ResponseDirectives - do_not_repeat_responses
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
# Test 1: YAML Configuration - intent categories
# =============================================================================
class TestYamlIntentCategories:
    """Тесты для YAML конфигурации intent categories."""

    def test_price_related_category_exists(self):
        """Категория price_related должна существовать в constants.yaml."""
        import yaml

        constants_path = os.path.join(src_path, 'yaml_config', 'constants.yaml')
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        assert 'intents' in constants
        assert 'categories' in constants['intents']
        assert 'price_related' in constants['intents']['categories']

        price_related = constants['intents']['categories']['price_related']
        assert 'price_question' in price_related
        assert 'pricing_details' in price_related

    def test_question_requires_facts_category_exists(self):
        """Категория question_requires_facts должна существовать (as composed category)."""
        from src.yaml_config.constants import INTENT_CATEGORIES

        # BUG #4 FIX: question_requires_facts is now a composed category (includes all_questions)
        assert 'question_requires_facts' in INTENT_CATEGORIES

        requires_facts = INTENT_CATEGORIES['question_requires_facts']
        assert 'price_question' in requires_facts
        assert 'pricing_details' in requires_facts
        assert 'question_features' in requires_facts
        # Now includes ALL question intents, not just 4
        assert 'question_security' in requires_facts

    def test_intent_action_overrides_exists(self):
        """Секция intent_action_overrides должна существовать."""
        import yaml

        constants_path = os.path.join(src_path, 'yaml_config', 'constants.yaml')
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        assert 'intent_action_overrides' in constants['intents']

        overrides = constants['intents']['intent_action_overrides']
        assert overrides.get('price_question') == 'answer_with_pricing'
        assert overrides.get('pricing_details') == 'answer_with_pricing'


# =============================================================================
# Test 2: Generator - Deduplication
# =============================================================================
class TestGeneratorDeduplication:
    """Тесты для deduplication в генераторе."""

    def test_compute_similarity_exact_match(self):
        """Точное совпадение должно давать similarity = 1.0."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())

        text = "Сколько человек работает в вашей команде?"
        similarity = gen._compute_similarity(text, text)

        assert similarity == 1.0

    def test_compute_similarity_partial_match(self):
        """Частичное совпадение должно давать высокую similarity."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())

        # Используем тексты с большим overlap для тестирования
        text1 = "Сколько человек работает в вашей команде продаж?"
        text2 = "Сколько человек работает в вашей команде маркетинга?"

        similarity = gen._compute_similarity(text1, text2)

        # Много общих слов (6 из 8) - высокая similarity (~0.75)
        assert similarity > 0.5

    def test_compute_similarity_different_texts(self):
        """Разные тексты должны давать низкую similarity."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())

        text1 = "Сколько человек работает в вашей команде?"
        text2 = "Наша CRM помогает автоматизировать продажи."

        similarity = gen._compute_similarity(text1, text2)

        # Мало общих слов - низкая similarity
        assert similarity < 0.3

    def test_is_duplicate_detects_history_duplicate(self):
        """_is_duplicate должен обнаруживать дубликаты в истории."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())

        history = [
            {"user": "Привет", "bot": "Здравствуйте! Чем могу помочь?"},
            {"user": "Сколько стоит?", "bot": "А сколько человек работает в команде?"},
        ]

        # Тот же вопрос - дубликат
        new_response = "А сколько человек работает в команде?"
        assert gen._is_duplicate(new_response, history) == True

    def test_is_duplicate_allows_unique_response(self):
        """_is_duplicate должен пропускать уникальные ответы."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())

        history = [
            {"user": "Привет", "bot": "Здравствуйте! Чем могу помочь?"},
            {"user": "Сколько стоит?", "bot": "А сколько человек работает в команде?"},
        ]

        # Совершенно другой ответ
        new_response = "Стоимость от 590 до 990 рублей за человека."
        assert gen._is_duplicate(new_response, history) == False

    def test_add_to_response_history(self):
        """_add_to_response_history должен добавлять ответы в историю."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())

        gen._add_to_response_history("Ответ 1")
        gen._add_to_response_history("Ответ 2")
        gen._add_to_response_history("Ответ 3")

        assert len(gen._response_history) == 3
        assert "Ответ 1" in gen._response_history

    def test_response_history_limit(self):
        """История ответов должна ограничиваться max_response_history."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())
        gen._max_response_history = 3

        for i in range(5):
            gen._add_to_response_history(f"Ответ {i}")

        assert len(gen._response_history) == 3
        assert "Ответ 0" not in gen._response_history
        assert "Ответ 4" in gen._response_history

    def test_reset_clears_history(self):
        """reset() должен очищать историю ответов."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())

        gen._add_to_response_history("Ответ 1")
        gen._add_to_response_history("Ответ 2")

        gen.reset()

        assert len(gen._response_history) == 0

    def test_price_related_intents_constant(self):
        """PRICE_RELATED_INTENTS должен содержать price интенты."""
        from generator import ResponseGenerator

        assert hasattr(ResponseGenerator, 'PRICE_RELATED_INTENTS')
        assert 'price_question' in ResponseGenerator.PRICE_RELATED_INTENTS
        assert 'pricing_details' in ResponseGenerator.PRICE_RELATED_INTENTS

    def test_get_price_template_key(self):
        """_get_price_template_key должен возвращать правильные шаблоны."""
        from generator import ResponseGenerator

        gen = ResponseGenerator(llm=Mock())

        assert gen._get_price_template_key("price_question", "any") == "answer_with_pricing"
        assert gen._get_price_template_key("pricing_details", "any") == "answer_pricing_details"
        assert gen._get_price_template_key("other", "any") == "answer_with_facts"


# =============================================================================
# Test 3: State Machine - Price Priority
# =============================================================================
class TestStateMachinePricePriority:
    """Тесты для ПРИОРИТЕТ 2.5 в state machine."""

    @pytest.fixture
    def state_machine(self):
        """Создать StateMachine для тестов."""
        from state_machine import StateMachine
        return StateMachine()

    def test_price_question_returns_answer_with_pricing(self, state_machine):
        """price_question должен возвращать action=answer_with_pricing."""
        # Убедимся что feature flag включён
        from feature_flags import flags

        if not flags.is_enabled("price_question_override"):
            pytest.skip("price_question_override flag is disabled")

        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules("price_question")

        assert action == "answer_with_pricing", (
            f"price_question должен возвращать answer_with_pricing, получили {action}"
        )

    def test_pricing_details_returns_answer_with_pricing(self, state_machine):
        """pricing_details должен возвращать action=answer_with_pricing."""
        from feature_flags import flags

        if not flags.is_enabled("price_question_override"):
            pytest.skip("price_question_override flag is disabled")

        state_machine.state = "spin_problem"
        action, next_state = state_machine.apply_rules("pricing_details")

        assert action == "answer_with_pricing", (
            f"pricing_details должен возвращать answer_with_pricing, получили {action}"
        )

    def test_get_intent_category_returns_price_related(self, state_machine):
        """_get_intent_category должен возвращать price_related категорию."""
        category = state_machine._get_intent_category("price_related")

        if category is None:
            # Fallback если нет FlowConfig
            pytest.skip("No FlowConfig or constants loaded")

        assert "price_question" in category
        assert "pricing_details" in category


# =============================================================================
# Test 4: DialoguePolicy - Price Question Overlay
# =============================================================================
class TestDialoguePolicyPriceOverlay:
    """Тесты для price question overlay в DialoguePolicy."""

    def test_policy_decision_has_price_question(self):
        """PolicyDecision должен иметь PRICE_QUESTION."""
        from dialogue_policy import PolicyDecision

        assert hasattr(PolicyDecision, 'PRICE_QUESTION')
        assert PolicyDecision.PRICE_QUESTION.value == "price_question"

    def test_is_price_question_condition_registered(self):
        """Условие is_price_question должно быть зарегистрировано."""
        from src.conditions.policy import policy_registry

        # Проверяем что условие зарегистрировано
        assert "is_price_question" in policy_registry._conditions

    def test_is_price_question_returns_true_for_price_intent(self):
        """is_price_question должен возвращать True для price_question intent."""
        from src.conditions.policy import is_price_question, PolicyContext

        ctx = Mock(spec=PolicyContext)
        ctx.last_intent = "price_question"

        result = is_price_question(ctx)

        assert result == True

    def test_is_price_question_returns_true_for_pricing_details(self):
        """is_price_question должен возвращать True для pricing_details intent."""
        from src.conditions.policy import is_price_question, PolicyContext

        ctx = Mock(spec=PolicyContext)
        ctx.last_intent = "pricing_details"

        result = is_price_question(ctx)

        assert result == True

    def test_is_price_question_returns_false_for_other_intents(self):
        """is_price_question должен возвращать False для других интентов."""
        from src.conditions.policy import is_price_question, PolicyContext

        ctx = Mock(spec=PolicyContext)
        ctx.last_intent = "greeting"

        result = is_price_question(ctx)

        assert result == False

    def test_reason_code_policy_price_override_exists(self):
        """ReasonCode должен иметь POLICY_PRICE_OVERRIDE."""
        from context_envelope import ReasonCode

        assert hasattr(ReasonCode, 'POLICY_PRICE_OVERRIDE')
        assert ReasonCode.POLICY_PRICE_OVERRIDE.value == "policy.price_override"


# =============================================================================
# Test 5: ResponseDirectives - do_not_repeat_responses
# =============================================================================
class TestResponseDirectivesDoNotRepeat:
    """Тесты для do_not_repeat_responses в ResponseDirectives."""

    def test_response_directives_has_do_not_repeat_responses(self):
        """ResponseDirectives должен иметь поле do_not_repeat_responses."""
        from response_directives import ResponseDirectives

        directives = ResponseDirectives()

        assert hasattr(directives, 'do_not_repeat_responses')
        assert isinstance(directives.do_not_repeat_responses, list)

    def test_response_directives_to_dict_includes_do_not_repeat_responses(self):
        """to_dict должен включать do_not_repeat_responses."""
        from response_directives import ResponseDirectives

        directives = ResponseDirectives()
        directives.do_not_repeat_responses = ["Ответ 1", "Ответ 2"]

        result = directives.to_dict()

        assert 'memory' in result
        assert 'do_not_repeat_responses' in result['memory']
        assert result['memory']['do_not_repeat_responses'] == ["Ответ 1", "Ответ 2"]

    def test_get_instruction_includes_do_not_repeat_responses(self):
        """get_instruction должен включать инструкцию о не-повторе ответов."""
        from response_directives import ResponseDirectives

        directives = ResponseDirectives()
        directives.do_not_repeat_responses = ["Старый ответ 1", "Старый ответ 2"]

        instruction = directives.get_instruction()

        assert "НЕ ПОВТОРЯЙ" in instruction


# =============================================================================
# Test 6: Feature Flags
# =============================================================================
class TestFeatureFlags:
    """Тесты для новых feature flags."""

    def test_response_deduplication_flag_exists(self):
        """Флаг response_deduplication должен существовать."""
        from feature_flags import FeatureFlags

        assert 'response_deduplication' in FeatureFlags.DEFAULTS

    def test_price_question_override_flag_exists(self):
        """Флаг price_question_override должен существовать."""
        from feature_flags import FeatureFlags

        assert 'price_question_override' in FeatureFlags.DEFAULTS

    def test_flags_enabled_by_default(self):
        """Новые флаги должны быть включены по умолчанию."""
        from feature_flags import FeatureFlags

        assert FeatureFlags.DEFAULTS['response_deduplication'] == True
        assert FeatureFlags.DEFAULTS['price_question_override'] == True


# =============================================================================
# Test 7: YAML Templates
# =============================================================================
class TestYamlTemplates:
    """Тесты для новых YAML шаблонов."""

    def test_answer_with_pricing_template_exists(self):
        """Шаблон answer_with_pricing должен существовать."""
        import yaml

        prompts_path = os.path.join(
            src_path, 'yaml_config', 'templates', '_base', 'prompts.yaml'
        )
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts = yaml.safe_load(f)

        assert 'templates' in prompts
        assert 'answer_with_pricing' in prompts['templates']

        template = prompts['templates']['answer_with_pricing']
        assert 'template' in template
        assert 'цен' in template['template'].lower()

    def test_answer_pricing_details_template_exists(self):
        """Шаблон answer_pricing_details должен существовать."""
        import yaml

        prompts_path = os.path.join(
            src_path, 'yaml_config', 'templates', '_base', 'prompts.yaml'
        )
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts = yaml.safe_load(f)

        assert 'answer_pricing_details' in prompts['templates']


# =============================================================================
# Test 8: Integration Tests
# =============================================================================
class TestIntegration:
    """Интеграционные тесты для всей цепочки."""

    def test_price_question_flow_end_to_end(self):
        """E2E: price_question должен приводить к ответу о цене."""
        from state_machine import StateMachine
        from feature_flags import flags

        if not flags.is_enabled("price_question_override"):
            pytest.skip("price_question_override flag is disabled")

        sm = StateMachine()
        sm.state = "spin_situation"

        # Клиент спрашивает о цене
        action, next_state = sm.apply_rules("price_question")

        # Должны получить pricing action
        assert action in ("answer_with_pricing", "answer_with_facts"), (
            f"Ожидался pricing action, получили {action}"
        )

        # Состояние не должно меняться (остаёмся в текущем)
        assert next_state == "spin_situation"

    def test_deduplication_integration(self):
        """E2E: deduplication должен предотвращать повторы."""
        from generator import ResponseGenerator
        from feature_flags import flags

        if not flags.is_enabled("response_deduplication"):
            pytest.skip("response_deduplication flag is disabled")

        gen = ResponseGenerator(llm=Mock())

        history = [
            {"user": "Привет", "bot": "Здравствуйте! Чем могу помочь?"},
            {"user": "Интересует CRM", "bot": "А сколько человек работает в вашей команде?"},
        ]

        # Проверяем что дубликат обнаруживается
        duplicate = "А сколько человек работает в вашей команде?"
        is_dup = gen._is_duplicate(duplicate, history)

        assert is_dup == True, "Дубликат должен быть обнаружен"


# =============================================================================
# Run tests
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

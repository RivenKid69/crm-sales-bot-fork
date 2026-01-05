"""
Интеграционные тесты для Phase 2: Естественность диалога.

Проверяют:
- Интеграцию ToneAnalyzer с ResponseVariations
- Интеграцию ToneAnalyzer с PersonalizationEngine
- Полный workflow от анализа тона до генерации ответа
- Совместимость новых промптов
"""

import pytest
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tone_analyzer import ToneAnalyzer, Tone, Style
from response_variations import ResponseVariations, variations
from generator import PersonalizationEngine
from config import SYSTEM_PROMPT, PROMPT_TEMPLATES


class TestToneAnalyzerWithResponseVariations:
    """Интеграция ToneAnalyzer с ResponseVariations"""

    def setup_method(self):
        self.tone_analyzer = ToneAnalyzer()
        self.variations = ResponseVariations()

    def test_frustrated_client_gets_apology(self):
        """Раздражённый клиент получает извинение"""
        # Анализируем раздражённое сообщение
        analysis = self.tone_analyzer.analyze("Достали уже! Сколько можно!")

        # Если frustration высокий — используем apologetic response
        guidance = self.tone_analyzer.get_response_guidance(analysis)

        if guidance["should_apologize"]:
            response = self.variations.build_apologetic_response(
                core_message="Давайте сразу к делу.",
                offer_exit=guidance["should_offer_exit"]
            )
            # Должен содержать извинение
            has_apology = any(
                apology in response
                for apology in ResponseVariations.APOLOGIES
            )
            assert has_apology

    def test_positive_client_gets_expanded_response(self):
        """Позитивный клиент получает более развёрнутый ответ"""
        analysis = self.tone_analyzer.analyze("Отлично! Это то что нужно! 👍")
        guidance = self.tone_analyzer.get_response_guidance(analysis)

        # Для позитивного клиента max_words больше
        assert guidance["max_words"] >= 50

        # Можно использовать более развёрнутое вступление
        response = self.variations.build_natural_response(
            core_message="Рад что понравилось! Хотите посмотреть демо?",
            add_opening=True,
            opening_category="positive_reaction",
            skip_opening_probability=0.0
        )
        assert response  # Не пустой

    def test_informal_client_style_adaptation(self):
        """Адаптация к неформальному стилю клиента"""
        analysis = self.tone_analyzer.analyze("Привет, ну чё там по ценам?")

        assert analysis.style == Style.INFORMAL

        guidance = self.tone_analyzer.get_response_guidance(analysis)
        assert guidance["formality"] == "casual"

        # При неформальном стиле можно использовать casual вступления
        response = self.variations.build_natural_response(
            core_message="по ценам от 590 до 990 за человека",
            add_opening=True,
            opening_category="acknowledgment",
            skip_opening_probability=0.0
        )
        assert response

    def test_empathetic_response_for_problem_phase(self):
        """Эмпатичный ответ для problem-фазы"""
        # Клиент озвучил проблему
        analysis = self.tone_analyzer.analyze("Теряем клиентов постоянно, не успеваем обрабатывать заявки")

        # Используем эмпатичный ответ
        response = self.variations.build_empathetic_response(
            problem_acknowledgment="Да, это знакомая проблема.",
            question="Сколько примерно клиентов теряете в месяц?",
            skip_probability=0.0
        )

        assert "знакомая проблема" in response
        assert "клиентов теряете" in response


class TestToneAnalyzerWithPersonalizationEngine:
    """Интеграция ToneAnalyzer с PersonalizationEngine"""

    def setup_method(self):
        self.tone_analyzer = ToneAnalyzer()

    def test_personalized_response_for_frustrated_micro_company(self):
        """Персонализированный ответ для раздражённой micro компании"""
        # Данные клиента
        collected_data = {
            "company_size": 3,
            "pain_point": "теряем клиентов"
        }

        # Анализируем тон - несколько сообщений для накопления frustration
        self.tone_analyzer.analyze("Достали!")
        analysis = self.tone_analyzer.analyze("Уже говорил, сколько можно!")
        guidance = self.tone_analyzer.get_response_guidance(analysis)

        # Получаем персонализацию
        personalization = PersonalizationEngine.get_context(collected_data)

        # Для micro компании + frustrated клиент:
        # - Должен быть frustrated тон
        # - Фокус на простоте (personalization)
        assert analysis.tone == Tone.FRUSTRATED
        assert "простота" in personalization["business_context"]["pain_focus"].lower() or \
               "время" in personalization["business_context"]["pain_focus"].lower()

    def test_personalized_response_for_interested_large_company(self):
        """Персонализированный ответ для заинтересованной large компании"""
        collected_data = {
            "company_size": 100,
            "business_type": "IT компания"
        }

        analysis = self.tone_analyzer.analyze("Интересно, расскажите подробнее про интеграции")
        guidance = self.tone_analyzer.get_response_guidance(analysis)

        personalization = PersonalizationEngine.get_context(collected_data)

        # Для large компании + заинтересованный клиент:
        # - Можно подробнее (guidance)
        # - Фокус на интеграциях и кастомизации (personalization)
        assert guidance["max_words"] >= 50
        assert "интеграция" in personalization["business_context"]["pain_focus"].lower() or \
               "кастомизация" in personalization["business_context"]["pain_focus"].lower()

    def test_objection_handling_with_tone(self):
        """Обработка возражения с учётом тона"""
        collected_data = {"company_size": 10}

        # Скептическое возражение о цене
        analysis = self.tone_analyzer.analyze("Сомневаюсь что это стоит таких денег")
        guidance = self.tone_analyzer.get_response_guidance(analysis)

        # Получаем контраргумент
        counter = PersonalizationEngine.get_objection_counter(collected_data, "price")

        # Для скептика нужны факты
        assert "факт" in guidance["tone_instruction"].lower() or \
               "цифр" in guidance["tone_instruction"].lower()

        # Контраргумент должен быть непустым
        assert counter


class TestNewPromptsCompatibility:
    """Тесты совместимости новых промптов"""

    def test_system_prompt_with_tone_instruction(self):
        """SYSTEM_PROMPT поддерживает tone_instruction"""
        tone_instruction = "Будь кратким и по делу."
        formatted = SYSTEM_PROMPT.format(tone_instruction=tone_instruction)

        assert "Будь кратким и по делу." in formatted
        assert "СТИЛЬ ОБЩЕНИЯ" in formatted

    def test_system_prompt_without_tone_instruction(self):
        """SYSTEM_PROMPT работает без tone_instruction"""
        formatted = SYSTEM_PROMPT.format(tone_instruction="")

        # Должен сформироваться без ошибок
        assert "СТИЛЬ ОБЩЕНИЯ" in formatted

    def test_answer_with_range_and_qualify_template_exists(self):
        """Шаблон answer_with_range_and_qualify существует"""
        assert "answer_with_range_and_qualify" in PROMPT_TEMPLATES

    def test_short_response_frustrated_template_exists(self):
        """Шаблон short_response_frustrated существует"""
        assert "short_response_frustrated" in PROMPT_TEMPLATES

    def test_empathetic_response_template_exists(self):
        """Шаблон empathetic_response существует"""
        assert "empathetic_response" in PROMPT_TEMPLATES

    def test_informal_response_template_exists(self):
        """Шаблон informal_response существует"""
        assert "informal_response" in PROMPT_TEMPLATES

    def test_soft_exit_frustrated_template_exists(self):
        """Шаблон soft_exit_frustrated существует"""
        assert "soft_exit_frustrated" in PROMPT_TEMPLATES

    def test_templates_have_required_placeholders(self):
        """Шаблоны имеют необходимые плейсхолдеры"""
        required_templates = [
            "answer_with_range_and_qualify",
            "short_response_frustrated",
            "empathetic_response",
            "informal_response",
            "soft_exit_frustrated"
        ]

        for template_name in required_templates:
            template = PROMPT_TEMPLATES[template_name]
            # Все шаблоны должны иметь {system}
            assert "{system}" in template, f"Missing {{system}} in {template_name}"
            # Большинство должны иметь {user_message}
            if template_name != "soft_exit_frustrated":
                assert "{user_message}" in template or "{history}" in template, \
                    f"Missing user context in {template_name}"


class TestFullWorkflow:
    """Тесты полного workflow"""

    def setup_method(self):
        self.tone_analyzer = ToneAnalyzer()
        self.variations = ResponseVariations()

    def test_workflow_positive_client_first_message(self):
        """Workflow: позитивный клиент, первое сообщение"""
        # 1. Получаем сообщение
        message = "Привет! Интересует ваша CRM система"

        # 2. Анализируем тон
        analysis = self.tone_analyzer.analyze(message)
        assert analysis.tone in [Tone.NEUTRAL, Tone.POSITIVE, Tone.INTERESTED]

        # 3. Получаем рекомендации
        guidance = self.tone_analyzer.get_response_guidance(analysis)
        assert guidance["should_apologize"] is False

        # 4. Генерируем вариативный ответ
        response = self.variations.build_natural_response(
            core_message="Расскажу с удовольствием! Сколько человек в вашей команде?",
            add_opening=True,
            opening_category="positive_reaction"
        )
        assert "Сколько человек" in response

    def test_workflow_frustrated_client_escalation(self):
        """Workflow: эскалация frustration"""
        messages = [
            "Сколько стоит?",
            "Я уже спрашивал!",
            "Опять одно и то же! Достали!"
        ]

        frustration_levels = []
        for msg in messages:
            analysis = self.tone_analyzer.analyze(msg)
            frustration_levels.append(analysis.frustration_level)

        # Frustration должен расти
        assert frustration_levels[-1] >= frustration_levels[0]

        # После нескольких раздражённых сообщений should_apologize = True
        final_guidance = self.tone_analyzer.get_response_guidance(analysis)
        # Может потребоваться извинение (зависит от порогов)
        if frustration_levels[-1] >= ToneAnalyzer.FRUSTRATION_THRESHOLDS["warning"]:
            assert final_guidance["should_apologize"] is True

    def test_workflow_personalized_response_generation(self):
        """Workflow: генерация персонализированного ответа"""
        # Данные клиента
        collected_data = {
            "company_size": 25,
            "business_type": "ресторан",
            "pain_point": "теряем заказы"
        }

        # Анализ тона
        analysis = self.tone_analyzer.analyze("Да, часто теряем заказы, клиенты уходят")
        guidance = self.tone_analyzer.get_response_guidance(analysis)

        # Персонализация
        personalization = PersonalizationEngine.get_context(collected_data)

        # Проверяем что все части работают вместе
        # 25 человек = medium (16-50)
        assert personalization["size_category"] == "medium"
        assert personalization["industry"] == "horeca"
        assert personalization["has_pain_point"] is True

        # Формируем ответ
        response = self.variations.build_empathetic_response(
            problem_acknowledgment="Да, потеря заказов — это серьёзная проблема для ресторана.",
            question="Сколько примерно заказов теряете за смену?",
            skip_probability=0.0
        )
        assert response

    def test_workflow_decay_frustration_with_positive(self):
        """Workflow: снижение frustration позитивными ответами"""
        # Поднимаем frustration
        self.tone_analyzer.analyze("Достали!")
        self.tone_analyzer.analyze("Надоело!")
        high_frustration = self.tone_analyzer.get_frustration_level()

        # Позитивные сообщения снижают
        self.tone_analyzer.analyze("Ладно, окей, давайте попробуем")
        self.tone_analyzer.analyze("Хорошо, интересно")
        lower_frustration = self.tone_analyzer.get_frustration_level()

        assert lower_frustration < high_frustration

    def test_workflow_reset_between_conversations(self):
        """Workflow: сброс между разговорами"""
        # Первый разговор — раздражённый клиент
        self.tone_analyzer.analyze("Достали!")
        self.tone_analyzer.analyze("Сколько можно!")
        assert self.tone_analyzer.get_frustration_level() > 0

        # Сброс для нового разговора
        self.tone_analyzer.reset()
        self.variations.reset()

        # Новый разговор начинается с чистого листа
        assert self.tone_analyzer.get_frustration_level() == 0
        analysis = self.tone_analyzer.analyze("Привет!")
        assert analysis.frustration_level == 0


class TestFeatureFlagsCompatibility:
    """Тесты совместимости с feature flags"""

    def test_phase2_flags_defined(self):
        """Phase 2 флаги определены"""
        from feature_flags import FeatureFlags

        phase2_flags = ["tone_analysis", "response_variations", "personalization"]
        defaults = FeatureFlags.DEFAULTS

        for flag in phase2_flags:
            assert flag in defaults, f"Missing flag: {flag}"

    def test_phase2_group_defined(self):
        """Группа phase_2 определена"""
        from feature_flags import FeatureFlags

        assert "phase_2" in FeatureFlags.GROUPS
        group_flags = FeatureFlags.GROUPS["phase_2"]

        assert "tone_analysis" in group_flags
        assert "response_variations" in group_flags
        assert "personalization" in group_flags


class TestEdgeCasesIntegration:
    """Интеграционные тесты граничных случаев"""

    def setup_method(self):
        self.tone_analyzer = ToneAnalyzer()
        self.variations = ResponseVariations()

    def test_empty_message_handling(self):
        """Обработка пустого сообщения"""
        analysis = self.tone_analyzer.analyze("")
        guidance = self.tone_analyzer.get_response_guidance(analysis)

        # Не должно падать
        assert analysis.tone == Tone.NEUTRAL
        assert guidance["max_words"] > 0

    def test_very_long_message_handling(self):
        """Обработка очень длинного сообщения"""
        long_message = "Интересно " * 500
        analysis = self.tone_analyzer.analyze(long_message)

        # Не должно падать
        assert analysis.tone is not None

    def test_special_characters_handling(self):
        """Обработка специальных символов"""
        message = "Цена: 590₽/мес — это нормально? 👍"
        analysis = self.tone_analyzer.analyze(message)

        # Не должно падать
        assert analysis.tone is not None

    def test_mixed_emotions_handling(self):
        """Обработка смешанных эмоций"""
        message = "С одной стороны интересно, но сомневаюсь что это работает"
        analysis = self.tone_analyzer.analyze(message)

        # Должен выбрать доминирующий тон
        assert analysis.tone in [Tone.INTERESTED, Tone.SKEPTICAL]

    def test_personalization_with_partial_data(self):
        """Персонализация с неполными данными"""
        # Только размер
        context1 = PersonalizationEngine.get_context({"company_size": 10})
        assert context1["size_category"] is not None

        # Только отрасль
        context2 = PersonalizationEngine.get_context({"business_type": "ресторан"})
        assert context2["industry"] is not None

        # Только боль
        context3 = PersonalizationEngine.get_context({"pain_point": "теряем клиентов"})
        assert context3["has_pain_point"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

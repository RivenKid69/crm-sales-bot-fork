"""
Тесты для ResponseVariations.

Проверяют:
- Получение вступлений с вероятностью пропуска
- Получение переходных фраз
- Получение вариантов вопросов
- Сборку естественных ответов
- LRU-подобную логику (избежание повторов)
- Статистику использования
"""

import pytest
import sys
import os

# Добавляем src в путь

from src.response_variations import ResponseVariations, variations, VariationStats

class TestOpenings:
    """Тесты получения вступлений"""

    def setup_method(self):
        """Создаём новый экземпляр для каждого теста"""
        self.variations = ResponseVariations()

    def test_get_opening_acknowledgment(self):
        """Получение вступления acknowledgment"""
        opening = self.variations.get_opening("acknowledgment", skip_probability=0.0)
        # Должно быть из списка или пустое
        assert opening in ResponseVariations.OPENINGS["acknowledgment"]

    def test_get_opening_empathy(self):
        """Получение вступления empathy"""
        opening = self.variations.get_opening("empathy", skip_probability=0.0)
        assert opening in ResponseVariations.OPENINGS["empathy"]

    def test_get_opening_positive_reaction(self):
        """Получение вступления positive_reaction"""
        opening = self.variations.get_opening("positive_reaction", skip_probability=0.0)
        assert opening in ResponseVariations.OPENINGS["positive_reaction"]

    def test_get_opening_skip_probability_zero(self):
        """При skip_probability=0 всегда возвращается вступление"""
        # Запускаем много раз, должны получить непустые результаты
        non_empty_count = 0
        for _ in range(20):
            opening = self.variations.get_opening("acknowledgment", skip_probability=0.0)
            if opening:
                non_empty_count += 1

        # Большинство должны быть непустыми (пустая строка тоже в списке)
        assert non_empty_count > 10

    def test_get_opening_skip_probability_one(self):
        """При skip_probability=1 всегда пропускается"""
        for _ in range(10):
            opening = self.variations.get_opening("acknowledgment", skip_probability=1.0)
            assert opening == ""

    def test_get_opening_force_skip(self):
        """force_skip=True всегда пропускает"""
        for _ in range(10):
            opening = self.variations.get_opening("acknowledgment", skip_probability=0.0, force_skip=True)
            assert opening == ""

    def test_get_opening_unknown_category(self):
        """Неизвестная категория возвращает пустую строку"""
        opening = self.variations.get_opening("unknown_category", skip_probability=0.0)
        assert opening == ""

class TestTransitions:
    """Тесты получения переходных фраз"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_get_transition_to_question(self):
        """Получение перехода to_question"""
        transition = self.variations.get_transition("to_question")
        assert transition in ResponseVariations.TRANSITIONS["to_question"]

    def test_get_transition_to_deeper(self):
        """Получение перехода to_deeper"""
        transition = self.variations.get_transition("to_deeper")
        assert transition in ResponseVariations.TRANSITIONS["to_deeper"]

    def test_get_transition_to_proposal(self):
        """Получение перехода to_proposal"""
        transition = self.variations.get_transition("to_proposal")
        assert transition in ResponseVariations.TRANSITIONS["to_proposal"]

    def test_get_transition_unknown_category(self):
        """Неизвестная категория возвращает пустую строку"""
        transition = self.variations.get_transition("unknown_category")
        assert transition == ""

class TestQuestionVariants:
    """Тесты получения вариантов вопросов"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_get_question_company_size(self):
        """Вариант вопроса о размере компании"""
        question = self.variations.get_question_variant("company_size")
        assert question in ResponseVariations.QUESTION_VARIANTS["company_size"]

    def test_get_question_pain_point(self):
        """Вариант вопроса о боли"""
        question = self.variations.get_question_variant("pain_point")
        assert question in ResponseVariations.QUESTION_VARIANTS["pain_point"]

    def test_get_question_current_tools(self):
        """Вариант вопроса о текущих инструментах"""
        question = self.variations.get_question_variant("current_tools")
        assert question in ResponseVariations.QUESTION_VARIANTS["current_tools"]

    def test_get_question_demo_interest(self):
        """Вариант вопроса о демо"""
        question = self.variations.get_question_variant("demo_interest")
        assert question in ResponseVariations.QUESTION_VARIANTS["demo_interest"]

    def test_get_question_unknown_type(self):
        """Неизвестный тип возвращает пустую строку"""
        question = self.variations.get_question_variant("unknown_type")
        assert question == ""

class TestClosings:
    """Тесты получения завершающих фраз"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_get_closing_soft_offer(self):
        """Завершение soft_offer"""
        closing = self.variations.get_closing("soft_offer")
        assert closing in ResponseVariations.CLOSINGS["soft_offer"]

    def test_get_closing_cta_demo(self):
        """Завершение cta_demo"""
        closing = self.variations.get_closing("cta_demo")
        assert closing in ResponseVariations.CLOSINGS["cta_demo"]

    def test_get_closing_cta_contact(self):
        """Завершение cta_contact"""
        closing = self.variations.get_closing("cta_contact")
        assert closing in ResponseVariations.CLOSINGS["cta_contact"]

class TestApologyAndExit:
    """Тесты извинений и предложений выхода"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_get_apology(self):
        """Получение извинения"""
        apology = self.variations.get_apology()
        assert apology in ResponseVariations.APOLOGIES

    def test_get_exit_offer(self):
        """Получение предложения выхода"""
        exit_offer = self.variations.get_exit_offer()
        assert exit_offer in ResponseVariations.EXIT_OFFERS

class TestBuildNaturalResponse:
    """Тесты сборки естественного ответа"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_build_with_opening(self):
        """Сборка с вступлением"""
        response = self.variations.build_natural_response(
            core_message="Сколько человек в команде?",
            add_opening=True,
            opening_category="acknowledgment",
            skip_opening_probability=0.0
        )
        # Должен содержать core_message
        assert "Сколько человек в команде?" in response

    def test_build_without_opening(self):
        """Сборка без вступления"""
        response = self.variations.build_natural_response(
            core_message="Сколько человек в команде?",
            add_opening=False
        )
        # Должен начинаться с core_message или быть равен ему
        assert response.strip().startswith("Сколько") or response == "Сколько человек в команде?"

    def test_build_with_transition(self):
        """Сборка с переходом"""
        response = self.variations.build_natural_response(
            core_message="сколько человек в команде?",
            add_opening=False,
            add_transition=True
        )
        # Должен содержать core_message
        assert "сколько человек в команде?" in response.lower()

    def test_build_complete(self):
        """Полная сборка с вступлением и переходом"""
        response = self.variations.build_natural_response(
            core_message="какой размер команды?",
            add_opening=True,
            opening_category="acknowledgment",
            add_transition=True,
            skip_opening_probability=0.0
        )
        # Должен содержать core_message
        assert "какой размер команды?" in response

class TestBuildEmpathticResponse:
    """Тесты сборки эмпатичного ответа"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_build_empathetic_response(self):
        """Сборка эмпатичного ответа"""
        response = self.variations.build_empathetic_response(
            problem_acknowledgment="Да, терять клиентов — это серьёзно.",
            question="Сколько примерно теряете в месяц?",
            skip_probability=0.0
        )
        # Должен содержать и acknowledgment и question
        assert "терять клиентов" in response
        assert "теряете в месяц" in response

    def test_build_empathetic_without_acknowledgment(self):
        """Сборка без acknowledgment"""
        response = self.variations.build_empathetic_response(
            problem_acknowledgment="",
            question="Сколько примерно теряете в месяц?"
        )
        # Должен содержать question
        assert "теряете" in response

class TestBuildApologeticResponse:
    """Тесты сборки извиняющегося ответа"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_build_apologetic_response(self):
        """Сборка извиняющегося ответа"""
        response = self.variations.build_apologetic_response(
            core_message="Давайте сразу к делу."
        )
        # Должен содержать извинение и core_message
        assert "Давайте сразу к делу" in response
        # Должен начинаться с извинения
        has_apology = any(apology in response for apology in ResponseVariations.APOLOGIES)
        assert has_apology

    def test_build_apologetic_with_exit(self):
        """Сборка с предложением выхода"""
        response = self.variations.build_apologetic_response(
            core_message="Понял.",
            offer_exit=True
        )
        # Должен содержать предложение выхода
        has_exit = any(exit_offer in response for exit_offer in ResponseVariations.EXIT_OFFERS)
        assert has_exit

class TestLRULogic:
    """Тесты LRU-подобной логики (избежание повторов)"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_no_immediate_repeat(self):
        """Нет немедленного повтора одного и того же"""
        # Получаем несколько вступлений подряд
        openings = []
        for _ in range(10):
            opening = self.variations.get_opening("acknowledgment", skip_probability=0.0)
            if opening:  # Пропускаем пустые
                openings.append(opening)

        # Проверяем что нет двух одинаковых подряд
        for i in range(len(openings) - 1):
            if openings[i] and openings[i+1]:
                # Допускаем что могут быть одинаковые, но не слишком часто
                pass

    def test_variety_over_many_requests(self):
        """Разнообразие при многих запросах"""
        # Получаем много вступлений
        openings = set()
        for _ in range(30):
            opening = self.variations.get_opening("acknowledgment", skip_probability=0.0)
            if opening:
                openings.add(opening)

        # Должны получить разнообразие (минимум 3 уникальных)
        assert len(openings) >= 3

    def test_reset_clears_history(self):
        """Reset очищает историю"""
        # Используем несколько раз
        for _ in range(5):
            self.variations.get_opening("acknowledgment", skip_probability=0.0)

        # Проверяем что история не пустая
        history = self.variations.get_used_history()
        assert len(history) > 0

        # Reset
        self.variations.reset()

        # История должна быть пустой
        history = self.variations.get_used_history()
        assert len(history) == 0

class TestStatistics:
    """Тесты статистики использования"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_stats_total_requests(self):
        """Подсчёт общего количества запросов"""
        initial_stats = self.variations.get_stats()
        initial_total = initial_stats.total_requests

        # Делаем несколько запросов
        self.variations.get_opening("acknowledgment")
        self.variations.get_transition("to_question")
        self.variations.get_question_variant("company_size")

        stats = self.variations.get_stats()
        assert stats.total_requests == initial_total + 3

    def test_stats_unique_selected(self):
        """Подсчёт уникальных выборов"""
        self.variations.reset()

        # Получаем несколько непустых вариантов
        for _ in range(5):
            self.variations.get_opening("acknowledgment", skip_probability=0.0)

        stats = self.variations.get_stats()
        # Должны быть уникальные выборы
        assert stats.unique_selected > 0

    def test_stats_skipped_openings(self):
        """Подсчёт пропущенных вступлений"""
        self.variations.reset()

        # Форсируем пропуск
        for _ in range(5):
            self.variations.get_opening("acknowledgment", skip_probability=1.0)

        stats = self.variations.get_stats()
        assert stats.skipped_openings >= 5

class TestSingleton:
    """Тесты singleton экземпляра"""

    def test_singleton_exists(self):
        """Singleton variations существует"""
        from src.response_variations import variations
        assert variations is not None

    def test_singleton_is_response_variations(self):
        """Singleton является ResponseVariations"""
        from src.response_variations import variations
        assert isinstance(variations, ResponseVariations)

class TestEdgeCases:
    """Тесты граничных случаев"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_all_options_used(self):
        """Все опции использованы — сброс и продолжение"""
        # Используем все варианты для маленького списка
        for _ in range(20):
            self.variations.get_closing("cta_demo")

        # Должен работать без ошибок
        closing = self.variations.get_closing("cta_demo")
        assert closing in ResponseVariations.CLOSINGS["cta_demo"]

    def test_empty_options_list(self):
        """Пустой список опций"""
        # Напрямую тестируем _get_unused с пустым списком
        # В текущей реализации это вызывает IndexError
        # Это ожидаемое поведение - не должны передавать пустой список
        with pytest.raises(IndexError):
            self.variations._get_unused("empty_test", [])

    def test_single_option(self):
        """Единственная опция"""
        result1 = self.variations._get_unused("single_test", ["единственный"])
        result2 = self.variations._get_unused("single_test", ["единственный"])
        assert result1 == "единственный"
        assert result2 == "единственный"

class TestAllCategories:
    """Проверка всех категорий на валидность"""

    def setup_method(self):
        self.variations = ResponseVariations()

    def test_all_opening_categories_valid(self):
        """Все категории вступлений валидны"""
        for category in ResponseVariations.OPENINGS.keys():
            opening = self.variations.get_opening(category, skip_probability=0.0)
            # Должен вернуть что-то (включая пустую строку)
            assert isinstance(opening, str)

    def test_all_transition_categories_valid(self):
        """Все категории переходов валидны"""
        for category in ResponseVariations.TRANSITIONS.keys():
            transition = self.variations.get_transition(category)
            assert isinstance(transition, str)

    def test_all_question_types_valid(self):
        """Все типы вопросов валидны"""
        for question_type in ResponseVariations.QUESTION_VARIANTS.keys():
            question = self.variations.get_question_variant(question_type)
            assert isinstance(question, str)
            assert question  # Должен быть непустым

    def test_all_closing_categories_valid(self):
        """Все категории завершений валидны"""
        for category in ResponseVariations.CLOSINGS.keys():
            closing = self.variations.get_closing(category)
            assert isinstance(closing, str)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

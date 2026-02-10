"""
Тесты для CTA Generator модуля.

Покрывает:
- Генерацию CTA по состояниям
- Условия добавления CTA
- Мягкие CTA
- Избежание повторений
- Статистику использования
"""

import pytest
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH

from src.cta_generator import (
    CTAGenerator,
    CTAResult,
)

class TestCTAGeneratorBasics:
    """Тесты базовой функциональности"""

    def test_initial_state(self):
        """Начальное состояние генератора"""
        generator = CTAGenerator()

        assert generator.turn_count == 0
        assert len(generator.used_ctas) == 0

    def test_reset_clears_state(self):
        """Reset очищает состояние"""
        generator = CTAGenerator()
        generator.increment_turn()
        generator.increment_turn()
        generator.get_cta("presentation")

        generator.reset()

        assert generator.turn_count == 0
        assert len(generator.used_ctas) == 0

    def test_increment_turn(self):
        """increment_turn увеличивает счётчик"""
        generator = CTAGenerator()

        generator.increment_turn()
        assert generator.turn_count == 1

        generator.increment_turn()
        assert generator.turn_count == 2

class TestShouldAddCTA:
    """Тесты условий добавления CTA"""

    def test_no_cta_for_greeting(self):
        """Нет CTA для greeting (early phase)"""
        generator = CTAGenerator()
        generator.turn_count = 5

        should_add, reason = generator.should_add_cta(
            "greeting",
            "Здравствуйте!",
            {}
        )

        assert not should_add
        assert reason == "early_phase_no_cta"

    def test_no_cta_for_spin_situation(self):
        """Нет CTA для spin_situation"""
        generator = CTAGenerator()
        generator.turn_count = 5

        should_add, reason = generator.should_add_cta(
            "spin_situation",
            "Понял, у вас 15 человек.",
            {}
        )

        assert not should_add

    def test_no_cta_when_response_ends_with_question_mid_phase(self):
        """Нет CTA если ответ заканчивается вопросом в mid-phase"""
        generator = CTAGenerator()
        generator.turn_count = 5

        # mid-phase state (spin_implication) blocks CTA on question
        should_add, reason = generator.should_add_cta(
            "spin_implication",
            "Как это влияет на ваш бизнес?",
            {}
        )

        assert not should_add
        assert reason == "response_ends_with_question"

    def test_cta_allowed_with_question_in_late_phase(self):
        """CTA допускается в late/close фазах даже с вопросом (relaxed gate)"""
        generator = CTAGenerator()
        generator.turn_count = 5

        should_add, reason = generator.should_add_cta(
            "presentation",
            "Wipon решает эту проблему. Хотите узнать как?",
            {}
        )

        # Late phase: question gate is relaxed, CTA is allowed
        assert should_add

    def test_no_cta_high_frustration(self):
        """Нет CTA при высоком frustration"""
        generator = CTAGenerator()
        generator.turn_count = 5

        should_add, reason = generator.should_add_cta(
            "presentation",
            "Wipon решает эту проблему.",
            {"frustration_level": 6}
        )

        assert not should_add
        assert "high_frustration" in reason

    def test_no_cta_too_early(self):
        """Нет CTA в первые ходы"""
        generator = CTAGenerator()
        generator.turn_count = 2

        should_add, reason = generator.should_add_cta(
            "presentation",
            "Wipon решает эту проблему.",
            {}
        )

        assert not should_add
        assert "too_early" in reason

    def test_no_cta_after_answer_question(self):
        """Нет CTA после ответа на вопрос"""
        generator = CTAGenerator()
        generator.turn_count = 5

        should_add, reason = generator.should_add_cta(
            "presentation",
            "Цена от 590 рублей.",
            {"last_action": "answer_question"}
        )

        assert not should_add
        assert reason == "just_answered_question"

    def test_cta_allowed_in_presentation(self):
        """CTA разрешён в presentation"""
        generator = CTAGenerator()
        generator.turn_count = 5

        should_add, reason = generator.should_add_cta(
            "presentation",
            "Wipon решает эту проблему.",
            {}
        )

        assert should_add
        assert reason is None

class TestGetCTA:
    """Тесты получения CTA"""

    def test_get_cta_for_presentation(self):
        """Получение CTA для presentation"""
        generator = CTAGenerator()

        cta = generator.get_cta("presentation")

        assert cta is not None
        assert len(cta) > 0

    def test_get_cta_for_spin_implication(self):
        """Получение CTA для spin_implication"""
        generator = CTAGenerator()

        cta = generator.get_cta("spin_implication")

        assert cta is not None

    def test_get_cta_for_spin_need_payoff(self):
        """Получение CTA для spin_need_payoff"""
        generator = CTAGenerator()

        cta = generator.get_cta("spin_need_payoff")

        assert cta is not None

    def test_no_cta_for_greeting(self):
        """Нет CTA для greeting"""
        generator = CTAGenerator()

        cta = generator.get_cta("greeting")

        assert cta is None

    def test_get_cta_by_type(self):
        """Получение CTA по типу"""
        generator = CTAGenerator()

        demo_cta = generator.get_cta("presentation", cta_type="demo")
        assert demo_cta is not None

        contact_cta = generator.get_cta("presentation", cta_type="contact")
        assert contact_cta is not None

        trial_cta = generator.get_cta("presentation", cta_type="trial")
        assert trial_cta is not None

    def test_get_soft_cta(self):
        """Получение мягкого CTA"""
        generator = CTAGenerator()

        soft_cta = generator.get_cta("presentation", soft=True)

        assert soft_cta is not None
        # Мягкие CTA обычно менее прямолинейные
        assert "?" not in soft_cta or "интересно" in soft_cta.lower()

class TestAppendCTA:
    """Тесты добавления CTA к ответу"""

    def test_append_cta_to_presentation(self):
        """Добавление CTA к presentation"""
        generator = CTAGenerator()
        generator.turn_count = 5

        response = "Wipon помогает автоматизировать работу."
        result = generator.append_cta(response, "presentation", {})

        assert len(result) > len(response)
        assert response in result

    def test_append_cta_preserves_original(self):
        """append_cta сохраняет оригинальный ответ"""
        generator = CTAGenerator()
        generator.turn_count = 5

        response = "Wipon помогает автоматизировать работу."
        result = generator.append_cta(response, "presentation", {})

        assert result.startswith(response.rstrip())

    def test_no_append_when_not_appropriate(self):
        """Не добавляем CTA когда не уместно"""
        generator = CTAGenerator()
        generator.turn_count = 5

        response = "Цена от 590 рублей."
        result = generator.append_cta(
            response,
            "presentation",
            {"last_action": "answer_question"}
        )

        assert result == response

class TestGenerateCTAResult:
    """Тесты генерации полного результата"""

    def test_result_structure(self):
        """Структура CTAResult"""
        generator = CTAGenerator()
        generator.turn_count = 5

        result = generator.generate_cta_result(
            "Wipon решает проблему.",
            "presentation",
            {}
        )

        assert isinstance(result, CTAResult)
        assert hasattr(result, "original_response")
        assert hasattr(result, "cta")
        assert hasattr(result, "final_response")
        assert hasattr(result, "cta_added")
        assert hasattr(result, "skip_reason")

    def test_result_when_cta_added(self):
        """Результат когда CTA добавлен"""
        generator = CTAGenerator()
        generator.turn_count = 5

        result = generator.generate_cta_result(
            "Wipon решает проблему.",
            "presentation",
            {}
        )

        assert result.cta_added
        assert result.cta is not None
        assert result.skip_reason is None
        assert result.final_response != result.original_response

    def test_result_when_cta_skipped(self):
        """Результат когда CTA пропущен"""
        generator = CTAGenerator()
        generator.turn_count = 1  # Слишком рано

        result = generator.generate_cta_result(
            "Wipon решает проблему.",
            "presentation",
            {}
        )

        assert not result.cta_added
        assert result.cta is None
        assert result.skip_reason is not None
        assert result.final_response == result.original_response

class TestAvoidRepetition:
    """Тесты избежания повторений"""

    def test_different_ctas_selected(self):
        """Разные CTA выбираются последовательно"""
        generator = CTAGenerator()

        ctas = set()
        for _ in range(10):
            cta = generator.get_cta("presentation")
            if cta:
                ctas.add(cta)

        # Должно быть несколько уникальных CTA
        assert len(ctas) > 1

    def test_used_ctas_tracked(self):
        """Использованные CTA отслеживаются"""
        generator = CTAGenerator()

        generator.get_cta("presentation")
        generator.get_cta("presentation")

        assert "presentation" in generator.used_ctas
        assert len(generator.used_ctas["presentation"]) > 0

    def test_reset_clears_used_ctas(self):
        """Reset очищает историю использования"""
        generator = CTAGenerator()

        generator.get_cta("presentation")
        generator.reset()

        assert len(generator.used_ctas) == 0

class TestDirectCTA:
    """Тесты прямого получения CTA"""

    def test_get_direct_cta_demo(self):
        """Прямое получение demo CTA"""
        generator = CTAGenerator()

        cta = generator.get_direct_cta("demo")

        assert cta is not None
        assert any(word in cta.lower() for word in ["демо", "показать", "увидеть"])

    def test_get_direct_cta_contact(self):
        """Прямое получение contact CTA"""
        generator = CTAGenerator()

        cta = generator.get_direct_cta("contact")

        assert cta is not None
        assert any(word in cta.lower() for word in ["контакт", "почту", "прислать"])

    def test_get_direct_cta_unknown_type(self):
        """Неизвестный тип — None"""
        generator = CTAGenerator()

        cta = generator.get_direct_cta("unknown_type")

        assert cta is None

    def test_get_soft_cta_method(self):
        """Метод get_soft_cta"""
        generator = CTAGenerator()

        cta = generator.get_soft_cta()

        assert cta is not None
        assert len(cta) > 0

class TestUsageStats:
    """Тесты статистики использования"""

    def test_usage_stats_structure(self):
        """Структура статистики"""
        generator = CTAGenerator()

        stats = generator.get_usage_stats()

        assert "turn_count" in stats
        assert "used_ctas_by_state" in stats
        assert "total_ctas_used" in stats

    def test_usage_stats_tracking(self):
        """Отслеживание статистики"""
        generator = CTAGenerator()
        generator.increment_turn()
        generator.increment_turn()
        generator.get_cta("presentation")
        generator.get_cta("presentation")
        generator.get_cta("spin_implication")

        stats = generator.get_usage_stats()

        assert stats["turn_count"] == 2
        assert stats["total_ctas_used"] == 3

class TestFrustrationAwareness:
    """Тесты учёта frustration"""

    def test_soft_cta_at_medium_frustration(self):
        """Мягкий CTA при среднем frustration"""
        generator = CTAGenerator()
        generator.turn_count = 5

        # При frustration >= 3 используется soft CTA
        result = generator.generate_cta_result(
            "Wipon помогает.",
            "presentation",
            {"frustration_level": 3}
        )

        if result.cta_added:
            # Soft CTA менее агрессивные
            assert "?" not in result.cta or "интересно" in result.cta.lower()

    def test_no_cta_at_high_frustration(self):
        """Нет CTA при высоком frustration"""
        generator = CTAGenerator()
        generator.turn_count = 5

        result = generator.generate_cta_result(
            "Wipon помогает.",
            "presentation",
            {"frustration_level": 7}
        )

        assert not result.cta_added

class TestCTAContent:
    """Тесты содержимого CTA"""

    def test_presentation_ctas_are_actionable(self):
        """CTA для presentation содержат призыв к действию"""
        generator = CTAGenerator()

        for _ in range(5):
            cta = generator.get_cta("presentation")
            if cta:
                assert "?" in cta  # Должен быть вопрос

    def test_close_ctas_ask_for_contact(self):
        """CTA для close спрашивают контакт"""
        generator = CTAGenerator()

        cta = generator.get_cta("close")
        if cta:
            assert any(word in cta.lower() for word in ["контакт", "email", "когда", "почту"])

    def test_handle_objection_ctas_reassuring(self):
        """CTA для handle_objection успокаивающие"""
        generator = CTAGenerator()

        cta = generator.get_cta("handle_objection")
        if cta:
            # Должны содержать успокаивающие слова
            assert any(word in cta.lower() for word in ["бесплатно", "ни к чему не обязывает", "просто"])

class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_empty_response(self):
        """Пустой ответ"""
        generator = CTAGenerator()
        generator.turn_count = 5

        result = generator.append_cta("", "presentation", {})
        # Должен добавить CTA даже к пустому ответу
        assert len(result) > 0

    def test_whitespace_response(self):
        """Ответ с пробелами"""
        generator = CTAGenerator()
        generator.turn_count = 5

        result = generator.append_cta("   ", "presentation", {})
        assert len(result.strip()) > 0

    def test_response_with_trailing_space(self):
        """Ответ с trailing space"""
        generator = CTAGenerator()
        generator.turn_count = 5

        response = "Wipon помогает.   "
        result = generator.append_cta(response, "presentation", {})

        # Не должно быть двойных пробелов
        assert "  " not in result.replace(response.rstrip(), "")

    def test_unknown_state(self):
        """Неизвестное состояние — defaults to early phase (safe, no CTA)"""
        generator = CTAGenerator()
        generator.turn_count = 5

        should_add, reason = generator.should_add_cta(
            "unknown_state",
            "Some response",
            {}
        )

        assert not should_add
        assert reason == "early_phase_no_cta"

class TestIntegrationScenarios:
    """Интеграционные сценарии"""

    def test_typical_conversation_flow(self):
        """Типичный flow диалога"""
        generator = CTAGenerator()

        # Greeting — нет CTA
        generator.increment_turn()
        result1 = generator.generate_cta_result(
            "Здравствуйте!",
            "greeting",
            {}
        )
        assert not result1.cta_added

        # Spin situation — нет CTA
        generator.increment_turn()
        result2 = generator.generate_cta_result(
            "Понял, у вас 15 человек.",
            "spin_situation",
            {}
        )
        assert not result2.cta_added

        # Spin problem — нет CTA
        generator.increment_turn()
        result3 = generator.generate_cta_result(
            "Да, это частая проблема.",
            "spin_problem",
            {}
        )
        assert not result3.cta_added

        # Presentation — есть CTA (turn >= 3)
        generator.increment_turn()
        result4 = generator.generate_cta_result(
            "Wipon решает эту проблему.",
            "presentation",
            {}
        )
        assert result4.cta_added

    def test_cta_after_objection(self):
        """CTA после обработки возражения"""
        generator = CTAGenerator()
        generator.turn_count = 5

        result = generator.generate_cta_result(
            "Понимаю опасения. Давайте посмотрим на цифры.",
            "handle_objection",
            {}
        )

        assert result.cta_added

    def test_no_cta_spam_mid_phase(self):
        """CTA не добавляется если уже есть вопрос в mid-phase"""
        generator = CTAGenerator()
        generator.turn_count = 5

        responses = [
            "Что скажете?",
            "Интересно попробовать?",
            "Хотите узнать больше?",
        ]

        # In mid-phase (spin_implication), question gate blocks CTA
        for response in responses:
            result = generator.generate_cta_result(response, "spin_implication", {})
            assert not result.cta_added, f"CTA added to mid-phase question: {response}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

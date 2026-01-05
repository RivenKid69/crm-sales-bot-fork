"""
Тесты для Objection Handler модуля.

Покрывает:
- Определение типов возражений
- Стратегии 4P's и 3F's
- Ограничение попыток
- Soft close при исчерпании попыток
- Персонализацию ответов
"""

import pytest
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from objection_handler import (
    ObjectionHandler,
    ObjectionType,
    ObjectionFramework,
    ObjectionStrategy,
    ObjectionResult,
)


class TestObjectionDetection:
    """Тесты определения типа возражения"""

    def test_detect_price_objection(self):
        """Определение возражения о цене"""
        handler = ObjectionHandler()

        messages = [
            "Это слишком дорого",
            "Нет бюджета на это",
            "Дороговато для нас",
            "Денег нет",
            "Накладно",
            "Можно скидку?",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection == ObjectionType.PRICE, f"Failed for: {msg}"

    def test_detect_competitor_objection(self):
        """Определение возражения о конкуренте"""
        handler = ObjectionHandler()

        messages = [
            "Мы уже используем Битрикс",
            "У нас есть АМО",
            "Используем iiko",
            "Работаем в своей системе",
            "Уже внедрили CRM",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection == ObjectionType.COMPETITOR, f"Failed for: {msg}"

    def test_detect_no_time_objection(self):
        """Определение возражения о нехватке времени"""
        handler = ObjectionHandler()

        messages = [
            "Нет времени на это",
            "Сейчас занят",
            "Некогда разбираться",
            "Завал на работе",
            "Аврал у нас",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection == ObjectionType.NO_TIME, f"Failed for: {msg}"

    def test_detect_think_objection(self):
        """Определение возражения "надо подумать\""""
        handler = ObjectionHandler()

        messages = [
            "Мне нужно подумать",
            "Надо посоветоваться с партнёром",
            "Хочу обсудить с командой",
            "Нужно согласовать с директором",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection == ObjectionType.THINK, f"Failed for: {msg}"

    def test_detect_no_need_objection(self):
        """Определение возражения "не нужно\""""
        handler = ObjectionHandler()

        messages = [
            "Нам это не нужно",
            "Справляемся без CRM",
            "Обойдёмся",
            "Всё и так работает",
            "Хватает того что есть",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection == ObjectionType.NO_NEED, f"Failed for: {msg}"

    def test_detect_trust_objection(self):
        """Определение возражения о недоверии"""
        handler = ObjectionHandler()

        messages = [
            "Не верю что это работает",
            "Сомневаюсь в эффективности",
            "Правда ли это?",
            "Какие гарантии?",
            "Есть ли отзывы клиентов?",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection == ObjectionType.TRUST, f"Failed for: {msg}"

    def test_detect_timing_objection(self):
        """Определение возражения о тайминге"""
        handler = ObjectionHandler()

        messages = [
            "Не сейчас",
            "Позже вернёмся",
            "Через месяц поговорим",
            "После нового года",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection == ObjectionType.TIMING, f"Failed for: {msg}"

    def test_detect_complexity_objection(self):
        """Определение возражения о сложности"""
        handler = ObjectionHandler()

        messages = [
            "Это сложно внедрять",
            "Долго обучаться",
            "Много работы по настройке",
            "Геморрой с переходом",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection == ObjectionType.COMPLEXITY, f"Failed for: {msg}"

    def test_no_objection_in_neutral_message(self):
        """Нейтральное сообщение — не возражение"""
        handler = ObjectionHandler()

        messages = [
            "Расскажите подробнее",
            "Интересно",
            "А какие есть функции?",
            "Как это работает?",
        ]

        for msg in messages:
            objection = handler.detect_objection(msg)
            assert objection is None, f"False positive for: {msg}"


class TestObjectionStrategies:
    """Тесты стратегий обработки возражений"""

    def test_price_uses_4ps(self):
        """Возражение о цене использует 4P's"""
        handler = ObjectionHandler()
        strategy = handler.get_strategy(ObjectionType.PRICE)

        assert strategy is not None
        assert strategy.framework == ObjectionFramework.FOUR_PS
        assert strategy.max_attempts == 2

    def test_competitor_uses_4ps(self):
        """Возражение о конкуренте использует 4P's"""
        handler = ObjectionHandler()
        strategy = handler.get_strategy(ObjectionType.COMPETITOR)

        assert strategy is not None
        assert strategy.framework == ObjectionFramework.FOUR_PS

    def test_think_uses_3fs(self):
        """Возражение "подумать" использует 3F's"""
        handler = ObjectionHandler()
        strategy = handler.get_strategy(ObjectionType.THINK)

        assert strategy is not None
        assert strategy.framework == ObjectionFramework.THREE_FS

    def test_no_need_uses_3fs(self):
        """Возражение "не нужно" использует 3F's"""
        handler = ObjectionHandler()
        strategy = handler.get_strategy(ObjectionType.NO_NEED)

        assert strategy is not None
        assert strategy.framework == ObjectionFramework.THREE_FS

    def test_trust_uses_3fs(self):
        """Возражение о недоверии использует 3F's"""
        handler = ObjectionHandler()
        strategy = handler.get_strategy(ObjectionType.TRUST)

        assert strategy is not None
        assert strategy.framework == ObjectionFramework.THREE_FS

    def test_strategy_has_response_template(self):
        """Стратегия содержит шаблон ответа"""
        handler = ObjectionHandler()

        for obj_type in ObjectionType:
            strategy = handler.get_strategy(obj_type)
            if strategy:
                assert len(strategy.response_template) > 0
                assert len(strategy.follow_up_question) > 0


class TestAttemptLimiting:
    """Тесты ограничения попыток"""

    def test_first_attempt_returns_strategy(self):
        """Первая попытка возвращает стратегию"""
        handler = ObjectionHandler()
        strategy = handler.get_strategy(ObjectionType.PRICE)

        assert strategy is not None

    def test_second_attempt_returns_strategy(self):
        """Вторая попытка (для max_attempts=2) возвращает стратегию"""
        handler = ObjectionHandler()
        handler.get_strategy(ObjectionType.PRICE)
        strategy = handler.get_strategy(ObjectionType.PRICE)

        assert strategy is not None

    def test_third_attempt_returns_none(self):
        """Третья попытка (для max_attempts=2) возвращает None"""
        handler = ObjectionHandler()
        handler.get_strategy(ObjectionType.PRICE)
        handler.get_strategy(ObjectionType.PRICE)
        strategy = handler.get_strategy(ObjectionType.PRICE)

        assert strategy is None

    def test_no_time_single_attempt(self):
        """no_time имеет только 1 попытку"""
        handler = ObjectionHandler()
        strategy1 = handler.get_strategy(ObjectionType.NO_TIME)
        strategy2 = handler.get_strategy(ObjectionType.NO_TIME)

        assert strategy1 is not None
        assert strategy2 is None

    def test_attempts_tracked_separately(self):
        """Попытки отслеживаются отдельно для каждого типа"""
        handler = ObjectionHandler()

        # Исчерпываем попытки для PRICE
        handler.get_strategy(ObjectionType.PRICE)
        handler.get_strategy(ObjectionType.PRICE)
        price_strategy = handler.get_strategy(ObjectionType.PRICE)

        # COMPETITOR ещё не исчерпан
        competitor_strategy = handler.get_strategy(ObjectionType.COMPETITOR)

        assert price_strategy is None
        assert competitor_strategy is not None

    def test_reset_clears_attempts(self):
        """Reset сбрасывает счётчик попыток"""
        handler = ObjectionHandler()

        # Исчерпываем попытки
        handler.get_strategy(ObjectionType.PRICE)
        handler.get_strategy(ObjectionType.PRICE)
        assert handler.get_strategy(ObjectionType.PRICE) is None

        # Сбрасываем
        handler.reset()

        # Попытки снова доступны
        assert handler.get_strategy(ObjectionType.PRICE) is not None


class TestHandleObjection:
    """Тесты полной обработки возражения"""

    def test_handle_returns_result(self):
        """handle_objection возвращает ObjectionResult"""
        handler = ObjectionHandler()
        result = handler.handle_objection("Это дорого")

        assert isinstance(result, ObjectionResult)
        assert result.objection_type == ObjectionType.PRICE
        assert result.strategy is not None
        assert result.attempt_number == 1

    def test_handle_no_objection(self):
        """Нет возражения — пустой результат"""
        handler = ObjectionHandler()
        result = handler.handle_objection("Расскажите подробнее")

        assert result.objection_type is None
        assert result.strategy is None
        assert not result.should_soft_close

    def test_handle_exhausted_attempts_soft_close(self):
        """Исчерпанные попытки → soft close"""
        handler = ObjectionHandler()

        # Исчерпываем попытки
        handler.handle_objection("Это дорого")
        handler.handle_objection("Всё равно дорого")
        result = handler.handle_objection("Очень дорого")

        assert result.should_soft_close
        assert result.strategy is None
        assert "message" in result.response_parts

    def test_handle_includes_response_parts(self):
        """Результат содержит части ответа"""
        handler = ObjectionHandler()
        result = handler.handle_objection("Это дорого")

        assert "template" in result.response_parts
        assert "follow_up" in result.response_parts
        assert "framework" in result.response_parts


class TestPersonalization:
    """Тесты персонализации ответов"""

    def test_personalize_pain_point(self):
        """Персонализация pain_point"""
        handler = ObjectionHandler()
        result = handler.handle_objection(
            "Это дорого",
            collected_data={"pain_point": "потеря клиентов"}
        )

        assert "потеря клиентов" in result.response_parts.get("follow_up", "")

    def test_personalize_routine_task(self):
        """Персонализация routine_task"""
        handler = ObjectionHandler()
        result = handler.handle_objection(
            "Нам это не нужно",
            collected_data={"routine_task": "ввод данных вручную"}
        )

        follow_up = result.response_parts.get("follow_up", "")
        assert "ввод данных вручную" in follow_up or "ручную работу" in follow_up

    def test_default_placeholders(self):
        """Дефолтные значения для плейсхолдеров"""
        handler = ObjectionHandler()
        result = handler.handle_objection("Это дорого")

        # Должен использовать дефолт "текущую проблему"
        follow_up = result.response_parts.get("follow_up", "")
        assert len(follow_up) > 0


class TestCanHandleMore:
    """Тесты проверки возможности обработки"""

    def test_can_handle_more_fresh(self):
        """Свежий handler может обрабатывать"""
        handler = ObjectionHandler()
        assert handler.can_handle_more(ObjectionType.PRICE)

    def test_can_handle_more_after_one(self):
        """После одной попытки ещё можно"""
        handler = ObjectionHandler()
        handler.get_strategy(ObjectionType.PRICE)
        assert handler.can_handle_more(ObjectionType.PRICE)

    def test_cannot_handle_more_exhausted(self):
        """После исчерпания попыток нельзя"""
        handler = ObjectionHandler()
        handler.get_strategy(ObjectionType.PRICE)
        handler.get_strategy(ObjectionType.PRICE)
        assert not handler.can_handle_more(ObjectionType.PRICE)


class TestGetAttempts:
    """Тесты получения статистики попыток"""

    def test_get_attempts_count(self):
        """get_attempts_count возвращает правильное значение"""
        handler = ObjectionHandler()

        assert handler.get_attempts_count(ObjectionType.PRICE) == 0

        handler.get_strategy(ObjectionType.PRICE)
        assert handler.get_attempts_count(ObjectionType.PRICE) == 1

        handler.get_strategy(ObjectionType.PRICE)
        assert handler.get_attempts_count(ObjectionType.PRICE) == 2

    def test_get_all_attempts(self):
        """get_all_attempts возвращает все попытки"""
        handler = ObjectionHandler()

        handler.get_strategy(ObjectionType.PRICE)
        handler.get_strategy(ObjectionType.COMPETITOR)
        handler.get_strategy(ObjectionType.COMPETITOR)

        attempts = handler.get_all_attempts()

        assert attempts["price"] == 1
        assert attempts["competitor"] == 2


class TestSoftCloseTemplates:
    """Тесты шаблонов soft close"""

    def test_soft_close_templates_exist(self):
        """Шаблоны soft close существуют"""
        handler = ObjectionHandler()
        assert len(handler.SOFT_CLOSE_TEMPLATES) > 0

    def test_soft_close_message_in_result(self):
        """Soft close содержит сообщение"""
        handler = ObjectionHandler()

        # Исчерпываем попытки
        handler.handle_objection("Дорого")
        handler.handle_objection("Дорого")
        result = handler.handle_objection("Дорого")

        assert result.should_soft_close
        assert "message" in result.response_parts
        assert len(result.response_parts["message"]) > 0


class TestObjectionPriority:
    """Тесты приоритета возражений"""

    def test_price_has_high_priority(self):
        """Цена имеет высокий приоритет"""
        handler = ObjectionHandler()

        # Сообщение с несколькими возражениями
        msg = "Это дорого и нам не нужно"
        objection = handler.detect_objection(msg)

        # PRICE должен иметь приоритет
        assert objection == ObjectionType.PRICE

    def test_think_over_no_need(self):
        """THINK имеет приоритет над NO_NEED (для 'нужно подумать')"""
        handler = ObjectionHandler()

        # THINK должен иметь приоритет чтобы "нужно подумать" не путать с "не нужно"
        msg = "Не нужно, хотя надо подумать"
        objection = handler.detect_objection(msg)

        # THINK проверяется раньше и "подума" матчится
        assert objection == ObjectionType.THINK


class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_empty_message(self):
        """Пустое сообщение"""
        handler = ObjectionHandler()
        objection = handler.detect_objection("")
        assert objection is None

    def test_very_short_message(self):
        """Очень короткое сообщение"""
        handler = ObjectionHandler()
        objection = handler.detect_objection("нет")
        # Короткое "нет" без контекста может не быть возражением
        # Зависит от паттернов

    def test_long_message_with_objection(self):
        """Длинное сообщение с возражением"""
        handler = ObjectionHandler()
        msg = "Мы тут долго обсуждали, и в итоге решили, что это слишком дорого для нашего бюджета в текущем году"
        objection = handler.detect_objection(msg)
        assert objection == ObjectionType.PRICE

    def test_case_insensitive(self):
        """Регистронезависимость"""
        handler = ObjectionHandler()

        assert handler.detect_objection("ДОРОГО") == ObjectionType.PRICE
        assert handler.detect_objection("Дорого") == ObjectionType.PRICE
        assert handler.detect_objection("дорого") == ObjectionType.PRICE


class TestIntegrationScenarios:
    """Интеграционные сценарии"""

    def test_typical_price_objection_flow(self):
        """Типичный flow возражения о цене"""
        handler = ObjectionHandler()

        # Первое возражение
        result1 = handler.handle_objection("Это дорого для нас")
        assert result1.objection_type == ObjectionType.PRICE
        assert result1.strategy is not None
        assert result1.attempt_number == 1
        assert not result1.should_soft_close

        # Повторное возражение
        result2 = handler.handle_objection("Всё равно дорого")
        assert result2.attempt_number == 2
        assert not result2.should_soft_close

        # Третье — soft close
        result3 = handler.handle_objection("Нет, дорого")
        assert result3.should_soft_close
        assert result3.strategy is None

    def test_mixed_objections(self):
        """Разные типы возражений"""
        handler = ObjectionHandler()

        # Разные возражения
        r1 = handler.handle_objection("Дорого")
        r2 = handler.handle_objection("Нет времени")
        r3 = handler.handle_objection("Используем Битрикс")

        assert r1.objection_type == ObjectionType.PRICE
        assert r2.objection_type == ObjectionType.NO_TIME
        assert r3.objection_type == ObjectionType.COMPETITOR

        # У всех есть стратегии (разные попытки)
        assert r1.strategy is not None
        assert r2.strategy is not None
        assert r3.strategy is not None

    def test_personalized_response_flow(self):
        """Flow с персонализацией"""
        handler = ObjectionHandler()

        collected_data = {
            "pain_point": "потеря 20% клиентов",
            "company_size": 15,
            "industry": "розница",
        }

        result = handler.handle_objection(
            "Это слишком дорого",
            collected_data=collected_data
        )

        # Персонализированный follow_up
        assert "потеря 20% клиентов" in result.response_parts["follow_up"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

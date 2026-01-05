"""
Система вариативности ответов для избежания повторений.

Исследование Stanford 2024: 1.6-2.1x рост diversity при использовании вариаций.

Использование:
    from response_variations import variations

    # Получить вступление
    opening = variations.get_opening("acknowledgment")

    # Получить вариант вопроса
    question = variations.get_question_variant("company_size")

    # Собрать естественный ответ
    response = variations.build_natural_response(
        core_message="Сколько человек у вас в команде?",
        add_opening=True,
        opening_category="acknowledgment"
    )
"""

from dataclasses import dataclass, field
from random import choice, random
from typing import Dict, List, Optional, Set

from logger import logger


@dataclass
class VariationStats:
    """Статистика использования вариаций"""
    total_requests: int = 0
    unique_selected: int = 0
    skipped_openings: int = 0


class ResponseVariations:
    """
    Система вариативности ответов для избежания повторений.

    Особенности:
    - Разные категории вступлений (acknowledgment, empathy, positive_reaction)
    - Переходы к вопросам (to_question, to_deeper)
    - Альтернативные формулировки вопросов
    - Отслеживание использованных вариантов (LRU-подобное)
    - Вероятностный пропуск вступлений для краткости
    """

    # Вступления (можно опустить для краткости)
    OPENINGS: Dict[str, List[str]] = {
        "acknowledgment": [
            "Понял.",
            "Хорошо.",
            "Ясно.",
            "Так.",
            "Угу.",
            "Окей.",
            "Принял.",
            "Услышал.",
            "Понятно.",
            "",  # Пустой = без вступления
        ],
        "empathy": [
            "Понимаю.",
            "Знакомая ситуация.",
            "Многие с этим сталкиваются.",
            "Да, это частая проблема.",
            "Слышу вас.",
            "Это важный момент.",
            "Да, это актуально.",
            "",
        ],
        "positive_reaction": [
            "Отлично.",
            "Хорошо.",
            "Здорово.",
            "Звучит неплохо.",
            "Интересно.",
            "Отличный вопрос.",
            "Рад слышать.",
            "",
        ],
        "problem_acknowledgment": [
            "Да, это серьёзно.",
            "Понимаю, это неудобно.",
            "Это действительно проблема.",
            "Да, с этим сталкиваются многие.",
            "Знакомая боль.",
            "",
        ],
    }

    # Переходы к вопросам
    TRANSITIONS: Dict[str, List[str]] = {
        "to_question": [
            "Скажите,",
            "Подскажите,",
            "А",
            "Кстати,",
            "Вот что интересно:",
            "Ещё момент:",
            "Уточните,",
            "",
        ],
        "to_deeper": [
            "И ещё:",
            "Важный момент:",
            "А вот что интересно:",
            "Кстати говоря,",
            "",
        ],
        "to_proposal": [
            "Давайте так:",
            "Предлагаю:",
            "Вот что могу предложить:",
            "Смотрите,",
            "",
        ],
    }

    # Альтернативные формулировки вопросов
    QUESTION_VARIANTS: Dict[str, List[str]] = {
        "company_size": [
            "сколько человек в команде?",
            "сколько сотрудников работает с клиентами?",
            "какой размер команды?",
            "команда большая или небольшая?",
            "сколько человек будет пользоваться системой?",
        ],
        "pain_point": [
            "какая главная сложность сейчас?",
            "что отнимает больше всего времени?",
            "что хотелось бы улучшить в первую очередь?",
            "какая задача самая «больная»?",
            "с какими проблемами сталкиваетесь чаще всего?",
        ],
        "current_tools": [
            "чем сейчас пользуетесь для учёта?",
            "как сейчас ведёте клиентскую базу?",
            "какие инструменты используете?",
            "в чём ведёте учёт?",
        ],
        "impact": [
            "как это влияет на работу?",
            "сколько это стоит бизнесу?",
            "во что это обходится?",
            "какие последствия?",
        ],
        "desired_outcome": [
            "что было бы идеальным результатом?",
            "чего хотите добиться?",
            "какой результат вас бы устроил?",
            "что изменилось бы в идеале?",
        ],
        "demo_interest": [
            "хотите посмотреть как это работает?",
            "интересно увидеть систему в деле?",
            "готовы глянуть демо?",
            "показать как это работает?",
        ],
        "contact_request": [
            "как с вами связаться?",
            "куда прислать информацию?",
            "подскажите контакт для связи?",
            "какой номер или почта удобнее?",
        ],
    }

    # Завершающие фразы
    CLOSINGS: Dict[str, List[str]] = {
        "soft_offer": [
            "Если интересно — расскажу подробнее.",
            "Могу показать на примере.",
            "Готов ответить на вопросы.",
        ],
        "cta_demo": [
            "Хотите посмотреть демо?",
            "Показать как это работает?",
            "Запланируем демо?",
        ],
        "cta_contact": [
            "Оставите контакт?",
            "Куда прислать информацию?",
            "Как с вами связаться?",
        ],
    }

    # Извинения (для frustrated клиентов)
    APOLOGIES: List[str] = [
        "Извините за неудобства.",
        "Прошу прощения.",
        "Понимаю, это может раздражать.",
        "Сорри за это.",
    ]

    # Предложения выхода (для очень frustrated клиентов)
    EXIT_OFFERS: List[str] = [
        "Если сейчас неудобно — можем продолжить позже.",
        "Давайте так: пришлю информацию на почту, посмотрите когда удобно.",
        "Не буду отнимать время — оставлю контакты если понадобится.",
    ]

    def __init__(self):
        # История использованных вариантов (LRU-подобное)
        self._used_recently: Dict[str, List[str]] = {}
        # Статистика
        self._stats = VariationStats()

    def reset(self) -> None:
        """Сброс истории использованных вариантов"""
        self._used_recently.clear()
        self._stats = VariationStats()

    def get_opening(
        self,
        category: str,
        skip_probability: float = 0.3,
        force_skip: bool = False
    ) -> str:
        """
        Получить вступление с вероятностью пропуска.

        Args:
            category: Категория вступления (acknowledgment, empathy, etc.)
            skip_probability: Вероятность вернуть пустую строку (для краткости)
            force_skip: Принудительно пропустить вступление

        Returns:
            Строка со вступлением или пустая строка
        """
        self._stats.total_requests += 1

        if force_skip or random() < skip_probability:
            self._stats.skipped_openings += 1
            return ""

        options = self.OPENINGS.get(category, [""])
        result = self._get_unused(f"opening_{category}", options)

        if result:
            self._stats.unique_selected += 1

        return result

    def get_transition(self, category: str) -> str:
        """
        Получить переходную фразу к вопросу.

        Args:
            category: Категория перехода (to_question, to_deeper, to_proposal)

        Returns:
            Строка с переходом
        """
        self._stats.total_requests += 1

        options = self.TRANSITIONS.get(category, [""])
        result = self._get_unused(f"trans_{category}", options)

        if result:
            self._stats.unique_selected += 1

        return result

    def get_question_variant(self, question_type: str) -> str:
        """
        Получить вариант формулировки вопроса.

        Args:
            question_type: Тип вопроса (company_size, pain_point, etc.)

        Returns:
            Строка с вопросом или пустая строка если тип не найден
        """
        self._stats.total_requests += 1

        options = self.QUESTION_VARIANTS.get(question_type, [])
        if not options:
            logger.warning(f"Unknown question type: {question_type}")
            return ""

        result = self._get_unused(f"q_{question_type}", options)
        self._stats.unique_selected += 1

        return result

    def get_closing(self, category: str) -> str:
        """
        Получить завершающую фразу.

        Args:
            category: Категория завершения (soft_offer, cta_demo, cta_contact)

        Returns:
            Строка с завершением
        """
        self._stats.total_requests += 1

        options = self.CLOSINGS.get(category, [""])
        result = self._get_unused(f"closing_{category}", options)

        if result:
            self._stats.unique_selected += 1

        return result

    def get_apology(self) -> str:
        """Получить фразу извинения"""
        self._stats.total_requests += 1
        return self._get_unused("apology", self.APOLOGIES)

    def get_exit_offer(self) -> str:
        """Получить предложение выхода"""
        self._stats.total_requests += 1
        return self._get_unused("exit_offer", self.EXIT_OFFERS)

    def _get_unused(self, key: str, options: List[str]) -> str:
        """
        Возвращает вариант, не использованный недавно.

        Реализует LRU-подобную логику:
        - Если все варианты использованы — сбрасывает историю
        - Ограничивает историю половиной доступных вариантов
        """
        if key not in self._used_recently:
            self._used_recently[key] = []

        used = self._used_recently[key]

        # Фильтруем неиспользованные (исключая пустые строки из фильтрации)
        non_empty_options = [o for o in options if o]
        available = [o for o in options if o not in used or not o]

        if not available:
            # Все использованы — сбросить историю
            self._used_recently[key] = []
            available = options

        # Выбираем случайный
        selected = choice(available)

        # Запоминаем использованный (кроме пустых)
        if selected:
            self._used_recently[key].append(selected)

        # Ограничиваем историю
        max_history = max(len(non_empty_options) // 2, 2)
        if len(self._used_recently[key]) > max_history:
            self._used_recently[key] = self._used_recently[key][-max_history:]

        return selected

    def build_natural_response(
        self,
        core_message: str,
        add_opening: bool = True,
        opening_category: str = "acknowledgment",
        add_transition: bool = False,
        transition_category: str = "to_question",
        skip_opening_probability: float = 0.3
    ) -> str:
        """
        Собирает естественный ответ из компонентов.

        Args:
            core_message: Основное сообщение
            add_opening: Добавить вступление
            opening_category: Категория вступления
            add_transition: Добавить переходную фразу
            transition_category: Категория перехода
            skip_opening_probability: Вероятность пропуска вступления

        Returns:
            Собранный ответ
        """
        parts: List[str] = []

        if add_opening:
            opening = self.get_opening(opening_category, skip_opening_probability)
            if opening:
                parts.append(opening)

        if add_transition:
            transition = self.get_transition(transition_category)
            if transition:
                parts.append(transition)

        parts.append(core_message)

        return " ".join(parts).strip()

    def build_empathetic_response(
        self,
        problem_acknowledgment: str,
        question: str,
        skip_probability: float = 0.2
    ) -> str:
        """
        Собирает эмпатичный ответ для problem-фазы.

        Args:
            problem_acknowledgment: Признание проблемы (кастомное или из шаблонов)
            question: Следующий вопрос
            skip_probability: Вероятность пропуска вступления

        Returns:
            Собранный ответ
        """
        parts: List[str] = []

        # Вступление (эмпатия или acknowledgment)
        opening = self.get_opening("empathy", skip_probability)
        if opening:
            parts.append(opening)

        # Признание проблемы
        if problem_acknowledgment:
            parts.append(problem_acknowledgment)

        # Вопрос
        parts.append(question)

        return " ".join(parts).strip()

    def build_apologetic_response(
        self,
        core_message: str,
        offer_exit: bool = False
    ) -> str:
        """
        Собирает извиняющийся ответ (для frustrated клиентов).

        Args:
            core_message: Основное сообщение
            offer_exit: Предложить выход из разговора

        Returns:
            Собранный ответ с извинением
        """
        parts: List[str] = []

        # Извинение
        apology = self.get_apology()
        parts.append(apology)

        # Основное сообщение
        parts.append(core_message)

        # Предложение выхода
        if offer_exit:
            exit_offer = self.get_exit_offer()
            parts.append(exit_offer)

        return " ".join(parts).strip()

    def get_stats(self) -> VariationStats:
        """Получить статистику использования"""
        return self._stats

    def get_used_history(self) -> Dict[str, List[str]]:
        """Получить историю использованных вариантов"""
        return self._used_recently.copy()


# Singleton экземпляр
variations = ResponseVariations()


# =============================================================================
# CLI для тестирования
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ДЕМО RESPONSE VARIATIONS")
    print("=" * 60)

    # Тест вступлений
    print("\n--- Вступления (acknowledgment) ---")
    for i in range(5):
        opening = variations.get_opening("acknowledgment", skip_probability=0.0)
        print(f"  {i+1}. '{opening}'")

    # Тест переходов
    print("\n--- Переходы ---")
    for i in range(3):
        trans = variations.get_transition("to_question")
        print(f"  {i+1}. '{trans}'")

    # Тест вопросов
    print("\n--- Варианты вопросов ---")
    for q_type in ["company_size", "pain_point", "demo_interest"]:
        variant = variations.get_question_variant(q_type)
        print(f"  {q_type}: '{variant}'")

    # Тест сборки ответа
    print("\n--- Сборка естественного ответа ---")
    for i in range(3):
        response = variations.build_natural_response(
            core_message="сколько человек в команде?",
            add_opening=True,
            opening_category="acknowledgment",
            add_transition=True
        )
        print(f"  {i+1}. '{response}'")

    # Тест эмпатичного ответа
    print("\n--- Эмпатичный ответ ---")
    response = variations.build_empathetic_response(
        problem_acknowledgment="Да, терять клиентов — это серьёзно.",
        question="Сколько примерно теряете в месяц?"
    )
    print(f"  '{response}'")

    # Тест извиняющегося ответа
    print("\n--- Извиняющийся ответ ---")
    response = variations.build_apologetic_response(
        core_message="Давайте я сразу отвечу на ваш вопрос.",
        offer_exit=True
    )
    print(f"  '{response}'")

    # Статистика
    print("\n--- Статистика ---")
    stats = variations.get_stats()
    print(f"  Всего запросов: {stats.total_requests}")
    print(f"  Уникальных выбрано: {stats.unique_selected}")
    print(f"  Пропущено вступлений: {stats.skipped_openings}")

    print("\n" + "=" * 60)

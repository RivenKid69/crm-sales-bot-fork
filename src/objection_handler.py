"""
Objection Handler для CRM Sales Bot.

Обработчик возражений с фреймворками 4P's и 3F's.

4P's: Pause → Probe → Present → Proceed
3F's: Feel → Felt → Found (для эмоциональных возражений)

Использование:
    from objection_handler import ObjectionHandler, ObjectionType

    handler = ObjectionHandler()
    objection = handler.detect_objection("слишком дорого")

    if objection:
        strategy = handler.get_strategy(objection)
        if strategy:
            # Использовать strategy.response_template и strategy.follow_up
            pass
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Pattern
from enum import Enum

from logger import logger


class ObjectionType(Enum):
    """
    Типы возражений клиентов.

    Каждый тип имеет свою стратегию обработки.
    """
    PRICE = "price"               # Дорого, нет бюджета
    COMPETITOR = "competitor"     # Уже используем другую систему
    NO_TIME = "no_time"           # Нет времени, занят
    THINK = "think"               # Надо подумать, посоветоваться
    NO_NEED = "no_need"           # Не нужно, справляемся
    TRUST = "trust"               # Не верю, сомневаюсь
    TIMING = "timing"             # Не сейчас, потом
    COMPLEXITY = "complexity"     # Сложно, долго внедрять


class ObjectionFramework(Enum):
    """Фреймворки обработки возражений"""
    FOUR_PS = "4ps"      # Pause → Probe → Present → Proceed
    THREE_FS = "3fs"     # Feel → Felt → Found


@dataclass
class ObjectionStrategy:
    """
    Стратегия обработки возражения.

    Attributes:
        framework: Используемый фреймворк
        response_template: Шаблон ответа
        follow_up_question: Уточняющий вопрос
        max_attempts: Максимум попыток обработки
        can_soft_close: Можно ли перейти к мягкому закрытию
    """
    framework: ObjectionFramework
    response_template: str
    follow_up_question: str
    max_attempts: int = 2
    can_soft_close: bool = False


@dataclass
class ObjectionResult:
    """
    Результат обработки возражения.

    Attributes:
        objection_type: Тип возражения
        strategy: Стратегия обработки (если есть)
        attempt_number: Номер попытки
        should_soft_close: Нужно ли мягко закрыть
        response_parts: Части ответа (template, follow_up)
    """
    objection_type: ObjectionType
    strategy: Optional[ObjectionStrategy]
    attempt_number: int
    should_soft_close: bool
    response_parts: Dict[str, str] = field(default_factory=dict)


class ObjectionHandler:
    """
    Обработчик возражений с фреймворками 4P's и 3F's.

    Принципы:
    1. Сначала определяем тип возражения
    2. Выбираем подходящий фреймворк
    3. Ограничиваем количество попыток
    4. При исчерпании попыток → soft close

    Attributes:
        objection_attempts: Счётчик попыток по типам возражений
    """

    # Паттерны для определения типа возражения
    OBJECTION_PATTERNS: Dict[ObjectionType, List[str]] = {
        ObjectionType.PRICE: [
            r"дорог",
            r"дешевл",
            r"скидк",
            r"бюджет",
            r"денег\s+нет",
            r"не\s+потянем",
            r"накладн",
            r"неподъём",
            r"кусает",
            r"не\s+по\s+карман",
            r"много\s+хотите",
            r"много\s+просите",
            r"завышен",
            r"переплат",
            r"не\s+окуп",
            r"экономим",
            r"не\s+тянем",
        ],
        ObjectionType.COMPETITOR: [
            r"уже\s+есть",
            r"уже\s+пользу",
            r"используем",
            r"работаем\s+в",
            r"внедрили",
            r"перешли\s+на",
            r"купили",
            r"подключили",
            r"битрикс",
            r"амо",
            r"amocrm",
            r"мегаплан",
            r"salesforce",
            r"1с.*crm",
            r"iiko",
            r"poster",
            r"r.keeper",
            r"своя\s+система",
            r"самописн",
        ],
        ObjectionType.NO_TIME: [
            r"нет\s+времен",
            r"времени\s+нет",
            r"некогда",
            r"занят",
            r"не\s+до\s+этого",
            r"голова\s+забит",
            r"завал",
            r"запар",
            r"аврал",
            r"горит",
            r"дедлайн",
            r"не\s+успева",
            r"загружен",
            r"зашива",
        ],
        ObjectionType.THINK: [
            r"подума",
            r"посоветова",
            r"обсуди",
            r"согласова",
            r"надо\s+обдума",
            r"посовещ",
            r"посмотр",
            r"взвес",
            r"прикин",
            r"нужно\s+подума",   # "нужно подумать" - важно до NO_NEED
        ],
        ObjectionType.NO_NEED: [
            r"не\s+нужн",
            r"не\s+надо",
            r"обойдёмся",
            r"обойдемся",
            r"справляемся",
            r"справимся",
            r"хватает",
            r"достаточно",
            r"устраивает",
            r"и\s+так\s+норм",
            r"всё\s+работает",
            r"все\s+работает",
            r"и\s+так\s+работает",  # "и так работает"
            r"нет\s+проблем",
        ],
        ObjectionType.TRUST: [
            r"не\s+верю",
            r"не\s+верит",
            r"сомнева",
            r"правда\s*\?",
            r"правда\s+ли",        # "Правда ли это?"
            r"серьёзно\s*\?",
            r"серьезно\s*\?",
            r"гарантии",
            r"докаж",
            r"подтверд",
            r"кто\s+пользуется",
            r"отзыв",
            r"референс",
        ],
        ObjectionType.TIMING: [
            r"не\s+сейчас",
            r"не\s+время",
            r"позже",
            r"потом",
            r"позвон.*позже",
            r"через\s+недел",
            r"через\s+месяц",
            r"в\s+следующ",
            r"после\s+нового",
            r"после\s+праздник",
            r"после\s+отпуск",
            r"в\s+новом\s+году",
        ],
        ObjectionType.COMPLEXITY: [
            r"сложно",
            r"долго\s+внедр",
            r"долго\s+настраив",
            r"долго\s+обуч",
            r"переучива",
            r"перестраива",
            r"тяжело\s+переход",
            r"много\s+работы",
            r"геморро",
            r"заморочк",
        ],
    }

    # Стратегии 4P's (для рациональных возражений)
    STRATEGIES_4PS: Dict[ObjectionType, ObjectionStrategy] = {
        ObjectionType.PRICE: ObjectionStrategy(
            framework=ObjectionFramework.FOUR_PS,
            response_template=(
                "Понимаю, вопрос бюджета важен. "
                "Скажите, вы сравниваете с чем-то конкретным или просто кажется дорого в абсолюте?"
            ),
            follow_up_question="Кстати, посчитаем: сколько примерно теряете сейчас на {pain_point}?",
            max_attempts=2,
        ),
        ObjectionType.COMPETITOR: ObjectionStrategy(
            framework=ObjectionFramework.FOUR_PS,
            response_template=(
                "Хорошо что уже пользуетесь системой. "
                "Что именно не устраивает или чего не хватает?"
            ),
            follow_up_question="Если бы можно было что-то улучшить — что бы это было?",
            max_attempts=2,
        ),
        ObjectionType.NO_TIME: ObjectionStrategy(
            framework=ObjectionFramework.FOUR_PS,
            response_template=(
                "Понимаю, времени всегда не хватает. "
                "Когда было бы удобнее вернуться к разговору?"
            ),
            follow_up_question="Могу просто прислать информацию на почту — посмотрите когда будет время?",
            max_attempts=1,
            can_soft_close=True,
        ),
        ObjectionType.TIMING: ObjectionStrategy(
            framework=ObjectionFramework.FOUR_PS,
            response_template=(
                "Понимаю, сейчас не лучший момент. "
                "Когда планируете вернуться к этому вопросу?"
            ),
            follow_up_question="Могу напомнить ближе к этому времени?",
            max_attempts=1,
            can_soft_close=True,
        ),
        ObjectionType.COMPLEXITY: ObjectionStrategy(
            framework=ObjectionFramework.FOUR_PS,
            response_template=(
                "Понимаю опасения. На самом деле внедрение занимает 1-2 дня. "
                "Данные переносим мы, обучение включено."
            ),
            follow_up_question="Что именно вызывает больше всего опасений?",
            max_attempts=2,
        ),
    }

    # Стратегии 3F's (для эмоциональных возражений)
    STRATEGIES_3FS: Dict[ObjectionType, ObjectionStrategy] = {
        ObjectionType.THINK: ObjectionStrategy(
            framework=ObjectionFramework.THREE_FS,
            response_template=(
                "Понимаю, решение важное — нужно обдумать. "
                "Многие клиенты говорили то же самое. "
                "Они потом отмечали, что демо помогло определиться — увидели систему в деле."
            ),
            follow_up_question="Может запланируем демо? Это ни к чему не обязывает.",
            max_attempts=1,
            can_soft_close=True,
        ),
        ObjectionType.NO_NEED: ObjectionStrategy(
            framework=ObjectionFramework.THREE_FS,
            response_template=(
                "Понимаю, если всё работает — зачем менять. "
                "Другие клиенты тоже так думали. "
                "А потом считали сколько времени тратят на рутину — и удивлялись."
            ),
            follow_up_question="Кстати, сколько времени у вас уходит на {routine_task}?",
            max_attempts=1,
            can_soft_close=True,
        ),
        ObjectionType.TRUST: ObjectionStrategy(
            framework=ObjectionFramework.THREE_FS,
            response_template=(
                "Понимаю сомнения — это нормально перед покупкой. "
                "Многие клиенты сначала сомневались. "
                "Сейчас они говорят, что зря не попробовали раньше."
            ),
            follow_up_question="Могу показать кейсы компаний из вашей сферы — интересно?",
            max_attempts=2,
        ),
    }

    # Шаблоны для soft close
    SOFT_CLOSE_TEMPLATES: List[str] = [
        "Хорошо, не буду настаивать. Оставлю контакты — свяжетесь когда будет удобно?",
        "Понимаю. Могу прислать информацию на почту — посмотрите когда будет время?",
        "Окей, давайте так: я оставлю контакты, и вы свяжетесь когда созреет решение.",
    ]

    def __init__(self):
        """Инициализация обработчика"""
        self.objection_attempts: Dict[ObjectionType, int] = {}
        self._compiled_patterns: Dict[ObjectionType, List[Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Предкомпиляция regex паттернов для производительности"""
        for obj_type, patterns in self.OBJECTION_PATTERNS.items():
            self._compiled_patterns[obj_type] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

    def reset(self) -> None:
        """Сброс счётчика попыток для нового разговора"""
        self.objection_attempts.clear()

    def detect_objection(self, message: str) -> Optional[ObjectionType]:
        """
        Определить тип возражения в сообщении.

        Args:
            message: Текст сообщения клиента

        Returns:
            ObjectionType или None если возражение не найдено
        """
        message_lower = message.lower()

        # Проверяем паттерны в порядке приоритета
        priority_order = [
            ObjectionType.PRICE,
            ObjectionType.THINK,      # THINK before NO_NEED for "нужно подумать"
            ObjectionType.NO_NEED,
            ObjectionType.COMPETITOR,
            ObjectionType.NO_TIME,
            ObjectionType.TRUST,
            ObjectionType.TIMING,
            ObjectionType.COMPLEXITY,
        ]

        for obj_type in priority_order:
            patterns = self._compiled_patterns.get(obj_type, [])
            for pattern in patterns:
                if pattern.search(message_lower):
                    logger.info(
                        "Objection detected",
                        type=obj_type.value,
                        pattern=pattern.pattern
                    )
                    return obj_type

        return None

    def get_strategy(self, objection_type: ObjectionType) -> Optional[ObjectionStrategy]:
        """
        Получить стратегию обработки возражения.

        Учитывает количество попыток — если лимит исчерпан, возвращает None.

        Args:
            objection_type: Тип возражения

        Returns:
            ObjectionStrategy или None если попытки исчерпаны
        """
        # Получаем текущее количество попыток
        attempts = self.objection_attempts.get(objection_type, 0)

        # Сначала проверяем 4P's
        strategy = self.STRATEGIES_4PS.get(objection_type)
        if not strategy:
            # Затем 3F's
            strategy = self.STRATEGIES_3FS.get(objection_type)

        if not strategy:
            logger.warning(
                "No strategy for objection",
                type=objection_type.value
            )
            return None

        # Проверяем лимит попыток
        if attempts >= strategy.max_attempts:
            logger.info(
                "Objection max attempts reached",
                type=objection_type.value,
                attempts=attempts
            )
            return None

        # Увеличиваем счётчик попыток
        self.objection_attempts[objection_type] = attempts + 1

        return strategy

    def handle_objection(
        self,
        message: str,
        collected_data: Optional[Dict] = None
    ) -> ObjectionResult:
        """
        Полная обработка возражения.

        Args:
            message: Сообщение клиента
            collected_data: Собранные данные для персонализации

        Returns:
            ObjectionResult с результатом обработки
        """
        collected_data = collected_data or {}

        # Определяем тип возражения
        objection_type = self.detect_objection(message)
        if not objection_type:
            # Не возражение — возвращаем пустой результат
            return ObjectionResult(
                objection_type=None,
                strategy=None,
                attempt_number=0,
                should_soft_close=False,
            )

        # Получаем стратегию
        attempt = self.objection_attempts.get(objection_type, 0) + 1
        strategy = self.get_strategy(objection_type)

        if not strategy:
            # Попытки исчерпаны — soft close
            return ObjectionResult(
                objection_type=objection_type,
                strategy=None,
                attempt_number=attempt,
                should_soft_close=True,
                response_parts={
                    "message": self._get_soft_close_message(),
                }
            )

        # Персонализируем follow-up
        follow_up = self._personalize_follow_up(
            strategy.follow_up_question,
            collected_data
        )

        return ObjectionResult(
            objection_type=objection_type,
            strategy=strategy,
            attempt_number=attempt,
            should_soft_close=strategy.can_soft_close and attempt >= strategy.max_attempts,
            response_parts={
                "template": strategy.response_template,
                "follow_up": follow_up,
                "framework": strategy.framework.value,
            }
        )

    def _personalize_follow_up(
        self,
        template: str,
        collected_data: Dict
    ) -> str:
        """Персонализация follow-up вопроса"""
        # Заменяем плейсхолдеры
        placeholders = {
            "{pain_point}": collected_data.get("pain_point", "текущую проблему"),
            "{routine_task}": collected_data.get("routine_task", "ручную работу"),
            "{company_name}": collected_data.get("company_name", ""),
            "{industry}": collected_data.get("industry", ""),
        }

        result = template
        for placeholder, value in placeholders.items():
            result = result.replace(placeholder, value)

        return result

    def _get_soft_close_message(self) -> str:
        """Получить сообщение для мягкого закрытия"""
        import random
        return random.choice(self.SOFT_CLOSE_TEMPLATES)

    def get_attempts_count(self, objection_type: ObjectionType) -> int:
        """Получить количество попыток для типа возражения"""
        return self.objection_attempts.get(objection_type, 0)

    def get_all_attempts(self) -> Dict[str, int]:
        """Получить все попытки для аналитики"""
        return {
            obj_type.value: count
            for obj_type, count in self.objection_attempts.items()
        }

    def can_handle_more(self, objection_type: ObjectionType) -> bool:
        """Проверить можно ли ещё обрабатывать это возражение"""
        strategy = self.STRATEGIES_4PS.get(objection_type) or \
                   self.STRATEGIES_3FS.get(objection_type)

        if not strategy:
            return False

        attempts = self.objection_attempts.get(objection_type, 0)
        return attempts < strategy.max_attempts


# =============================================================================
# CLI для тестирования
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("OBJECTION HANDLER DEMO")
    print("=" * 60)

    handler = ObjectionHandler()

    # Тестовые сообщения
    test_messages = [
        "Это слишком дорого для нас",
        "Мы уже используем Битрикс24",
        "Сейчас нет времени на это",
        "Мне нужно подумать",
        "Нам это не нужно, справляемся",
        "А вы точно не обманете?",
    ]

    for message in test_messages:
        print(f"\n--- Сообщение: '{message}' ---")
        result = handler.handle_objection(message)

        if result.objection_type:
            print(f"Тип: {result.objection_type.value}")
            print(f"Попытка: {result.attempt_number}")
            print(f"Soft close: {result.should_soft_close}")
            if result.strategy:
                print(f"Framework: {result.strategy.framework.value}")
                print(f"Template: {result.strategy.response_template[:50]}...")
            if result.response_parts:
                print(f"Response parts: {list(result.response_parts.keys())}")
        else:
            print("Возражение не найдено")

    print("\n" + "=" * 60)
    print("ATTEMPTS SUMMARY")
    print("=" * 60)
    print(handler.get_all_attempts())

"""
Question Deduplication Engine — SSoT модуль для предотвращения повторных вопросов.

Решает проблему: бот переспрашивает о данных, которые клиент уже предоставил.
Пример: Клиент сказал "ручной учёт" → бот спрашивает "Чем пользуетесь для учёта?"

Архитектурные принципы:
1. SSoT (Single Source of Truth) — конфигурация в question_dedup.yaml
2. Dynamic filtering — автоматическое исключение уже отвеченных вопросов
3. Context-aware — разные вопросы для разных фаз SPIN
4. Graceful Degradation — при ошибках возвращаем fallback инструкции
5. Observable — метрики и логирование всех фильтраций

Использование:
    from question_dedup import question_dedup_engine

    # Получить доступные вопросы для фазы
    result = question_dedup_engine.get_available_questions(
        phase="situation",
        collected_data={"company_size": 10},
        missing_data=["current_tools", "business_type"]
    )

    # Получить инструкцию "не спрашивай"
    instruction = question_dedup_engine.get_do_not_ask_instruction(
        collected_data={"company_size": 10, "current_tools": "Excel"}
    )

    # Полный контекст для промпта
    prompt_context = question_dedup_engine.get_prompt_context(
        phase="situation",
        collected_data={"company_size": 10},
        missing_data=["current_tools"]
    )
"""

from dataclasses import dataclass, field
from pathlib import Path
from random import choice
from typing import Any, Dict, List, Optional, Set

import yaml

from logger import logger


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class QuestionDedupConfig:
    """Конфигурация из question_dedup.yaml."""

    data_fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    phase_questions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    prompt_instructions: Dict[str, str] = field(default_factory=dict)
    strategies: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QuestionDedupMetrics:
    """Метрики использования question deduplication engine."""

    total_requests: int = 0
    questions_filtered: int = 0
    questions_generated: int = 0
    phases_with_all_data: int = 0
    fallback_used: int = 0

    # История для анализа
    filtered_fields: Dict[str, int] = field(default_factory=dict)
    phase_requests: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для логирования."""
        return {
            "total_requests": self.total_requests,
            "questions_filtered": self.questions_filtered,
            "questions_generated": self.questions_generated,
            "phases_with_all_data": self.phases_with_all_data,
            "fallback_used": self.fallback_used,
            "filtering_rate": (
                self.questions_filtered / self.total_requests
                if self.total_requests > 0
                else 0.0
            ),
        }


@dataclass
class QuestionGenerationResult:
    """Результат генерации вопросов."""

    available_questions: List[str]
    do_not_ask_fields: List[str]
    do_not_ask_instruction: str
    available_questions_instruction: str
    all_data_collected: bool
    phase: str
    filtered_count: int

    def to_prompt_variables(self) -> Dict[str, str]:
        """Конвертация в переменные для промпта."""
        return {
            "available_questions": self.available_questions_instruction,
            "do_not_ask": self.do_not_ask_instruction,
            "missing_data_questions": "\n".join(
                f"- {q}" for q in self.available_questions
            ) if self.available_questions else "Все данные собраны",
            "collected_fields_list": ", ".join(self.do_not_ask_fields) if self.do_not_ask_fields else "пока ничего",
        }


# =============================================================================
# QUESTION DEDUPLICATION ENGINE
# =============================================================================


class QuestionDeduplicationEngine:
    """
    Движок дедупликации вопросов.

    Функции:
    1. Генерация списка доступных вопросов на основе missing_data
    2. Генерация инструкции "не спрашивай" на основе collected_data
    3. Фильтрация вопросов по фазе (любой flow: SPIN, MEDDIC, BANT, etc.)
    4. Generic fallback для фаз без phase-specific конфигурации
    5. Метрики и мониторинг
    """

    CONFIG_PATH = Path(__file__).parent / "yaml_config" / "question_dedup.yaml"

    # Fallback вопросы если конфиг недоступен
    FALLBACK_QUESTIONS = {
        # SPIN phases
        "situation": [
            "Сколько человек в вашей команде?",
            "Чем сейчас пользуетесь для учёта?",
            "Какой у вас формат бизнеса?",
        ],
        "problem": [
            "Какая главная сложность сейчас?",
            "Что не устраивает в текущем процессе?",
        ],
        "implication": [
            "Как это влияет на работу?",
            "Сколько времени/денег теряете?",
        ],
        "need_payoff": [
            "Что было бы идеально для вас?",
            "Как должна работать система?",
        ],
        # MEDDIC phases
        "metrics": [
            "По каким метрикам оцениваете успех?",
            "Какие KPI важны?",
        ],
        "buyer": [
            "Кто принимает финальное решение?",
            "С кем нужно согласовать?",
        ],
        "criteria": [
            "Что для вас ключевое при выборе?",
            "Какие критерии важны?",
        ],
        "process": [
            "Какие шаги в процессе принятия решения?",
            "Нужны ли согласования?",
        ],
        "pain": [
            "Какая главная сложность?",
            "Что мешает работать?",
        ],
        "champion": [
            "Кто внутри команды будет вести проект?",
            "Есть человек кто поможет внедрению?",
        ],
        # BANT phases
        "budget": [
            "Какой бюджет рассматриваете?",
            "На какую сумму ориентируетесь?",
        ],
        "authority": [
            "Кто принимает финальное решение?",
            "Вы сами решаете или есть руководство?",
        ],
        "need": [
            "Какая главная потребность сейчас?",
            "Что хотели бы улучшить?",
        ],
        "timeline": [
            "Когда планируете внедрение?",
            "Какие сроки рассматриваете?",
        ],
        # Shared phases
        "discover": [
            "Расскажите о вашей компании?",
            "Сколько человек в команде?",
        ],
        "interest": [
            "Что вас заинтересовало?",
            "Какой у вас формат бизнеса?",
        ],
        "desire": [
            "Что хотели бы улучшить?",
            "Какой результат был бы идеальным?",
        ],
        "features": [
            "Сколько человек будет пользоваться?",
            "Чем сейчас пользуетесь?",
        ],
        "advantages": [
            "Какая главная сложность сейчас?",
            "Что не устраивает?",
        ],
        "benefits": [
            "Какой результат хотите получить?",
            "Что было бы идеально?",
        ],
        "quantify": [
            "Как это влияет на бизнес в цифрах?",
            "Сколько теряете из-за этого?",
        ],
        # Default fallback
        "_default": [
            "Расскажите подробнее о вашей ситуации?",
            "Что для вас сейчас самое важное?",
        ],
    }

    def __init__(self, config_path: Optional[Path] = None):
        """
        Инициализация движка.

        Args:
            config_path: Путь к конфигурации (по умолчанию question_dedup.yaml)
        """
        self._config_path = config_path or self.CONFIG_PATH
        self._config: Optional[QuestionDedupConfig] = None
        self._metrics = QuestionDedupMetrics()

        # Кэш для быстрого доступа: field -> related_questions
        self._field_to_questions: Dict[str, List[str]] = {}

        # Загружаем конфигурацию
        self._load_config()

    def _load_config(self) -> None:
        """Загрузить конфигурацию из YAML."""
        try:
            if not self._config_path.exists():
                logger.warning(
                    "Question dedup config not found, using defaults",
                    path=str(self._config_path),
                )
                self._config = QuestionDedupConfig()
                return

            with open(self._config_path, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)

            self._config = QuestionDedupConfig(
                data_fields=raw_config.get("data_fields", {}),
                phase_questions=raw_config.get("phase_questions", {}),
                prompt_instructions=raw_config.get("prompt_instructions", {}),
                strategies=raw_config.get("strategies", {}),
                metrics=raw_config.get("metrics", {}),
            )

            # Строим индекс field -> questions
            self._build_field_index()

            logger.info(
                "Question dedup config loaded",
                data_fields=len(self._config.data_fields),
                phases=len(self._config.phase_questions),
            )

        except Exception as e:
            logger.error("Failed to load question dedup config", error=str(e))
            self._config = QuestionDedupConfig()
            self._metrics.fallback_used += 1

    def _build_field_index(self) -> None:
        """Построить индекс field -> related_questions."""
        self._field_to_questions = {}

        if not self._config:
            return

        for field_name, field_config in self._config.data_fields.items():
            related = field_config.get("related_questions", [])
            self._field_to_questions[field_name] = related

    def get_available_questions(
        self,
        phase: str,
        collected_data: Dict[str, Any],
        missing_data: Optional[List[str]] = None,
    ) -> QuestionGenerationResult:
        """
        Получить список доступных вопросов для фазы.

        Args:
            phase: Текущая фаза (any flow phase: situation, problem, budget, metrics, etc.)
            collected_data: Уже собранные данные
            missing_data: Список полей которые ещё нужно собрать (опционально)

        Returns:
            QuestionGenerationResult с доступными вопросами и инструкциями
        """
        self._metrics.total_requests += 1
        self._metrics.phase_requests[phase] = self._metrics.phase_requests.get(phase, 0) + 1

        # Определяем какие поля уже собраны
        collected_fields = set(
            k for k, v in collected_data.items()
            if v is not None and v != "" and v != 0
        )

        # Определяем какие поля нужны для этой фазы
        phase_config = self._config.phase_questions.get(phase, {}) if self._config else {}

        # If no phase-specific config exists, use generic dedup
        if not phase_config:
            return self._generic_dedup(phase, collected_data, missing_data)

        required_fields = set(phase_config.get("required_fields", []))
        optional_fields = set(phase_config.get("optional_fields", []))
        all_phase_fields = required_fields | optional_fields

        # Вычисляем missing если не передано
        if missing_data is None:
            missing_fields = all_phase_fields - collected_fields
        else:
            missing_fields = set(missing_data)

        # Генерируем доступные вопросы
        available_questions = self._generate_questions_for_fields(
            phase=phase,
            missing_fields=missing_fields,
            collected_data=collected_data,
        )

        # Генерируем инструкцию "не спрашивай"
        do_not_ask_fields = list(collected_fields & all_phase_fields)
        do_not_ask_instruction = self._generate_do_not_ask_instruction(
            do_not_ask_fields, collected_data
        )

        # Генерируем инструкцию с доступными вопросами
        available_instruction = self._generate_available_questions_instruction(
            available_questions
        )

        # Проверяем собраны ли все данные
        all_collected = len(missing_fields) == 0

        if all_collected:
            self._metrics.phases_with_all_data += 1

        # Логируем фильтрацию
        filtered_count = len(do_not_ask_fields)
        self._metrics.questions_filtered += filtered_count
        self._metrics.questions_generated += len(available_questions)

        for field in do_not_ask_fields:
            self._metrics.filtered_fields[field] = (
                self._metrics.filtered_fields.get(field, 0) + 1
            )

        if filtered_count > 0:
            logger.debug(
                "Questions filtered by dedup engine",
                phase=phase,
                filtered_fields=do_not_ask_fields,
                available_count=len(available_questions),
            )

        return QuestionGenerationResult(
            available_questions=available_questions,
            do_not_ask_fields=do_not_ask_fields,
            do_not_ask_instruction=do_not_ask_instruction,
            available_questions_instruction=available_instruction,
            all_data_collected=all_collected,
            phase=phase,
            filtered_count=filtered_count,
        )

    def _generic_dedup(
        self,
        phase: str,
        collected_data: Dict[str, Any],
        missing_data: Optional[List[str]] = None,
    ) -> QuestionGenerationResult:
        """
        Universal dedup: works for any flow without phase-specific config.

        Generates do_not_ask for ALL collected fields and uses fallback questions.
        """
        collected_fields = [
            k for k, v in collected_data.items()
            if v is not None and v != "" and v != 0
        ]
        do_not_ask = self._generate_do_not_ask_instruction(collected_fields, collected_data)

        available_questions = []
        if missing_data:
            for field in missing_data:
                field_config = self._config.data_fields.get(field, {}) if self._config else {}
                related = field_config.get("related_questions", [])
                if related:
                    available_questions.append(choice(related))

        # If no questions from data_fields, use fallback
        if not available_questions:
            fallback = self.FALLBACK_QUESTIONS.get(phase, self.FALLBACK_QUESTIONS.get("_default", []))
            available_questions = fallback[:2]

        available_instruction = self._generate_available_questions_instruction(available_questions)

        all_collected = not bool(missing_data)
        if all_collected:
            self._metrics.phases_with_all_data += 1

        filtered_count = len(collected_fields)
        self._metrics.questions_filtered += filtered_count
        self._metrics.questions_generated += len(available_questions)

        for field in collected_fields:
            self._metrics.filtered_fields[field] = (
                self._metrics.filtered_fields.get(field, 0) + 1
            )

        logger.debug(
            "Generic dedup applied (no phase config)",
            phase=phase,
            filtered_fields=collected_fields,
            available_count=len(available_questions),
        )

        return QuestionGenerationResult(
            available_questions=available_questions,
            do_not_ask_fields=collected_fields,
            do_not_ask_instruction=do_not_ask,
            available_questions_instruction=available_instruction,
            all_data_collected=all_collected,
            phase=phase,
            filtered_count=filtered_count,
        )

    def _generate_questions_for_fields(
        self,
        phase: str,
        missing_fields: Set[str],
        collected_data: Dict[str, Any],
    ) -> List[str]:
        """Генерировать вопросы для недостающих полей."""
        questions = []

        if not self._config or not self._config.phase_questions:
            # Fallback
            return self.FALLBACK_QUESTIONS.get(phase, [])[:2]

        phase_config = self._config.phase_questions.get(phase, {})
        question_templates = phase_config.get("question_templates", {})

        for field in missing_fields:
            field_questions = question_templates.get(field, [])
            if field_questions:
                # Выбираем один вопрос и подставляем переменные
                question = choice(field_questions) if len(field_questions) > 1 else field_questions[0]
                # Подставляем known values
                question = self._substitute_variables(question, collected_data)
                questions.append(question)

        # Если нет вопросов из конфига, используем fallback
        if not questions and missing_fields:
            fallback = self.FALLBACK_QUESTIONS.get(phase, [])
            questions = fallback[:min(2, len(fallback))]

        return questions

    def _substitute_variables(self, question: str, collected_data: Dict[str, Any]) -> str:
        """Подставить переменные в вопрос (напр. {current_tools})."""
        try:
            # Безопасная подстановка - только известные поля
            safe_data = {k: str(v) for k, v in collected_data.items() if v}
            return question.format_map(SafeDict(safe_data))
        except Exception:
            return question

    def _generate_do_not_ask_instruction(
        self,
        do_not_ask_fields: List[str],
        collected_data: Dict[str, Any],
    ) -> str:
        """Генерировать инструкцию 'не спрашивай'."""
        if not do_not_ask_fields:
            return ""

        if not self._config or not self._config.prompt_instructions:
            # Fallback инструкция
            items = []
            for field in do_not_ask_fields:
                value = collected_data.get(field)
                if value:
                    items.append(f"- {field}: уже известно ({value})")
            if items:
                return "НЕ спрашивай о:\n" + "\n".join(items)
            return ""

        template = self._config.prompt_instructions.get("do_not_ask_template", "")
        if not template:
            return ""

        # Формируем список
        items = []
        for field in do_not_ask_fields:
            field_config = self._config.data_fields.get(field, {})
            description = field_config.get("description", field)
            value = collected_data.get(field)

            if value:
                items.append(f"- {description}: уже известно \"{value}\"")
            else:
                items.append(f"- {description}: уже собрано")

        do_not_ask_list = "\n".join(items)
        return template.format(do_not_ask_list=do_not_ask_list)

    def _generate_available_questions_instruction(
        self,
        available_questions: List[str],
    ) -> str:
        """Генерировать инструкцию с доступными вопросами."""
        if not available_questions:
            if self._config and self._config.prompt_instructions:
                return self._config.prompt_instructions.get(
                    "all_data_collected_instruction",
                    "Все данные для этой фазы собраны."
                )
            return "Все данные для этой фазы собраны."

        if not self._config or not self._config.prompt_instructions:
            # Fallback
            questions_list = "\n".join(f"- \"{q}\"" for q in available_questions)
            return f"Выбери ОДИН вопрос из доступных:\n{questions_list}"

        template = self._config.prompt_instructions.get("available_questions_template", "")
        if not template:
            questions_list = "\n".join(f"- \"{q}\"" for q in available_questions)
            return f"Выбери ОДИН вопрос из доступных:\n{questions_list}"

        questions_list = "\n".join(f"- \"{q}\"" for q in available_questions)
        return template.format(available_questions_list=questions_list)

    def get_prompt_context(
        self,
        phase: str,
        collected_data: Dict[str, Any],
        missing_data: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """
        Получить полный контекст для промпта.

        Args:
            phase: Текущая фаза SPIN
            collected_data: Уже собранные данные
            missing_data: Список полей которые ещё нужно собрать

        Returns:
            Dict с переменными для промпта:
            - available_questions: инструкция с доступными вопросами
            - do_not_ask: инструкция что не спрашивать
            - missing_data_questions: форматированный список вопросов
            - collected_fields_list: список собранных полей
        """
        result = self.get_available_questions(phase, collected_data, missing_data)
        return result.to_prompt_variables()

    def get_do_not_ask_instruction(
        self,
        collected_data: Dict[str, Any],
    ) -> str:
        """
        Получить инструкцию 'не спрашивай' на основе collected_data.

        Args:
            collected_data: Уже собранные данные

        Returns:
            Строка с инструкцией или пустая строка
        """
        collected_fields = [
            k for k, v in collected_data.items()
            if v is not None and v != "" and v != 0
        ]
        return self._generate_do_not_ask_instruction(collected_fields, collected_data)

    def is_question_about_collected_field(
        self,
        question: str,
        collected_data: Dict[str, Any],
    ) -> bool:
        """
        Проверить, спрашивает ли вопрос о уже собранном поле.

        Args:
            question: Текст вопроса
            collected_data: Собранные данные

        Returns:
            True если вопрос о уже известном поле
        """
        question_lower = question.lower()

        for field, value in collected_data.items():
            if value is None or value == "" or value == 0:
                continue

            # Проверяем related_questions
            related = self._field_to_questions.get(field, [])
            for related_q in related:
                # Простое совпадение по ключевым словам
                related_words = set(related_q.lower().split())
                question_words = set(question_lower.split())
                overlap = related_words & question_words
                # Если >50% слов совпадают, считаем похожим вопросом
                if len(overlap) >= len(related_words) * 0.5:
                    logger.debug(
                        "Detected question about collected field",
                        question=question[:50],
                        field=field,
                        matched_related=related_q[:50],
                    )
                    return True

        return False

    def get_metrics(self) -> Dict[str, Any]:
        """Получить метрики."""
        return self._metrics.to_dict()

    def reset_metrics(self) -> None:
        """Сбросить метрики."""
        self._metrics = QuestionDedupMetrics()


class SafeDict(dict):
    """Dict который возвращает placeholder для отсутствующих ключей."""

    def __missing__(self, key):
        return f"{{{key}}}"


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

# Глобальный экземпляр движка
question_dedup_engine = QuestionDeduplicationEngine()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def get_available_questions(
    phase: str,
    collected_data: Dict[str, Any],
    missing_data: Optional[List[str]] = None,
) -> QuestionGenerationResult:
    """Convenience function для получения доступных вопросов."""
    return question_dedup_engine.get_available_questions(phase, collected_data, missing_data)


def get_prompt_context(
    phase: str,
    collected_data: Dict[str, Any],
    missing_data: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Convenience function для получения контекста промпта."""
    return question_dedup_engine.get_prompt_context(phase, collected_data, missing_data)


def get_do_not_ask_instruction(collected_data: Dict[str, Any]) -> str:
    """Convenience function для получения инструкции 'не спрашивай'."""
    return question_dedup_engine.get_do_not_ask_instruction(collected_data)

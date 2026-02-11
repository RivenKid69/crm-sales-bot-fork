"""
Response Diversity Engine — SSoT модуль для управления разнообразием ответов.

Решает проблему монотонности ответов (1203 ответа начинающихся с "Понимаю").

Архитектурные принципы:
1. SSoT (Single Source of Truth) — конфигурация в diversity.yaml
2. LRU Rotation — не повторяем недавно использованные фразы
3. Context-aware — разные вступления для разных ситуаций
4. Graceful Degradation — при ошибках возвращаем оригинальный ответ
5. Observable — метрики и логирование всех замен

Использование:
    from response_diversity import diversity_engine

    # Post-process ответ
    processed = diversity_engine.process_response(
        response="Понимаю, это важно. Расскажите подробнее.",
        context={"intent": "problem_shared", "frustration_level": 0}
    )

    # Получить альтернативное вступление
    opening = diversity_engine.get_opening(
        category="empathy",
        context={"frustration_level": 2}
    )

Исследование: Stanford 2024 — 1.6-2.1x рост diversity при использовании rotation.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from random import choice, random
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from src.logger import logger


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class DiversityConfig:
    """Конфигурация из diversity.yaml."""

    banned_openings: Dict[str, List[str]] = field(default_factory=dict)
    alternative_openings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    transitions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    context_mapping: Dict[str, Dict[str, str]] = field(default_factory=dict)
    replacement_strategies: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    prompt_instructions: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiversityMetrics:
    """Метрики использования diversity engine."""

    total_processed: int = 0
    banned_replaced: int = 0
    openings_generated: int = 0
    skipped_openings: int = 0
    lru_rotations: int = 0

    # История для анализа
    last_openings: List[str] = field(default_factory=list)
    opening_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для логирования."""
        return {
            "total_processed": self.total_processed,
            "banned_replaced": self.banned_replaced,
            "openings_generated": self.openings_generated,
            "skipped_openings": self.skipped_openings,
            "lru_rotations": self.lru_rotations,
            "replacement_rate": (
                self.banned_replaced / self.total_processed
                if self.total_processed > 0
                else 0.0
            ),
        }


@dataclass
class ProcessingResult:
    """Результат обработки ответа."""

    original: str
    processed: str
    was_modified: bool
    modification_type: Optional[str] = None  # "banned_replaced", "opening_added", etc.
    opening_used: Optional[str] = None
    category_used: Optional[str] = None


# =============================================================================
# RESPONSE DIVERSITY ENGINE
# =============================================================================


class ResponseDiversityEngine:
    """
    Движок разнообразия ответов.

    Функции:
    1. Замена запрещённых вступлений (banned_openings)
    2. Генерация альтернативных вступлений (alternative_openings)
    3. LRU rotation для избежания повторов
    4. Context-aware выбор вступлений
    5. Метрики и мониторинг
    """

    CONFIG_PATH = Path(__file__).parent / "yaml_config" / "diversity.yaml"

    def __init__(self, config_path: Optional[Path] = None):
        """
        Инициализация движка.

        Args:
            config_path: Путь к конфигурации (по умолчанию diversity.yaml)
        """
        self._config_path = config_path or self.CONFIG_PATH
        self._config: Optional[DiversityConfig] = None
        self._metrics = DiversityMetrics()

        # LRU история для каждой категории
        self._lru_history: Dict[str, List[str]] = {}

        # Компилированные regex паттерны
        self._banned_patterns: List[re.Pattern] = []

        # Загружаем конфигурацию
        self._load_config()

    def _load_config(self) -> None:
        """Загрузить конфигурацию из YAML."""
        try:
            if not self._config_path.exists():
                logger.warning(
                    "Diversity config not found, using defaults",
                    path=str(self._config_path),
                )
                self._config = DiversityConfig()
                return

            with open(self._config_path, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)

            self._config = DiversityConfig(
                banned_openings=raw_config.get("banned_openings", {}),
                alternative_openings=raw_config.get("alternative_openings", {}),
                transitions=raw_config.get("transitions", {}),
                context_mapping=raw_config.get("context_mapping", {}),
                replacement_strategies=raw_config.get("replacement_strategies", {}),
                prompt_instructions=raw_config.get("prompt_instructions", {}),
                metrics=raw_config.get("metrics", {}),
            )

            # Компилируем regex паттерны
            self._compile_banned_patterns()

            logger.info(
                "Diversity config loaded",
                banned_patterns=len(self._banned_patterns),
                opening_categories=len(self._config.alternative_openings),
            )

        except Exception as e:
            logger.error("Failed to load diversity config", error=str(e))
            self._config = DiversityConfig()

    def _compile_banned_patterns(self) -> None:
        """Компилировать regex паттерны для banned openings."""
        self._banned_patterns = []

        if not self._config:
            return

        # Добавляем exact match как regex
        exact_matches = self._config.banned_openings.get("exact_match", [])
        for phrase in exact_matches:
            # Экранируем и добавляем ^ для начала строки
            pattern = f"^{re.escape(phrase)}[,.]?\\s*"
            try:
                self._banned_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid regex pattern: {pattern}, error: {e}")

        # Добавляем паттерны
        patterns = self._config.banned_openings.get("patterns", [])
        for pattern in patterns:
            try:
                self._banned_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid regex pattern: {pattern}, error: {e}")

    def reload_config(self) -> None:
        """Перезагрузить конфигурацию."""
        self._load_config()

    def reset(self) -> None:
        """Сбросить состояние (LRU история, метрики)."""
        self._lru_history.clear()
        self._metrics = DiversityMetrics()

    # =========================================================================
    # MAIN PROCESSING
    # =========================================================================

    def process_response(
        self,
        response: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Обработать ответ: заменить запрещённые вступления.

        Args:
            response: Оригинальный ответ
            context: Контекст (intent, state, frustration_level)

        Returns:
            ProcessingResult с обработанным ответом
        """
        context = context or {}
        self._metrics.total_processed += 1

        # Проверяем на banned openings
        banned_match = self._find_banned_opening(response)

        if banned_match:
            # Заменяем на альтернативу
            processed, opening_used, category = self._replace_banned_opening(
                response, banned_match, context
            )

            self._metrics.banned_replaced += 1

            logger.debug(
                "Banned opening replaced",
                original_start=response[:50],
                new_start=processed[:50],
                category=category,
            )

            return ProcessingResult(
                original=response,
                processed=processed,
                was_modified=True,
                modification_type="banned_replaced",
                opening_used=opening_used,
                category_used=category,
            )

        # Ответ не содержит banned openings
        return ProcessingResult(
            original=response,
            processed=response,
            was_modified=False,
        )

    def _find_banned_opening(self, response: str) -> Optional[re.Match]:
        """Найти banned opening в ответе."""
        for pattern in self._banned_patterns:
            match = pattern.match(response)
            if match:
                return match
        return None

    def _replace_banned_opening(
        self,
        response: str,
        match: re.Match,
        context: Dict[str, Any],
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Заменить banned opening на альтернативу.

        Returns:
            Tuple[processed_response, opening_used, category]
        """
        # Определяем категорию по контексту
        category = self._determine_category(context)

        # Получаем альтернативное вступление
        opening = self.get_opening(category, context)

        # Вырезаем banned opening из ответа
        rest_of_response = response[match.end() :].lstrip()
        # Remove artifacts like "—", "-", ":" that can appear after replacement.
        rest_of_response = re.sub(r"^[—\-:]+\s*", "", rest_of_response)

        # Если вступление пустое — возвращаем без него
        if not opening:
            # Capitalize first letter of rest
            if len(rest_of_response) >= 1:
                rest_of_response = rest_of_response[0].upper() + rest_of_response[1:]
            return rest_of_response, None, category

        # Собираем новый ответ
        # Capitalize first letter of rest if needed
        if len(rest_of_response) >= 1 and opening.endswith((".", "!", "?")):
            # If opening already ends with punctuation, leading dash in rest is noise.
            rest_of_response = re.sub(r"^[—\-]+\s*", "", rest_of_response)
            rest_of_response = rest_of_response[0].upper() + rest_of_response[1:]

        processed = f"{opening} {rest_of_response}".strip()

        return processed, opening, category

    def _determine_category(self, context: Dict[str, Any]) -> str:
        """Определить категорию вступления по контексту."""
        if not self._config:
            return "acknowledgment"

        mapping = self._config.context_mapping

        # 1. По интенту
        intent = context.get("intent", "")
        intent_mapping = mapping.get("intent_to_opening", {})
        if intent in intent_mapping:
            return intent_mapping[intent]

        # 2. По состоянию
        state = context.get("state", "")
        state_mapping = mapping.get("state_to_opening", {})
        if state in state_mapping:
            return state_mapping[state]

        # 3. По уровню фрустрации
        frustration = context.get("frustration_level", 0)
        frustration_mapping = mapping.get("frustration_to_opening", {})
        # Ключи в YAML — строки, frustration — int
        if str(frustration) in frustration_mapping:
            return frustration_mapping[str(frustration)]

        # Default
        return "acknowledgment"

    # =========================================================================
    # OPENING GENERATION
    # =========================================================================

    def get_opening(
        self,
        category: str,
        context: Optional[Dict[str, Any]] = None,
        force_skip: bool = False,
    ) -> str:
        """
        Получить вступление для ответа.

        Args:
            category: Категория вступления (empathy, acknowledgment, etc.)
            context: Контекст
            force_skip: Принудительно пропустить вступление

        Returns:
            Строка вступления или пустая строка
        """
        context = context or {}
        self._metrics.openings_generated += 1

        if not self._config:
            return ""

        # Получаем конфигурацию категории
        category_config = self._config.alternative_openings.get(category, {})
        if not category_config:
            logger.debug(f"Unknown opening category: {category}")
            return ""

        phrases = category_config.get("phrases", [])
        if not phrases:
            return ""

        # Проверяем skip probability
        skip_prob = category_config.get("skip_probability", 0.3)
        if force_skip or random() < skip_prob:
            self._metrics.skipped_openings += 1
            return ""

        # LRU selection
        opening = self._select_with_lru(category, phrases)

        # Track usage
        self._track_opening_usage(opening)

        return opening

    def _select_with_lru(self, category: str, phrases: List[str]) -> str:
        """
        Выбрать фразу с LRU rotation.

        Не повторяет недавно использованные фразы.
        """
        lru_key = f"opening_{category}"

        if lru_key not in self._lru_history:
            self._lru_history[lru_key] = []

        used = self._lru_history[lru_key]

        # Фильтруем не-пустые фразы для LRU
        non_empty = [p for p in phrases if p]

        # Находим доступные (не использованные недавно)
        available = [p for p in phrases if p not in used or not p]

        if not available:
            # Все использованы — сбрасываем LRU
            self._lru_history[lru_key] = []
            available = phrases
            self._metrics.lru_rotations += 1

        # Выбираем случайную
        selected = choice(available)

        # Добавляем в LRU (кроме пустых)
        if selected:
            self._lru_history[lru_key].append(selected)

        # Ограничиваем размер LRU
        max_history = self._get_max_lru_history()
        if len(self._lru_history[lru_key]) > max_history:
            self._lru_history[lru_key] = self._lru_history[lru_key][-max_history:]

        return selected

    def _get_max_lru_history(self) -> int:
        """Получить максимальный размер LRU истории."""
        if not self._config:
            return 5

        default_strategy = self._config.replacement_strategies.get("default", {})
        return default_strategy.get("max_lru_history", 5)

    def _track_opening_usage(self, opening: str) -> None:
        """Отслеживать использование вступлений."""
        if not opening:
            return

        # Добавляем в историю последних
        self._metrics.last_openings.append(opening)
        if len(self._metrics.last_openings) > 20:
            self._metrics.last_openings = self._metrics.last_openings[-20:]

        # Увеличиваем счётчик
        self._metrics.opening_counts[opening] = (
            self._metrics.opening_counts.get(opening, 0) + 1
        )

    # =========================================================================
    # TRANSITION PHRASES
    # =========================================================================

    def get_transition(
        self,
        category: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Получить переходную фразу.

        Args:
            category: Категория перехода (to_question, to_deeper, to_proposal)
            context: Контекст

        Returns:
            Строка перехода или пустая строка
        """
        if not self._config:
            return ""

        transition_config = self._config.transitions.get(category, {})
        if not transition_config:
            return ""

        phrases = transition_config.get("phrases", [])
        if not phrases:
            return ""

        # Проверяем skip probability
        skip_prob = transition_config.get("skip_probability", 0.3)
        if random() < skip_prob:
            return ""

        # LRU selection
        return self._select_with_lru(f"trans_{category}", phrases)

    # =========================================================================
    # PROMPT INSTRUCTIONS
    # =========================================================================

    def get_system_instruction(self) -> str:
        """Получить инструкцию для system prompt."""
        if not self._config:
            return ""
        return self._config.prompt_instructions.get("system_instruction", "")

    def get_example_instruction(self) -> str:
        """Получить инструкцию для примеров."""
        if not self._config:
            return ""
        return self._config.prompt_instructions.get("example_instruction", "")

    # =========================================================================
    # METRICS & DIAGNOSTICS
    # =========================================================================

    def get_metrics(self) -> DiversityMetrics:
        """Получить метрики."""
        return self._metrics

    def get_metrics_dict(self) -> Dict[str, Any]:
        """Получить метрики как словарь."""
        return self._metrics.to_dict()

    def check_monotony(self, threshold: int = 3) -> Optional[str]:
        """
        Проверить на монотонность (одинаковые вступления подряд).

        Args:
            threshold: Порог для детекции (default: 3)

        Returns:
            Предупреждение если обнаружена монотонность, иначе None
        """
        last = self._metrics.last_openings
        if len(last) < threshold:
            return None

        # Проверяем последние N вступлений
        recent = last[-threshold:]
        if len(set(recent)) == 1 and recent[0]:
            return f"Monotony detected: '{recent[0]}' used {threshold} times in a row"

        return None

    def get_lru_history(self) -> Dict[str, List[str]]:
        """Получить LRU историю для диагностики."""
        return self._lru_history.copy()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

# Глобальный экземпляр для использования во всём приложении
diversity_engine = ResponseDiversityEngine()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def process_response(
    response: str,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Удобная функция для обработки ответа.

    Args:
        response: Оригинальный ответ
        context: Контекст

    Returns:
        Обработанный ответ
    """
    result = diversity_engine.process_response(response, context)
    return result.processed


def get_opening(
    category: str,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Удобная функция для получения вступления.

    Args:
        category: Категория
        context: Контекст

    Returns:
        Вступление
    """
    return diversity_engine.get_opening(category, context)


# =============================================================================
# CLI FOR TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("RESPONSE DIVERSITY ENGINE DEMO")
    print("=" * 60)

    engine = ResponseDiversityEngine()

    # Test banned opening replacement
    print("\n--- Banned Opening Replacement ---")
    test_responses = [
        "Понимаю, это важный момент. Расскажите подробнее о проблеме.",
        "Понимаю вас, цена — важный фактор. Давайте разберём.",
        "Понимаю. Сколько человек в команде?",
        "Да, это серьёзная проблема. Как давно она существует?",
    ]

    for resp in test_responses:
        result = engine.process_response(resp)
        status = "MODIFIED" if result.was_modified else "UNCHANGED"
        print(f"\n[{status}]")
        print(f"  Original:  {resp[:60]}...")
        print(f"  Processed: {result.processed[:60]}...")
        if result.opening_used:
            print(f"  Opening:   '{result.opening_used}' ({result.category_used})")

    # Test opening generation
    print("\n--- Opening Generation ---")
    categories = ["empathy", "acknowledgment", "objection", "problem_acknowledgment"]
    for cat in categories:
        openings = [engine.get_opening(cat, force_skip=False) for _ in range(5)]
        print(f"\n{cat}:")
        for i, op in enumerate(openings, 1):
            display = op if op else "(empty)"
            print(f"  {i}. {display}")

    # Show metrics
    print("\n--- Metrics ---")
    metrics = engine.get_metrics_dict()
    for key, value in metrics.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 60)

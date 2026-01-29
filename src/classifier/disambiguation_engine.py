"""
Unified Disambiguation Decision Engine.

Центральный компонент для принятия решений о необходимости уточнения намерения.
Объединяет логику из ConfidenceRouter и DisambiguationAnalyzer в единый pipeline.

Архитектурные принципы:
- Config-driven: все пороги из YAML/config
- Fail-safe: graceful degradation при ошибках
- Observable: структурированное логирование
- Testable: чистые функции с DI
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import time

from src.logger import logger


class DisambiguationDecision(Enum):
    """
    Решение о disambiguation.

    EXECUTE: Уверенность высокая, выполнять действие
    CONFIRM: Уверенность средняя, уточнить одним вопросом
    DISAMBIGUATE: Уверенность низкая, показать варианты
    FALLBACK: Уверенность очень низкая, передать человеку
    """
    EXECUTE = "execute"
    CONFIRM = "confirm"
    DISAMBIGUATE = "disambiguate"
    FALLBACK = "fallback"


@dataclass
class DisambiguationOption:
    """Опция для показа пользователю."""
    intent: str
    label: str
    confidence: float


@dataclass
class DisambiguationResult:
    """
    Результат анализа disambiguation.

    Содержит всю информацию необходимую для:
    - Принятия решения (decision)
    - Формирования UI (options, question)
    - Метрик и логирования (scores, reasoning)
    """
    decision: DisambiguationDecision
    needs_disambiguation: bool

    # Основной intent и confidence
    intent: str
    confidence: float

    # Опции для disambiguation
    options: List[DisambiguationOption] = field(default_factory=list)
    question: str = ""
    confirm_question: str = ""

    # Метаданные для метрик
    gap: float = 0.0
    reasoning: str = ""
    analysis_time_ms: float = 0.0

    # Оригинальные данные
    original_scores: Dict[str, float] = field(default_factory=dict)
    alternatives: List[Dict] = field(default_factory=list)

    @property
    def disambiguation_triggered(self) -> bool:
        """Флаг для метрик: была ли инициирована disambiguation."""
        return self.decision in (
            DisambiguationDecision.CONFIRM,
            DisambiguationDecision.DISAMBIGUATE
        )

    def to_classification_result(self) -> Dict[str, Any]:
        """
        Преобразовать в формат совместимый с classification result.

        Returns:
            Dict с полями для bot.py
        """
        if not self.needs_disambiguation:
            return {}

        return {
            "intent": "disambiguation_needed",
            "confidence": self.confidence,
            "disambiguation_options": [
                {"intent": o.intent, "label": o.label, "confidence": o.confidence}
                for o in self.options
            ],
            "disambiguation_question": self.question or self.confirm_question,
            "original_intent": self.intent,
            "original_scores": self.original_scores,
            "disambiguation_decision": self.decision.value,
            "disambiguation_gap": self.gap,
            "disambiguation_reasoning": self.reasoning,
        }


# =============================================================================
# INTENT LABELS (маппинг интентов на человекопонятные названия)
# =============================================================================

INTENT_LABELS = {
    # Ценовые
    "price_question": "Узнать цену",
    "pricing_details": "Детали тарифов",
    "objection_price": "Обсудить стоимость",

    # Вопросы
    "question_features": "Узнать о функциях",
    "question_integrations": "Об интеграциях",
    "comparison": "Сравнить с другими",

    # Запросы
    "demo_request": "Записаться на демо",
    "callback_request": "Заказать звонок",
    "consultation_request": "Получить консультацию",
    "contact_provided": "Оставить контакт",

    # Возражения
    "objection_no_time": "Нет времени сейчас",
    "objection_timing": "Обсудить сроки",
    "objection_think": "Нужно подумать",
    "objection_competitor": "Сравнить с конкурентом",
    "objection_complexity": "Обсудить сложность",
    "objection_trust": "Узнать о надёжности",
    "objection_no_need": "Объяснить зачем нужно",

    # SPIN
    "situation_provided": "Рассказать о компании",
    "problem_revealed": "Обсудить проблемы",
    "need_expressed": "Обсудить потребности",
    "info_provided": "Предоставить информацию",

    # Управление
    "request_brevity": "Короткий ответ",
    "agreement": "Продолжить",
    "rejection": "Завершить разговор",
    "unclear": "Уточнить вопрос",

    # Общее
    "greeting": "Поздороваться",
    "small_talk": "Поболтать",
    "gratitude": "Поблагодарить",
    "farewell": "Попрощаться",
}


@dataclass
class DisambiguationConfig:
    """
    Конфигурация для DisambiguationDecisionEngine.

    Все значения можно переопределить через YAML config.
    """
    # Пороги confidence
    high_confidence: float = 0.85
    medium_confidence: float = 0.65
    low_confidence: float = 0.45
    min_confidence: float = 0.30

    # Порог gap между top-1 и top-2
    gap_threshold: float = 0.20

    # Disambiguation options
    max_options: int = 3
    min_option_confidence: float = 0.25

    # Bypass conditions (populated from taxonomy at runtime)
    bypass_intents: List[str] = field(default_factory=list)

    excluded_intents: List[str] = field(default_factory=lambda: [
        "unclear",
        "small_talk",
    ])

    # Cooldown
    cooldown_turns: int = 3

    @staticmethod
    def _get_taxonomy_bypass_intents() -> List[str]:
        """Get bypass intents from taxonomy (SSoT).

        Falls back to hardcoded list if taxonomy is unavailable.
        """
        try:
            from src.config_loader import get_config
            config = get_config()
            bypass = config.taxonomy_bypass_intents
            if bypass:
                return bypass
        except Exception:
            pass
        # Fallback for when config is not yet loaded
        return ["rejection", "contact_provided", "demo_request"]

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "DisambiguationConfig":
        """
        Создать из словаря конфигурации.

        Args:
            config: Словарь с параметрами (из DISAMBIGUATION_CONFIG)

        Returns:
            DisambiguationConfig instance
        """
        return cls(
            high_confidence=config.get("high_confidence", 0.85),
            medium_confidence=config.get("medium_confidence", 0.65),
            low_confidence=config.get("low_confidence", 0.45),
            min_confidence=config.get("min_confidence", 0.30),
            gap_threshold=config.get("gap_threshold", config.get("max_score_gap", 0.20)),
            max_options=config.get("max_options", 3),
            min_option_confidence=config.get("min_option_confidence", 0.25),
            bypass_intents=config.get("bypass_intents_override", []) or cls._get_taxonomy_bypass_intents(),
            excluded_intents=config.get("excluded_intents", ["unclear", "small_talk"]),
            cooldown_turns=config.get("cooldown_turns", 3),
        )


class DisambiguationDecisionEngine:
    """
    Unified engine для принятия решений о disambiguation.

    Объединяет логику из:
    - ConfidenceRouter (confidence-based routing)
    - DisambiguationAnalyzer (score gap analysis)

    Pipeline:
        classification_result → analyze() → DisambiguationResult

    Usage:
        engine = DisambiguationDecisionEngine(config)
        result = engine.analyze(classification, context)

        if result.needs_disambiguation:
            # Show options to user
            options = result.options
            question = result.question
    """

    def __init__(self, config: Optional[DisambiguationConfig] = None):
        """
        Инициализация.

        Args:
            config: Конфигурация (если None, используются defaults)
        """
        self.config = config or DisambiguationConfig()

        # Статистика
        self._total_analyses = 0
        self._decisions_count = {d: 0 for d in DisambiguationDecision}

    def analyze(
        self,
        classification: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> DisambiguationResult:
        """
        Анализировать результат классификации и принять решение.

        Args:
            classification: Результат от классификатора
                - intent: str
                - confidence: float
                - alternatives: List[Dict] (optional)
                - extracted_data: Dict (optional)
            context: Контекст диалога
                - turns_since_last_disambiguation: int
                - in_disambiguation: bool
                - state: str
                - spin_phase: str

        Returns:
            DisambiguationResult с решением и данными
        """
        start_time = time.time()
        context = context or {}

        self._total_analyses += 1

        try:
            # Extract data from classification
            intent = classification.get("intent", "unclear")
            confidence = classification.get("confidence", 0.0)
            alternatives = classification.get("alternatives", [])

            # Step 1: Check bypass conditions
            bypass_result = self._check_bypass_conditions(intent, confidence, context)
            if bypass_result:
                self._decisions_count[DisambiguationDecision.EXECUTE] += 1
                return self._build_result(
                    decision=DisambiguationDecision.EXECUTE,
                    intent=intent,
                    confidence=confidence,
                    reasoning=bypass_result,
                    start_time=start_time
                )

            # Step 2: Calculate gap
            gap = self._calculate_gap(confidence, alternatives)

            # Step 3: Make decision based on confidence and gap
            decision, reasoning = self._make_decision(confidence, gap, intent)
            self._decisions_count[decision] += 1

            # Step 4: Build options if needed
            options = []
            question = ""
            confirm_question = ""

            if decision == DisambiguationDecision.CONFIRM:
                confirm_question = self._build_confirm_question(intent)
                options = [DisambiguationOption(
                    intent=intent,
                    label=INTENT_LABELS.get(intent, intent),
                    confidence=confidence
                )]

            elif decision == DisambiguationDecision.DISAMBIGUATE:
                options = self._build_options(intent, confidence, alternatives)
                question = "Уточните, пожалуйста:"

            # Step 5: Build and return result
            return self._build_result(
                decision=decision,
                intent=intent,
                confidence=confidence,
                gap=gap,
                options=options,
                question=question,
                confirm_question=confirm_question,
                reasoning=reasoning,
                alternatives=alternatives,
                start_time=start_time
            )

        except Exception as e:
            # Fail-safe: return EXECUTE on any error
            logger.error(
                "Disambiguation analysis failed",
                extra={
                    "error": str(e),
                    "intent": classification.get("intent"),
                    "confidence": classification.get("confidence"),
                }
            )
            self._decisions_count[DisambiguationDecision.EXECUTE] += 1
            return self._build_result(
                decision=DisambiguationDecision.EXECUTE,
                intent=classification.get("intent", "unclear"),
                confidence=classification.get("confidence", 0.0),
                reasoning=f"Error in analysis: {str(e)}",
                start_time=start_time
            )

    def _check_bypass_conditions(
        self,
        intent: str,
        confidence: float,
        context: Dict[str, Any]
    ) -> Optional[str]:
        """
        Проверить условия bypass (когда disambiguation не нужен).

        Returns:
            Reason string если bypass, None если нужно продолжить анализ
        """
        # Bypass 1: Already in disambiguation
        if context.get("in_disambiguation"):
            return "Already in disambiguation mode"

        # Bypass 2: Cooldown
        turns_since = context.get("turns_since_last_disambiguation", 999)
        if turns_since < self.config.cooldown_turns:
            return f"Cooldown active ({turns_since} < {self.config.cooldown_turns} turns)"

        # Bypass 3: Bypass intents (critical actions)
        if intent in self.config.bypass_intents:
            return f"Bypass intent: {intent}"

        # Bypass 4: Very high confidence
        if confidence >= self.config.high_confidence + 0.10:  # 0.95+
            return f"Very high confidence: {confidence:.2f}"

        return None

    def _calculate_gap(
        self,
        top_confidence: float,
        alternatives: List[Dict]
    ) -> float:
        """
        Вычислить gap между top-1 и top-2.

        Args:
            top_confidence: Confidence top-1 интента
            alternatives: Список альтернатив [{intent, confidence}, ...]

        Returns:
            Gap value (0.0-1.0)
        """
        if not alternatives:
            # Нет альтернатив - используем proxy на основе confidence
            # Высокая confidence = большой gap, низкая = маленький
            return min(top_confidence, 0.5)  # Cap at 0.5 to be conservative

        # Get second highest confidence
        second_confidence = max(
            (alt.get("confidence", 0.0) for alt in alternatives),
            default=0.0
        )

        return top_confidence - second_confidence

    def _make_decision(
        self,
        confidence: float,
        gap: float,
        intent: str
    ) -> Tuple[DisambiguationDecision, str]:
        """
        Принять решение на основе confidence и gap.

        Decision matrix:

        | Confidence | Gap      | Decision     |
        |------------|----------|--------------|
        | >= 0.85    | >= 0.20  | EXECUTE      |
        | >= 0.85    | < 0.20   | CONFIRM      |
        | >= 0.65    | >= 0.20  | EXECUTE      |
        | >= 0.65    | < 0.20   | CONFIRM      |
        | >= 0.45    | any      | DISAMBIGUATE |
        | >= 0.30    | any      | DISAMBIGUATE |
        | < 0.30     | any      | FALLBACK     |
        """
        # Level 1: High confidence + large gap
        if confidence >= self.config.high_confidence and gap >= self.config.gap_threshold:
            return (
                DisambiguationDecision.EXECUTE,
                f"High confidence ({confidence:.2f}) with clear leader (gap={gap:.2f})"
            )

        # Level 2: High confidence + small gap
        if confidence >= self.config.high_confidence and gap < self.config.gap_threshold:
            return (
                DisambiguationDecision.CONFIRM,
                f"High confidence ({confidence:.2f}) but close alternatives (gap={gap:.2f})"
            )

        # Level 3: Medium confidence + large gap
        if confidence >= self.config.medium_confidence and gap >= self.config.gap_threshold:
            return (
                DisambiguationDecision.EXECUTE,
                f"Medium confidence ({confidence:.2f}) with clear leader (gap={gap:.2f})"
            )

        # Level 4: Medium confidence + small gap
        if confidence >= self.config.medium_confidence and gap < self.config.gap_threshold:
            return (
                DisambiguationDecision.CONFIRM,
                f"Medium confidence ({confidence:.2f}) with close alternatives (gap={gap:.2f})"
            )

        # Level 5: Low confidence
        if confidence >= self.config.low_confidence:
            return (
                DisambiguationDecision.DISAMBIGUATE,
                f"Low confidence ({confidence:.2f}), need user clarification"
            )

        # Level 6: Very low confidence
        if confidence >= self.config.min_confidence:
            return (
                DisambiguationDecision.DISAMBIGUATE,
                f"Very low confidence ({confidence:.2f}), showing options"
            )

        # Level 7: Below minimum
        return (
            DisambiguationDecision.FALLBACK,
            f"Cannot classify ({confidence:.2f} < {self.config.min_confidence})"
        )

    def _build_confirm_question(self, intent: str) -> str:
        """Построить уточняющий вопрос для CONFIRM."""
        templates = {
            "demo_request": "Вы хотите записаться на демо?",
            "callback_request": "Перезвонить вам?",
            "price_question": "Вас интересует стоимость?",
            "agreement": "Продолжаем?",
            "rejection": "Вы хотите завершить разговор?",
            "request_brevity": "Хотите короткий ответ по сути?",
            "objection_competitor": "Хотите сравнить с вашим текущим решением?",
            "consultation_request": "Нужна консультация специалиста?",
        }

        if intent in templates:
            return templates[intent]

        label = INTENT_LABELS.get(intent, intent)
        return f"Правильно ли я понял — {label.lower()}?"

    def _build_options(
        self,
        top_intent: str,
        top_confidence: float,
        alternatives: List[Dict]
    ) -> List[DisambiguationOption]:
        """Построить список опций для disambiguation."""
        options = []
        seen_intents = set()

        # Add top-1
        if top_intent not in self.config.excluded_intents:
            options.append(DisambiguationOption(
                intent=top_intent,
                label=INTENT_LABELS.get(top_intent, top_intent),
                confidence=top_confidence
            ))
            seen_intents.add(top_intent)

        # Add alternatives (up to max_options - 1)
        for alt in alternatives[:self.config.max_options]:
            alt_intent = alt.get("intent", "unclear")
            alt_conf = alt.get("confidence", 0.0)

            if alt_intent in seen_intents:
                continue
            if alt_intent in self.config.excluded_intents:
                continue
            if alt_conf < self.config.min_option_confidence:
                continue
            if len(options) >= self.config.max_options - 1:
                break

            options.append(DisambiguationOption(
                intent=alt_intent,
                label=INTENT_LABELS.get(alt_intent, alt_intent),
                confidence=alt_conf
            ))
            seen_intents.add(alt_intent)

        # Always add "Other" option at the end
        options.append(DisambiguationOption(
            intent="other",
            label="Другое",
            confidence=0.0
        ))

        return options

    def _build_result(
        self,
        decision: DisambiguationDecision,
        intent: str,
        confidence: float,
        reasoning: str,
        start_time: float,
        gap: float = 0.0,
        options: List[DisambiguationOption] = None,
        question: str = "",
        confirm_question: str = "",
        alternatives: List[Dict] = None
    ) -> DisambiguationResult:
        """Build DisambiguationResult with all fields."""
        elapsed_ms = (time.time() - start_time) * 1000

        return DisambiguationResult(
            decision=decision,
            needs_disambiguation=decision in (
                DisambiguationDecision.CONFIRM,
                DisambiguationDecision.DISAMBIGUATE
            ),
            intent=intent,
            confidence=confidence,
            options=options or [],
            question=question,
            confirm_question=confirm_question,
            gap=gap,
            reasoning=reasoning,
            analysis_time_ms=elapsed_ms,
            alternatives=alternatives or []
        )

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику engine."""
        return {
            "total_analyses": self._total_analyses,
            "decisions": {d.value: count for d, count in self._decisions_count.items()},
            "config": {
                "high_confidence": self.config.high_confidence,
                "medium_confidence": self.config.medium_confidence,
                "low_confidence": self.config.low_confidence,
                "min_confidence": self.config.min_confidence,
                "gap_threshold": self.config.gap_threshold,
            }
        }


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

_engine_instance: Optional[DisambiguationDecisionEngine] = None


def get_disambiguation_engine(
    config: Optional[Dict[str, Any]] = None
) -> DisambiguationDecisionEngine:
    """
    Получить singleton экземпляр DisambiguationDecisionEngine.

    Config priority:
    1. Explicit config parameter
    2. YAML config from yaml_config/constants.yaml
    3. Python config from config.py DISAMBIGUATION_CONFIG
    4. Hardcoded defaults

    Args:
        config: Optional config dict (uses defaults if None)

    Returns:
        DisambiguationDecisionEngine instance
    """
    global _engine_instance

    if _engine_instance is None:
        engine_config = None

        if config:
            engine_config = DisambiguationConfig.from_config(config)
        else:
            # Priority 1: Try YAML config
            try:
                from yaml_config.constants import get_disambiguation_config
                yaml_config = get_disambiguation_config()
                if yaml_config:
                    engine_config = DisambiguationConfig.from_config(yaml_config)
                    logger.debug("Loaded disambiguation config from YAML")
            except ImportError:
                pass

            # Priority 2: Try Python config
            if engine_config is None:
                try:
                    from config import DISAMBIGUATION_CONFIG
                    engine_config = DisambiguationConfig.from_config(DISAMBIGUATION_CONFIG)
                    logger.debug("Loaded disambiguation config from config.py")
                except ImportError:
                    pass

            # Priority 3: Use defaults
            if engine_config is None:
                engine_config = DisambiguationConfig()
                logger.debug("Using default disambiguation config")

        _engine_instance = DisambiguationDecisionEngine(engine_config)

    return _engine_instance


def reset_disambiguation_engine() -> None:
    """Reset singleton instance (for testing)."""
    global _engine_instance
    _engine_instance = None

"""
ConfidenceRouter — надстройка над классификатором для robust решений.

Анализирует confidence и gap между top интентами, решает:
- Execute: уверен, выполнять сразу
- Confirm: почти уверен, уточнить одним вопросом
- Disambiguate: не уверен, показать кнопки с вариантами
- Fallback: совсем не понял, передать человеку

Based on Rasa Two-Stage Fallback и Amazon Lex confidence patterns.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import json
from datetime import datetime
from pathlib import Path

from src.logger import logger


class RouterDecision(Enum):
    """Решение роутера."""
    EXECUTE = "execute"           # Уверен, выполнять
    CONFIRM = "confirm"           # Почти уверен, уточнить
    DISAMBIGUATE = "disambiguate" # Не уверен, показать варианты
    FALLBACK = "fallback"         # Совсем не понял


@dataclass
class DisambiguationOption:
    """Опция для disambiguation кнопки."""
    intent: str
    label: str  # Текст кнопки для пользователя
    confidence: float


@dataclass
class RouterResult:
    """Результат роутинга."""
    decision: RouterDecision
    intent: str
    confidence: float
    reasoning: str

    # Для CONFIRM
    confirm_question: Optional[str] = None

    # Для DISAMBIGUATE
    options: List[DisambiguationOption] = field(default_factory=list)

    # Оригинальный результат классификации
    classification_result: Optional[Dict] = None

    # Метрики для логирования
    gap: Optional[float] = None  # Разница между top-1 и top-2
    alternatives_count: int = 0


# Маппинг интентов на человекопонятные названия для кнопок
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


class ConfidenceRouter:
    """
    Роутер на основе confidence для graceful degradation.

    Пороги (можно настроить):
    - high_confidence (0.85): выполнять сразу
    - medium_confidence (0.65): уточнить если gap маленький
    - low_confidence (0.45): показать варианты
    - min_confidence (0.30): fallback

    Gap threshold (0.20): если разница между top-1 и top-2 меньше — двусмысленность
    """

    def __init__(
        self,
        high_confidence: float = 0.85,
        medium_confidence: float = 0.65,
        low_confidence: float = 0.45,
        min_confidence: float = 0.30,
        gap_threshold: float = 0.20,
        log_uncertain: bool = True,
        log_dir: Optional[str] = None
    ):
        self.high_confidence = high_confidence
        self.medium_confidence = medium_confidence
        self.low_confidence = low_confidence
        self.min_confidence = min_confidence
        self.gap_threshold = gap_threshold
        self.log_uncertain = log_uncertain
        self.log_dir = Path(log_dir) if log_dir else Path("logs/uncertain_classifications")

        # Статистика
        self._total_routes = 0
        self._decisions_count = {d: 0 for d in RouterDecision}

    def route(self, classification_result: Dict) -> RouterResult:
        """
        Принять решение на основе результата классификации.

        Args:
            classification_result: Результат от LLMClassifier с alternatives

        Returns:
            RouterResult с решением и опциями
        """
        self._total_routes += 1

        intent = classification_result.get("intent", "unclear")
        confidence = classification_result.get("confidence", 0.0)
        alternatives = classification_result.get("alternatives", [])
        reasoning = classification_result.get("reasoning", "")

        # Вычисляем gap
        gap = self._calculate_gap(confidence, alternatives)

        # Принимаем решение
        decision, result_reasoning = self._make_decision(confidence, gap, intent)
        self._decisions_count[decision] += 1

        # Формируем результат
        result = RouterResult(
            decision=decision,
            intent=intent,
            confidence=confidence,
            reasoning=result_reasoning,
            classification_result=classification_result,
            gap=gap,
            alternatives_count=len(alternatives)
        )

        # Добавляем данные в зависимости от решения
        if decision == RouterDecision.CONFIRM:
            result.confirm_question = self._build_confirm_question(intent)

        elif decision == RouterDecision.DISAMBIGUATE:
            result.options = self._build_options(intent, confidence, alternatives)

        # Логируем неуверенные классификации для обучения
        if self.log_uncertain and decision in (RouterDecision.DISAMBIGUATE, RouterDecision.FALLBACK):
            self._log_uncertain(classification_result, result)

        return result

    def _calculate_gap(self, top_confidence: float, alternatives: List[Dict]) -> float:
        """Вычислить gap между top-1 и top-2."""
        if not alternatives:
            return 1.0  # Нет альтернатив — считаем что явный лидер

        second_confidence = alternatives[0].get("confidence", 0.0)
        return top_confidence - second_confidence

    def _make_decision(self, confidence: float, gap: float, intent: str) -> tuple[RouterDecision, str]:
        """Принять решение на основе confidence и gap."""

        # Уровень 1: Высокая уверенность + большой gap
        if confidence >= self.high_confidence and gap >= self.gap_threshold:
            return RouterDecision.EXECUTE, f"Высокая уверенность ({confidence:.2f}) с явным лидером (gap={gap:.2f})"

        # Уровень 2: Высокая уверенность но маленький gap — уточнить
        if confidence >= self.high_confidence and gap < self.gap_threshold:
            return RouterDecision.CONFIRM, f"Высокая уверенность ({confidence:.2f}) но близкие альтернативы (gap={gap:.2f})"

        # Уровень 3: Средняя уверенность + большой gap — можно выполнять
        if confidence >= self.medium_confidence and gap >= self.gap_threshold:
            return RouterDecision.EXECUTE, f"Средняя уверенность ({confidence:.2f}) с явным лидером (gap={gap:.2f})"

        # Уровень 4: Средняя уверенность + маленький gap — уточнить
        if confidence >= self.medium_confidence and gap < self.gap_threshold:
            return RouterDecision.CONFIRM, f"Средняя уверенность ({confidence:.2f}) с близкими альтернативами (gap={gap:.2f})"

        # Уровень 5: Низкая уверенность — показать варианты
        if confidence >= self.low_confidence:
            return RouterDecision.DISAMBIGUATE, f"Низкая уверенность ({confidence:.2f}), нужно уточнить у пользователя"

        # Уровень 6: Очень низкая уверенность — fallback
        if confidence >= self.min_confidence:
            return RouterDecision.DISAMBIGUATE, f"Очень низкая уверенность ({confidence:.2f}), показываем варианты"

        # Уровень 7: Ниже минимума — передаём человеку
        return RouterDecision.FALLBACK, f"Не удалось классифицировать ({confidence:.2f} < {self.min_confidence})"

    def _build_confirm_question(self, intent: str) -> str:
        """Построить уточняющий вопрос для CONFIRM."""
        label = INTENT_LABELS.get(intent, intent)

        # Шаблоны уточняющих вопросов
        templates = {
            "demo_request": "Вы хотите записаться на демо?",
            "callback_request": "Перезвонить вам?",
            "price_question": "Вас интересует стоимость?",
            "agreement": "Продолжаем?",
            "rejection": "Вы хотите завершить разговор?",
            "request_brevity": "Хотите короткий ответ по сути?",
            "objection_competitor": "Хотите сравнить с вашим текущим решением?",
        }

        return templates.get(intent, f"Правильно ли я понял — {label.lower()}?")

    def _build_options(
        self,
        top_intent: str,
        top_confidence: float,
        alternatives: List[Dict]
    ) -> List[DisambiguationOption]:
        """Построить список опций для disambiguation кнопок."""
        options = []

        # Добавляем top-1
        options.append(DisambiguationOption(
            intent=top_intent,
            label=INTENT_LABELS.get(top_intent, top_intent),
            confidence=top_confidence
        ))

        # Добавляем alternatives (top-2, top-3)
        for alt in alternatives[:2]:  # Максимум 2 альтернативы
            alt_intent = alt.get("intent", "unclear")
            if alt_intent != top_intent:  # Избегаем дублей
                options.append(DisambiguationOption(
                    intent=alt_intent,
                    label=INTENT_LABELS.get(alt_intent, alt_intent),
                    confidence=alt.get("confidence", 0.0)
                ))

        # Всегда добавляем "Другое" как последнюю опцию
        options.append(DisambiguationOption(
            intent="other",
            label="Другое",
            confidence=0.0
        ))

        return options

    def _log_uncertain(self, classification_result: Dict, router_result: RouterResult):
        """Логировать неуверенные классификации для последующего анализа."""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "message": classification_result.get("_original_message", ""),
                "decision": router_result.decision.value,
                "top_intent": router_result.intent,
                "confidence": router_result.confidence,
                "gap": router_result.gap,
                "alternatives": classification_result.get("alternatives", []),
                "reasoning": classification_result.get("reasoning", ""),
                "options": [
                    {"intent": o.intent, "label": o.label, "confidence": o.confidence}
                    for o in router_result.options
                ]
            }

            # Пишем в файл по дате
            log_file = self.log_dir / f"uncertain_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.warning(f"Failed to log uncertain classification: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику роутера."""
        return {
            "total_routes": self._total_routes,
            "decisions": {d.value: count for d, count in self._decisions_count.items()},
            "thresholds": {
                "high_confidence": self.high_confidence,
                "medium_confidence": self.medium_confidence,
                "low_confidence": self.low_confidence,
                "min_confidence": self.min_confidence,
                "gap_threshold": self.gap_threshold
            }
        }


# Singleton instance для использования в приложении
_router_instance: Optional[ConfidenceRouter] = None


def get_confidence_router() -> ConfidenceRouter:
    """Получить singleton экземпляр ConfidenceRouter."""
    global _router_instance
    if _router_instance is None:
        _router_instance = ConfidenceRouter()
    return _router_instance

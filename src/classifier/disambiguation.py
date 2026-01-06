"""
DisambiguationAnalyzer - анализ scores для принятия решения о disambiguation.

Когда confidence близок между несколькими интентами, система предлагает
пользователю уточнить свой запрос.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from config import DISAMBIGUATION_CONFIG, CLASSIFIER_CONFIG
from constants.intent_labels import get_label


@dataclass
class DisambiguationResult:
    """Результат анализа disambiguation."""

    needs_disambiguation: bool
    options: List[Dict]
    top_confidence: float
    merged_scores: Dict[str, float]
    question: str = ""
    fallback_intent: Optional[str] = None


class DisambiguationAnalyzer:
    """
    Анализатор для принятия решения о необходимости disambiguation.

    Алгоритм:
    1. Получить scores от root_classifier и lemma_classifier
    2. Объединить scores (weighted merge)
    3. Проверить cooldown
    4. Проверить bypass условия
    5. Проверить confidence и score gap
    6. Сформировать опции для пользователя
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Args:
            config: Конфигурация классификатора (CLASSIFIER_CONFIG)
        """
        self.config = config or CLASSIFIER_CONFIG
        self.disambiguation_config = DISAMBIGUATION_CONFIG

    def analyze(
        self,
        root_scores: Dict[str, int],
        lemma_scores: Dict[str, float],
        context: Optional[Dict] = None
    ) -> DisambiguationResult:
        """
        Проанализировать scores и определить нужен ли disambiguation.

        Args:
            root_scores: Scores от RootClassifier {intent: int}
            lemma_scores: Scores от LemmaClassifier {intent: float}
            context: Контекст из StateMachine

        Returns:
            DisambiguationResult с результатом анализа
        """
        context = context or {}

        # Шаг 1-2: Объединить scores
        merged = self._merge_scores(root_scores, lemma_scores)

        if not merged:
            return DisambiguationResult(
                needs_disambiguation=False,
                options=[],
                top_confidence=0.0,
                merged_scores={},
                fallback_intent="unclear"
            )

        # Шаг 3: Отсортировать по убыванию
        sorted_intents = sorted(merged.items(), key=lambda x: -x[1])
        top_intent, top_confidence = sorted_intents[0]

        # Шаг 4: Проверить cooldown
        turns_since = context.get("turns_since_last_disambiguation", 999)
        cooldown = self.disambiguation_config["cooldown_turns"]
        if turns_since < cooldown:
            return DisambiguationResult(
                needs_disambiguation=False,
                options=[],
                top_confidence=top_confidence,
                merged_scores=merged
            )

        # Шаг 5: Проверить bypass условия
        bypass_intents = self.disambiguation_config["bypass_disambiguation_intents"]
        if top_intent in bypass_intents:
            return DisambiguationResult(
                needs_disambiguation=False,
                options=[],
                top_confidence=top_confidence,
                merged_scores=merged
            )

        # Шаг 6: Проверить confidence
        min_conf = self.disambiguation_config["min_confidence_threshold"]
        if top_confidence < min_conf:
            return DisambiguationResult(
                needs_disambiguation=False,
                options=[],
                top_confidence=top_confidence,
                merged_scores=merged,
                fallback_intent="unclear"
            )

        # Шаг 7: Проверить score gap
        if len(sorted_intents) >= 2:
            second_confidence = sorted_intents[1][1]
            gap = top_confidence - second_confidence
            max_gap = self.disambiguation_config["max_score_gap"]

            if gap >= max_gap:
                return DisambiguationResult(
                    needs_disambiguation=False,
                    options=[],
                    top_confidence=top_confidence,
                    merged_scores=merged
                )

        # Шаг 8: Сформировать опции
        options = self._build_options(sorted_intents)

        # Шаг 9: Проверить что опций достаточно
        if len(options) < 2:
            return DisambiguationResult(
                needs_disambiguation=False,
                options=[],
                top_confidence=top_confidence,
                merged_scores=merged
            )

        # Шаг 10: Нужен disambiguation
        return DisambiguationResult(
            needs_disambiguation=True,
            options=options,
            top_confidence=top_confidence,
            merged_scores=merged,
            question="Уточните, пожалуйста:"
        )

    def _merge_scores(
        self,
        root_scores: Dict[str, int],
        lemma_scores: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Нормализация и слияние scores от разных классификаторов.

        Формулы из реального кода:
        - RootClassifier: confidence = min(score * root_match_weight / 3, 1.0)
        - LemmaClassifier: confidence = min(score / 4, 1.0)

        Args:
            root_scores: Raw scores от RootClassifier
            lemma_scores: Raw scores от LemmaClassifier

        Returns:
            Нормализованные и объединённые scores
        """
        if not root_scores and not lemma_scores:
            return {}

        # Если только root scores
        if not lemma_scores:
            root_weight = self.config.get("root_match_weight", 1.0)
            return {
                intent: min(score * root_weight / 3, 1.0)
                for intent, score in root_scores.items()
            }

        # Объединяем оба источника
        merged = {}
        all_intents = set(root_scores.keys()) | set(lemma_scores.keys())
        root_weight = self.config.get("root_match_weight", 1.0)

        for intent in all_intents:
            # Нормализация root score
            root_raw = root_scores.get(intent, 0)
            root_norm = min(root_raw * root_weight / 3, 1.0)

            # Нормализация lemma score
            lemma_raw = lemma_scores.get(intent, 0.0)
            lemma_norm = min(lemma_raw / 4, 1.0)

            # Взвешенное среднее: 60% root, 40% lemma
            merged[intent] = root_norm * 0.6 + lemma_norm * 0.4

        return merged

    def _build_options(self, sorted_intents: List[tuple]) -> List[Dict]:
        """
        Построить список опций для отображения пользователю.

        Args:
            sorted_intents: Отсортированный список (intent, confidence)

        Returns:
            Список опций с intent, label, confidence
        """
        excluded = self.disambiguation_config["excluded_intents"]
        min_conf = self.disambiguation_config["min_option_confidence"]
        max_opts = self.disambiguation_config["max_options"]

        options = []
        for intent, confidence in sorted_intents:
            # Пропускаем исключённые интенты
            if intent in excluded:
                continue

            # Пропускаем опции с низким confidence
            if confidence < min_conf:
                continue

            options.append({
                "intent": intent,
                "label": get_label(intent),
                "confidence": confidence
            })

            if len(options) >= max_opts:
                break

        return options

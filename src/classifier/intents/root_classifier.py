"""
Быстрая классификация по корням слов

Использует словарь INTENT_ROOTS из config.py для быстрого
определения интента по наличию ключевых корней в тексте.
"""

import re
from typing import Dict, Tuple

from config import INTENT_ROOTS, CLASSIFIER_CONFIG
from .patterns import COMPILED_PRIORITY_PATTERNS


class RootClassifier:
    """Быстрая классификация по корням слов"""

    def __init__(self):
        self.roots = INTENT_ROOTS
        self.config = CLASSIFIER_CONFIG
        self.priority_patterns = COMPILED_PRIORITY_PATTERNS

    def classify(self, message: str) -> Tuple[str, float, Dict[str, int]]:
        """
        Классификация по корням

        Returns:
            (intent, confidence, scores_dict)
        """
        message_lower = message.lower()

        # ШАГ 0: Проверяем приоритетные паттерны
        # Это решает проблему "не интересно" → rejection (а не agreement)
        for pattern, intent, confidence in self.priority_patterns:
            if pattern.search(message_lower):
                return intent, confidence, {intent: 3}  # высокий score

        # ШАГ 1: Обычная классификация по корням
        scores: Dict[str, int] = {}

        for intent, roots in self.roots.items():
            score = 0
            for root in roots:
                if root in message_lower:
                    score += 1
            if score > 0:
                scores[intent] = score

        if not scores:
            return "unclear", 0.0, {}

        # Находим лучший интент
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # Нормализуем confidence
        # Чем больше совпадений, тем выше уверенность
        confidence = min(best_score * self.config["root_match_weight"] / 3, 1.0)

        # Бонус если есть явный лидер (разрыв с вторым местом)
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) > 1:
            gap = sorted_scores[0] - sorted_scores[1]
            if gap >= 2:
                confidence = min(confidence + 0.2, 1.0)

        return best_intent, confidence, scores

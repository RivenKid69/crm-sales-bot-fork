"""
Fallback классификация через pymorphy2/3

Использует лемматизацию для более точного определения интента,
когда быстрая классификация по корням даёт низкую уверенность.
"""

import re
from typing import Dict, List, Tuple

from config import INTENT_PHRASES, CLASSIFIER_CONFIG

# Попытка импорта pymorphy (2 или 3)
try:
    from pymorphy3 import MorphAnalyzer
    PYMORPHY_AVAILABLE = True
except ImportError:
    try:
        from pymorphy2 import MorphAnalyzer
        PYMORPHY_AVAILABLE = True
    except ImportError:
        PYMORPHY_AVAILABLE = False
        MorphAnalyzer = None
        print("[WARNING] pymorphy2/pymorphy3 не установлен. Fallback на лемматизацию недоступен.")


class LemmaClassifier:
    """Fallback классификация через pymorphy2"""

    def __init__(self):
        self.phrases = INTENT_PHRASES
        self.config = CLASSIFIER_CONFIG
        self.morph = MorphAnalyzer() if PYMORPHY_AVAILABLE else None

    def _lemmatize(self, text: str) -> List[str]:
        """Приводим слова к нормальной форме"""
        if not self.morph:
            return text.lower().split()

        words = re.findall(r'[а-яёa-z0-9]+', text.lower())
        lemmas = []
        for word in words:
            parsed = self.morph.parse(word)
            if parsed:
                lemmas.append(parsed[0].normal_form)
            else:
                lemmas.append(word)
        return lemmas

    def _lemmatize_phrase(self, phrase: str) -> str:
        """Лемматизируем фразу и склеиваем обратно"""
        return " ".join(self._lemmatize(phrase))

    def classify(self, message: str) -> Tuple[str, float, Dict[str, float]]:
        """
        Классификация через лемматизацию

        Returns:
            (intent, confidence, scores_dict)
        """
        if not PYMORPHY_AVAILABLE:
            return "unclear", 0.0, {}

        message_lemmas = self._lemmatize(message)
        message_lemma_str = " ".join(message_lemmas)

        scores: Dict[str, float] = {}

        for intent, phrases in self.phrases.items():
            best_match_score = 0.0

            for phrase in phrases:
                phrase_lemmas = self._lemmatize(phrase)
                phrase_lemma_str = " ".join(phrase_lemmas)

                # Точное совпадение лемматизированной фразы
                if phrase_lemma_str in message_lemma_str:
                    match_score = len(phrase_lemmas) * self.config["lemma_match_weight"]
                    best_match_score = max(best_match_score, match_score)
                    continue

                # Частичное совпадение (все леммы фразы есть в сообщении)
                matching_lemmas = sum(1 for lemma in phrase_lemmas if lemma in message_lemmas)
                if matching_lemmas == len(phrase_lemmas):
                    match_score = matching_lemmas * self.config["lemma_match_weight"] * 0.8
                    best_match_score = max(best_match_score, match_score)

            if best_match_score > 0:
                scores[intent] = best_match_score

        if not scores:
            return "unclear", 0.0, {}

        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # Нормализуем confidence
        confidence = min(best_score / 4, 1.0)

        return best_intent, confidence, scores

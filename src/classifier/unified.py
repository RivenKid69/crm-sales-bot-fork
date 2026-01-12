"""
Унифицированный классификатор с feature flag.

Позволяет переключаться между LLM и Hybrid классификаторами.
"""
from typing import Dict, Optional, Any

from logger import logger
from feature_flags import flags


class UnifiedClassifier:
    """
    Адаптер для переключения между классификаторами.

    Если flags.llm_classifier == True: использует LLMClassifier
    Иначе: использует HybridClassifier
    """

    def __init__(self):
        """Инициализация с lazy loading."""
        self._hybrid = None
        self._llm = None

    @property
    def hybrid(self):
        """Lazy init HybridClassifier."""
        if self._hybrid is None:
            from .hybrid import HybridClassifier
            self._hybrid = HybridClassifier()
        return self._hybrid

    @property
    def llm(self):
        """Lazy init LLMClassifier с HybridClassifier как fallback."""
        if self._llm is None:
            from .llm import LLMClassifier
            self._llm = LLMClassifier(fallback_classifier=self.hybrid)
        return self._llm

    def classify(self, message: str, context: Dict = None) -> Dict:
        """
        Классифицировать сообщение.

        Args:
            message: Сообщение пользователя
            context: Контекст диалога

        Returns:
            Результат классификации
        """
        if flags.llm_classifier:
            return self.llm.classify(message, context)
        return self.hybrid.classify(message, context)

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику."""
        stats = {"active_classifier": "llm" if flags.llm_classifier else "hybrid"}

        if self._llm is not None:
            stats["llm_stats"] = self._llm.get_stats()

        return stats

"""
Унифицированный классификатор с feature flag.

Позволяет переключаться между LLM и Hybrid классификаторами.
Включает ClassificationRefinementLayer для контекстного уточнения
коротких ответов (State Loop Fix).
"""
from typing import Dict, Optional, Any

from logger import logger
from feature_flags import flags


class UnifiedClassifier:
    """
    Адаптер для переключения между классификаторами.

    Если flags.llm_classifier == True: использует LLMClassifier
    Иначе: использует HybridClassifier

    Если flags.classification_refinement == True: применяет
    ClassificationRefinementLayer для уточнения коротких ответов.

    Pipeline:
        message → LLM/Hybrid Classifier → RefinementLayer → result
    """

    def __init__(self):
        """Инициализация с lazy loading."""
        self._hybrid = None
        self._llm = None
        self._refinement_layer = None

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

    @property
    def refinement_layer(self):
        """Lazy init ClassificationRefinementLayer."""
        if self._refinement_layer is None:
            from .refinement import ClassificationRefinementLayer
            self._refinement_layer = ClassificationRefinementLayer()
        return self._refinement_layer

    def classify(self, message: str, context: Dict = None) -> Dict:
        """
        Классифицировать сообщение.

        Pipeline:
        1. Primary classification (LLM or Hybrid based on feature flag)
        2. Contextual refinement (if classification_refinement flag enabled)

        Args:
            message: Сообщение пользователя
            context: Контекст диалога (state, spin_phase, last_action, last_intent)

        Returns:
            Результат классификации с полями:
            - intent: str
            - confidence: float
            - extracted_data: dict
            - method: str ("llm", "hybrid", или "llm_fallback")
            - refined: bool (если было уточнение)
            - original_intent: str (если было уточнение)
        """
        context = context or {}

        # Step 1: Primary classification
        if flags.llm_classifier:
            result = self.llm.classify(message, context)
        else:
            result = self.hybrid.classify(message, context)

        # Step 2: Contextual refinement for short answers (State Loop Fix)
        if flags.classification_refinement:
            result = self._apply_refinement(message, result, context)

        return result

    def _apply_refinement(
        self,
        message: str,
        result: Dict,
        context: Dict
    ) -> Dict:
        """
        Apply ClassificationRefinementLayer to refine short answer classification.

        This addresses the State Loop bug where short answers like "1", "да"
        are incorrectly classified as "greeting".

        Args:
            message: User's message
            result: Classification result from primary classifier
            context: Dialog context

        Returns:
            Refined result (or original if refinement not applicable)
        """
        try:
            from .refinement import RefinementContext

            refinement_ctx = RefinementContext(
                message=message,
                spin_phase=context.get("spin_phase"),
                state=context.get("state"),
                last_action=context.get("last_action"),
                last_intent=context.get("last_intent"),
            )

            refined_result = self.refinement_layer.refine(
                message, result, refinement_ctx
            )

            return refined_result

        except Exception as e:
            # Fail-safe: return original result on any error
            logger.warning(
                "Refinement layer failed, returning original result",
                extra={"error": str(e), "message": message[:50]}
            )
            return result

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику."""
        stats = {
            "active_classifier": "llm" if flags.llm_classifier else "hybrid",
            "refinement_enabled": flags.classification_refinement,
        }

        if self._llm is not None:
            stats["llm_stats"] = self._llm.get_stats()

        return stats

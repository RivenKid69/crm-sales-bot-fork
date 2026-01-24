"""
Унифицированный классификатор с feature flag.

Позволяет переключаться между LLM и Hybrid классификаторами.
Включает ClassificationRefinementLayer для контекстного уточнения
коротких ответов (State Loop Fix).

Включает UnifiedDisambiguationLayer для принятия решений о необходимости
уточнения намерения пользователя.

Pipeline:
    message → LLM/Hybrid Classifier → RefinementLayer → DisambiguationLayer → result
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

    Если flags.unified_disambiguation == True: применяет
    DisambiguationDecisionEngine для унифицированного анализа
    необходимости уточнения намерения.

    Pipeline:
        message → LLM/Hybrid Classifier → RefinementLayer → DisambiguationLayer → result
    """

    def __init__(self):
        """Инициализация с lazy loading."""
        self._hybrid = None
        self._llm = None
        self._refinement_layer = None
        self._disambiguation_engine = None

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

    @property
    def disambiguation_engine(self):
        """Lazy init DisambiguationDecisionEngine."""
        if self._disambiguation_engine is None:
            from .disambiguation_engine import get_disambiguation_engine
            self._disambiguation_engine = get_disambiguation_engine()
        return self._disambiguation_engine

    def classify(self, message: str, context: Dict = None) -> Dict:
        """
        Классифицировать сообщение.

        Pipeline:
        1. Primary classification (LLM or Hybrid based on feature flag)
        2. Contextual refinement (if classification_refinement flag enabled)
        3. Disambiguation analysis (if unified_disambiguation flag enabled)

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
            - disambiguation_triggered: bool (если нужно уточнение)
            - disambiguation_options: list (если нужно уточнение)
            - disambiguation_decision: str (если анализ проведён)
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

        # Step 3: Unified disambiguation analysis
        if flags.unified_disambiguation:
            result = self._apply_disambiguation(result, context)

        return result

    def _apply_disambiguation(
        self,
        result: Dict,
        context: Dict
    ) -> Dict:
        """
        Apply DisambiguationDecisionEngine to analyze if disambiguation needed.

        This provides unified disambiguation logic for both LLM and Hybrid
        classifiers, replacing the separate ConfidenceRouter and
        DisambiguationAnalyzer paths.

        Args:
            result: Classification result from primary classifier
            context: Dialog context

        Returns:
            Result with disambiguation fields added (or original if no disambiguation)
        """
        try:
            # Skip if already disambiguation_needed (from HybridClassifier)
            if result.get("intent") == "disambiguation_needed":
                result["disambiguation_triggered"] = True
                return result

            # Run disambiguation analysis
            disambiguation_result = self.disambiguation_engine.analyze(result, context)

            # Add disambiguation metadata to result
            result["disambiguation_triggered"] = disambiguation_result.disambiguation_triggered
            result["disambiguation_decision"] = disambiguation_result.decision.value
            result["disambiguation_gap"] = disambiguation_result.gap
            result["disambiguation_reasoning"] = disambiguation_result.reasoning

            # If disambiguation needed, transform result
            if disambiguation_result.needs_disambiguation:
                # Merge disambiguation data into result
                disambiguation_data = disambiguation_result.to_classification_result()
                result.update(disambiguation_data)

                logger.info(
                    "Disambiguation triggered",
                    extra={
                        "original_intent": result.get("original_intent", result.get("intent")),
                        "decision": disambiguation_result.decision.value,
                        "confidence": result.get("confidence"),
                        "gap": disambiguation_result.gap,
                        "options_count": len(disambiguation_result.options),
                    }
                )

            return result

        except Exception as e:
            # Fail-safe: return original result on any error
            logger.warning(
                "Disambiguation analysis failed, returning original result",
                extra={"error": str(e), "intent": result.get("intent")}
            )
            result["disambiguation_triggered"] = False
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
            "unified_disambiguation_enabled": flags.unified_disambiguation,
        }

        if self._llm is not None:
            stats["llm_stats"] = self._llm.get_stats()

        if self._disambiguation_engine is not None:
            stats["disambiguation_stats"] = self._disambiguation_engine.get_stats()

        return stats

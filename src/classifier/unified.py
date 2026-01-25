"""
Унифицированный классификатор с feature flag.

Позволяет переключаться между LLM и Hybrid классификаторами.
Включает ClassificationRefinementLayer для контекстного уточнения
коротких ответов (State Loop Fix).

Включает CompositeMessageRefinementLayer для обработки составных сообщений
с приоритетом извлечения данных (Composite Message Fix).

Включает ObjectionRefinementLayer для контекстной валидации
objection классификаций (Objection Stuck Fix).

Включает UnifiedDisambiguationLayer для принятия решений о необходимости
уточнения намерения пользователя.

Pipeline:
    message → LLM/Hybrid Classifier → RefinementLayer → CompositeRefinementLayer →
    → ObjectionRefinementLayer → DisambiguationLayer → result
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

    Если flags.composite_refinement == True: применяет
    CompositeMessageRefinementLayer для обработки составных сообщений
    с приоритетом извлечения данных.

    Если flags.objection_refinement == True: применяет
    ObjectionRefinementLayer для контекстной валидации objection классификаций.

    Если flags.unified_disambiguation == True: применяет
    DisambiguationDecisionEngine для унифицированного анализа
    необходимости уточнения намерения.

    Pipeline:
        message → LLM/Hybrid → RefinementLayer → CompositeRefinementLayer →
        → ObjectionRefinementLayer → DisambiguationLayer → result
    """

    def __init__(self):
        """Инициализация с lazy loading."""
        self._hybrid = None
        self._llm = None
        self._refinement_layer = None
        self._composite_refinement_layer = None
        self._objection_refinement_layer = None
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
    def composite_refinement_layer(self):
        """Lazy init CompositeMessageRefinementLayer."""
        if self._composite_refinement_layer is None:
            from .composite_refinement import CompositeMessageRefinementLayer
            self._composite_refinement_layer = CompositeMessageRefinementLayer()
        return self._composite_refinement_layer

    @property
    def objection_refinement_layer(self):
        """Lazy init ObjectionRefinementLayer."""
        if self._objection_refinement_layer is None:
            from .objection_refinement import ObjectionRefinementLayer
            self._objection_refinement_layer = ObjectionRefinementLayer()
        return self._objection_refinement_layer

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
        2. Contextual refinement for short answers (State Loop Fix)
        3. Composite message refinement (Composite Message Fix)
        4. Objection refinement (Objection Stuck Fix)
        5. Disambiguation analysis (if unified_disambiguation flag enabled)

        Args:
            message: Сообщение пользователя
            context: Контекст диалога (state, spin_phase, last_action, last_intent,
                     last_bot_message, turn_number, last_objection_turn, last_objection_type,
                     expects_data_type)

        Returns:
            Результат классификации с полями:
            - intent: str
            - confidence: float
            - extracted_data: dict
            - method: str ("llm", "hybrid", или "llm_fallback")
            - refined: bool (если было уточнение)
            - original_intent: str (если было уточнение)
            - refinement_layer: str ("short_answer", "composite", или "objection")
            - secondary_signals: list (если обнаружены мета-сигналы)
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

        # Step 3: Composite message refinement (Composite Message Fix)
        if flags.composite_refinement:
            result = self._apply_composite_refinement(message, result, context)

        # Step 4: Objection refinement (Objection Stuck Fix)
        if flags.objection_refinement:
            result = self._apply_objection_refinement(message, result, context)

        # Step 5: Unified disambiguation analysis
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

    def _apply_composite_refinement(
        self,
        message: str,
        result: Dict,
        context: Dict
    ) -> Dict:
        """
        Apply CompositeMessageRefinementLayer to handle composite messages.

        This addresses misclassification of messages containing both data and
        meta-signals, like "5 человек, больше не нужно, быстрее" which should
        be classified as info_provided (with company_size=5) rather than
        objection_think.

        Works with any dialogue flow (SPIN, BANT, custom).

        Args:
            message: User's message
            result: Classification result from previous layers
            context: Dialog context with state, phase, last_action, etc.

        Returns:
            Refined result (or original if refinement not applicable)
        """
        try:
            from .composite_refinement import CompositeMessageContext

            composite_ctx = CompositeMessageContext(
                message=message,
                intent=result.get("intent", "unclear"),
                confidence=result.get("confidence", 0.0),
                current_phase=(
                    context.get("current_phase") or
                    context.get("spin_phase") or
                    context.get("phase")
                ),
                state=context.get("state"),
                last_action=context.get("last_action"),
                extracted_data=result.get("extracted_data", {}),
                turn_number=context.get("turn_number", 0),
                expects_data_type=context.get("expects_data_type"),
            )

            refined_result = self.composite_refinement_layer.refine(
                message, result, composite_ctx
            )

            return refined_result

        except Exception as e:
            # Fail-safe: return original result on any error
            logger.warning(
                "Composite refinement layer failed, returning original result",
                extra={
                    "error": str(e),
                    "message": message[:50],
                    "intent": result.get("intent")
                }
            )
            return result

    def _apply_objection_refinement(
        self,
        message: str,
        result: Dict,
        context: Dict
    ) -> Dict:
        """
        Apply ObjectionRefinementLayer to validate objection classifications.

        This addresses the Objection Stuck bug where messages like
        "бюджет пока не определён" are incorrectly classified as objection_price
        when the bot just asked about budget (making it an answer, not objection).

        Args:
            message: User's message
            result: Classification result from previous layers
            context: Dialog context with last_bot_message, last_action, etc.

        Returns:
            Refined result (or original if refinement not applicable)
        """
        try:
            from .objection_refinement import ObjectionRefinementContext

            objection_ctx = ObjectionRefinementContext(
                message=message,
                intent=result.get("intent", "unclear"),
                confidence=result.get("confidence", 0.0),
                last_bot_message=context.get("last_bot_message"),
                last_action=context.get("last_action"),
                state=context.get("state", "greeting"),
                turn_number=context.get("turn_number", 0),
                last_objection_turn=context.get("last_objection_turn"),
                last_objection_type=context.get("last_objection_type"),
            )

            refined_result = self.objection_refinement_layer.refine(
                message, result, objection_ctx
            )

            return refined_result

        except Exception as e:
            # Fail-safe: return original result on any error
            logger.warning(
                "Objection refinement layer failed, returning original result",
                extra={"error": str(e), "message": message[:50], "intent": result.get("intent")}
            )
            return result

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику."""
        stats = {
            "active_classifier": "llm" if flags.llm_classifier else "hybrid",
            "refinement_enabled": flags.classification_refinement,
            "composite_refinement_enabled": flags.composite_refinement,
            "objection_refinement_enabled": flags.objection_refinement,
            "unified_disambiguation_enabled": flags.unified_disambiguation,
        }

        if self._llm is not None:
            stats["llm_stats"] = self._llm.get_stats()

        if self._composite_refinement_layer is not None:
            stats["composite_refinement_stats"] = self._composite_refinement_layer.get_stats()

        if self._objection_refinement_layer is not None:
            stats["objection_refinement_stats"] = self._objection_refinement_layer.get_stats()

        if self._disambiguation_engine is not None:
            stats["disambiguation_stats"] = self._disambiguation_engine.get_stats()

        return stats

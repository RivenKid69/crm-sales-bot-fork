"""LLM-based классификатор интентов."""
from typing import Dict, Optional, Any

from logger import logger
from llm import OllamaClient
from .schemas import ClassificationResult
from .prompts import build_classification_prompt
from ..extractors.extraction_validator import validate_extracted_data


class LLMClassifier:
    """
    Классификатор на базе LLM с fallback на HybridClassifier.

    Использует Ollama для structured output с гарантией валидного JSON.
    При ошибке LLM падает на старый regex классификатор.
    """

    def __init__(
        self,
        vllm_client: Optional[OllamaClient] = None,
        fallback_classifier: Optional[Any] = None
    ):
        """
        Инициализация.

        Args:
            vllm_client: Ollama клиент (создаётся если не передан).
                         Параметр называется vllm_client для обратной совместимости.
            fallback_classifier: Fallback классификатор (HybridClassifier)
        """
        self.vllm = vllm_client or OllamaClient()
        self.fallback = fallback_classifier

        # Статистика
        self._llm_calls = 0
        self._llm_successes = 0
        self._fallback_calls = 0
        self._extraction_validations = 0
        self._extraction_corrections = 0

    def classify(self, message: str, context: Dict = None) -> Dict:
        """
        Классифицировать сообщение.

        Args:
            message: Сообщение пользователя
            context: Контекст диалога

        Returns:
            {
                "intent": str,
                "confidence": float,
                "extracted_data": dict,
                "method": "llm" | "llm_fallback",
                "reasoning": str (только для LLM)
            }
        """
        context = context or {}
        self._llm_calls += 1

        try:
            # Строим промпт
            prompt = build_classification_prompt(message, context)

            # Вызываем LLM с structured output
            result = self.vllm.generate_structured(prompt, ClassificationResult)

            if result is None:
                # LLM вернул None (circuit breaker или все retry провалились)
                logger.warning("LLM classifier returned None, using fallback")
                return self._use_fallback(message, context)

            self._llm_successes += 1

            # Формируем alternatives для ConfidenceRouter
            alternatives = []
            for alt in result.alternatives:
                alternatives.append({
                    "intent": alt.intent,
                    "confidence": alt.confidence
                })

            # Получаем raw extracted_data от LLM
            raw_extracted = result.extracted_data.model_dump(exclude_none=True)

            # Валидируем и очищаем extracted_data от галлюцинаций
            self._extraction_validations += 1
            validation_result = validate_extracted_data(raw_extracted, context)

            if validation_result.removed_fields:
                self._extraction_corrections += 1
                logger.info(
                    "Extraction validation corrected LLM output",
                    extra={
                        "removed": validation_result.removed_fields,
                        "corrections": validation_result.corrected_fields,
                        "errors": validation_result.errors,
                    }
                )

            # Используем очищенные данные
            validated_extracted = validation_result.validated_data

            return {
                "intent": result.intent,
                "confidence": result.confidence,
                "extracted_data": validated_extracted,
                "method": "llm",
                "reasoning": result.reasoning,
                "alternatives": alternatives
            }

        except Exception as e:
            logger.error(f"LLM classifier error: {e}")
            return self._use_fallback(message, context)

    def _use_fallback(self, message: str, context: Dict) -> Dict:
        """Использовать fallback классификатор."""
        self._fallback_calls += 1

        if self.fallback is None:
            # Нет fallback — возвращаем unclear
            logger.warning("No fallback classifier, returning unclear")
            return {
                "intent": "unclear",
                "confidence": 0.5,
                "extracted_data": {},
                "method": "llm_fallback",
                "alternatives": []
            }

        try:
            result = self.fallback.classify(message, context)
            result["method"] = "llm_fallback"
            # Добавляем alternatives если их нет (для совместимости со старым HybridClassifier)
            if "alternatives" not in result:
                result["alternatives"] = []
            return result
        except Exception as e:
            logger.error(f"Fallback classifier error: {e}")
            return {
                "intent": "unclear",
                "confidence": 0.3,
                "extracted_data": {},
                "method": "llm_fallback",
                "alternatives": []
            }

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику классификатора."""
        success_rate = (self._llm_successes / self._llm_calls * 100) if self._llm_calls > 0 else 0
        correction_rate = (
            self._extraction_corrections / self._extraction_validations * 100
        ) if self._extraction_validations > 0 else 0

        return {
            "llm_calls": self._llm_calls,
            "llm_successes": self._llm_successes,
            "fallback_calls": self._fallback_calls,
            "llm_success_rate": round(success_rate, 1),
            "extraction_validations": self._extraction_validations,
            "extraction_corrections": self._extraction_corrections,
            "extraction_correction_rate": round(correction_rate, 1),
            "vllm_stats": self.vllm.get_stats_dict()
        }

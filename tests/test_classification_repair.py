import json
from unittest.mock import Mock, patch

from pydantic import BaseModel, Field, ValidationError

from src.classifier.extractors.extraction_validator import ExtractionValidationResult
from src.classifier.llm.repair import (
    repair_classification_payload,
    salvage_classification_top_intent,
)
from src.classifier.llm.schemas import ClassificationResult
from src.llm import OllamaClient


def _ollama_response(content: str):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"message": {"content": content}}
    return response


class StrictScore(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)


class TestClassificationRepairRuntime:
    def test_repair_classification_payload_repairs_only_safe_schema_drift(self):
        repaired = repair_classification_payload(
            {
                "intent": "delivery_request",
                "confidence": "1.7",
                "reasoning": "user asked about shipping",
                "extracted_data": {"pain_category": "not_real", "contact_info": "+77771234567"},
                "alternatives": [
                    {"intent": "delivery_request", "confidence": "0.6"},
                    {"intent": "info_request", "confidence": 0.4},
                    {"intent": "question_features", "confidence": "-0.2"},
                    {"intent": "question_support", "confidence": "0.9"},
                    "bad",
                ],
            },
            ValidationError.from_exception_data("ClassificationResult", []),
        )

        assert repaired["intent"] == "question_delivery"
        assert repaired["confidence"] == 1.0
        assert repaired["extracted_data"] == {"contact_info": "+77771234567"}
        assert repaired["alternatives"] == [
            {"intent": "question_features", "confidence": 0.0},
            {"intent": "question_support", "confidence": 0.9},
        ]

    def test_repair_classification_payload_does_not_guess_new_top_intent(self):
        repaired = repair_classification_payload(
            {
                "intent": "question_scheduling",
                "confidence": "1.2",
                "reasoning": "invented label",
                "alternatives": [],
            },
            ValidationError.from_exception_data("ClassificationResult", []),
        )

        assert repaired["intent"] == "question_scheduling"
        assert repaired["confidence"] == 1.0

    def test_salvage_classification_top_intent_uses_safe_subset_and_validated_data(self):
        captured = {}

        def fake_validator(extracted_data, context):
            captured["extracted_data"] = dict(extracted_data)
            captured["context"] = dict(context)
            return ExtractionValidationResult(
                is_valid=True,
                original_data=dict(extracted_data),
                validated_data={"contact_info": "+7 777 123 45 67"},
            )

        fallback = Mock()
        fallback.classify.return_value = {
            "intent": "contact_provided",
            "confidence": 0.84,
            "extracted_data": {"ignored": True},
        }

        result = salvage_classification_top_intent(
            message="мой номер +7 777 123 45 67",
            context={"state": "spin_need"},
            last_cleaned_structured_response=json.dumps({
                "intent": "question_scheduling",
                "confidence": 0.72,
                "reasoning": "old llm reasoning",
                "extracted_data": {
                    "contact_info": "+7 777 123 45 67",
                    "company_name": "Acme",
                    "city": "Алматы",
                    "budget_range": "100k",
                },
                "alternatives": [{"intent": "greeting", "confidence": 0.1}],
            }),
            fallback_classifier=fallback,
            extraction_validator=fake_validator,
        )

        assert captured["extracted_data"] == {
            "contact_info": "+7 777 123 45 67",
            "company_name": "Acme",
            "city": "Алматы",
        }
        assert captured["context"] == {"state": "spin_need"}
        assert result == {
            "intent": "contact_provided",
            "confidence": 0.84,
            "alternatives": [],
            "extracted_data": {"contact_info": "+7 777 123 45 67"},
            "method": "llm_salvaged_top_intent",
            "structured_salvaged": True,
            "reasoning": "structured_salvage_via_fallback_intent",
            "metadata": {"original_llm_reasoning": "old llm reasoning"},
        }

    def test_salvage_classification_top_intent_returns_empty_extracted_data_after_validation(self):
        fallback = Mock()
        fallback.classify.return_value = {
            "intent": "contact_provided",
            "confidence": 0.84,
            "extracted_data": {},
        }

        result = salvage_classification_top_intent(
            message="test",
            context={},
            last_cleaned_structured_response=json.dumps({
                "intent": "question_scheduling",
                "confidence": 0.72,
                "reasoning": "old llm reasoning",
                "extracted_data": {"budget_range": "100k"},
            }),
            fallback_classifier=fallback,
            extraction_validator=lambda extracted_data, context: ExtractionValidationResult(
                is_valid=True,
                original_data=dict(extracted_data),
                validated_data={},
            ),
        )

        assert result["extracted_data"] == {}

    def test_salvage_classification_top_intent_returns_none_for_invalid_fallback_intent(self):
        fallback = Mock()
        fallback.classify.return_value = {
            "intent": "info_request",
            "confidence": 0.84,
            "extracted_data": {},
        }

        result = salvage_classification_top_intent(
            message="test",
            context={},
            last_cleaned_structured_response=json.dumps({
                "intent": "question_scheduling",
                "confidence": 0.72,
                "reasoning": "old llm reasoning",
            }),
            fallback_classifier=fallback,
        )

        assert result is None


class TestStructuredGenerateRepairHook:
    def test_generate_structured_repairs_classification_payload_without_retry(self):
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        payload = {
            "intent": "delivery_request",
            "confidence": "1.7",
            "reasoning": "user asked about shipping",
            "extracted_data": {"pain_category": "not_real", "contact_info": "+77771234567"},
            "alternatives": [
                {"intent": "delivery_request", "confidence": "0.6"},
                {"intent": "info_request", "confidence": 0.4},
                {"intent": "question_features", "confidence": "-0.2"},
                {"intent": "question_support", "confidence": "0.9"},
            ],
        }

        with patch("requests.post", return_value=_ollama_response(json.dumps(payload))) as mock_post:
            result, trace = client.generate_structured(
                "test",
                ClassificationResult,
                return_trace=True,
                repair_payload=repair_classification_payload,
            )

        assert result is not None
        assert result.intent == "question_delivery"
        assert result.confidence == 1.0
        assert [alt.intent for alt in result.alternatives] == ["question_features", "question_support"]
        assert trace.success is True
        assert trace.retry_count == 0
        assert trace.raw_response == json.dumps(payload)
        assert trace.last_cleaned_structured_response == json.dumps(payload)
        assert '"delivery_request"' in trace.raw_response
        assert '"question_delivery"' not in trace.raw_response
        assert mock_post.call_count == 1
        assert client.stats.successful_requests == 1
        assert client.stats.failed_requests == 0
        assert client.stats.total_retries == 0

    def test_generate_structured_retries_when_top_intent_stays_invalid(self):
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001
        payload = {
            "intent": "question_scheduling",
            "confidence": 0.72,
            "reasoning": "invented label",
            "extracted_data": {},
            "alternatives": [],
        }

        with patch("requests.post", return_value=_ollama_response(json.dumps(payload))) as mock_post:
            result, trace = client.generate_structured(
                "test",
                ClassificationResult,
                return_trace=True,
                repair_payload=repair_classification_payload,
            )

        assert result is None
        assert trace.success is False
        assert trace.retry_count == 2
        assert trace.raw_response == ""
        assert trace.last_cleaned_structured_response == json.dumps(payload)
        assert mock_post.call_count == 2
        assert client.stats.failed_requests == 1
        assert client.stats.total_retries == 1

    def test_generate_structured_keeps_behavior_without_repair_hook(self):
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        payload = {"score": 1.5}

        with patch("requests.post", return_value=_ollama_response(json.dumps(payload))):
            result, trace = client.generate_structured(
                "test",
                StrictScore,
                return_trace=True,
            )

        assert result is None
        assert trace.success is False
        assert trace.raw_response == ""
        assert trace.last_cleaned_structured_response == json.dumps(payload)
        assert trace.to_dict()["last_cleaned_structured_response"] == json.dumps(payload)

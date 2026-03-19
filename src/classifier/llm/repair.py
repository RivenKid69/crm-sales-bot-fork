"""Runtime repair and salvage helpers for LLM classification payloads."""

import json
from typing import Any, Callable, Dict, Optional

from src.classifier.extractors.extraction_validator import validate_extracted_data
from src.classifier.llm.schemas import (
    VALID_INTENTS,
    VALID_PAIN_CATEGORIES,
    normalize_intent_label,
    normalize_pain_category,
)

SAFE_SALVAGE_EXTRACTED_FIELDS = frozenset({
    "contact_info",
    "kaspi_phone",
    "iin",
    "city",
    "contact_name",
    "company_name",
})


def _coerce_confidence(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            return None
    else:
        return None
    return max(0.0, min(1.0, numeric))


def repair_classification_payload(payload: dict, validation_error: Exception) -> Optional[dict]:
    """Deterministically repair safe ClassificationResult schema drift."""
    del validation_error

    if not isinstance(payload, dict):
        return None

    repaired = dict(payload)

    repaired["intent"] = normalize_intent_label(repaired.get("intent"))

    confidence = _coerce_confidence(repaired.get("confidence"))
    if confidence is not None:
        repaired["confidence"] = confidence

    extracted_data = repaired.get("extracted_data")
    if not isinstance(extracted_data, dict):
        extracted_data = {}
    else:
        extracted_data = dict(extracted_data)

    if "pain_category" in extracted_data:
        normalized_pain = normalize_pain_category(extracted_data.get("pain_category"))
        if normalized_pain in VALID_PAIN_CATEGORIES:
            extracted_data["pain_category"] = normalized_pain
        else:
            extracted_data.pop("pain_category", None)
    repaired["extracted_data"] = extracted_data

    raw_alternatives = repaired.get("alternatives")
    repaired_alternatives = []
    if isinstance(raw_alternatives, list):
        for item in raw_alternatives:
            if not isinstance(item, dict):
                continue
            normalized_intent = normalize_intent_label(item.get("intent"))
            if normalized_intent not in VALID_INTENTS:
                continue
            if normalized_intent == repaired["intent"]:
                continue
            alt_confidence = _coerce_confidence(item.get("confidence"))
            if alt_confidence is None:
                continue
            repaired_alternatives.append({
                "intent": normalized_intent,
                "confidence": alt_confidence,
            })
            if len(repaired_alternatives) == 2:
                break
    repaired["alternatives"] = repaired_alternatives

    return repaired


def salvage_classification_top_intent(
    message: str,
    context: Optional[Dict[str, Any]],
    last_cleaned_structured_response: str,
    fallback_classifier: Optional[Any],
    extraction_validator: Callable[[Dict[str, Any], Optional[Dict[str, Any]]], Any] = validate_extracted_data,
) -> Optional[Dict[str, Any]]:
    """Use fallback classifier only for final top-intent salvage."""
    if not fallback_classifier or not last_cleaned_structured_response:
        return None

    try:
        payload = json.loads(last_cleaned_structured_response)
    except (TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    try:
        fallback_result = fallback_classifier.classify(message, context or {})
    except Exception:
        return None

    if not isinstance(fallback_result, dict):
        return None

    intent = normalize_intent_label(fallback_result.get("intent"))
    if intent not in VALID_INTENTS:
        return None

    confidence = _coerce_confidence(fallback_result.get("confidence"))
    if confidence is None:
        return None

    extracted_data = payload.get("extracted_data")
    safe_subset = {}
    if isinstance(extracted_data, dict):
        safe_subset = {
            key: extracted_data[key]
            for key in SAFE_SALVAGE_EXTRACTED_FIELDS
            if key in extracted_data
        }

    validation_result = extraction_validator(safe_subset, context or {})
    validated_extracted = validation_result.validated_data or {}

    metadata: Dict[str, Any] = {}
    original_reasoning = payload.get("reasoning")
    if original_reasoning is not None:
        metadata["original_llm_reasoning"] = original_reasoning

    return {
        "intent": intent,
        "confidence": confidence,
        "alternatives": [],
        "extracted_data": validated_extracted,
        "method": "llm_salvaged_top_intent",
        "structured_salvaged": True,
        "reasoning": "structured_salvage_via_fallback_intent",
        "metadata": metadata,
    }

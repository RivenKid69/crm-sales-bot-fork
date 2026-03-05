"""Tests for priority-pattern path extraction validation in UnifiedClassifier."""

import copy
import re
from unittest.mock import Mock, patch

from src.classifier.unified import UnifiedClassifier
from src.feature_flags import flags


def test_priority_pattern_validates_extracted_data():
    classifier = UnifiedClassifier()
    classifier._hybrid = Mock()
    classifier._hybrid.data_extractor.extract = Mock(
        return_value={
            "timeline": "undefined",   # sentinel garbage, must be removed
            "custom_field": "valid value",  # unknown field passthrough
        }
    )

    with patch(
        "src.classifier.intents.patterns.COMPILED_PRIORITY_PATTERNS",
        [(re.compile(r"^привет$", re.IGNORECASE), "greeting", 0.99)],
    ):
        result = classifier.classify("привет", context={})

    assert result["method"] == "priority_pattern"
    assert "timeline" not in result["extracted_data"]
    assert result["extracted_data"]["custom_field"] == "valid value"


def test_semantic_intent_arbitration_overrides_when_confident():
    classifier = UnifiedClassifier()
    result = {
        "intent": "situation_provided",
        "confidence": 0.78,
        "method": "llm",
        "alternatives": [{"intent": "question_features", "confidence": 0.66}],
        "semantic_frame": {
            "recommended_intent": "question_features",
            "recommended_confidence": 0.91,
            "override_intent": True,
        },
    }

    with patch.object(flags, "is_enabled", side_effect=lambda name: name == "semantic_intent_arbitration"):
        out = classifier._apply_semantic_intent_arbitration(copy.deepcopy(result))

    assert out["intent"] == "question_features"
    assert out["semantic_intent_original_intent"] == "situation_provided"
    assert out["semantic_intent_arbitration"]["overridden"] is True


def test_semantic_intent_arbitration_skips_priority_pattern_terminal_intent():
    classifier = UnifiedClassifier()
    result = {
        "intent": "greeting",
        "confidence": 0.95,
        "method": "priority_pattern",
        "semantic_frame": {
            "recommended_intent": "question_features",
            "recommended_confidence": 0.99,
            "override_intent": True,
        },
    }

    with patch.object(flags, "is_enabled", side_effect=lambda name: name == "semantic_intent_arbitration"):
        out = classifier._apply_semantic_intent_arbitration(copy.deepcopy(result))

    assert out["intent"] == "greeting"
    assert "semantic_intent_arbitration" not in out


def test_semantic_intent_arbitration_can_override_non_terminal_priority_pattern():
    classifier = UnifiedClassifier()
    result = {
        "intent": "situation_provided",
        "confidence": 0.8,
        "method": "priority_pattern",
        "semantic_frame": {
            "recommended_intent": "question_features",
            "recommended_confidence": 0.95,
            "override_intent": True,
        },
    }

    with patch.object(flags, "is_enabled", side_effect=lambda name: name == "semantic_intent_arbitration"):
        out = classifier._apply_semantic_intent_arbitration(copy.deepcopy(result))

    assert out["intent"] == "question_features"
    assert out["semantic_intent_arbitration"]["overridden"] is True


def test_attach_semantic_frame_passes_intent_candidates():
    classifier = UnifiedClassifier()
    classifier._semantic_frame_extractor = Mock()
    classifier._semantic_frame_extractor.extract = Mock(return_value={"asked_dimensions": ["features"]})
    result = {
        "intent": "question_features",
        "confidence": 0.8,
        "secondary_signals": ["price_question"],
        "alternatives": [{"intent": "pricing_details", "confidence": 0.4}],
    }

    with patch.object(flags, "is_enabled", side_effect=lambda name: name == "semantic_frame"):
        out = classifier._attach_semantic_frame("что умеете", copy.deepcopy(result), context={})

    assert "semantic_frame" in out
    kwargs = classifier._semantic_frame_extractor.extract.call_args.kwargs
    assert kwargs["candidate_intents"] == [
        "question_features",
        "pricing_details",
        "price_question",
    ]

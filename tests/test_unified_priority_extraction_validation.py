"""Tests for priority-pattern path extraction validation in UnifiedClassifier."""

import re
from unittest.mock import Mock, patch

from src.classifier.unified import UnifiedClassifier


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

"""
Anti-regression tests for Intent Label Leakage.

Ensures that:
- Only the SSoT (src/constants/intent_labels.py) defines INTENT_LABELS
- All labels are human-readable Russian (not raw snake_case)
- DisambiguationUI never returns snake_case to users
- disambiguation_engine.py and confidence_router.py import from SSoT
"""
import re
from pathlib import Path

import pytest

from src.constants.intent_labels import INTENT_LABELS
from src.disambiguation_ui import DisambiguationUI

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# =============================================================================
# TEST: No local INTENT_LABELS definitions
# =============================================================================

class TestNoLocalIntentLabels:
    """Ensure INTENT_LABELS is only defined in the SSoT file."""

    def test_no_local_intent_labels_definitions(self):
        """Scan all src/*.py for `INTENT_LABELS = {` and assert only SSoT defines it."""
        ssot_path = PROJECT_ROOT / "src" / "constants" / "intent_labels.py"
        violations = []

        for py_file in (PROJECT_ROOT / "src").rglob("*.py"):
            if py_file == ssot_path:
                continue
            content = py_file.read_text(encoding="utf-8")
            # Match assignment like `INTENT_LABELS = {`
            if re.search(r"^INTENT_LABELS\s*=\s*\{", content, re.MULTILINE):
                violations.append(str(py_file.relative_to(PROJECT_ROOT)))

        assert violations == [], (
            f"INTENT_LABELS must only be defined in SSoT "
            f"(src/constants/intent_labels.py), but found in: {violations}"
        )

# =============================================================================
# TEST: Label quality
# =============================================================================

SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")

class TestLabelQuality:
    """Ensure all SSoT labels are human-readable Russian."""

    # Brand names that are legitimately in Latin script
    BRAND_NAME_EXCEPTIONS = {
        "question_whatsapp_business",  # "WhatsApp Business"
    }

    def test_all_labels_are_russian(self):
        """All SSoT labels contain at least one Cyrillic character (except brand names)."""
        non_russian = {}
        for intent, label in INTENT_LABELS.items():
            if intent in self.BRAND_NAME_EXCEPTIONS:
                continue
            has_cyrillic = any("\u0400" <= c <= "\u04FF" for c in label)
            if not has_cyrillic:
                non_russian[intent] = label

        assert non_russian == {}, (
            f"Labels must contain Cyrillic characters: {non_russian}"
        )

    def test_no_label_is_raw_snake_case(self):
        """No label matches raw snake_case pattern like `question_tax_optimization`."""
        snake_case_labels = {
            intent: label
            for intent, label in INTENT_LABELS.items()
            if SNAKE_CASE_RE.match(label)
        }

        assert snake_case_labels == {}, (
            f"Labels must not be raw snake_case: {snake_case_labels}"
        )

# =============================================================================
# TEST: DisambiguationUI resolves labels via SSoT
# =============================================================================

class TestUIResolvesLabels:
    """Ensure DisambiguationUI._get_option_label never returns snake_case."""

    def test_ui_resolves_label_for_all_ssot_intents(self):
        """
        Simulate the bug scenario: option has intent=X and label=X (raw name).
        Assert UI never returns a snake_case label.
        """
        ui = DisambiguationUI()
        leaks = {}

        for intent in INTENT_LABELS:
            # Simulate the bug: label == raw intent name
            option = {"intent": intent, "label": intent}
            result = ui._get_option_label(option)

            if SNAKE_CASE_RE.match(result):
                leaks[intent] = result

        assert leaks == {}, (
            f"UI returned raw snake_case labels for: {leaks}"
        )

    def test_ui_returns_ssot_label_over_raw_label(self):
        """When option has label=intent (raw), UI must return the SSoT label."""
        ui = DisambiguationUI()

        option = {"intent": "question_tax_optimization", "label": "question_tax_optimization"}
        result = ui._get_option_label(option)

        assert result == INTENT_LABELS["question_tax_optimization"]
        assert result != "question_tax_optimization"

    def test_ui_fallback_for_unknown_intent(self):
        """For unknown intent without a valid label, return 'Другое'."""
        ui = DisambiguationUI()

        option = {"intent": "", "label": ""}
        result = ui._get_option_label(option)

        assert result == "Другое"

    def test_ui_uses_explicit_label_for_unknown_intent(self):
        """For unknown intent with a human-readable label, use that label."""
        ui = DisambiguationUI()

        option = {"intent": "some_new_intent", "label": "Новая функция"}
        result = ui._get_option_label(option)

        assert result == "Новая функция"

# =============================================================================
# TEST: Source file imports
# =============================================================================

class TestSourceImports:
    """Verify that disambiguation_engine.py and confidence_router.py import from SSoT."""

    def test_disambiguation_engine_imports_ssot(self):
        """disambiguation_engine.py imports INTENT_LABELS from SSoT."""
        source = (
            PROJECT_ROOT / "src" / "classifier" / "disambiguation_engine.py"
        ).read_text(encoding="utf-8")

        assert "from src.constants.intent_labels import INTENT_LABELS" in source, (
            "disambiguation_engine.py must import INTENT_LABELS from "
            "src.constants.intent_labels"
        )

    def test_confidence_router_imports_ssot(self):
        """confidence_router.py imports INTENT_LABELS from SSoT."""
        source = (
            PROJECT_ROOT / "src" / "classifier" / "confidence_router.py"
        ).read_text(encoding="utf-8")

        assert "from src.constants.intent_labels import INTENT_LABELS" in source, (
            "confidence_router.py must import INTENT_LABELS from "
            "src.constants.intent_labels"
        )

# =============================================================================
# TEST: Confirmed leak cases from bug report
# =============================================================================

class TestConfirmedLeakCases:
    """Verify the 5 confirmed leak cases now resolve correctly."""

    CONFIRMED_LEAKS = {
        "objection_bad_experience": "Обсудить прошлый опыт",
        "question_tax_optimization": "Оптимизировать налоги",
        "question_delivery": "Узнать о доставке",
        "question_business_registration": "Открыть ИП/ТОО",
        "question_accounting_services": "Бухгалтерские услуги",
    }

    @pytest.mark.parametrize("intent,expected_label", CONFIRMED_LEAKS.items())
    def test_confirmed_leak_resolved(self, intent, expected_label):
        """Each confirmed leak case now returns the correct Russian label."""
        ui = DisambiguationUI()

        # Simulate the exact bug: option has label=intent (raw snake_case)
        option = {"intent": intent, "label": intent}
        result = ui._get_option_label(option)

        assert result == expected_label, (
            f"Intent '{intent}' should resolve to '{expected_label}', got '{result}'"
        )

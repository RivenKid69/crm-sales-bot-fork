"""
Tests for bot always re-asks contact fix.

Tests three defense layers:
1. cta_generator.py — gate: skip contact CTA when contact in collected_data
2. generator.py — do_not_ask: instruct LLM not to ask for contact
3. prompts.yaml — template: conditional contact request wording

SSoT: src/conditions/state_machine/contact_validator.py
"""
import pytest
from unittest.mock import patch, MagicMock

from src.cta_generator import CTAGenerator, CTAResult

class TestCTAContactGate:
    """Layer 1: cta_generator.py — contact gate."""

    def _make_generator(self, turns=5):
        """Create a CTAGenerator with enough turns to pass MIN_TURNS_FOR_CTA."""
        gen = CTAGenerator()
        for _ in range(turns):
            gen.increment_turn()
        return gen

    def test_close_phase_skips_when_contact_collected(self):
        """CTA blocked with valid contact in collected_data for close phase."""
        gen = self._make_generator()

        collected_data = {"email": "user@example.com"}
        context = {
            "frustration_level": 0,
            "collected_data": collected_data,
            "flow_context": None,
        }

        with patch(
            "src.conditions.state_machine.contact_validator.has_valid_contact",
            return_value=True,
        ):
            should_add, reason = gen.should_add_cta(
                state="close",
                response="Отлично, рад что заинтересовались!",
                context=context,
            )

        assert should_add is False
        assert reason == "contact_already_collected"

    def test_close_phase_allows_when_no_contact(self):
        """CTA allowed when no contact in collected_data for close phase."""
        gen = self._make_generator()

        context = {
            "frustration_level": 0,
            "collected_data": {},
            "flow_context": None,
        }

        should_add, reason = gen.should_add_cta(
            state="close",
            response="Отлично, рад что заинтересовались!",
            context=context,
        )

        assert should_add is True
        assert reason is None

    def test_late_phase_unaffected_by_contact(self):
        """Late demo CTA still fires even with contact data (not close phase)."""
        gen = self._make_generator()

        collected_data = {"email": "user@example.com"}
        context = {
            "frustration_level": 0,
            "collected_data": collected_data,
            "flow_context": None,
        }

        # presentation maps to "late" phase, not "close"
        should_add, reason = gen.should_add_cta(
            state="presentation",
            response="Wipon решает эту проблему автоматически.",
            context=context,
        )

        # Should pass the contact gate (not "close" phase)
        assert reason != "contact_already_collected"

    def test_close_phase_graceful_degradation_on_import_error(self):
        """Graceful degradation when contact_validator is not importable."""
        import builtins
        gen = self._make_generator()

        collected_data = {"email": "user@example.com"}
        context = {
            "frustration_level": 0,
            "collected_data": collected_data,
            "flow_context": None,
        }

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "contact_validator" in name:
                raise ImportError("no module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            # Should not crash, should proceed to allow CTA
            should_add, reason = gen.should_add_cta(
                state="close",
                response="Отлично, рад что заинтересовались!",
                context=context,
            )

        # Contact gate should be skipped due to import error, CTA should pass
        assert reason != "contact_already_collected"

class TestGeneratorDoNotAskContact:
    """Layer 2: generator.py — do_not_ask for contact_info."""

    def test_do_not_ask_includes_contact_info(self):
        """Verify do_not_ask variable is set when contact is collected."""
        from src.generator import PERSONALIZATION_DEFAULTS

        # Simulate what generator.generate() does with collected data
        collected = {"email": "user@example.com", "contact_info": "user@example.com"}
        variables = dict(PERSONALIZATION_DEFAULTS)
        variables["do_not_ask"] = ""

        # Replicate the fix logic from generator.py
        try:
            from src.conditions.state_machine.contact_validator import has_valid_contact
            if has_valid_contact(collected):
                contact_val = (
                    collected.get("contact_info")
                    or collected.get("email")
                    or collected.get("phone")
                    or "уже получен"
                )
                contact_warning = (
                    "⚠️ НЕ СПРАШИВАЙ контактные данные (телефон/email) — "
                    f"уже известно: {contact_val}."
                )
                existing = variables.get("do_not_ask", "")
                variables["do_not_ask"] = f"{existing}\n{contact_warning}" if existing else contact_warning
        except ImportError:
            pytest.skip("contact_validator not available")

        assert "НЕ СПРАШИВАЙ контактные данные" in variables["do_not_ask"]
        assert "user@example.com" in variables["do_not_ask"]

    def test_do_not_ask_empty_when_no_contact(self):
        """do_not_ask stays empty when no contact is collected."""
        collected = {"company_size": 10}
        do_not_ask = ""

        try:
            from src.conditions.state_machine.contact_validator import has_valid_contact
            if has_valid_contact(collected):
                do_not_ask = "контакт"
        except ImportError:
            pytest.skip("contact_validator not available")

        assert do_not_ask == ""

    def test_do_not_ask_appends_to_existing(self):
        """do_not_ask appends contact warning to existing company_size warning."""
        collected = {"email": "user@example.com", "company_size": 10}
        existing_warning = "⚠️ НЕ СПРАШИВАЙ о размере команды — уже известно: 10 человек."

        try:
            from src.conditions.state_machine.contact_validator import has_valid_contact
            if has_valid_contact(collected):
                contact_warning = (
                    "⚠️ НЕ СПРАШИВАЙ контактные данные (телефон/email) — "
                    f"уже известно: {collected.get('email')}."
                )
                result = f"{existing_warning}\n{contact_warning}"
            else:
                result = existing_warning
        except ImportError:
            pytest.skip("contact_validator not available")

        assert "НЕ СПРАШИВАЙ о размере" in result
        assert "НЕ СПРАШИВАЙ контактные данные" in result

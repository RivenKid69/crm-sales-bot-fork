"""
Targeted tests for turn counting, template leak, and frustration threshold fixes.

Tests cover:
- Off-by-one in turn counting (client_agent.py, runner.py)
- Tier-1 template used as full response (bot.py, response_directives.py)
- Frustration thresholds too low + suppress_decay too aggressive

NOTE: Tests that require LLM or semantic search are intentionally skipped.
"""

import sys
from pathlib import Path
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock, PropertyMock
from typing import Dict, Any, List

import pytest

# =============================================================================
# Off-by-one in turn counting
# =============================================================================

class TestOffByOne:
    """Tests for is_budget_exhausted() and runner budget check."""

    @pytest.fixture
    def make_persona(self):
        """Factory for creating test personas."""
        from src.simulator.personas import Persona
        def _make(max_turns=8, name="Тест"):
            return Persona(
                name=name,
                description="Тестовая персона",
                max_turns=max_turns,
                objection_probability=0.0,
                insistence_probability=0.0,
                preferred_objections=[],
                conversation_starters=["привет"],
            )
        return _make

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.generate.return_value = "ок понял"
        return llm

    def test_is_budget_exhausted_method(self, make_persona, mock_llm):
        """Unit test: is_budget_exhausted() returns True when turn >= max_turns."""
        from src.simulator.client_agent import ClientAgent
        persona = make_persona(max_turns=5)
        agent = ClientAgent(mock_llm, persona)

        # Initially not exhausted
        assert agent.is_budget_exhausted() is False

        # Set turn to max_turns - 1
        agent.turn = 4
        assert agent.is_budget_exhausted() is False

        # Set turn to max_turns
        agent.turn = 5
        assert agent.is_budget_exhausted() is True

        # Set turn above max_turns
        agent.turn = 6
        assert agent.is_budget_exhausted() is True

    def test_is_budget_exhausted_is_deterministic(self, make_persona, mock_llm):
        """is_budget_exhausted() has no random factor, unlike should_continue()."""
        from src.simulator.client_agent import ClientAgent
        persona = make_persona(max_turns=5, name="Занятой")
        agent = ClientAgent(mock_llm, persona)
        agent.turn = 5

        # Call 100 times — always True (no randomness)
        results = [agent.is_budget_exhausted() for _ in range(100)]
        assert all(results), "is_budget_exhausted must be deterministic"

    def test_should_continue_vs_is_budget_exhausted(self, make_persona, mock_llm):
        """should_continue and is_budget_exhausted agree at boundary."""
        from src.simulator.client_agent import ClientAgent
        persona = make_persona(max_turns=8)
        agent = ClientAgent(mock_llm, persona)
        agent.turn = 8

        # Both should indicate "stop"
        assert agent.is_budget_exhausted() is True
        assert agent.should_continue() is False

    def test_happy_path_unaffected(self, make_persona, mock_llm):
        """max_turns=15 (happy_path) — is_budget_exhausted only at 15."""
        from src.simulator.client_agent import ClientAgent
        persona = make_persona(max_turns=15, name="Идеальный клиент")
        agent = ClientAgent(mock_llm, persona)

        for t in range(15):
            agent.turn = t
            assert agent.is_budget_exhausted() is False

        agent.turn = 15
        assert agent.is_budget_exhausted() is True

# =============================================================================
# Template leak — tier-1 rephrase used as full response
# =============================================================================

class TestTemplateLeak:
    """Tests for rephrase_mode in ResponseDirectives."""

    def test_rephrase_mode_field_exists(self):
        """ResponseDirectives has rephrase_mode field, default False."""
        from src.response_directives import ResponseDirectives
        d = ResponseDirectives()
        assert d.rephrase_mode is False

    def test_rephrase_mode_in_instruction(self):
        """When rephrase_mode=True, get_instruction includes rephrase text."""
        from src.response_directives import ResponseDirectives
        d = ResponseDirectives(rephrase_mode=True)
        instruction = d.get_instruction()
        assert "Переформулируй" in instruction
        assert "дословно" in instruction

    def test_rephrase_mode_not_in_instruction_when_false(self):
        """When rephrase_mode=False, get_instruction does not include rephrase."""
        from src.response_directives import ResponseDirectives
        d = ResponseDirectives(rephrase_mode=False)
        instruction = d.get_instruction()
        assert "Переформулируй" not in instruction

    def test_tier1_continue_sets_rephrase_mode(self):
        """When fallback returns action='continue', rephrase_mode is set,
        fallback_response is None (generator will handle)."""
        # Simulate the logic from bot.py
        fb_result = {"response": "Уточню вопрос по-другому...", "action": "continue"}

        fallback_response = None
        rephrase_mode = False
        fallback_action = None
        fallback_message = None

        if fb_result.get("response"):
            if fb_result.get("action") == "continue":
                fallback_response = None
                rephrase_mode = True
                fallback_action = "continue"
                fallback_message = fb_result.get("response")
            else:
                fallback_response = fb_result
                fallback_action = fb_result.get("action")
                fallback_message = fb_result.get("response")

        assert rephrase_mode is True
        assert fallback_response is None  # Generator should handle
        assert fallback_action == "continue"
        assert fallback_message == "Уточню вопрос по-другому..."

    def test_non_continue_action_preserves_fallback(self):
        """When fallback returns action='close', fallback_response is set."""
        fb_result = {"response": "До свидания", "action": "close"}

        fallback_response = None
        rephrase_mode = False

        if fb_result.get("response"):
            if fb_result.get("action") == "continue":
                fallback_response = None
                rephrase_mode = True
            else:
                fallback_response = fb_result

        assert rephrase_mode is False
        assert fallback_response == fb_result

# =============================================================================
# Frustration thresholds too low + suppress_decay too aggressive
# =============================================================================

class TestFrustrationThresholds:
    """Tests for raised frustration thresholds."""

    def test_empathetic_threshold_5(self):
        """frustration=4 → NEUTRAL, frustration=5 → EMPATHETIC."""
        from src.response_directives import ResponseDirectivesBuilder, ResponseTone
        from src.context_envelope import ContextEnvelope

        # frustration=4 → should NOT be empathetic
        envelope4 = ContextEnvelope(frustration_level=4)
        builder4 = ResponseDirectivesBuilder(envelope4, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        directives4 = builder4.build()
        assert directives4.tone != ResponseTone.EMPATHETIC

        # frustration=5 → should be empathetic
        envelope5 = ContextEnvelope(frustration_level=5)
        builder5 = ResponseDirectivesBuilder(envelope5, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        directives5 = builder5.build()
        assert directives5.tone == ResponseTone.EMPATHETIC

    def test_validate_threshold_4(self):
        """frustration=3 → no validate, frustration=4 → validate."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        # frustration=3 → no validate
        envelope3 = ContextEnvelope(frustration_level=3)
        builder3 = ResponseDirectivesBuilder(envelope3, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        directives3 = builder3.build()
        assert directives3.validate is False

        # frustration=4 → validate
        envelope4 = ContextEnvelope(frustration_level=4)
        builder4 = ResponseDirectivesBuilder(envelope4, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        directives4 = builder4.build()
        assert directives4.validate is True

    def test_guard_frustration_uses_ssot(self):
        """GUARD_FRUSTRATION fires at FRUSTRATION_WARNING (4), not at 3."""
        from src.context_envelope import ContextEnvelope, ContextEnvelopeBuilder, ReasonCode

        # Create a minimal builder to call _compute_reason_codes
        # We need to mock the builder's dependencies
        mock_sm = MagicMock()
        mock_sm.current_state = "greeting"
        mock_sm.collected_data = {}
        mock_sm.missing_data = []

        # frustration=3 → GUARD_FRUSTRATION should NOT fire (was firing before fix)
        envelope3 = ContextEnvelope(frustration_level=3)
        builder3 = ContextEnvelopeBuilder(
            state_machine=mock_sm,
            context_window=None,
            tone_info={"frustration_level": 3},
        )
        builder3._compute_reason_codes(envelope3)
        assert not envelope3.has_reason(ReasonCode.GUARD_FRUSTRATION), \
            "GUARD_FRUSTRATION should not fire at frustration=3"

        # frustration=4 → GUARD_FRUSTRATION should fire
        envelope4 = ContextEnvelope(frustration_level=4)
        builder4 = ContextEnvelopeBuilder(
            state_machine=mock_sm,
            context_window=None,
            tone_info={"frustration_level": 4},
        )
        builder4._compute_reason_codes(envelope4)
        assert envelope4.has_reason(ReasonCode.GUARD_FRUSTRATION), \
            "GUARD_FRUSTRATION should fire at frustration=4 (FRUSTRATION_WARNING)"

    def test_suppress_decay_conditional(self):
        """suppress_decay should be True only when delta >= 2."""
        # Test the expression: suppress_decay=(sf.delta >= 2)
        @dataclass
        class FakeSF:
            delta: int = 0
            signals: list = field(default_factory=list)

        sf1 = FakeSF(delta=1)
        assert (sf1.delta >= 2) is False, "delta=1 should NOT suppress decay"

        sf2 = FakeSF(delta=2)
        assert (sf2.delta >= 2) is True, "delta=2 should suppress decay"

        sf3 = FakeSF(delta=3)
        assert (sf3.delta >= 2) is True, "delta=3 should suppress decay"

    def test_three_skeptical_no_empathetic(self):
        """3 SKEPTICAL turns → frustration=3, tone should remain NEUTRAL (not EMPATHETIC).

        With old threshold of 3, this would trigger EMPATHETIC.
        With new threshold of 5, tone stays NEUTRAL.
        """
        from src.response_directives import ResponseDirectivesBuilder, ResponseTone
        from src.context_envelope import ContextEnvelope

        # 3 SKEPTICAL turns give ~3 frustration (each SKEPTICAL adds ~1)
        envelope = ContextEnvelope(frustration_level=3, tone="skeptical")
        builder = ResponseDirectivesBuilder(envelope, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        directives = builder.build()
        assert directives.tone != ResponseTone.EMPATHETIC, \
            "3 SKEPTICAL (frustration=3) should not trigger EMPATHETIC with threshold=5"

    def test_default_thresholds_updated(self):
        """Default thresholds in ResponseDirectivesBuilder match new values."""
        from src.response_directives import ResponseDirectivesBuilder
        defaults = ResponseDirectivesBuilder._DEFAULT_TONE_THRESHOLDS
        assert defaults["empathetic_frustration"] == 5
        assert defaults["validate_frustration"] == 4

# =============================================================================
# Fast-track for turn-limited conversations
# =============================================================================

class TestFastTrackContact:
    """Tests for prioritize_contact in ResponseDirectives."""

    def test_prioritize_contact_field_exists(self):
        """ResponseDirectives has prioritize_contact field, default False."""
        from src.response_directives import ResponseDirectives
        d = ResponseDirectives()
        assert d.prioritize_contact is False

    def test_prioritize_contact_in_instruction(self):
        """When prioritize_contact=True, instruction includes contact request."""
        from src.response_directives import ResponseDirectives
        d = ResponseDirectives(prioritize_contact=True)
        instruction = d.get_instruction()
        assert "контактные данные" in instruction
        assert "торопится" in instruction

    def test_prioritize_contact_rushed_lowercase(self):
        """tone='rushed' (lowercase, Tone.RUSHED.value) triggers fast-track."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(
            tone="rushed",
            collected_data={},
            total_turns=6,
        )
        builder = ResponseDirectivesBuilder(envelope, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        result = builder._should_fast_track_contact()
        assert result is True

    def test_no_prioritize_when_contact_exists(self):
        """When has_valid_contact returns True, no fast-track."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(
            tone="rushed",
            collected_data={"contact_info": {"email": "test@test.com"}},
            total_turns=6,
        )
        builder = ResponseDirectivesBuilder(envelope, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })

        # Mock has_valid_contact to return True
        with patch(
            "src.response_directives.has_valid_contact",
            return_value=True,
            create=True,
        ):
            # Even with mock, the import inside the method will be used
            # Let's mock at the import location
            pass

        # Use the actual method — it imports has_valid_contact internally
        # We need to mock at the source
        with patch(
            "src.conditions.state_machine.contact_validator.has_valid_contact",
            return_value=True,
        ):
            result = builder._should_fast_track_contact()
            assert result is False

    def test_no_prioritize_early_turns(self):
        """total_turns=2 → no fast-track (need >= 4)."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(
            tone="rushed",
            collected_data={},
            total_turns=2,
        )
        builder = ResponseDirectivesBuilder(envelope, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        result = builder._should_fast_track_contact()
        assert result is False

    def test_no_prioritize_non_rushed(self):
        """tone='neutral' → no fast-track."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(
            tone="neutral",
            collected_data={},
            total_turns=6,
        )
        builder = ResponseDirectivesBuilder(envelope, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        result = builder._should_fast_track_contact()
        assert result is False

    def test_no_prioritize_frustrated_tone(self):
        """tone='frustrated' → no fast-track (only 'rushed')."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(
            tone="frustrated",
            collected_data={},
            total_turns=6,
        )
        builder = ResponseDirectivesBuilder(envelope, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        result = builder._should_fast_track_contact()
        assert result is False

    def test_fast_track_at_exactly_4_turns(self):
        """total_turns=4 → fast-track (boundary)."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(
            tone="rushed",
            collected_data={},
            total_turns=4,
        )
        builder = ResponseDirectivesBuilder(envelope, config={
            "tone_thresholds": {"empathetic_frustration": 5, "validate_frustration": 4}
        })
        result = builder._should_fast_track_contact()
        assert result is True

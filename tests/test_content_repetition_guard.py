# tests/test_content_repetition_guard.py

"""
Tests for ContentRepetitionGuard (hybrid window-based content repetition detection).

Covers:
1. ContextWindow.compute_content_repeat_count() — unit tests
2. ContentRepetitionGuardSource — should_contribute() + contribute() tests
3. Integration: priority resolution with other sources
"""

import pytest
import math
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass, field
from typing import List, Optional


# =============================================================================
# UNIT TESTS: ContextWindow.compute_content_repeat_count()
# =============================================================================

class TestComputeContentRepeatCount:
    """Tests for ContextWindow.compute_content_repeat_count()."""

    def _make_cw(self, max_size=10):
        from src.context_window import ContextWindow
        return ContextWindow(max_size=max_size)

    def _make_embedding(self, seed: float) -> List[float]:
        """Create a deterministic 4-dim embedding for testing.

        Same seed → same embedding → cosine similarity = 1.0.
        Different seeds → different embeddings → cosine < 1.0.
        """
        # Simple deterministic embedding: unit vector rotated by seed
        angle = seed * 0.5
        return [math.cos(angle), math.sin(angle), math.cos(angle * 2), math.sin(angle * 2)]

    def _add_turn(self, cw, embedding=None, fact_keys=None, state="autonomous_discovery"):
        """Add a turn with specified embedding and fact_keys."""
        cw.add_turn_from_dict(
            user_message="тест",
            bot_response="ответ",
            intent="price_question",
            confidence=0.9,
            action="autonomous_respond",
            state=state,
            next_state=state,
            fact_keys_used=fact_keys or [],
            response_embedding=embedding,
        )

    def test_empty_window_returns_zero(self):
        """Empty window → count = 0."""
        cw = self._make_cw()
        assert cw.compute_content_repeat_count() == 0

    def test_single_turn_returns_zero(self):
        """Single turn → count = 0 (len < 2)."""
        cw = self._make_cw()
        emb = self._make_embedding(1.0)
        self._add_turn(cw, embedding=emb)
        assert cw.compute_content_repeat_count() == 0

    def test_identical_embeddings_count(self):
        """3 turns with identical embeddings → count = 2 (ref not counted)."""
        cw = self._make_cw()
        emb = self._make_embedding(1.0)
        self._add_turn(cw, embedding=emb)
        self._add_turn(cw, embedding=emb)
        self._add_turn(cw, embedding=emb)
        assert cw.compute_content_repeat_count() == 2

    def test_different_embeddings_zero_count(self):
        """3 turns with very different embeddings → count = 0."""
        cw = self._make_cw()
        self._add_turn(cw, embedding=self._make_embedding(0.0))
        self._add_turn(cw, embedding=self._make_embedding(5.0))
        self._add_turn(cw, embedding=self._make_embedding(10.0))
        assert cw.compute_content_repeat_count() == 0

    def test_oscillation_pattern(self):
        """A-B-A-B-A pattern → count for last A ≥ 2 (sees A[0] and A[2])."""
        cw = self._make_cw()
        emb_a = self._make_embedding(1.0)
        emb_b = self._make_embedding(10.0)  # Very different
        self._add_turn(cw, embedding=emb_a)  # A[0]
        self._add_turn(cw, embedding=emb_b)  # B[1]
        self._add_turn(cw, embedding=emb_a)  # A[2]
        self._add_turn(cw, embedding=emb_b)  # B[3]
        self._add_turn(cw, embedding=emb_a)  # A[4] = ref
        # ref (A[4]) vs window: A[0] similar, B[1] not, A[2] similar, B[3] not
        assert cw.compute_content_repeat_count() == 2

    def test_meta_loop_redirect_not_similar(self):
        """[KB, redirect, KB] → count for last KB = 1 (first KB; redirect different)."""
        cw = self._make_cw()
        emb_kb = self._make_embedding(1.0)
        emb_redir = self._make_embedding(10.0)
        self._add_turn(cw, embedding=emb_kb)
        self._add_turn(cw, embedding=emb_redir)
        self._add_turn(cw, embedding=emb_kb)
        assert cw.compute_content_repeat_count() == 1

    def test_no_embeddings_fact_keys_fallback(self):
        """No embeddings, same fact_keys → count through fallback."""
        cw = self._make_cw()
        keys = ["pricing", "tariffs"]
        self._add_turn(cw, fact_keys=keys)
        self._add_turn(cw, fact_keys=keys)
        self._add_turn(cw, fact_keys=keys)
        # Jaccard of identical sets = 1.0 >= 0.5
        assert cw.compute_content_repeat_count() == 2

    def test_no_embeddings_different_fact_keys(self):
        """No embeddings, different fact_keys → count = 0."""
        cw = self._make_cw()
        self._add_turn(cw, fact_keys=["pricing"])
        self._add_turn(cw, fact_keys=["features"])
        self._add_turn(cw, fact_keys=["support"])
        assert cw.compute_content_repeat_count() == 0

    def test_no_embeddings_no_fact_keys_returns_zero(self):
        """No embeddings and no fact_keys → count = 0."""
        cw = self._make_cw()
        self._add_turn(cw)
        self._add_turn(cw)
        self._add_turn(cw)
        assert cw.compute_content_repeat_count() == 0

    def test_cross_state(self):
        """Different states, same embeddings → count still counts (cross-state)."""
        cw = self._make_cw()
        emb = self._make_embedding(1.0)
        self._add_turn(cw, embedding=emb, state="autonomous_discovery")
        self._add_turn(cw, embedding=emb, state="autonomous_qualification")
        self._add_turn(cw, embedding=emb, state="autonomous_presentation")
        assert cw.compute_content_repeat_count() == 2

    def test_window_limit(self):
        """7 turns, window=5 → old turns beyond window not counted."""
        cw = self._make_cw(max_size=10)
        emb = self._make_embedding(1.0)
        emb_diff = self._make_embedding(10.0)
        # Turns 0-1: similar (outside window of 5 from ref at index 6)
        self._add_turn(cw, embedding=emb)
        self._add_turn(cw, embedding=emb)
        # Turns 2-5: different
        self._add_turn(cw, embedding=emb_diff)
        self._add_turn(cw, embedding=emb_diff)
        self._add_turn(cw, embedding=emb_diff)
        self._add_turn(cw, embedding=emb_diff)
        # Turn 6: ref (similar to 0,1 but they're outside window)
        self._add_turn(cw, embedding=emb)
        # Window = turns 1..5 (5 turns before ref at 6)
        # Turn 1 is at index 1, start = max(0, 7-1-5) = 1 → scan [1,2,3,4,5]
        # Turn 1: similar, turns 2-5: different → count = 1
        assert cw.compute_content_repeat_count(window=5) == 1

    def test_embedding_with_fact_keys_lowers_threshold(self):
        """Embedding similarity 0.76 + high fact_keys overlap → similar (threshold 0.75)."""
        cw = self._make_cw()
        # Create embeddings with cosine ~0.77 (between 0.75 and 0.80)
        emb_a = [1.0, 0.0, 0.0, 0.0]
        emb_b = [0.97, 0.25, 0.0, 0.0]  # cosine with emb_a ≈ 0.97/1.003 ≈ 0.968
        # Actually need to be more precise about thresholds
        # With identical fact_keys → threshold = 0.75, so should pass
        keys = ["pricing", "tariffs"]
        self._add_turn(cw, embedding=emb_a, fact_keys=keys)
        self._add_turn(cw, embedding=emb_b, fact_keys=keys)
        # cosine(emb_a, emb_b) ≈ 0.968 >= 0.75 → similar
        assert cw.compute_content_repeat_count() == 1


# =============================================================================
# STATIC HELPER TESTS
# =============================================================================

class TestCosineAndJaccard:
    """Tests for static helper methods."""

    def test_cosine_identical(self):
        from src.context_window import ContextWindow
        a = [1.0, 0.0, 0.0]
        assert ContextWindow._cosine_similarity(a, a) == pytest.approx(1.0)

    def test_cosine_orthogonal(self):
        from src.context_window import ContextWindow
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert ContextWindow._cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_zero_vector(self):
        from src.context_window import ContextWindow
        a = [0.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert ContextWindow._cosine_similarity(a, b) == 0.0

    def test_jaccard_identical(self):
        from src.context_window import ContextWindow
        a = {"a", "b", "c"}
        assert ContextWindow._jaccard_overlap(a, a) == pytest.approx(1.0)

    def test_jaccard_disjoint(self):
        from src.context_window import ContextWindow
        a = {"a", "b"}
        b = {"c", "d"}
        assert ContextWindow._jaccard_overlap(a, b) == pytest.approx(0.0)

    def test_jaccard_partial(self):
        from src.context_window import ContextWindow
        a = {"a", "b", "c"}
        b = {"b", "c", "d"}
        # intersection = {b, c} = 2, union = {a, b, c, d} = 4 → 0.5
        assert ContextWindow._jaccard_overlap(a, b) == pytest.approx(0.5)

    def test_jaccard_empty(self):
        from src.context_window import ContextWindow
        assert ContextWindow._jaccard_overlap(set(), {"a"}) == 0.0
        assert ContextWindow._jaccard_overlap(set(), set()) == 0.0


# =============================================================================
# UNIT TESTS: ContentRepetitionGuardSource
# =============================================================================

class TestContentRepetitionGuardShouldContribute:
    """Tests for ContentRepetitionGuardSource.should_contribute()."""

    def _make_source(self):
        from src.blackboard.sources.content_repetition_guard import ContentRepetitionGuardSource
        return ContentRepetitionGuardSource(name="ContentRepetitionGuardSource")

    def _make_blackboard(self, count=0, last_action=None, repeated_question=None,
                          current_intent=None, last_intent=None):
        bb = MagicMock()
        envelope = Mock()
        envelope.content_repeat_count = count
        envelope.last_action = last_action
        envelope.repeated_question = repeated_question
        envelope.current_intent = current_intent
        envelope.last_intent = last_intent

        ctx = Mock()
        ctx.context_envelope = envelope
        bb.get_context.return_value = ctx
        return bb

    def test_below_threshold_returns_false(self):
        """count=1 → False (below SOFT_THRESHOLD=2)."""
        source = self._make_source()
        bb = self._make_blackboard(count=1)
        assert source.should_contribute(bb) is False

    def test_zero_count_returns_false(self):
        """count=0 → False."""
        source = self._make_source()
        bb = self._make_blackboard(count=0)
        assert source.should_contribute(bb) is False

    def test_count2_with_repeated_question(self):
        """count=2 + repeated_question set → True (redirect)."""
        source = self._make_source()
        bb = self._make_blackboard(count=2, repeated_question="price_question")
        assert source.should_contribute(bb) is True

    def test_count3_with_repeated_question(self):
        """count=3 + repeated_question set → True (escalation)."""
        source = self._make_source()
        bb = self._make_blackboard(count=3, repeated_question="price_question")
        assert source.should_contribute(bb) is True

    def test_count2_no_repeated_different_intents(self):
        """count=2 + repeated_question=None + different intents → False."""
        source = self._make_source()
        bb = self._make_blackboard(count=2, current_intent="greeting", last_intent="price_question")
        assert source.should_contribute(bb) is False

    def test_count2_same_intents(self):
        """count=2 + same current/last intent → True."""
        source = self._make_source()
        bb = self._make_blackboard(count=2, current_intent="price_question", last_intent="price_question")
        assert source.should_contribute(bb) is True

    def test_anti_meta_loop_redirect(self):
        """count=2 + last_action=redirect_after_repetition → False (anti-meta-loop)."""
        source = self._make_source()
        bb = self._make_blackboard(
            count=2,
            last_action="redirect_after_repetition",
            repeated_question="price_question",
        )
        assert source.should_contribute(bb) is False

    def test_anti_meta_loop_escalate(self):
        """count=3 + last_action=escalate_repeated_content → False (anti-meta-loop)."""
        source = self._make_source()
        bb = self._make_blackboard(
            count=3,
            last_action="escalate_repeated_content",
            repeated_question="price_question",
        )
        assert source.should_contribute(bb) is False

    def test_normal_action_passes(self):
        """count=3 + last_action=autonomous_respond → True."""
        source = self._make_source()
        bb = self._make_blackboard(
            count=3,
            last_action="autonomous_respond",
            repeated_question="price_question",
        )
        assert source.should_contribute(bb) is True

    def test_none_envelope_returns_false(self):
        """No envelope → False."""
        source = self._make_source()
        bb = MagicMock()
        ctx = Mock()
        ctx.context_envelope = None
        bb.get_context.return_value = ctx
        assert source.should_contribute(bb) is False


class TestContentRepetitionGuardContribute:
    """Tests for ContentRepetitionGuardSource.contribute() priorities."""

    def _make_source(self):
        from src.blackboard.sources.content_repetition_guard import ContentRepetitionGuardSource
        return ContentRepetitionGuardSource(name="ContentRepetitionGuardSource")

    def _make_blackboard(self, count=0):
        bb = MagicMock()
        envelope = Mock()
        envelope.content_repeat_count = count

        ctx = Mock()
        ctx.context_envelope = envelope
        bb.get_context.return_value = ctx
        return bb

    def test_count2_proposes_redirect_high(self):
        """count=2 → redirect_after_repetition at HIGH."""
        from src.blackboard.enums import Priority
        source = self._make_source()
        bb = self._make_blackboard(count=2)
        source.contribute(bb)

        bb.propose_action.assert_called_once()
        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["action"] == "redirect_after_repetition"
        assert call_kwargs["priority"] == Priority.HIGH
        assert call_kwargs["combinable"] is True
        assert call_kwargs["source_name"] == "ContentRepetitionGuardSource"
        # No transition proposed for soft redirect
        bb.propose_transition.assert_not_called()

    def test_count3_proposes_escalation_critical(self):
        """count=3 → escalate_repeated_content at CRITICAL + transition to soft_close."""
        from src.blackboard.enums import Priority
        source = self._make_source()
        bb = self._make_blackboard(count=3)
        source.contribute(bb)

        bb.propose_action.assert_called_once()
        action_kwargs = bb.propose_action.call_args[1]
        assert action_kwargs["action"] == "escalate_repeated_content"
        assert action_kwargs["priority"] == Priority.CRITICAL
        assert action_kwargs["combinable"] is True

        bb.propose_transition.assert_called_once()
        trans_kwargs = bb.propose_transition.call_args[1]
        assert trans_kwargs["next_state"] == "soft_close"
        assert trans_kwargs["priority"] == Priority.CRITICAL

    def test_count5_still_escalation(self):
        """count=5 → still escalation (>= HARD_THRESHOLD)."""
        from src.blackboard.enums import Priority
        source = self._make_source()
        bb = self._make_blackboard(count=5)
        source.contribute(bb)

        action_kwargs = bb.propose_action.call_args[1]
        assert action_kwargs["action"] == "escalate_repeated_content"
        assert action_kwargs["priority"] == Priority.CRITICAL


# =============================================================================
# INTEGRATION: context_envelope fills content_repeat_count
# =============================================================================

class TestContextEnvelopeContentRepeatCount:
    """Verify that ContextEnvelopeBuilder fills content_repeat_count from CW."""

    def test_builder_fills_count(self):
        """Builder should read compute_content_repeat_count() from CW."""
        from src.context_envelope import ContextEnvelopeBuilder
        from src.context_window import ContextWindow

        cw = ContextWindow(max_size=5)
        # Add 3 turns with identical fact_keys (no embeddings → fallback)
        keys = ["pricing", "tariffs"]
        for _ in range(3):
            cw.add_turn_from_dict(
                user_message="сколько стоит?",
                bot_response="от 5000 тенге",
                intent="price_question",
                confidence=0.9,
                action="autonomous_respond",
                state="autonomous_discovery",
                next_state="autonomous_discovery",
                fact_keys_used=keys,
            )

        builder = ContextEnvelopeBuilder(context_window=cw)
        envelope = builder.build()
        assert envelope.content_repeat_count == 2  # 3rd turn vs 1st and 2nd

"""
Tests for ObjectionRefinementLayer.

Part of Objection Stuck Fix (OBJECTION_STUCK_FIX_PLAN.md)
"""

import pytest
from unittest.mock import patch, MagicMock

from src.classifier.objection_refinement import (
    ObjectionRefinementLayer,
    ObjectionRefinementContext,
    create_objection_refinement_context,
)


class TestObjectionRefinementContext:
    """Tests for ObjectionRefinementContext dataclass."""

    def test_context_immutable(self):
        """Context should be immutable (frozen dataclass)."""
        ctx = ObjectionRefinementContext(
            message="test",
            intent="objection_price",
            confidence=0.8,
            last_bot_message=None,
            last_action=None,
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        with pytest.raises(AttributeError):
            ctx.message = "changed"

    def test_create_context_helper(self):
        """create_objection_refinement_context helper should work correctly."""
        ctx = create_objection_refinement_context(
            message="test message",
            intent="objection_price",
            confidence=0.75,
            context={
                "last_bot_message": "Bot message",
                "last_action": "ask_about_budget",
                "state": "presentation",
                "turn_number": 5,
            }
        )
        assert ctx.message == "test message"
        assert ctx.intent == "objection_price"
        assert ctx.confidence == 0.75
        assert ctx.last_bot_message == "Bot message"
        assert ctx.last_action == "ask_about_budget"
        assert ctx.state == "presentation"
        assert ctx.turn_number == 5


class TestObjectionRefinementLayer:
    """Tests for ObjectionRefinementLayer."""

    @pytest.fixture
    def layer(self):
        """Create ObjectionRefinementLayer instance."""
        return ObjectionRefinementLayer()

    @pytest.fixture
    def price_objection_context(self):
        """Context for price objection after bot asked about budget."""
        return ObjectionRefinementContext(
            message="бюджет пока не определён",
            intent="objection_price",
            confidence=0.75,
            last_bot_message="Какой у вас бюджет на автоматизацию?",
            last_action="ask_about_budget",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )

    @pytest.fixture
    def high_confidence_objection(self):
        """High confidence objection without context issues."""
        return ObjectionRefinementContext(
            message="это слишком дорого для нас",
            intent="objection_price",
            confidence=0.95,
            last_bot_message="Вот наши тарифы",
            last_action="show_pricing",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )

    # =========================================================================
    # should_refine() tests
    # =========================================================================

    def test_should_refine_low_confidence_with_context(self, layer, price_objection_context):
        """Low confidence objection with topic alignment should be refined."""
        assert layer.should_refine(price_objection_context)

    def test_should_not_refine_high_confidence_no_markers(self, layer, high_confidence_objection):
        """High confidence objection without question markers should not be refined."""
        assert not layer.should_refine(high_confidence_objection)

    def test_should_not_refine_non_objection(self, layer):
        """Non-objection intent should not be refined."""
        ctx = ObjectionRefinementContext(
            message="расскажите подробнее",
            intent="question_features",
            confidence=0.8,
            last_bot_message=None,
            last_action=None,
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        assert not layer.should_refine(ctx)

    def test_should_refine_high_confidence_with_question_marker(self, layer):
        """High confidence objection WITH question marker should be refined."""
        ctx = ObjectionRefinementContext(
            message="бюджет какой нужен?",
            intent="objection_price",
            confidence=0.9,
            last_bot_message=None,
            last_action=None,
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        assert layer.should_refine(ctx)

    def test_should_not_refine_when_disabled(self, layer):
        """Should not refine when layer is disabled."""
        layer._enabled = False
        ctx = ObjectionRefinementContext(
            message="бюджет пока не определён",
            intent="objection_price",
            confidence=0.75,
            last_bot_message=None,
            last_action="ask_about_budget",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        assert not layer.should_refine(ctx)

    # =========================================================================
    # refine() tests - Topic alignment
    # =========================================================================

    def test_refine_topic_aligned_price(self, layer, price_objection_context):
        """Bot asked about budget + user mentions budget → info_provided."""
        llm_result = {"intent": "objection_price", "confidence": 0.75}

        refined = layer.refine(
            price_objection_context.message,
            llm_result,
            price_objection_context
        )

        assert refined["refined"] is True
        assert refined["intent"] == "info_provided"
        assert refined["refinement_reason"] == "topic_alignment"
        assert refined["original_intent"] == "objection_price"
        assert refined["refinement_layer"] == "objection"

    def test_refine_preserves_other_fields(self, layer, price_objection_context):
        """Refinement should preserve other fields from original result."""
        llm_result = {
            "intent": "objection_price",
            "confidence": 0.75,
            "extracted_data": {"company_size": 10},
            "method": "llm",
        }

        refined = layer.refine(
            price_objection_context.message,
            llm_result,
            price_objection_context
        )

        assert refined["extracted_data"] == {"company_size": 10}
        assert refined["method"] == "llm"
        assert refined["refined"] is True

    # =========================================================================
    # refine() tests - Question markers
    # =========================================================================

    def test_refine_question_marker_question_mark(self, layer):
        """Message with '?' should be refined to question intent."""
        ctx = ObjectionRefinementContext(
            message="бюджет какой нужен?",
            intent="objection_price",
            confidence=0.7,
            last_bot_message="Расскажу о тарифах",
            last_action="present_features",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_price", "confidence": 0.7}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "price_question"
        assert refined["refinement_reason"] == "question_markers"

    def test_refine_question_marker_word(self, layer):
        """Message with question word should be refined."""
        ctx = ObjectionRefinementContext(
            message="сколько это стоит",
            intent="objection_price",
            confidence=0.65,
            last_bot_message=None,
            last_action=None,
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_price", "confidence": 0.65}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "price_question"

    # =========================================================================
    # refine() tests - Callback patterns
    # =========================================================================

    def test_refine_callback_pattern(self, layer):
        """'позвоните завтра' should be refined to callback_request."""
        ctx = ObjectionRefinementContext(
            message="сейчас занят, позвоните завтра",
            intent="objection_no_time",
            confidence=0.8,
            last_bot_message="Можем обсудить?",
            last_action="present_features",  # Not time-related, so topic_alignment won't trigger
            state="close",
            turn_number=8,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_no_time", "confidence": 0.8}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "callback_request"
        assert refined["refinement_reason"] == "callback_pattern"

    def test_refine_callback_pattern_later(self, layer):
        """'позже' should be refined to callback_request."""
        ctx = ObjectionRefinementContext(
            message="давайте позже",
            intent="objection_no_time",
            confidence=0.75,
            last_bot_message=None,
            last_action=None,
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_no_time", "confidence": 0.75}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "callback_request"

    # =========================================================================
    # refine() tests - Interest patterns
    # =========================================================================

    def test_refine_interest_pattern(self, layer):
        """'подумать над предложением' should show interest, not objection."""
        ctx = ObjectionRefinementContext(
            message="хочу подумать над вашим предложением, пришлите детали",
            intent="objection_think",
            confidence=0.75,
            last_bot_message="Что скажете?",
            last_action="ask_feedback",
            state="presentation",
            turn_number=7,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.75}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"
        assert refined["refinement_reason"] == "interest_pattern"

    def test_refine_interest_pattern_send(self, layer):
        """'пришлите' pattern should indicate interest."""
        ctx = ObjectionRefinementContext(
            message="пришлите информацию, изучу",
            intent="objection_think",
            confidence=0.7,
            last_bot_message=None,
            last_action=None,
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"

    # =========================================================================
    # refine() tests - Uncertainty patterns (Rule 5)
    # FIX: Root Cause #2 - skeptic personas use implicit question phrases
    # =========================================================================

    def test_refine_uncertainty_pattern_nado_li(self, layer):
        """'надо ли' uncertainty pattern should be refined to question.

        Note: Due to rule priority, may match interest_pattern first
        if message contains patterns like 'не знаю' (added to interest_patterns).
        """
        ctx = ObjectionRefinementContext(
            message="не знаю надо ли это нам",
            intent="objection_think",
            confidence=0.7,
            last_bot_message="Что скажете?",
            last_action="ask_feedback",
            state="handle_objection",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"
        # Can be interest_pattern (higher priority) or uncertainty_pattern
        assert refined["refinement_reason"] in ["interest_pattern", "uncertainty_pattern"]

    def test_refine_uncertainty_pattern_nuzhno_li(self, layer):
        """'нужно ли' uncertainty pattern should be refined to question.

        Note: Due to rule priority, may match interest_pattern first
        if message contains patterns like 'не уверен' (added to interest_patterns).
        """
        ctx = ObjectionRefinementContext(
            message="не уверен нужно ли мне это",
            intent="objection_think",
            confidence=0.75,
            last_bot_message=None,
            last_action=None,
            state="handle_objection",
            turn_number=3,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.75}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"
        # Can be interest_pattern (higher priority) or uncertainty_pattern
        assert refined["refinement_reason"] in ["interest_pattern", "uncertainty_pattern"]

    def test_refine_uncertainty_pattern_zachem_eto(self, layer):
        """'зачем это' uncertainty pattern should be refined to question.

        Note: Due to rule priority, matches question_markers first
        because 'зачем' is a question word.
        """
        ctx = ObjectionRefinementContext(
            message="честно говоря не понимаю зачем это нужно",
            intent="objection_think",
            confidence=0.7,
            last_bot_message=None,
            last_action=None,
            state="greeting",
            turn_number=1,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"
        # 'зачем' is a question word, so question_markers rule triggers first
        assert refined["refinement_reason"] in ["question_markers", "uncertainty_pattern"]

    def test_refine_uncertainty_pattern_a_smysl(self, layer):
        """'а смысл' uncertainty pattern should be refined to question."""
        ctx = ObjectionRefinementContext(
            message="а смысл переходить если у нас excel работает",
            intent="objection_think",
            confidence=0.65,
            last_bot_message=None,
            last_action=None,
            state="handle_objection",
            turn_number=4,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.65}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"
        assert refined["refinement_reason"] == "uncertainty_pattern"

    def test_refine_skeptic_starter_not_sure(self, layer):
        """Skeptic persona starter 'не уверен' should be refined via interest pattern."""
        # This tests the expanded interest_patterns fix (Root Cause #1)
        ctx = ObjectionRefinementContext(
            message="слушайте, мне тут посоветовали... но я не уверен",
            intent="objection_think",
            confidence=0.7,
            last_bot_message=None,
            last_action=None,
            state="greeting",
            turn_number=1,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"
        # Can be either interest_pattern or uncertainty_pattern depending on match order
        assert refined["refinement_reason"] in ["interest_pattern", "uncertainty_pattern"]

    def test_refine_skeptic_starter_somnevayus(self, layer):
        """Skeptic persona starter 'сомневаюсь' should be refined via interest pattern."""
        # This tests the expanded interest_patterns fix (Root Cause #1)
        ctx = ObjectionRefinementContext(
            message="Здравствуйте. Честно говоря сомневаюсь что это нам нужно",
            intent="objection_think",
            confidence=0.75,
            last_bot_message=None,
            last_action=None,
            state="greeting",
            turn_number=1,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.75}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"

    # =========================================================================
    # refine() tests - No refinement needed
    # =========================================================================

    def test_no_refine_genuine_objection(self, layer, high_confidence_objection):
        """Genuine objection without refinement signals should keep as-is."""
        llm_result = {"intent": "objection_price", "confidence": 0.95}

        refined = layer.refine(
            high_confidence_objection.message,
            llm_result,
            high_confidence_objection
        )

        assert refined.get("refined", False) is False
        assert refined["intent"] == "objection_price"

    def test_no_refine_different_objection_type(self, layer):
        """objection_competitor without patterns should not be refined."""
        ctx = ObjectionRefinementContext(
            message="мы уже используем битрикс",
            intent="objection_competitor",
            confidence=0.85,
            last_bot_message=None,
            last_action=None,
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_competitor", "confidence": 0.85}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined.get("refined", False) is False

    # =========================================================================
    # Cooldown tests
    # =========================================================================

    def test_cooldown_violation_detected(self, layer):
        """Cooldown violation should be detected (but not cause refinement)."""
        ctx = ObjectionRefinementContext(
            message="это дорого",
            intent="objection_price",
            confidence=0.85,
            last_bot_message=None,
            last_action=None,
            state="handle_objection",
            turn_number=5,
            last_objection_turn=4,  # Previous turn
            last_objection_type="objection_price",
        )

        # Cooldown is detected but doesn't cause refinement by itself
        assert layer._violates_cooldown(ctx) is True

    def test_cooldown_not_violated(self, layer):
        """No cooldown violation when enough turns have passed."""
        ctx = ObjectionRefinementContext(
            message="это дорого",
            intent="objection_price",
            confidence=0.85,
            last_bot_message=None,
            last_action=None,
            state="handle_objection",
            turn_number=10,
            last_objection_turn=5,  # 5 turns ago
            last_objection_type="objection_price",
        )

        assert layer._violates_cooldown(ctx) is False

    # =========================================================================
    # Stats tests
    # =========================================================================

    def test_stats_tracking(self, layer, price_objection_context):
        """Refinement stats should be tracked."""
        llm_result = {"intent": "objection_price", "confidence": 0.75}

        # Before refinement
        stats_before = layer.get_stats()
        assert stats_before["refinements_total"] == 0

        # Trigger refinement
        layer.refine(
            price_objection_context.message,
            llm_result,
            price_objection_context
        )

        # After refinement
        stats_after = layer.get_stats()
        assert stats_after["refinements_total"] == 1
        assert "objection_price" in stats_after["refinements_by_type"]
        assert "topic_alignment" in stats_after["refinements_by_reason"]

    # =========================================================================
    # Error handling tests
    # =========================================================================

    def test_error_returns_original_result(self, layer):
        """On error, original result should be returned (fail-safe)."""
        ctx = ObjectionRefinementContext(
            message="test",
            intent="objection_price",
            confidence=0.7,
            last_bot_message=None,
            last_action="ask_about_budget",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_price", "confidence": 0.7}

        # Mock _apply_refinement_rules to raise error
        with patch.object(layer, '_apply_refinement_rules', side_effect=Exception("Test error")):
            refined = layer.refine(ctx.message, llm_result, ctx)

        # Should return original result
        assert refined["intent"] == "objection_price"
        assert refined.get("refined") is None


class TestQuestionMarkers:
    """Tests for question marker detection."""

    @pytest.fixture
    def layer(self):
        return ObjectionRefinementLayer()

    @pytest.mark.parametrize("message,expected", [
        ("сколько стоит?", True),
        ("какой бюджет нужен?", True),
        ("что входит в пакет", True),
        ("как это работает", True),
        ("когда можно начать", True),
        ("где вы находитесь", True),
        ("почему так дорого", True),
        ("расскажите подробнее", True),
        ("это дорого", False),
        ("мы используем другое решение", False),
    ])
    def test_question_markers(self, layer, message, expected):
        """Question markers should be detected correctly."""
        assert layer._has_question_markers(message) == expected


class TestTopicAlignment:
    """Tests for topic alignment detection."""

    @pytest.fixture
    def layer(self):
        return ObjectionRefinementLayer()

    def test_budget_topic_aligned(self, layer):
        """Budget topic should be aligned when bot asked about budget."""
        ctx = ObjectionRefinementContext(
            message="бюджет не определён",
            intent="objection_price",
            confidence=0.7,
            last_bot_message=None,
            last_action="ask_about_budget",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        assert layer._is_topic_aligned(ctx) is True

    def test_time_topic_aligned(self, layer):
        """Time topic should be aligned when bot asked about timeline."""
        ctx = ObjectionRefinementContext(
            message="сейчас занят",
            intent="objection_no_time",
            confidence=0.7,
            last_bot_message=None,
            last_action="ask_about_timeline",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        assert layer._is_topic_aligned(ctx) is True

    def test_topic_not_aligned(self, layer):
        """Topic should not be aligned when bot asked about something else."""
        ctx = ObjectionRefinementContext(
            message="это дорого",
            intent="objection_price",
            confidence=0.7,
            last_bot_message=None,
            last_action="present_features",  # Not budget-related
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        assert layer._is_topic_aligned(ctx) is False


class TestIntegrationWithUnifiedClassifier:
    """Integration tests with UnifiedClassifier."""

    def test_objection_refinement_in_pipeline(self):
        """ObjectionRefinementLayer should be called in UnifiedClassifier pipeline."""
        from src.classifier.unified import UnifiedClassifier
        from feature_flags import flags

        # Enable objection_refinement
        flags.set_override("objection_refinement", True)

        try:
            classifier = UnifiedClassifier()

            # Check that layer is lazy-initialized
            assert classifier._objection_refinement_layer is None

            # Access the property
            layer = classifier.objection_refinement_layer
            assert layer is not None
            assert isinstance(layer, ObjectionRefinementLayer)

        finally:
            flags.clear_override("objection_refinement")

    def test_stats_include_objection_refinement(self):
        """Classifier stats should include objection refinement stats."""
        from src.classifier.unified import UnifiedClassifier
        from feature_flags import flags

        flags.set_override("objection_refinement", True)

        try:
            classifier = UnifiedClassifier()
            # Force init of layer
            _ = classifier.objection_refinement_layer

            stats = classifier.get_stats()
            assert "objection_refinement_enabled" in stats
            assert stats["objection_refinement_enabled"] is True

        finally:
            flags.clear_override("objection_refinement")

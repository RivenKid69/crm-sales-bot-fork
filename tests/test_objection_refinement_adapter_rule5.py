"""
Tests for ObjectionRefinementLayerAdapter Rule 5 (Uncertainty Patterns).

This test file specifically validates the fix for the bug where:
- ObjectionRefinementLayerAdapter was MISSING Rule 5 (uncertainty patterns)
- This caused ObjectionReturnSource to never trigger for skeptic personas
- Result: 37 dialogs with phases_reached: [] in e2e simulation

Root Cause Chain:
1. refinement_pipeline=True (default) → uses ObjectionRefinementLayerAdapter
2. Adapter was missing Rule 5 (uncertainty_patterns)
3. Skeptic says "не уверен нужно ли" → LLM classifies as objection_think
4. Without Rule 5, objection_think was NOT refined to question_features
5. ObjectionReturnSource checks: objection_think NOT in return_intents → returns False
6. No return to phase → greeting → handle_objection → soft_close (0% coverage)

Fix Applied:
- Added self._uncertainty_regex initialization in _init_patterns()
- Added Rule 5 in _do_refine() method
- Added _get_uncertainty_alternative() method

These tests verify the fix works correctly.
"""

import pytest
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
import importlib

from src.classifier.refinement_pipeline import (
    RefinementContext,
    RefinementResult,
    RefinementDecision,
    RefinementLayerRegistry,
    reset_refinement_pipeline,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_registry():
    """Reset registry before and after each test to ensure clean state."""
    reset_refinement_pipeline()
    yield
    reset_refinement_pipeline()


@pytest.fixture
def adapter():
    """Create fresh ObjectionRefinementLayerAdapter instance."""
    # Import directly without reload to avoid registry conflicts
    from src.classifier.refinement_layers import ObjectionRefinementLayerAdapter
    return ObjectionRefinementLayerAdapter()


@pytest.fixture
def skeptic_uncertainty_messages():
    """
    Skeptic persona uncertainty messages that should trigger Rule 5.

    These are PURE uncertainty patterns from constants.yaml that do NOT
    contain interest_patterns (Rule 4) or question_markers (Rule 2).

    IMPORTANT: Messages containing "не уверен", "не знаю", "сомневаюсь"
    will trigger Rule 4 (interest_pattern), not Rule 5.

    Messages containing "какой", "зачем", "?" will trigger Rule 2 (question_markers).

    Actual uncertainty_patterns from constants.yaml:
    - "надо ли"
    - "нужно ли"
    - "стоит ли"
    - "а смысл"
    - "толк какой"
    - "зачем это"
    - "нужно это"
    - "надо это"
    - "в чём смысл"
    - "какой смысл"
    - "есть ли смысл"

    NOTE: Some patterns like "зачем это", "какой смысл", "толк какой"
    contain question words and will trigger Rule 2 first.
    """
    return [
        # Pure "нужно ли" pattern (no interest patterns, no question markers)
        "нужно ли это внедрять",
        "нужно ли нам это",
        # Pure "надо ли" pattern
        "надо ли это вообще",
        "надо ли внедрять это решение",
        # Pure "стоит ли" pattern
        "стоит ли это внедрять",
        "стоит ли вообще это делать",
        # "а смысл" pattern (not a question word)
        "а смысл в этом есть",
        "а смысл от этого",
        # "нужно это" / "надо это" patterns
        "нужно это нам вообще",
        "надо это всё внедрять",
        # "в чём смысл" - contains question word, but test if works
        # "есть ли смысл"
        "есть ли смысл вообще",
    ]


@pytest.fixture
def non_uncertainty_objection_messages():
    """Messages that should NOT trigger Rule 5 but other rules or stay as objection."""
    return [
        # Clear objections (not uncertainty)
        "это слишком дорого для нас",
        "у нас нет на это времени",
        "мы уже используем другое решение",
        # Interest patterns (Rule 4, not Rule 5)
        "нужно подумать над предложением",
        "дайте время обдумать",
    ]


# =============================================================================
# TEST: Rule 5 Triggers Correctly
# =============================================================================

class TestRule5UncertaintyPatterns:
    """
    Tests that Rule 5 (uncertainty patterns) correctly refines
    objection_think → question_features for skeptic persona messages.
    """

    def test_rule5_refines_uncertainty_pattern_nuzhno_li(self, adapter):
        """
        Test Rule 5 refines 'нужно ли это внедрять' from objection_think to question_features.

        This is the PRIMARY test case for the bug fix:
        - Message contains "нужно ли" (uncertainty_pattern in Rule 5)
        - Does NOT contain "не уверен" (which is interest_pattern in Rule 4)
        - Rule 5 should refine to question_features (implicit question about value)
        - ObjectionReturnSource should then trigger return to phase

        Note: "не уверен нужно ли" contains BOTH:
        - "не уверен" → interest_pattern (Rule 4)
        - "нужно ли" → uncertainty_pattern (Rule 5)
        Rule 4 has priority, so it triggers first. That's why we test pure uncertainty here.
        """
        ctx = RefinementContext(
            message="нужно ли это внедрять вообще",
            state="handle_objection",
            phase=None,
            last_action="handle_objection",
            intent="objection_think",
            confidence=0.7,
        )

        result = adapter.refine(
            "нужно ли это внедрять вообще",
            {"intent": "objection_think", "confidence": 0.7},
            ctx
        )

        # CRITICAL: This MUST be refined to question_features
        assert result.refined is True, (
            "Rule 5 MUST refine uncertainty pattern 'нужно ли'"
        )
        assert result.intent == "question_features", (
            f"Expected question_features, got {result.intent}"
        )
        assert result.original_intent == "objection_think"
        assert result.refinement_reason == "uncertainty_pattern"

    def test_rule5_refines_stoit_li(self, adapter):
        """Test Rule 5 refines 'стоит ли' patterns."""
        ctx = RefinementContext(
            message="стоит ли это внедрять в нашей компании",
            state="handle_objection",
            intent="objection_think",
            confidence=0.65,
        )

        result = adapter.refine(
            ctx.message,
            {"intent": "objection_think", "confidence": 0.65},
            ctx
        )

        assert result.refined is True
        assert result.intent == "question_features"
        assert result.refinement_reason == "uncertainty_pattern"

    def test_rule5_refines_a_smysl(self, adapter):
        """
        Test Rule 5 refines 'а смысл' patterns.

        Note: "а смысл" is an uncertainty pattern (Rule 5),
        while "какой смысл" contains question word "какой" (Rule 2).
        """
        ctx = RefinementContext(
            message="а смысл в этом есть вообще",
            state="handle_objection",
            intent="objection_think",
            confidence=0.6,
        )

        result = adapter.refine(
            ctx.message,
            {"intent": "objection_think", "confidence": 0.6},
            ctx
        )

        assert result.refined is True
        assert result.intent == "question_features"
        assert result.refinement_reason == "uncertainty_pattern"

    def test_rule5_refines_nado_li(self, adapter):
        """Test Rule 5 refines 'надо ли' patterns."""
        ctx = RefinementContext(
            message="надо ли это внедрять вообще",
            state="handle_objection",
            intent="objection_think",
            confidence=0.65,
        )

        result = adapter.refine(
            ctx.message,
            {"intent": "objection_think", "confidence": 0.65},
            ctx
        )

        assert result.refined is True
        assert result.intent == "question_features"
        assert result.refinement_reason == "uncertainty_pattern"

    def test_rule5_all_uncertainty_patterns(self, adapter, skeptic_uncertainty_messages):
        """
        Test ALL uncertainty patterns are correctly refined.

        This is a comprehensive test to ensure no patterns are missed.
        """
        failed_patterns = []

        for message in skeptic_uncertainty_messages:
            ctx = RefinementContext(
                message=message,
                state="handle_objection",
                intent="objection_think",
                confidence=0.65,
            )

            result = adapter.refine(
                message,
                {"intent": "objection_think", "confidence": 0.65},
                ctx
            )

            if not result.refined or result.intent != "question_features":
                failed_patterns.append({
                    "message": message,
                    "refined": result.refined,
                    "intent": result.intent,
                    "reason": result.refinement_reason,
                })

        assert not failed_patterns, (
            f"Rule 5 failed for {len(failed_patterns)} patterns:\n"
            + "\n".join(f"  - '{p['message']}' → {p['intent']} (refined={p['refined']})"
                        for p in failed_patterns)
        )


# =============================================================================
# TEST: Rule 5 Does NOT Trigger When It Shouldn't
# =============================================================================

class TestRule5NotTriggered:
    """Tests that Rule 5 does NOT incorrectly refine messages."""

    def test_rule5_does_not_refine_non_objection_think(self, adapter):
        """Rule 5 should only apply to objection_think intent."""
        ctx = RefinementContext(
            message="не уверен нужно ли",  # Has uncertainty pattern
            state="handle_objection",
            intent="objection_price",  # NOT objection_think
            confidence=0.7,
        )

        result = adapter.refine(
            ctx.message,
            {"intent": "objection_price", "confidence": 0.7},
            ctx
        )

        # Should NOT be refined by Rule 5 (wrong intent)
        if result.refined:
            assert result.refinement_reason != "uncertainty_pattern", (
                "Rule 5 should only apply to objection_think, not objection_price"
            )

    def test_rule5_does_not_refine_clear_objection(self, adapter):
        """Rule 5 should not refine clear objections without uncertainty patterns."""
        ctx = RefinementContext(
            message="это слишком дорого для нас, мы не можем себе это позволить",
            state="handle_objection",
            intent="objection_think",  # Misclassified, but no uncertainty pattern
            confidence=0.7,
        )

        result = adapter.refine(
            ctx.message,
            {"intent": "objection_think", "confidence": 0.7},
            ctx
        )

        # Should NOT be refined by Rule 5 (no uncertainty pattern)
        if result.refined:
            assert result.refinement_reason != "uncertainty_pattern"

    def test_rule5_does_not_override_rule4_interest_patterns(self, adapter):
        """
        Rule 4 (interest patterns) should take precedence over Rule 5.

        This tests that the rule ordering is correct:
        Rule 4 checks interest patterns BEFORE Rule 5 checks uncertainty.
        """
        # Message that matches BOTH interest and potentially uncertainty
        ctx = RefinementContext(
            message="нужно подумать над предложением",  # Interest pattern
            state="handle_objection",
            intent="objection_think",
            confidence=0.65,
        )

        result = adapter.refine(
            ctx.message,
            {"intent": "objection_think", "confidence": 0.65},
            ctx
        )

        # If refined, should be by Rule 4 (interest), not Rule 5 (uncertainty)
        if result.refined:
            assert result.refinement_reason == "interest_pattern", (
                f"Expected interest_pattern (Rule 4), got {result.refinement_reason}"
            )


# =============================================================================
# TEST: Integration with ObjectionReturnSource
# =============================================================================

class TestRule5ObjectionReturnSourceIntegration:
    """
    Tests that Rule 5 refinement enables ObjectionReturnSource to trigger.

    This validates the FULL fix chain:
    1. Skeptic message → objection_think
    2. Rule 5 → question_features
    3. ObjectionReturnSource sees question_features in return_intents → triggers
    """

    def test_refined_intent_is_in_return_intents(self, adapter):
        """
        Test that question_features (Rule 5 output) is in ObjectionReturnSource's return_intents.
        """
        from src.blackboard.sources.objection_return import ObjectionReturnSource

        source = ObjectionReturnSource()

        # Verify question_features is in return_intents
        assert "question_features" in source.return_intents, (
            "question_features MUST be in ObjectionReturnSource.return_intents "
            "for Rule 5 fix to work"
        )

    def test_objection_think_not_in_return_intents(self, adapter):
        """
        Test that objection_think is NOT in return_intents (this is why fix was needed).
        """
        from src.blackboard.sources.objection_return import ObjectionReturnSource

        source = ObjectionReturnSource()

        # Verify objection_think is NOT in return_intents
        assert "objection_think" not in source.return_intents, (
            "objection_think should NOT be in return_intents - "
            "that's why Rule 5 refinement is necessary"
        )

    def test_full_chain_skeptic_scenario(self, adapter):
        """
        Full end-to-end test of the skeptic scenario.

        Scenario:
        1. Skeptic in handle_objection says "нужно ли это внедрять"
        2. LLM classifies as objection_think
        3. RefinementPipeline (with Rule 5) refines to question_features
        4. ObjectionReturnSource checks: question_features IN return_intents ✓
        5. Return to phase is proposed

        Note: We use "нужно ли это внедрять" (pure uncertainty pattern)
        instead of "не уверен нужно ли" (which also has interest pattern).
        Both lead to question_features, but via different rules.
        """
        from src.blackboard.sources.objection_return import ObjectionReturnSource

        # Step 1-2: Skeptic message classified as objection_think
        message = "нужно ли это внедрять"  # Pure uncertainty pattern (Rule 5)
        original_intent = "objection_think"

        # Step 3: Rule 5 refines to question_features
        ctx = RefinementContext(
            message=message,
            state="handle_objection",
            intent=original_intent,
            confidence=0.65,
        )

        result = adapter.refine(
            message,
            {"intent": original_intent, "confidence": 0.65},
            ctx
        )

        refined_intent = result.intent

        assert result.refined is True, "Rule 5 must refine this message"
        assert refined_intent == "question_features", (
            f"Rule 5 must refine to question_features, got {refined_intent}"
        )

        # Step 4-5: Verify ObjectionReturnSource would trigger
        source = ObjectionReturnSource()

        # Create mock blackboard
        mock_blackboard = Mock()
        mock_blackboard.current_state = "handle_objection"
        mock_blackboard.current_intent = refined_intent  # question_features
        mock_blackboard._state_machine = Mock()
        mock_blackboard._state_machine._state_before_objection = "bant_budget"

        # Check if source would contribute
        should_contribute = source.should_contribute(mock_blackboard)

        assert should_contribute is True, (
            f"ObjectionReturnSource MUST trigger with refined intent '{refined_intent}'. "
            f"return_intents contains: {source.return_intents}"
        )


# =============================================================================
# TEST: Adapter Has Required Components
# =============================================================================

class TestAdapterComponents:
    """Tests that adapter has all required components for Rule 5."""

    def test_adapter_has_uncertainty_regex(self, adapter):
        """Test adapter has _uncertainty_regex attribute."""
        assert hasattr(adapter, '_uncertainty_regex'), (
            "ObjectionRefinementLayerAdapter must have _uncertainty_regex attribute"
        )
        assert adapter._uncertainty_regex is not None, (
            "_uncertainty_regex must be initialized"
        )

    def test_adapter_has_get_uncertainty_alternative_method(self, adapter):
        """Test adapter has _get_uncertainty_alternative method."""
        assert hasattr(adapter, '_get_uncertainty_alternative'), (
            "ObjectionRefinementLayerAdapter must have _get_uncertainty_alternative method"
        )
        assert callable(adapter._get_uncertainty_alternative), (
            "_get_uncertainty_alternative must be callable"
        )

    def test_uncertainty_regex_matches_patterns(self, adapter, skeptic_uncertainty_messages):
        """Test _uncertainty_regex actually matches the expected patterns."""
        failed_matches = []

        for message in skeptic_uncertainty_messages:
            if not adapter._uncertainty_regex.search(message):
                failed_matches.append(message)

        assert not failed_matches, (
            f"_uncertainty_regex failed to match {len(failed_matches)} patterns:\n"
            + "\n".join(f"  - '{m}'" for m in failed_matches)
        )

    def test_get_uncertainty_alternative_returns_question_features(self, adapter):
        """Test _get_uncertainty_alternative returns correct intent."""
        ctx = RefinementContext(
            message="test",
            intent="objection_think",
            confidence=0.5,
        )

        alternative = adapter._get_uncertainty_alternative(ctx)

        assert alternative == "question_features", (
            f"Expected question_features, got {alternative}"
        )


# =============================================================================
# TEST: Rule Priority and Ordering
# =============================================================================

class TestRulePriority:
    """
    Tests that Rule 5 has correct priority relative to other rules.

    Rule order in _do_refine():
    1. Topic alignment
    2. Question markers (?)
    3. Callback patterns (objection_no_time)
    4. Interest patterns (objection_think)
    5. Uncertainty patterns (objection_think) ← NEW
    """

    def test_rule2_question_markers_takes_precedence_over_rule5(self, adapter):
        """
        Question markers (Rule 2) should take precedence over uncertainty (Rule 5).

        Message with both "?" and uncertainty pattern should be refined by Rule 2.
        """
        ctx = RefinementContext(
            message="не уверен, нужно ли это?",  # Has both "?" and uncertainty
            state="handle_objection",
            intent="objection_think",
            confidence=0.65,
        )

        result = adapter.refine(
            ctx.message,
            {"intent": "objection_think", "confidence": 0.65},
            ctx
        )

        if result.refined:
            # Rule 2 (question_markers) should win
            assert result.refinement_reason == "question_markers", (
                f"Expected question_markers (Rule 2), got {result.refinement_reason}"
            )

    def test_rule4_interest_takes_precedence_over_rule5(self, adapter):
        """
        Interest patterns (Rule 4) should take precedence over uncertainty (Rule 5).
        """
        # Get interest patterns from config to find overlapping message
        interest_patterns = adapter._config.get("interest_patterns", [])

        if interest_patterns:
            # Use first interest pattern that might overlap
            ctx = RefinementContext(
                message=interest_patterns[0],  # Use actual interest pattern
                state="handle_objection",
                intent="objection_think",
                confidence=0.65,
            )

            result = adapter.refine(
                ctx.message,
                {"intent": "objection_think", "confidence": 0.65},
                ctx
            )

            if result.refined:
                assert result.refinement_reason == "interest_pattern", (
                    f"Expected interest_pattern (Rule 4), got {result.refinement_reason}"
                )


# =============================================================================
# TEST: Regression - Original ObjectionRefinementLayer Parity
# =============================================================================

class TestParityWithOriginalLayer:
    """
    Tests that ObjectionRefinementLayerAdapter has parity with ObjectionRefinementLayer.

    The adapter should produce the same results as the original layer
    for all uncertainty patterns.
    """

    def test_adapter_matches_original_for_uncertainty(self, adapter):
        """
        Test adapter produces same results as ObjectionRefinementLayer for uncertainty.
        """
        from src.classifier.objection_refinement import (
            ObjectionRefinementLayer,
            ObjectionRefinementContext,
        )

        original_layer = ObjectionRefinementLayer()

        # Use actual patterns from constants.yaml
        test_messages = [
            "не уверен нужно ли",
            "стоит ли это внедрять",
            "зачем это нужно",
            "какой смысл в этом",
            "а смысл какой",
        ]

        for message in test_messages:
            # Original layer context
            original_ctx = ObjectionRefinementContext(
                message=message,
                intent="objection_think",
                confidence=0.65,
                last_bot_message=None,
                last_action=None,
                state="handle_objection",
                turn_number=5,
                last_objection_turn=None,
                last_objection_type=None,
            )

            # Adapter context
            adapter_ctx = RefinementContext(
                message=message,
                state="handle_objection",
                intent="objection_think",
                confidence=0.65,
            )

            # Get original result
            original_result = original_layer.refine(
                message,
                {"intent": "objection_think", "confidence": 0.65},
                original_ctx
            )
            original_refined = original_result.get("refined", False)
            original_intent = original_result.get("intent", "objection_think")

            # Get adapter result
            adapter_result = adapter.refine(
                message,
                {"intent": "objection_think", "confidence": 0.65},
                adapter_ctx
            )

            # Compare results
            assert adapter_result.refined == original_refined, (
                f"Adapter refined={adapter_result.refined} but original refined={original_refined} "
                f"for message: '{message}'"
            )

            if original_refined:
                assert adapter_result.intent == original_intent, (
                    f"Adapter intent={adapter_result.intent} but original intent={original_intent} "
                    f"for message: '{message}'"
                )


# =============================================================================
# TEST: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for Rule 5."""

    def test_empty_message(self, adapter):
        """Test empty message doesn't crash."""
        ctx = RefinementContext(
            message="",
            state="handle_objection",
            intent="objection_think",
            confidence=0.5,
        )

        # Should not crash, should pass through
        result = adapter.refine("", {"intent": "objection_think", "confidence": 0.5}, ctx)
        assert result is not None

    def test_message_with_only_whitespace(self, adapter):
        """Test whitespace-only message doesn't crash."""
        ctx = RefinementContext(
            message="   \n\t  ",
            state="handle_objection",
            intent="objection_think",
            confidence=0.5,
        )

        result = adapter.refine(
            "   \n\t  ",
            {"intent": "objection_think", "confidence": 0.5},
            ctx
        )
        assert result is not None

    def test_case_insensitive_matching(self, adapter):
        """Test uncertainty patterns match case-insensitively."""
        test_cases = [
            "НУЖНО ЛИ ЭТО ВНЕДРЯТЬ",
            "Нужно Ли Это Внедрять",
            "ЗАЧЕМ ЭТО НУЖНО",
            "Зачем Это Нужно",
            "КАКОЙ СМЫСЛ",
            "Какой Смысл",
        ]

        for message in test_cases:
            ctx = RefinementContext(
                message=message,
                state="handle_objection",
                intent="objection_think",
                confidence=0.65,
            )

            result = adapter.refine(
                message,
                {"intent": "objection_think", "confidence": 0.65},
                ctx
            )

            assert result.refined is True, (
                f"Case-insensitive matching failed for: '{message}'"
            )

    def test_partial_pattern_match(self, adapter):
        """Test patterns match within longer messages."""
        ctx = RefinementContext(
            message="честно говоря, нужно ли нам это сейчас внедрять",
            state="handle_objection",
            intent="objection_think",
            confidence=0.65,
        )

        result = adapter.refine(
            ctx.message,
            {"intent": "objection_think", "confidence": 0.65},
            ctx
        )

        assert result.refined is True
        assert result.refinement_reason == "uncertainty_pattern"


# =============================================================================
# TEST: Stats Tracking
# =============================================================================

class TestStatsTracking:
    """Tests that Rule 5 refinements are properly tracked in stats."""

    def test_uncertainty_pattern_tracked_in_stats(self, adapter):
        """
        Test uncertainty_pattern refinements are tracked.

        Note: We use "надо ли это внедрять" because:
        - It contains "надо ли" (uncertainty pattern, Rule 5)
        - It does NOT contain interest patterns like "не уверен", "подумать" (Rule 4)
        - It does NOT contain question markers like "?" or "какой" (Rule 2)
        """
        # Apply several uncertainty refinements
        for _ in range(3):
            ctx = RefinementContext(
                message="надо ли это внедрять",  # Pure uncertainty pattern
                state="handle_objection",
                intent="objection_think",
                confidence=0.65,
            )

            adapter.refine(
                "надо ли это внедрять",
                {"intent": "objection_think", "confidence": 0.65},
                ctx
            )

        stats = adapter.get_stats()

        assert stats["refinements_by_reason"].get("uncertainty_pattern", 0) == 3, (
            f"Expected 3 uncertainty_pattern refinements, got "
            f"{stats['refinements_by_reason'].get('uncertainty_pattern', 0)}. "
            f"All reasons: {stats['refinements_by_reason']}"
        )


# =============================================================================
# TEST: Original Bug Scenario is Fixed
# =============================================================================

class TestOriginalBugScenarioFixed:
    """
    Tests that the ORIGINAL bug scenario is fixed.

    The original bug:
    - Skeptic says "не уверен нужно ли"
    - LLM classifies as objection_think
    - ObjectionReturnSource never triggers
    - Dialog goes: greeting → handle_objection → handle_objection → soft_close
    - Result: phases_reached: [] for 37 dialogs

    The fix ensures objection_think is ALWAYS refined to question_features
    for skeptic uncertainty messages, regardless of which rule triggers.
    """

    def test_ne_uveren_nuzhno_li_is_refined_to_question_features(self, adapter):
        """
        Test that "не уверен нужно ли" IS refined to question_features.

        Note: This message contains BOTH:
        - "не уверен" → interest_pattern (Rule 4)
        - "нужно ли" → uncertainty_pattern (Rule 5)

        Rule 4 will trigger (it has priority), but the END RESULT is the same:
        objection_think → question_features

        This is the CRITICAL test that proves the original bug is fixed.
        """
        ctx = RefinementContext(
            message="не уверен нужно ли",  # Original bug scenario
            state="handle_objection",
            intent="objection_think",
            confidence=0.65,
        )

        result = adapter.refine(
            "не уверен нужно ли",
            {"intent": "objection_think", "confidence": 0.65},
            ctx
        )

        # THE CRITICAL ASSERTION: must be refined to question_features
        assert result.refined is True, (
            "Message 'не уверен нужно ли' MUST be refined (original bug scenario)"
        )
        assert result.intent == "question_features", (
            f"Message 'не уверен нужно ли' MUST be refined to question_features, "
            f"got {result.intent}. This is the original bug scenario!"
        )

        # Note: The reason can be either interest_pattern (Rule 4) or
        # uncertainty_pattern (Rule 5) - both are valid!
        assert result.refinement_reason in ["interest_pattern", "uncertainty_pattern"], (
            f"Unexpected refinement reason: {result.refinement_reason}"
        )

    def test_objection_return_source_triggers_for_original_bug(self, adapter):
        """
        Test that ObjectionReturnSource DOES trigger after refinement.

        This proves the full chain is fixed:
        1. "не уверен нужно ли" → objection_think (LLM classification)
        2. Rule 4 or Rule 5 → question_features (refinement)
        3. ObjectionReturnSource.should_contribute() → True
        4. Return to phase is proposed → dialog continues normally
        """
        from src.blackboard.sources.objection_return import ObjectionReturnSource
        from unittest.mock import Mock

        # Step 1: Original classification
        original_intent = "objection_think"
        message = "не уверен нужно ли"

        # Step 2: Refinement
        ctx = RefinementContext(
            message=message,
            state="handle_objection",
            intent=original_intent,
            confidence=0.65,
        )

        result = adapter.refine(
            message,
            {"intent": original_intent, "confidence": 0.65},
            ctx
        )

        refined_intent = result.intent

        # Step 3: Check ObjectionReturnSource
        source = ObjectionReturnSource()

        mock_blackboard = Mock()
        mock_blackboard.current_state = "handle_objection"
        mock_blackboard.current_intent = refined_intent
        mock_blackboard._state_machine = Mock()
        mock_blackboard._state_machine._state_before_objection = "bant_budget"

        should_contribute = source.should_contribute(mock_blackboard)

        # CRITICAL: ObjectionReturnSource MUST trigger
        assert should_contribute is True, (
            f"ObjectionReturnSource MUST trigger for refined intent '{refined_intent}'. "
            f"This was the root cause of the original bug! "
            f"return_intents: {source.return_intents}"
        )

    def test_multiple_skeptic_messages_all_refined(self, adapter):
        """
        Test various skeptic messages that should all be refined.

        All these messages should result in question_features,
        regardless of which rule triggers.
        """
        skeptic_messages = [
            # Contains interest patterns (Rule 4)
            "не уверен нужно ли",
            "сомневаюсь в этом",
            "не знаю, стоит ли",
            # Contains uncertainty patterns only (Rule 5)
            "нужно ли это внедрять",
            "надо ли это вообще",
            "стоит ли это делать",
            "а смысл в этом есть",
        ]

        failed_messages = []

        for message in skeptic_messages:
            ctx = RefinementContext(
                message=message,
                state="handle_objection",
                intent="objection_think",
                confidence=0.65,
            )

            result = adapter.refine(
                message,
                {"intent": "objection_think", "confidence": 0.65},
                ctx
            )

            if not result.refined or result.intent != "question_features":
                failed_messages.append({
                    "message": message,
                    "refined": result.refined,
                    "intent": result.intent,
                    "reason": result.refinement_reason,
                })

        assert not failed_messages, (
            f"Some skeptic messages were NOT refined to question_features:\n"
            + "\n".join(
                f"  - '{m['message']}' → {m['intent']} (refined={m['refined']}, reason={m['reason']})"
                for m in failed_messages
            )
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

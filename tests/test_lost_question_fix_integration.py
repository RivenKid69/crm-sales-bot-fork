# tests/test_lost_question_fix_integration.py

"""
Integration Tests for the Lost Question Fix.

These tests verify the complete architectural solution works end-to-end:
1. SecondaryIntentDetectionLayer detects secondary intents
2. FactQuestionSource responds to detected questions
3. Count-based conditions work correctly
4. BANT overlay_allowed_states are configured correctly

This is the comprehensive test suite for the "Lost Question" bug fix.
"""

import pytest
from typing import Dict, Any, List
from unittest.mock import Mock, patch

from src.classifier.secondary_intent_detection import SecondaryIntentDetectionLayer
from src.classifier.refinement_pipeline import RefinementContext, RefinementDecision
from src.blackboard.sources.fact_question import FactQuestionSource
from src.blackboard.enums import Priority
from src.yaml_config.constants import (
    OVERLAY_ALLOWED_STATES,
    get_secondary_intent_config,
    get_fact_question_source_config,
)

# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

class TestConfigurationIntegration:
    """Test that configuration is properly loaded and used."""

    def test_bant_states_in_overlay_allowed(self):
        """Test that BANT states are in overlay_allowed_states."""
        bant_states = [
            "bant_budget",
            "bant_authority",
            "bant_need",
            "bant_timeline",
        ]
        for state in bant_states:
            assert state in OVERLAY_ALLOWED_STATES, \
                f"BANT state '{state}' should be in overlay_allowed_states"

    def test_spin_states_in_overlay_allowed(self):
        """Test that SPIN states are still in overlay_allowed_states."""
        spin_states = [
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
        ]
        for state in spin_states:
            assert state in OVERLAY_ALLOWED_STATES, \
                f"SPIN state '{state}' should be in overlay_allowed_states"

    def test_secondary_intent_config_loads(self):
        """Test that secondary_intent_detection config loads."""
        config = get_secondary_intent_config()
        assert isinstance(config, dict)
        assert "enabled" in config or config == {}

    def test_fact_question_source_config_loads(self):
        """Test that fact_question_source config loads."""
        config = get_fact_question_source_config()
        assert isinstance(config, dict)

# =============================================================================
# PIPELINE INTEGRATION TESTS
# =============================================================================

class TestPipelineIntegration:
    """Test SecondaryIntentDetectionLayer + FactQuestionSource integration."""

    @pytest.fixture
    def detection_layer(self):
        """Create SecondaryIntentDetectionLayer."""
        return SecondaryIntentDetectionLayer()

    @pytest.fixture
    def fact_source(self):
        """Create FactQuestionSource."""
        return FactQuestionSource()

    def test_detection_to_source_flow(self, detection_layer, fact_source):
        """
        Test complete flow:
        1. User sends composite message
        2. LLM classifies as info_provided
        3. SecondaryIntentDetectionLayer detects question_features
        4. FactQuestionSource responds to detected question
        """
        # Step 1: Message classification
        message = "100 человек. Какие функции есть?"
        primary_intent = "info_provided"
        primary_confidence = 0.85

        # Step 2: Create context for detection layer
        ctx = RefinementContext(
            message=message,
            intent=primary_intent,
            confidence=primary_confidence,
            state="bant_budget",
            phase="budget",
            last_action="ask_about_budget",
        )
        result = {
            "intent": primary_intent,
            "confidence": primary_confidence,
            "extracted_data": {"company_size": 100},
        }

        # Step 3: Run detection layer
        refined = detection_layer.refine(message, result, ctx)

        # Verify detection
        assert refined.decision == RefinementDecision.REFINED
        assert refined.intent == primary_intent  # Primary preserved
        assert "question_features" in refined.secondary_signals

        # Step 4: Create mock blackboard with detected secondary intents
        class MockBlackboard:
            def __init__(self):
                self.current_intent = primary_intent
                self._proposals = []

            def get_context(self):
                class MockCtx:
                    state = "bant_budget"
                    current_intent = primary_intent
                    last_intent = "greeting"
                    collected_data = {}
                    state_config = {}
                    turn_number = 1
                    current_phase = "budget"
                    intent_tracker = None

                    class Envelope:
                        frustration_level = 0
                        is_stuck = False
                        has_oscillation = False
                        momentum = 0.0
                        engagement_level = "medium"
                        repeated_question = None
                        tone = None
                        secondary_intents = refined.secondary_signals
                        classification_result = {
                            "secondary_signals": refined.secondary_signals
                        }

                    context_envelope = Envelope()

                    def get_missing_required_data(self):
                        return []

                return MockCtx()

            def propose_action(self, action, priority, combinable, reason_code,
                             source_name, metadata=None):
                self._proposals.append({
                    "action": action,
                    "priority": priority,
                    "combinable": combinable,
                    "metadata": metadata or {},
                })

        blackboard = MockBlackboard()

        # Step 5: Verify FactQuestionSource contributes
        assert fact_source.should_contribute(blackboard) is True

        # Step 6: Run source contribution
        fact_source.contribute(blackboard)

        # Step 7: Verify proposal
        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "answer_with_facts"
        assert proposal["priority"] == Priority.HIGH
        assert proposal["combinable"] is True
        assert proposal["metadata"]["fact_intent"] == "question_features"
        assert proposal["metadata"]["detection_source"] == "secondary"

# =============================================================================
# COUNT-BASED CONDITIONS TESTS
# =============================================================================

class TestCountBasedConditions:
    """Test count-based conditions for reliable detection."""

    def test_price_total_count_condition_import(self):
        """Test that count-based conditions are importable."""
        from src.conditions.state_machine.conditions import (
            price_total_count_3x,
            price_total_count_2x,
            question_total_count_2x,
            unclear_total_count_3x,
            has_secondary_price_question,
            has_secondary_question_intent,
            should_answer_question_now,
        )

        # Conditions should be callable
        assert callable(price_total_count_3x)
        assert callable(price_total_count_2x)
        assert callable(question_total_count_2x)
        assert callable(unclear_total_count_3x)
        assert callable(has_secondary_price_question)
        assert callable(has_secondary_question_intent)
        assert callable(should_answer_question_now)

# =============================================================================
# REAL BUG SCENARIO TESTS
# =============================================================================

class TestRealBugScenarios:
    """Test the exact scenarios from the original bug report."""

    @pytest.fixture
    def detection_layer(self):
        return SecondaryIntentDetectionLayer()

    def test_bug_scenario_price_question_lost(self, detection_layer):
        """
        Original bug:
        User: "100 человек. Давайте уже по делу — сколько стоит?"
        LLM: info_provided (100 человек detected)
        Bug: price_question LOST

        Fix: SecondaryIntentDetectionLayer detects price_question
        """
        message = "100 человек. Давайте уже по делу — сколько стоит?"

        ctx = RefinementContext(
            message=message,
            intent="info_provided",
            confidence=0.85,
            state="bant_budget",
            phase="budget",
            last_action="ask_about_company",
        )
        result = {"intent": "info_provided", "confidence": 0.85}

        refined = detection_layer.refine(message, result, ctx)

        # Primary intent preserved
        assert refined.intent == "info_provided"

        # Secondary intents detected
        assert "price_question" in refined.secondary_signals
        assert "request_brevity" in refined.secondary_signals

    def test_bug_scenario_feature_question_lost(self, detection_layer):
        """
        Scenario:
        User: "У нас ресторан, 20 столов. Какие возможности есть?"
        LLM: situation_provided (restaurant info detected)
        Bug: question_features LOST

        Fix: SecondaryIntentDetectionLayer detects question_features
        """
        message = "У нас ресторан, 20 столов. Какие возможности есть?"

        ctx = RefinementContext(
            message=message,
            intent="situation_provided",
            confidence=0.82,
            state="spin_situation",
            phase="situation",
            last_action="ask_about_company",
        )
        result = {"intent": "situation_provided", "confidence": 0.82}

        refined = detection_layer.refine(message, result, ctx)

        # Primary intent preserved
        assert refined.intent == "situation_provided"

        # Secondary intent detected
        assert "question_features" in refined.secondary_signals

    def test_bug_scenario_integration_question_lost(self, detection_layer):
        """
        Scenario:
        User: "10 касс планируем. А интеграция с Каспи есть?"
        LLM: info_provided (10 касс detected)
        Bug: question_integrations LOST

        Fix: SecondaryIntentDetectionLayer detects question_integrations
        """
        message = "10 касс планируем. А интеграция с Каспи есть?"

        ctx = RefinementContext(
            message=message,
            intent="info_provided",
            confidence=0.80,
            state="bant_budget",
            phase="budget",
            last_action="ask_about_budget",
        )
        result = {"intent": "info_provided", "confidence": 0.80}

        refined = detection_layer.refine(message, result, ctx)

        # Primary intent preserved
        assert refined.intent == "info_provided"

        # Secondary intent detected
        assert "question_integrations" in refined.secondary_signals

# =============================================================================
# BANT FLOW INTEGRATION TESTS
# =============================================================================

class TestBANTFlowIntegration:
    """Test that the fix works correctly in BANT flow."""

    @pytest.fixture
    def detection_layer(self):
        return SecondaryIntentDetectionLayer()

    @pytest.fixture
    def fact_source(self):
        return FactQuestionSource()

    @pytest.mark.parametrize("bant_state", [
        "bant_budget",
        "bant_authority",
        "bant_need",
        "bant_timeline",
    ])
    def test_overlay_allowed_in_all_bant_states(self, bant_state):
        """Test that policy overlays are allowed in all BANT states."""
        assert bant_state in OVERLAY_ALLOWED_STATES

    def test_fact_question_in_bant_authority(
        self, detection_layer, fact_source
    ):
        """
        Test fact question handling in bant_authority phase.

        Previously: deflect_and_continue blocked answers
        Now: answer_with_facts is proposed
        """
        message = "Я принимаю решения. Какие функции есть?"

        # Detection layer
        ctx = RefinementContext(
            message=message,
            intent="info_provided",
            confidence=0.85,
            state="bant_authority",
            phase="authority",
            last_action="ask_about_authority",
        )
        result = {"intent": "info_provided", "confidence": 0.85}
        refined = detection_layer.refine(message, result, ctx)

        assert "question_features" in refined.secondary_signals

    def test_fact_question_in_bant_need(
        self, detection_layer, fact_source
    ):
        """
        Test fact question handling in bant_need phase.

        Previously: deflect_and_continue blocked answers
        Now: answer_with_facts is proposed
        """
        message = "Нужна автоматизация. Какая интеграция с 1С?"

        # Detection layer
        ctx = RefinementContext(
            message=message,
            intent="info_provided",
            confidence=0.85,
            state="bant_need",
            phase="need",
            last_action="ask_about_need",
        )
        result = {"intent": "info_provided", "confidence": 0.85}
        refined = detection_layer.refine(message, result, ctx)

        assert "question_integrations" in refined.secondary_signals

# =============================================================================
# REGRESSION TESTS
# =============================================================================

class TestRegressionPrevention:
    """Test that the fix doesn't break existing functionality."""

    @pytest.fixture
    def detection_layer(self):
        return SecondaryIntentDetectionLayer()

    def test_primary_intent_never_changed(self, detection_layer):
        """Test that primary intent is NEVER changed by detection layer."""
        test_cases = [
            ("Да", "agreement", 0.9),
            ("Нет", "rejection", 0.95),
            ("100 человек", "info_provided", 0.85),
            ("Привет", "greeting", 0.9),
            ("Сколько стоит?", "price_question", 0.9),
        ]

        for message, intent, confidence in test_cases:
            ctx = RefinementContext(
                message=message,
                intent=intent,
                confidence=confidence,
                state="bant_budget",
                phase="budget",
                last_action="ask_about_budget",
            )
            result = {"intent": intent, "confidence": confidence}

            refined = detection_layer.refine(message, result, ctx)

            # Primary intent must always be preserved
            assert refined.intent == intent, \
                f"Primary intent changed from {intent} to {refined.intent}"

    def test_short_messages_not_over_detected(self, detection_layer):
        """Test that short messages don't trigger false positives."""
        short_messages = [
            "Да",
            "Нет",
            "Ок",
            "5",
            "100",
        ]

        for message in short_messages:
            ctx = RefinementContext(
                message=message,
                intent="agreement",
                confidence=0.9,
                state="bant_budget",
                phase="budget",
                last_action="ask_about_budget",
            )
            result = {"intent": "agreement", "confidence": 0.9}

            refined = detection_layer.refine(message, result, ctx)

            # Should pass through without secondary detection
            assert refined.decision == RefinementDecision.PASS_THROUGH

    def test_spin_flow_still_works(self, detection_layer):
        """Test that SPIN flow detection still works."""
        # SPIN states should still be in overlay_allowed
        spin_states = [
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
        ]
        for state in spin_states:
            assert state in OVERLAY_ALLOWED_STATES

# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """Test performance characteristics."""

    @pytest.fixture
    def detection_layer(self):
        return SecondaryIntentDetectionLayer()

    def test_pattern_matching_performance(self, detection_layer):
        """Test that pattern matching is reasonably fast."""
        import time

        message = "100 человек. Сколько стоит и какие функции есть?"
        ctx = RefinementContext(
            message=message,
            intent="info_provided",
            confidence=0.85,
            state="bant_budget",
            phase="budget",
            last_action="ask_about_budget",
        )
        result = {"intent": "info_provided", "confidence": 0.85}

        # Warm up
        detection_layer.refine(message, result, ctx)

        # Measure
        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            detection_layer.refine(message, result, ctx)
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / iterations) * 1000

        # Should be fast (< 5ms per call)
        assert avg_time_ms < 5, f"Pattern matching too slow: {avg_time_ms:.2f}ms"

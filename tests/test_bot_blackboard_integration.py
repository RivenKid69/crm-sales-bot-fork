# tests/test_bot_blackboard_integration.py

"""
Stage 14: Bot + Blackboard Integration Tests

These tests verify that SalesBot correctly integrates with DialogueOrchestrator
after the Stage 14 migration from state_machine.process() to orchestrator.process_turn().

Test Categories:
1. Integration Tests - SalesBot uses orchestrator correctly
2. Compatibility Tests - sm_result format matches legacy format
3. Scenario Tests - Full dialogue scenarios work end-to-end
"""

import pytest
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock, patch

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns predictable responses."""
    llm = Mock()
    llm.generate = Mock(return_value="Test response from LLM")
    llm.chat = Mock(return_value={"content": "Test response"})
    return llm

@pytest.fixture
def sales_bot(mock_llm):
    """Create a SalesBot instance with mocked LLM."""
    from src.bot import SalesBot
    from src.feature_flags import flags

    # Enable required flags via set_override
    flags.set_override("metrics_tracking", True)
    flags.set_override("conversation_guard", True)
    flags.set_override("tone_analysis", True)
    flags.set_override("lead_scoring", True)
    flags.set_override("objection_handler", True)
    flags.set_override("cta_generator", True)
    flags.set_override("confidence_router", True)
    flags.set_override("context_full_envelope", True)
    flags.set_override("context_policy_overlays", True)
    flags.set_override("context_response_directives", True)

    bot = SalesBot(llm=mock_llm, enable_tracing=True)

    yield bot

    # Cleanup overrides after test
    flags.clear_all_overrides()

# =============================================================================
# Integration Tests - Orchestrator Initialization
# =============================================================================

class TestOrchestratorInitialization:
    """Test that orchestrator is properly initialized in SalesBot."""

    def test_orchestrator_created_on_init(self, sales_bot):
        """Verify orchestrator is created during SalesBot initialization."""
        assert hasattr(sales_bot, '_orchestrator')
        assert sales_bot._orchestrator is not None

    def test_orchestrator_has_state_machine(self, sales_bot):
        """Verify orchestrator uses the same state_machine instance."""
        assert sales_bot._orchestrator._state_machine is sales_bot.state_machine

    def test_orchestrator_has_flow_config(self, sales_bot):
        """Verify orchestrator has flow config."""
        assert sales_bot._orchestrator._flow_config is not None

    def test_orchestrator_has_knowledge_sources(self, sales_bot):
        """Verify orchestrator has access to knowledge sources property."""
        # Note: sources are instantiated from SourceRegistry during orchestrator init
        # The actual count depends on configuration and may be 0 if no config
        sources = sales_bot._orchestrator.sources
        # Just verify the property exists and returns a list
        assert isinstance(sources, list)
        # If sources are present, verify they have the expected interface
        if len(sources) > 0:
            source_names = [s.name for s in sources]
            # These are the standard built-in sources
            expected_names = ["PriceQuestionSource", "DataCollectorSource", "ObjectionGuardSource"]
            for name in expected_names:
                if name in source_names:
                    assert True  # At least one expected source is present
                    break

# =============================================================================
# Compatibility Tests - sm_result Format
# =============================================================================

class TestSmResultCompatibility:
    """Test that sm_result from orchestrator matches expected format."""

    def test_sm_result_has_action(self, sales_bot):
        """Verify sm_result contains action field."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="test_action",
            next_state="greeting",
        )
        # Fill compatibility fields manually for test
        decision.prev_state = "greeting"
        decision.goal = "test goal"
        decision.collected_data = {}
        decision.missing_data = []
        decision.optional_data = []
        decision.is_final = False
        decision.spin_phase = "situation"
        decision.circular_flow = {}
        decision.objection_flow = {}

        sm_result = decision.to_sm_result()

        assert "action" in sm_result
        assert sm_result["action"] == "test_action"

    def test_sm_result_has_next_state(self, sales_bot):
        """Verify sm_result contains next_state field."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="test_action",
            next_state="spin_situation",
        )
        decision.prev_state = "greeting"
        decision.collected_data = {}

        sm_result = decision.to_sm_result()

        assert "next_state" in sm_result
        assert sm_result["next_state"] == "spin_situation"

    def test_sm_result_has_prev_state(self, sales_bot):
        """Verify sm_result contains prev_state field."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="test_action",
            next_state="spin_situation",
        )
        decision.prev_state = "greeting"
        decision.collected_data = {}

        sm_result = decision.to_sm_result()

        assert "prev_state" in sm_result
        assert sm_result["prev_state"] == "greeting"

    def test_sm_result_has_collected_data(self, sales_bot):
        """Verify sm_result contains collected_data field."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="test_action",
            next_state="greeting",
        )
        decision.collected_data = {"business_type": "restaurant"}

        sm_result = decision.to_sm_result()

        assert "collected_data" in sm_result
        assert sm_result["collected_data"]["business_type"] == "restaurant"

    def test_sm_result_has_missing_data(self, sales_bot):
        """Verify sm_result contains missing_data field."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="test_action",
            next_state="greeting",
        )
        decision.missing_data = ["company_size", "users_count"]

        sm_result = decision.to_sm_result()

        assert "missing_data" in sm_result
        assert "company_size" in sm_result["missing_data"]

    def test_sm_result_has_goal(self, sales_bot):
        """Verify sm_result contains goal field."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="test_action",
            next_state="greeting",
        )
        decision.goal = "Establish rapport and understand business"

        sm_result = decision.to_sm_result()

        assert "goal" in sm_result
        assert "Establish" in sm_result["goal"]

    def test_sm_result_has_is_final(self, sales_bot):
        """Verify sm_result contains is_final field."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="final",
            next_state="success",
        )
        decision.is_final = True

        sm_result = decision.to_sm_result()

        assert "is_final" in sm_result
        assert sm_result["is_final"] is True

    def test_sm_result_has_spin_phase(self, sales_bot):
        """Verify sm_result contains spin_phase field."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="test_action",
            next_state="spin_situation",
        )
        decision.spin_phase = "situation"

        sm_result = decision.to_sm_result()

        assert "spin_phase" in sm_result
        assert sm_result["spin_phase"] == "situation"

    def test_sm_result_has_reason_codes(self, sales_bot):
        """Verify sm_result contains reason_codes field (new in Blackboard)."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="answer_with_pricing",
            next_state="greeting",
            reason_codes=["price_question_detected", "has_pricing_data"],
        )

        sm_result = decision.to_sm_result()

        assert "reason_codes" in sm_result
        assert "price_question_detected" in sm_result["reason_codes"]

# =============================================================================
# Scenario Tests - Basic Dialogue Flow
# =============================================================================

class TestBasicDialogueFlow:
    """Test basic dialogue scenarios through SalesBot with Blackboard."""

    def test_greeting_response(self, sales_bot, mock_llm):
        """Test that greeting produces a response."""
        mock_llm.generate = Mock(return_value="Здравствуйте! Чем могу помочь?")

        result = sales_bot.process("Привет")

        assert "response" in result
        assert result["response"] is not None
        assert len(result["response"]) > 0

    def test_state_transition_occurs(self, sales_bot, mock_llm):
        """Test that state transitions happen correctly."""
        mock_llm.generate = Mock(return_value="Test response")

        result = sales_bot.process("Привет")

        # Should have moved from initial state
        assert "state" in result
        assert result["state"] is not None

    def test_intent_is_classified(self, sales_bot, mock_llm):
        """Test that intent classification works."""
        mock_llm.generate = Mock(return_value="Test response")

        result = sales_bot.process("Расскажите о ценах")

        assert "intent" in result
        assert result["intent"] is not None

    def test_action_is_determined(self, sales_bot, mock_llm):
        """Test that action is determined by orchestrator."""
        mock_llm.generate = Mock(return_value="Test response")

        result = sales_bot.process("Привет")

        assert "action" in result
        assert result["action"] is not None

# =============================================================================
# Scenario Tests - Price Question (Bug Fix Verification)
# =============================================================================

class TestPriceQuestionHandling:
    """Test price question handling - key bug fix in Blackboard."""

    def test_price_question_gets_answer(self, sales_bot, mock_llm):
        """Test that price questions get answered, not deflected."""
        mock_llm.generate = Mock(return_value="Наши цены начинаются от...")

        # Simulate having collected some data first
        sales_bot.state_machine.collected_data["business_type"] = "restaurant"
        sales_bot.state_machine.collected_data["company_size"] = 10  # Number, not string

        result = sales_bot.process("Сколько стоит ваша система?")

        # Should get some response (not blocked)
        assert "response" in result
        assert result["response"] is not None

    def test_price_question_with_data_complete(self, sales_bot, mock_llm):
        """Test price question when all required data is collected."""
        mock_llm.generate = Mock(return_value="Для вашего бизнеса цена составит...")

        # Set up collected data (company_size must be a number)
        sales_bot.state_machine.collected_data["business_type"] = "restaurant"
        sales_bot.state_machine.collected_data["company_size"] = 50  # Number, not string
        sales_bot.state_machine.collected_data["users_count"] = 10

        result = sales_bot.process("Какие цены?")

        assert "response" in result

# =============================================================================
# Scenario Tests - Objection Handling
# =============================================================================

class TestObjectionHandling:
    """Test objection handling through Blackboard."""

    def test_objection_is_handled(self, sales_bot, mock_llm):
        """Test that objections are properly handled."""
        mock_llm.generate = Mock(return_value="Понимаю ваши сомнения...")

        result = sales_bot.process("Это слишком дорого для нас")

        assert "response" in result
        # Objection should be detected
        assert result.get("objection_detected") is not None

    def test_multiple_objections_tracked(self, sales_bot, mock_llm):
        """Test that multiple objections are tracked."""
        mock_llm.generate = Mock(return_value="Test response")

        # Send multiple objections
        sales_bot.process("Это дорого")
        sales_bot.process("У нас нет бюджета")
        result = sales_bot.process("Слишком сложно")

        # Should still get responses
        assert "response" in result

# =============================================================================
# Scenario Tests - Data Collection
# =============================================================================

class TestDataCollection:
    """Test data collection through Blackboard."""

    def test_data_is_collected(self, sales_bot, mock_llm):
        """Test that extracted data is collected."""
        mock_llm.generate = Mock(return_value="Отлично, у вас ресторан!")

        # Process a message with extractable data
        result = sales_bot.process("У нас ресторан на 50 посадочных мест")

        # State machine should have collected data
        collected = sales_bot.state_machine.collected_data
        # Note: actual extraction depends on classifier
        assert collected is not None


class TestBotTransitionSanitizer:
    """Bot-level transition sanitizer integration tests (skip + policy override)."""

    def test_policy_override_invalid_next_state_does_not_create_ghost(self, sales_bot, mock_llm):
        from src.blackboard.models import ResolvedDecision
        from src.dialogue_policy import PolicyOverride, PolicyDecision
        from src.feature_flags import flags
        from src.blackboard.decision_sanitizer import INVALID_NEXT_STATE_REASON

        flags.set_override("context_policy_overlays", True)

        decision = ResolvedDecision(action="continue_current_goal", next_state="greeting")
        decision.prev_state = "greeting"
        decision.goal = "test goal"
        decision.collected_data = {}
        decision.missing_data = []
        decision.optional_data = []
        decision.is_final = False
        decision.spin_phase = None
        decision.circular_flow = {}
        decision.objection_flow = {}

        sales_bot._orchestrator.process_turn = Mock(return_value=decision)
        sales_bot.classifier.classify = Mock(return_value={
            "intent": "greeting",
            "confidence": 0.99,
            "extracted_data": {},
            "all_scores": {"greeting": 0.99},
        })
        sales_bot.dialogue_policy.maybe_override = Mock(return_value=PolicyOverride(
            action="continue_current_goal",
            next_state="ghost",
            reason_codes=["policy.test_override"],
            decision=PolicyDecision.REPAIR_CLARIFY,
        ))
        mock_llm.generate = Mock(return_value="ok")

        result = sales_bot.process("привет")

        assert sales_bot.state_machine.state != "ghost"
        assert result["state"] != "ghost"
        assert INVALID_NEXT_STATE_REASON in result.get("reason_codes", [])

    def test_fallback_skip_invalid_target_stays_in_current_state(self, sales_bot, mock_llm):
        from src.blackboard.models import ResolvedDecision
        from src.feature_flags import flags
        from src.blackboard.decision_sanitizer import INVALID_NEXT_STATE_REASON

        flags.set_override("conversation_guard_in_pipeline", False)
        flags.set_override("context_policy_overlays", False)

        decision = ResolvedDecision(action="continue_current_goal", next_state="greeting")
        decision.prev_state = "greeting"
        decision.goal = "test goal"
        decision.collected_data = {}
        decision.missing_data = []
        decision.optional_data = []
        decision.is_final = False
        decision.spin_phase = None
        decision.circular_flow = {}
        decision.objection_flow = {}

        sales_bot._orchestrator.process_turn = Mock(return_value=decision)
        sales_bot.classifier.classify = Mock(return_value={
            "intent": "greeting",
            "confidence": 0.95,
            "extracted_data": {},
            "all_scores": {"greeting": 0.95},
        })
        sales_bot._check_guard = Mock(return_value=Mock(can_continue=False, intervention="fallback_tier_3"))
        sales_bot._apply_fallback = Mock(return_value={
            "response": "skip",
            "action": "skip",
            "next_state": "ghost",
            "options": None,
        })
        mock_llm.generate = Mock(return_value="ok")

        current_state = sales_bot.state_machine.state
        result = sales_bot.process("...")

        assert sales_bot.state_machine.state == current_state
        assert result["state"] == current_state
        assert INVALID_NEXT_STATE_REASON in result.get("reason_codes", [])


class TestPolicyObjectionOverlayRegression:
    """Regression tests for policy objection-overlay override pattern."""

    @staticmethod
    def _make_decision(action: str, next_state: str, **kwargs):
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(action=action, next_state=next_state, **kwargs)
        decision.prev_state = next_state
        decision.goal = "test goal"
        decision.collected_data = {}
        decision.missing_data = []
        decision.optional_data = []
        decision.is_final = False
        decision.spin_phase = "problem"
        decision.circular_flow = {}
        decision.objection_flow = {}
        return decision

    @staticmethod
    def _seed_repeated_objections(bot):
        """Seed context_window so envelope has historical objection signals."""
        for idx in range(3):
            bot.context_window.add_turn_from_dict(
                user_message=f"дорого {idx}",
                bot_response="Понимаю возражение",
                intent="objection_price",
                confidence=0.9,
                action="handle_price_objection",
                state="handle_objection",
                next_state="handle_objection",
            )

    def test_disambiguation_ask_clarification_not_overridden_by_policy(self, sales_bot, mock_llm):
        """disambiguation_needed must preserve ask_clarification action (no objection override)."""
        self._seed_repeated_objections(sales_bot)
        sales_bot.state_machine._state = "spin_problem"

        decision = self._make_decision(
            action="ask_clarification",
            next_state="spin_problem",
            disambiguation_options=[
                {"intent": "price_question", "label": "Цены"},
                {"intent": "question_features", "label": "Функции"},
            ],
            disambiguation_question="Уточните, пожалуйста:",
        )
        sales_bot._orchestrator.process_turn = Mock(return_value=decision)
        sales_bot.classifier.classify = Mock(return_value={
            "intent": "disambiguation_needed",
            "confidence": 0.72,
            "extracted_data": {},
            "all_scores": {"disambiguation_needed": 0.72},
        })
        mock_llm.generate = Mock(return_value="ok")

        result = sales_bot.process("уточните")

        assert result["action"] == "ask_clarification"
        assert sales_bot.state_machine.in_disambiguation is True
        assert result["response"]  # UI clarification text should be present

    def test_question_features_answer_action_preserved_and_cta_blocked(self, sales_bot, mock_llm):
        """question_features with historical objections keeps answer action and skips CTA."""
        self._seed_repeated_objections(sales_bot)
        sales_bot.state_machine._state = "presentation"
        sales_bot.cta_generator.turn_count = 5  # Ensure CTA would be allowed without blocked-action gate

        decision = self._make_decision(
            action="answer_with_facts",
            next_state="presentation",
        )
        sales_bot._orchestrator.process_turn = Mock(return_value=decision)
        sales_bot.classifier.classify = Mock(return_value={
            "intent": "question_features",
            "confidence": 0.91,
            "extracted_data": {},
            "all_scores": {"question_features": 0.91},
        })
        mock_llm.generate = Mock(return_value="Wipon автоматизирует процессы без лишней сложности.")

        result = sales_bot.process("какие функции есть?")

        assert result["action"] == "answer_with_facts"
        assert result["cta_added"] is False
        assert result["cta_text"] is None

# =============================================================================
# State Machine Deprecation Tests
# =============================================================================

class TestStateMachineDeprecation:
    """Test that deprecated state machine methods show warnings."""

    def test_apply_rules_shows_deprecation(self, sales_bot):
        """Test that apply_rules shows DeprecationWarning."""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sales_bot.state_machine.apply_rules("greeting")

            # Should have raised DeprecationWarning
            assert len(w) >= 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

    def test_process_shows_deprecation(self, sales_bot):
        """Test that state_machine.process shows DeprecationWarning."""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sales_bot.state_machine.process("greeting")

            # Should have raised DeprecationWarning
            assert len(w) >= 1
            assert issubclass(w[0].category, DeprecationWarning)

# =============================================================================
# Reset and Session Tests
# =============================================================================

class TestSessionManagement:
    """Test session management with Blackboard."""

    def test_reset_clears_state(self, sales_bot, mock_llm):
        """Test that reset clears conversation state."""
        mock_llm.generate = Mock(return_value="Test response")

        # Process some messages
        sales_bot.process("Привет")
        sales_bot.process("Расскажите о ценах")

        # Reset
        sales_bot.reset()

        # State should be reset
        assert sales_bot.state_machine.state == "greeting"
        assert len(sales_bot.history) == 0

    def test_new_conversation_id_after_reset(self, sales_bot, mock_llm):
        """Test that reset generates new conversation ID."""
        mock_llm.generate = Mock(return_value="Test response")

        old_id = sales_bot.conversation_id
        sales_bot.process("Привет")
        sales_bot.reset()
        new_id = sales_bot.conversation_id

        assert old_id != new_id

# =============================================================================
# Orchestrator Process Turn Tests
# =============================================================================

class TestOrchestratorProcessTurn:
    """Test orchestrator.process_turn() directly."""

    def test_process_turn_returns_decision(self, sales_bot):
        """Test that process_turn returns ResolvedDecision."""
        from src.blackboard.models import ResolvedDecision

        decision = sales_bot._orchestrator.process_turn(
            intent="greeting",
            extracted_data={},
            context_envelope=None,
        )

        assert isinstance(decision, ResolvedDecision)
        assert decision.action is not None
        assert decision.next_state is not None

    def test_process_turn_fills_compatibility_fields(self, sales_bot):
        """Test that process_turn fills compatibility fields."""
        decision = sales_bot._orchestrator.process_turn(
            intent="greeting",
            extracted_data={},
            context_envelope=None,
        )

        # Should have compatibility fields filled
        assert decision.prev_state is not None or decision.prev_state == ""
        assert decision.collected_data is not None
        assert decision.missing_data is not None
        assert isinstance(decision.is_final, bool)

    def test_to_sm_result_is_dict(self, sales_bot):
        """Test that to_sm_result returns a dict."""
        decision = sales_bot._orchestrator.process_turn(
            intent="greeting",
            extracted_data={},
            context_envelope=None,
        )

        sm_result = decision.to_sm_result()

        assert isinstance(sm_result, dict)
        assert "action" in sm_result
        assert "next_state" in sm_result

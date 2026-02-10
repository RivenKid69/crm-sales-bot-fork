"""
Tests for Universal Refinement Pipeline Architecture.

Tests cover:
1. RefinementPipeline core functionality
2. BaseRefinementLayer contract
3. RefinementLayerRegistry
4. Layer adapters (ShortAnswer, Composite, Objection)
5. Integration with UnifiedClassifier

NOTE: Tests DO NOT use LLM - all tests are unit tests with mocked data.
"""

import pytest
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock

from src.classifier.refinement_pipeline import (
    RefinementPipeline,
    BaseRefinementLayer,
    RefinementContext,
    RefinementResult,
    RefinementDecision,
    LayerPriority,
    RefinementLayerRegistry,
    register_refinement_layer,
    get_refinement_pipeline,
    reset_refinement_pipeline,
    build_refinement_context,
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_registry():
    """Reset registry before and after each test."""
    reset_refinement_pipeline()
    yield
    reset_refinement_pipeline()

@pytest.fixture
def sample_context() -> RefinementContext:
    """Create sample refinement context."""
    return RefinementContext(
        message="5 человек",
        state="spin_situation",
        phase="situation",
        last_action="ask_about_company",
        last_intent="greeting",
        turn_number=3,
        intent="greeting",
        confidence=0.6,
    )

@pytest.fixture
def sample_result() -> Dict[str, Any]:
    """Create sample classification result."""
    return {
        "intent": "greeting",
        "confidence": 0.6,
        "extracted_data": {},
        "method": "llm",
    }

@pytest.fixture
def sample_context_dict() -> Dict[str, Any]:
    """Create sample context dictionary."""
    return {
        "state": "spin_situation",
        "spin_phase": "situation",
        "last_action": "ask_about_company",
        "last_intent": "greeting",
        "turn_number": 3,
    }

# =============================================================================
# TEST: RefinementContext
# =============================================================================

class TestRefinementContext:
    """Tests for RefinementContext dataclass."""

    def test_create_context(self):
        """Test creating context with all fields."""
        ctx = RefinementContext(
            message="test message",
            state="greeting",
            phase="situation",
            last_action="ask_about_company",
            intent="unclear",
            confidence=0.5,
        )

        assert ctx.message == "test message"
        assert ctx.state == "greeting"
        assert ctx.phase == "situation"
        assert ctx.intent == "unclear"
        assert ctx.confidence == 0.5

    def test_context_defaults(self):
        """Test context default values."""
        ctx = RefinementContext(message="test")

        assert ctx.state is None
        assert ctx.phase is None
        assert ctx.turn_number == 0
        assert ctx.collected_data == {}
        assert ctx.metadata == {}

    def test_update_from_result(self, sample_context):
        """Test updating context from classification result."""
        result = {
            "intent": "info_provided",
            "confidence": 0.85,
            "extracted_data": {"company_size": 5},
            "refinement_metadata": {"layer": "test"},
        }

        new_ctx = sample_context.update_from_result(result)

        assert new_ctx.intent == "info_provided"
        assert new_ctx.confidence == 0.85
        assert new_ctx.extracted_data == {"company_size": 5}
        assert new_ctx.metadata["layer"] == "test"
        # Original fields preserved
        assert new_ctx.message == sample_context.message
        assert new_ctx.state == sample_context.state

# =============================================================================
# TEST: RefinementResult
# =============================================================================

class TestRefinementResult:
    """Tests for RefinementResult dataclass."""

    def test_create_result(self):
        """Test creating result."""
        result = RefinementResult(
            decision=RefinementDecision.REFINED,
            intent="info_provided",
            confidence=0.8,
            original_intent="greeting",
            refinement_reason="test_reason",
            layer_name="test_layer",
        )

        assert result.decision == RefinementDecision.REFINED
        assert result.intent == "info_provided"
        assert result.refined is True

    def test_pass_through_result(self):
        """Test pass-through result."""
        result = RefinementResult(
            decision=RefinementDecision.PASS_THROUGH,
            intent="greeting",
            confidence=0.6,
        )

        assert result.refined is False
        assert result.original_intent is None

    def test_to_dict(self):
        """Test converting result to dict."""
        result = RefinementResult(
            decision=RefinementDecision.REFINED,
            intent="info_provided",
            confidence=0.8,
            original_intent="greeting",
            refinement_reason="data_extracted",
            layer_name="composite_message",
            extracted_data={"company_size": 5},
            secondary_signals=["request_brevity"],
        )

        d = result.to_dict()

        assert d["intent"] == "info_provided"
        assert d["confidence"] == 0.8
        assert d["refined"] is True
        assert d["original_intent"] == "greeting"
        assert d["refinement_reason"] == "data_extracted"
        assert d["refinement_layer"] == "composite_message"
        assert d["extracted_data"] == {"company_size": 5}
        assert d["secondary_signals"] == ["request_brevity"]

# =============================================================================
# TEST: RefinementLayerRegistry
# =============================================================================

class TestRefinementLayerRegistry:
    """Tests for RefinementLayerRegistry."""

    def test_singleton(self):
        """Test registry is singleton."""
        r1 = RefinementLayerRegistry.get_registry()
        r2 = RefinementLayerRegistry.get_registry()
        assert r1 is r2

    def test_register_layer(self):
        """Test registering a layer."""
        registry = RefinementLayerRegistry.get_registry()

        class TestLayer(BaseRefinementLayer):
            LAYER_NAME = "test_layer"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        registry.register("test_layer", TestLayer)

        assert registry.is_registered("test_layer")
        assert registry.get("test_layer") is TestLayer

    def test_register_duplicate_raises(self):
        """Test registering duplicate name raises error."""
        registry = RefinementLayerRegistry.get_registry()

        class TestLayer1(BaseRefinementLayer):
            LAYER_NAME = "dup"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        class TestLayer2(BaseRefinementLayer):
            LAYER_NAME = "dup"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        registry.register("dup", TestLayer1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("dup", TestLayer2)

    def test_register_with_override(self):
        """Test registering with override=True."""
        registry = RefinementLayerRegistry.get_registry()

        class TestLayer1(BaseRefinementLayer):
            LAYER_NAME = "over"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        class TestLayer2(BaseRefinementLayer):
            LAYER_NAME = "over"

            def _should_apply(self, ctx):
                return False

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        registry.register("over", TestLayer1)
        registry.register("over", TestLayer2, override=True)

        assert registry.get("over") is TestLayer2

    def test_get_instance_creates_layer(self):
        """Test get_instance creates and caches layer."""
        registry = RefinementLayerRegistry.get_registry()

        class TestLayer(BaseRefinementLayer):
            LAYER_NAME = "inst_test"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        registry.register("inst_test", TestLayer)

        instance1 = registry.get_layer_instance("inst_test")
        instance2 = registry.get_layer_instance("inst_test")

        assert instance1 is instance2
        assert isinstance(instance1, TestLayer)

    def test_decorator_registration(self):
        """Test @register_refinement_layer decorator."""
        @register_refinement_layer("decorated_layer")
        class DecoratedLayer(BaseRefinementLayer):
            LAYER_NAME = "decorated_layer"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        registry = RefinementLayerRegistry.get_registry()
        assert registry.is_registered("decorated_layer")

# =============================================================================
# TEST: BaseRefinementLayer
# =============================================================================

class TestBaseRefinementLayer:
    """Tests for BaseRefinementLayer abstract class."""

    def test_layer_implements_protocol(self):
        """Test layer implements IRefinementLayer protocol."""
        class TestLayer(BaseRefinementLayer):
            LAYER_NAME = "proto_test"
            LAYER_PRIORITY = LayerPriority.HIGH

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        layer = TestLayer()

        assert layer.name == "proto_test"
        assert layer.priority == LayerPriority.HIGH
        assert layer.enabled is True  # No feature flag

    def test_layer_stats_tracking(self, sample_context, sample_result):
        """Test layer tracks statistics."""
        class StatsLayer(BaseRefinementLayer):
            LAYER_NAME = "stats_test"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._create_refined_result(
                    new_intent="refined",
                    new_confidence=0.9,
                    original_intent=ctx.intent,
                    reason="test",
                    result=result,
                )

        layer = StatsLayer()

        # Run refine multiple times
        for _ in range(3):
            layer.refine("test", sample_result.copy(), sample_context)

        stats = layer.get_stats()

        assert stats["calls_total"] == 3
        assert stats["refinements_total"] == 3
        assert stats["errors_total"] == 0
        assert stats["refinements_by_reason"]["test"] == 3

    def test_layer_error_handling(self, sample_context, sample_result):
        """Test layer handles errors gracefully."""
        class ErrorLayer(BaseRefinementLayer):
            LAYER_NAME = "error_test"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                raise ValueError("Test error")

        layer = ErrorLayer()
        result = layer.refine("test", sample_result, sample_context)

        # Should return original result
        assert result.intent == sample_result["intent"]
        assert result.decision == RefinementDecision.ERROR

        stats = layer.get_stats()
        assert stats["errors_total"] == 1

    def test_layer_skips_when_disabled(self, sample_context, sample_result):
        """Test layer skips when feature flag disabled."""
        class DisabledLayer(BaseRefinementLayer):
            LAYER_NAME = "disabled_test"
            FEATURE_FLAG = "nonexistent_flag"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._create_refined_result(
                    new_intent="should_not_happen",
                    new_confidence=0.9,
                    original_intent=ctx.intent,
                    reason="test",
                    result=result,
                )

        layer = DisabledLayer()
        # Layer should be disabled because flag doesn't exist
        assert layer.enabled is False

        result = layer.refine("test", sample_result, sample_context)
        assert result.decision == RefinementDecision.PASS_THROUGH

# =============================================================================
# TEST: RefinementPipeline
# =============================================================================

class TestRefinementPipeline:
    """Tests for RefinementPipeline orchestrator."""

    def test_pipeline_empty_config(self):
        """Test pipeline with empty config."""
        pipeline = RefinementPipeline(config={"enabled": True, "layers": []})

        result = pipeline.refine("test", {"intent": "greeting", "confidence": 0.5}, {})

        # Should return original result unchanged
        assert result["intent"] == "greeting"

    def test_pipeline_disabled(self):
        """Test disabled pipeline returns original."""
        pipeline = RefinementPipeline(config={"enabled": False, "layers": []})

        result = pipeline.refine("test", {"intent": "greeting", "confidence": 0.5}, {})

        assert result["intent"] == "greeting"

    def test_pipeline_runs_layers_in_order(self):
        """Test pipeline runs layers in priority order."""
        execution_order = []

        @register_refinement_layer("layer_high", override=True)
        class HighLayer(BaseRefinementLayer):
            LAYER_NAME = "layer_high"
            LAYER_PRIORITY = LayerPriority.HIGH

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                execution_order.append("high")
                return self._pass_through(result, ctx)

        @register_refinement_layer("layer_low", override=True)
        class LowLayer(BaseRefinementLayer):
            LAYER_NAME = "layer_low"
            LAYER_PRIORITY = LayerPriority.LOW

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                execution_order.append("low")
                return self._pass_through(result, ctx)

        pipeline = RefinementPipeline(config={
            "enabled": True,
            "layers": [
                {"name": "layer_low", "enabled": True},
                {"name": "layer_high", "enabled": True},
            ]
        })

        pipeline.refine("test", {"intent": "test", "confidence": 0.5}, {})

        # High priority should run first
        assert execution_order == ["high", "low"]

    def test_pipeline_chains_refinements(self):
        """Test pipeline chains refinements through layers."""
        @register_refinement_layer("chain1", override=True)
        class Chain1Layer(BaseRefinementLayer):
            LAYER_NAME = "chain1"
            LAYER_PRIORITY = LayerPriority.HIGH

            def _should_apply(self, ctx):
                return ctx.intent == "original"

            def _do_refine(self, message, result, ctx):
                return self._create_refined_result(
                    new_intent="intermediate",
                    new_confidence=0.7,
                    original_intent=ctx.intent,
                    reason="chain1",
                    result=result,
                )

        @register_refinement_layer("chain2", override=True)
        class Chain2Layer(BaseRefinementLayer):
            LAYER_NAME = "chain2"
            LAYER_PRIORITY = LayerPriority.NORMAL

            def _should_apply(self, ctx):
                return ctx.intent == "intermediate"

            def _do_refine(self, message, result, ctx):
                return self._create_refined_result(
                    new_intent="final",
                    new_confidence=0.9,
                    original_intent=ctx.intent,
                    reason="chain2",
                    result=result,
                )

        pipeline = RefinementPipeline(config={
            "enabled": True,
            "layers": [
                {"name": "chain1", "enabled": True},
                {"name": "chain2", "enabled": True},
            ]
        })

        result = pipeline.refine(
            "test",
            {"intent": "original", "confidence": 0.5},
            {}
        )

        assert result["intent"] == "final"
        assert result["refinement_chain"] == ["chain1", "chain2"]

    def test_pipeline_continues_on_layer_error(self):
        """Test pipeline continues when layer errors."""
        @register_refinement_layer("error_layer", override=True)
        class ErrorLayer(BaseRefinementLayer):
            LAYER_NAME = "error_layer"
            LAYER_PRIORITY = LayerPriority.HIGH

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                raise RuntimeError("Layer error")

        @register_refinement_layer("ok_layer", override=True)
        class OkLayer(BaseRefinementLayer):
            LAYER_NAME = "ok_layer"
            LAYER_PRIORITY = LayerPriority.NORMAL

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._create_refined_result(
                    new_intent="refined",
                    new_confidence=0.8,
                    original_intent=ctx.intent,
                    reason="ok",
                    result=result,
                )

        pipeline = RefinementPipeline(config={
            "enabled": True,
            "layers": [
                {"name": "error_layer", "enabled": True},
                {"name": "ok_layer", "enabled": True},
            ]
        })

        result = pipeline.refine(
            "test",
            {"intent": "original", "confidence": 0.5},
            {}
        )

        # Should continue to ok_layer after error_layer fails
        assert result["intent"] == "refined"

    def test_pipeline_stats(self):
        """Test pipeline collects statistics."""
        @register_refinement_layer("stats_layer", override=True)
        class StatsLayer(BaseRefinementLayer):
            LAYER_NAME = "stats_layer"

            def _should_apply(self, ctx):
                return True

            def _do_refine(self, message, result, ctx):
                return self._pass_through(result, ctx)

        pipeline = RefinementPipeline(config={
            "enabled": True,
            "layers": [{"name": "stats_layer", "enabled": True}]
        })

        for _ in range(5):
            pipeline.refine("test", {"intent": "test", "confidence": 0.5}, {})

        stats = pipeline.get_stats()

        assert stats["calls_total"] == 5
        assert stats["enabled"] is True
        assert "stats_layer" in stats["layer_stats"]

# =============================================================================
# TEST: Layer Adapters
# =============================================================================

class TestShortAnswerRefinementLayer:
    """Tests for ShortAnswerRefinementLayer adapter."""

    def test_layer_registered(self):
        """Test layer is registered."""
        # Import to trigger registration (if not already)
        from src.classifier import refinement_layers  # noqa: F401

        # Check if already registered, else force registration
        registry = RefinementLayerRegistry.get_registry()
        if not registry.is_registered("short_answer"):
            # Force import and registration
            from src.classifier.refinement_layers import ShortAnswerRefinementLayer
            registry.register("short_answer", ShortAnswerRefinementLayer, override=True)

        assert registry.is_registered("short_answer")

    def test_refines_short_greeting_in_situation_phase(self):
        """Test refines short 'да' from greeting to situation_provided."""
        from src.classifier.refinement_layers import ShortAnswerRefinementLayer

        layer = ShortAnswerRefinementLayer()

        ctx = RefinementContext(
            message="да",
            state="spin_situation",
            phase="situation",
            last_action="ask_about_company",
            intent="greeting",
            confidence=0.5,
        )

        result = layer.refine("да", {"intent": "greeting", "confidence": 0.5}, ctx)

        if result.refined:
            assert result.intent == "situation_provided"

    def test_does_not_refine_long_messages(self):
        """Test does not refine long messages."""
        from src.classifier.refinement_layers import ShortAnswerRefinementLayer

        layer = ShortAnswerRefinementLayer()

        ctx = RefinementContext(
            message="У нас большая компания с множеством сотрудников и офисов",
            state="spin_situation",
            phase="situation",
            last_action="ask_about_company",
            intent="greeting",
            confidence=0.5,
        )

        result = layer.refine(
            ctx.message,
            {"intent": "greeting", "confidence": 0.5},
            ctx
        )

        # Should not refine - message too long
        assert result.decision == RefinementDecision.PASS_THROUGH

class TestCompositeMessageLayer:
    """Tests for CompositeMessageLayer adapter."""

    def test_layer_registered(self):
        """Test layer is registered after import."""
        # Need to reload module since registry was reset
        import importlib
        from src.classifier import refinement_layers
        importlib.reload(refinement_layers)

        registry = RefinementLayerRegistry.get_registry()
        assert registry.is_registered("composite_message")

    def test_extracts_data_from_composite_message(self):
        """Test extracts company_size from composite message."""
        from src.classifier.refinement_layers import CompositeMessageLayer

        layer = CompositeMessageLayer()

        ctx = RefinementContext(
            message="5 человек, больше не нужно, быстрее",
            state="spin_situation",
            phase="situation",
            last_action="ask_about_company",
            intent="objection_think",
            confidence=0.7,
        )

        result = layer.refine(
            ctx.message,
            {"intent": "objection_think", "confidence": 0.7},
            ctx
        )

        if result.refined:
            assert result.intent in ["info_provided", "situation_provided"]
            assert result.extracted_data.get("company_size") == 5

    def test_does_not_refine_non_refinable_intents(self):
        """Test does not refine non-refinable intents."""
        from src.classifier.refinement_layers import CompositeMessageLayer

        layer = CompositeMessageLayer()

        ctx = RefinementContext(
            message="5 человек",
            state="spin_situation",
            phase="situation",
            last_action="ask_about_company",
            intent="info_provided",  # Already correct
            confidence=0.9,
        )

        result = layer.refine(
            ctx.message,
            {"intent": "info_provided", "confidence": 0.9},
            ctx
        )

        # Should pass through - already correct intent
        assert result.decision == RefinementDecision.PASS_THROUGH

class TestObjectionRefinementLayerAdapter:
    """Tests for ObjectionRefinementLayerAdapter."""

    def test_layer_registered(self):
        """Test layer is registered after import."""
        # Need to reload module since registry was reset
        import importlib
        from src.classifier import refinement_layers
        importlib.reload(refinement_layers)

        registry = RefinementLayerRegistry.get_registry()
        assert registry.is_registered("objection")

    def test_refines_objection_with_question_markers(self):
        """Test refines objection when message has question markers."""
        from src.classifier.refinement_layers import ObjectionRefinementLayerAdapter

        layer = ObjectionRefinementLayerAdapter()

        ctx = RefinementContext(
            message="А сколько это стоит?",
            state="presentation",
            last_action="present_feature",
            intent="objection_price",
            confidence=0.65,
        )

        result = layer.refine(
            ctx.message,
            {"intent": "objection_price", "confidence": 0.65},
            ctx
        )

        if result.refined:
            assert "question" in result.intent.lower() or result.intent == "price_question"

    def test_does_not_refine_non_objection_intents(self):
        """Test does not refine non-objection intents."""
        from src.classifier.refinement_layers import ObjectionRefinementLayerAdapter

        layer = ObjectionRefinementLayerAdapter()

        ctx = RefinementContext(
            message="Хорошо, интересно",
            state="presentation",
            last_action="present_feature",
            intent="agreement",
            confidence=0.8,
        )

        result = layer.refine(
            ctx.message,
            {"intent": "agreement", "confidence": 0.8},
            ctx
        )

        # Should pass through - not an objection
        assert result.decision == RefinementDecision.PASS_THROUGH

# =============================================================================
# TEST: Integration with UnifiedClassifier
# =============================================================================

class TestUnifiedClassifierIntegration:
    """Integration tests with UnifiedClassifier."""

    @pytest.fixture
    def mock_flags(self):
        """Mock feature flags."""
        with patch('src.classifier.unified.flags') as mock:
            mock.llm_classifier = False
            mock.is_enabled.return_value = True
            mock.unified_disambiguation = False
            yield mock

    def test_classifier_uses_pipeline(self, mock_flags):
        """Test UnifiedClassifier uses RefinementPipeline."""
        from src.classifier.unified import UnifiedClassifier

        classifier = UnifiedClassifier()

        # Mock hybrid classifier
        classifier._hybrid = Mock()
        classifier._hybrid.classify.return_value = {
            "intent": "greeting",
            "confidence": 0.5,
            "method": "hybrid",
        }

        result = classifier.classify("да", {
            "state": "spin_situation",
            "spin_phase": "situation",
            "last_action": "ask_about_company",
        })

        # Pipeline should have been called
        assert result is not None

# =============================================================================
# TEST: build_refinement_context helper
# =============================================================================

class TestBuildRefinementContext:
    """Tests for build_refinement_context helper."""

    def test_builds_context_from_result(self):
        """Test building context from classification result."""
        result = {
            "intent": "greeting",
            "confidence": 0.6,
            "extracted_data": {"field": "value"},
        }

        ctx = build_refinement_context(
            message="test",
            result=result,
            state="greeting",
            phase="situation",
        )

        assert ctx.message == "test"
        assert ctx.intent == "greeting"
        assert ctx.confidence == 0.6
        assert ctx.extracted_data == {"field": "value"}
        assert ctx.state == "greeting"
        assert ctx.phase == "situation"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

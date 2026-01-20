"""Tests for analyzer data models."""

import pytest
import json
import tempfile
from pathlib import Path

from codebase_analyzer.analyzer.models import (
    EntitySummary,
    ModuleSummary,
    ArchitectureSummary,
    AnalysisResult,
)


# ============================================================================
# Tests: EntitySummary
# ============================================================================

class TestEntitySummary:
    """Tests for EntitySummary model."""

    def test_create_basic_summary(self):
        """Should create a basic entity summary."""
        summary = EntitySummary(
            entity_id="src/auth/login.py::LoginService",
            summary="Handles user authentication and session management.",
            purpose="Provides login/logout functionality for the application.",
            domain="auth",
        )

        assert summary.entity_id == "src/auth/login.py::LoginService"
        assert summary.domain == "auth"
        assert summary.key_behaviors == []
        assert summary.input_tokens == 0

    def test_create_full_summary(self):
        """Should create a summary with all fields."""
        summary = EntitySummary(
            entity_id="src/payments/stripe.py::StripeClient",
            summary="Integrates with Stripe API for payment processing.",
            purpose="Process credit card payments via Stripe.",
            domain="payments",
            key_behaviors=["charge_card", "refund", "create_subscription"],
            dependencies_used=["httpx", "stripe-sdk"],
            input_tokens=150,
            output_tokens=200,
            model="qwen3:14b",
            code_hash="abc123def456",
        )

        assert len(summary.key_behaviors) == 3
        assert "charge_card" in summary.key_behaviors
        assert summary.input_tokens == 150
        assert summary.code_hash == "abc123def456"

    def test_to_context_string(self):
        """Should generate short context string."""
        summary = EntitySummary(
            entity_id="src/utils/logger.py::Logger",
            summary="Structured logging with JSON output.",
            purpose="Provides centralized logging for the application.",
            domain="logging",
        )

        context = summary.to_context_string()
        assert "src/utils/logger.py::Logger" in context
        assert "Provides centralized logging" in context

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        original = EntitySummary(
            entity_id="test::Entity",
            summary="Test summary",
            purpose="Test purpose",
            domain="test",
            key_behaviors=["action1", "action2"],
            dependencies_used=["dep1"],
            input_tokens=100,
            output_tokens=50,
            model="test-model",
            code_hash="hash123",
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = EntitySummary.from_dict(data)

        assert restored.entity_id == original.entity_id
        assert restored.summary == original.summary
        assert restored.purpose == original.purpose
        assert restored.domain == original.domain
        assert restored.key_behaviors == original.key_behaviors
        assert restored.input_tokens == original.input_tokens
        assert restored.code_hash == original.code_hash


# ============================================================================
# Tests: ModuleSummary
# ============================================================================

class TestModuleSummary:
    """Tests for ModuleSummary model."""

    def test_create_module_summary(self):
        """Should create a module summary."""
        summary = ModuleSummary(
            path="src/auth",
            name="auth",
            summary="Authentication and authorization module.",
            entities=["src/auth/login.py::Login", "src/auth/logout.py::Logout"],
            domains=["auth", "security"],
            responsibilities=["User authentication", "Session management"],
        )

        assert summary.path == "src/auth"
        assert summary.name == "auth"
        assert len(summary.entities) == 2
        assert "auth" in summary.domains

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        original = ModuleSummary(
            path="src/payments",
            name="payments",
            summary="Payment processing module.",
            entities=["e1", "e2"],
            domains=["payments"],
            responsibilities=["Process payments", "Handle refunds"],
            dependencies=["stripe", "paypal"],
            exports=["PaymentService"],
            entity_count=5,
            total_lines=500,
            input_tokens=200,
            output_tokens=100,
        )

        data = original.to_dict()
        restored = ModuleSummary.from_dict(data)

        assert restored.path == original.path
        assert restored.responsibilities == original.responsibilities
        assert restored.entity_count == original.entity_count


# ============================================================================
# Tests: ArchitectureSummary
# ============================================================================

class TestArchitectureSummary:
    """Tests for ArchitectureSummary model."""

    def test_create_architecture_summary(self):
        """Should create an architecture summary."""
        summary = ArchitectureSummary(
            overview="Microservices-based e-commerce platform.",
            modules=["auth", "payments", "catalog"],
            patterns_detected=["microservices", "event-driven"],
            tech_stack=["Python", "PostgreSQL", "Redis"],
        )

        assert "e-commerce" in summary.overview
        assert len(summary.modules) == 3
        assert "microservices" in summary.patterns_detected

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        original = ArchitectureSummary(
            overview="Test system overview.",
            modules=["m1", "m2"],
            patterns_detected=["MVC"],
            tech_stack=["Python"],
            data_flow="Request -> Service -> Database",
            key_components=["API Gateway", "Auth Service"],
            external_dependencies=["Stripe", "SendGrid"],
            diagram_mermaid="graph TD; A-->B;",
            input_tokens=300,
            output_tokens=200,
        )

        data = original.to_dict()
        restored = ArchitectureSummary.from_dict(data)

        assert restored.overview == original.overview
        assert restored.data_flow == original.data_flow
        assert restored.diagram_mermaid == original.diagram_mermaid


# ============================================================================
# Tests: AnalysisResult
# ============================================================================

class TestAnalysisResult:
    """Tests for AnalysisResult model."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample analysis result."""
        entity_summaries = {
            "e1": EntitySummary(
                entity_id="e1",
                summary="Entity 1",
                purpose="Purpose 1",
                domain="domain1",
            ),
            "e2": EntitySummary(
                entity_id="e2",
                summary="Entity 2",
                purpose="Purpose 2",
                domain="domain2",
            ),
        }

        module_summaries = {
            "src/module1": ModuleSummary(
                path="src/module1",
                name="module1",
                summary="Module 1",
                entities=["e1"],
            ),
        }

        architecture = ArchitectureSummary(
            overview="Test system",
            modules=["src/module1"],
        )

        return AnalysisResult(
            entity_summaries=entity_summaries,
            module_summaries=module_summaries,
            architecture=architecture,
            total_entities=2,
            total_modules=1,
            total_tokens_in=500,
            total_tokens_out=300,
            processing_time_seconds=10.5,
            model_used="qwen3:14b",
            analysis_timestamp="2024-01-20T10:00:00",
        )

    def test_create_result(self, sample_result):
        """Should create an analysis result."""
        assert sample_result.total_entities == 2
        assert sample_result.total_modules == 1
        assert len(sample_result.entity_summaries) == 2
        assert sample_result.architecture is not None

    def test_get_summary_for_entity(self, sample_result):
        """Should get summary for a specific entity."""
        summary = sample_result.get_summary_for_entity("e1")
        assert summary is not None
        assert summary.entity_id == "e1"

        # Non-existent entity
        assert sample_result.get_summary_for_entity("nonexistent") is None

    def test_get_summaries_for_module(self, sample_result):
        """Should get summaries for a module."""
        summaries = sample_result.get_summaries_for_module("src/module1")
        assert len(summaries) == 1
        assert summaries[0].entity_id == "e1"

        # Non-existent module
        assert sample_result.get_summaries_for_module("nonexistent") == []

    def test_serialization_roundtrip(self, sample_result):
        """Should serialize and deserialize correctly."""
        data = sample_result.to_dict()
        restored = AnalysisResult.from_dict(data)

        assert len(restored.entity_summaries) == 2
        assert len(restored.module_summaries) == 1
        assert restored.architecture is not None
        assert restored.total_entities == sample_result.total_entities
        assert restored.model_used == sample_result.model_used

    def test_save_and_load(self, sample_result):
        """Should save to file and load back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result.json"

            # Save
            sample_result.save(path)
            assert path.exists()

            # Load
            loaded = AnalysisResult.load(path)

            assert len(loaded.entity_summaries) == 2
            assert loaded.total_entities == sample_result.total_entities
            assert loaded.architecture.overview == sample_result.architecture.overview

    def test_empty_result(self):
        """Should handle empty result."""
        result = AnalysisResult()

        assert result.entity_summaries == {}
        assert result.module_summaries == {}
        assert result.architecture is None
        assert result.total_entities == 0

        # Should serialize/deserialize
        data = result.to_dict()
        restored = AnalysisResult.from_dict(data)
        assert restored.entity_summaries == {}

    def test_result_without_architecture(self):
        """Should handle result without architecture."""
        result = AnalysisResult(
            entity_summaries={
                "e1": EntitySummary(
                    entity_id="e1",
                    summary="Test",
                    purpose="Test",
                    domain="test",
                )
            },
        )

        data = result.to_dict()
        assert data["architecture"] is None

        restored = AnalysisResult.from_dict(data)
        assert restored.architecture is None

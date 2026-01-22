# tests/test_blackboard_knowledge_source.py

"""
Tests for Blackboard Stage 5: KnowledgeSource base class.

These tests verify:
1. KnowledgeSource ABC - initialization, properties, methods
2. Concrete subclass behavior
3. Enable/disable functionality
4. should_contribute default behavior
"""

import pytest
from unittest.mock import Mock, MagicMock


class TestKnowledgeSourceBase:
    """Test KnowledgeSource base class functionality."""

    def test_knowledge_source_is_abstract(self):
        """KnowledgeSource cannot be instantiated directly."""
        from src.blackboard.knowledge_source import KnowledgeSource

        with pytest.raises(TypeError):
            KnowledgeSource()

    def test_concrete_subclass_creation(self):
        """Concrete subclass can be instantiated."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class ConcreteSource(KnowledgeSource):
            def contribute(self, blackboard):
                pass

        source = ConcreteSource()
        assert isinstance(source, KnowledgeSource)

    def test_default_name_is_class_name(self):
        """Source name defaults to class name."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class MyTestSource(KnowledgeSource):
            def contribute(self, blackboard):
                pass

        source = MyTestSource()
        assert source.name == "MyTestSource"

    def test_custom_name(self):
        """Source can have a custom name."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class MyTestSource(KnowledgeSource):
            def contribute(self, blackboard):
                pass

        source = MyTestSource(name="CustomName")
        assert source.name == "CustomName"

    def test_enabled_by_default(self):
        """Source is enabled by default."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class TestSource(KnowledgeSource):
            def contribute(self, blackboard):
                pass

        source = TestSource()
        assert source.enabled is True

    def test_disable_source(self):
        """Source can be disabled."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class TestSource(KnowledgeSource):
            def contribute(self, blackboard):
                pass

        source = TestSource()
        source.disable()
        assert source.enabled is False

    def test_enable_source(self):
        """Source can be re-enabled."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class TestSource(KnowledgeSource):
            def contribute(self, blackboard):
                pass

        source = TestSource()
        source.disable()
        source.enable()
        assert source.enabled is True

    def test_should_contribute_default_returns_enabled(self):
        """Default should_contribute returns enabled state."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class TestSource(KnowledgeSource):
            def contribute(self, blackboard):
                pass

        source = TestSource()
        mock_bb = Mock()

        # Enabled by default
        assert source.should_contribute(mock_bb) is True

        # Disabled
        source.disable()
        assert source.should_contribute(mock_bb) is False

        # Re-enabled
        source.enable()
        assert source.should_contribute(mock_bb) is True

    def test_should_contribute_can_be_overridden(self):
        """should_contribute can be overridden by subclass."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class ConditionalSource(KnowledgeSource):
            def should_contribute(self, blackboard):
                # Only contribute for specific intents
                return blackboard.current_intent == "target_intent"

            def contribute(self, blackboard):
                pass

        source = ConditionalSource()
        mock_bb = Mock()

        mock_bb.current_intent = "target_intent"
        assert source.should_contribute(mock_bb) is True

        mock_bb.current_intent = "other_intent"
        assert source.should_contribute(mock_bb) is False

    def test_contribute_is_abstract(self):
        """Subclass must implement contribute method."""
        from src.blackboard.knowledge_source import KnowledgeSource

        # Class without contribute method will fail ABC check
        with pytest.raises(TypeError):
            class InvalidSource(KnowledgeSource):
                pass

            InvalidSource()

    def test_contribute_receives_blackboard(self):
        """contribute method receives blackboard argument."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class TestSource(KnowledgeSource):
            def contribute(self, blackboard):
                # Verify we can access blackboard
                blackboard.test_method()

        source = TestSource()
        mock_bb = Mock()

        source.contribute(mock_bb)

        mock_bb.test_method.assert_called_once()

    def test_log_contribution_helper(self):
        """_log_contribution helper method works."""
        from src.blackboard.knowledge_source import KnowledgeSource
        import logging

        class TestSource(KnowledgeSource):
            def contribute(self, blackboard):
                self._log_contribution(action="test_action", reason="test_reason")

        source = TestSource()
        mock_bb = Mock()

        # Should not raise - just logs
        source.contribute(mock_bb)


class TestKnowledgeSourceIntegration:
    """Integration tests for KnowledgeSource with mocked Blackboard."""

    def test_source_proposes_action(self):
        """Source can propose actions to blackboard."""
        from src.blackboard.knowledge_source import KnowledgeSource
        from src.blackboard.enums import Priority

        class ActionSource(KnowledgeSource):
            def contribute(self, blackboard):
                ctx = blackboard.get_context()
                if ctx.current_intent == "price_question":
                    blackboard.propose_action(
                        action="answer_with_pricing",
                        priority=Priority.HIGH,
                        combinable=True,
                        reason_code="price_question",
                        source_name=self.name,
                    )

        source = ActionSource()
        mock_bb = Mock()
        mock_ctx = Mock()
        mock_ctx.current_intent = "price_question"
        mock_bb.get_context.return_value = mock_ctx

        source.contribute(mock_bb)

        mock_bb.propose_action.assert_called_once()
        call_kwargs = mock_bb.propose_action.call_args[1]
        assert call_kwargs["action"] == "answer_with_pricing"
        assert call_kwargs["priority"] == Priority.HIGH
        assert call_kwargs["combinable"] is True

    def test_source_proposes_transition(self):
        """Source can propose transitions to blackboard."""
        from src.blackboard.knowledge_source import KnowledgeSource
        from src.blackboard.enums import Priority

        class TransitionSource(KnowledgeSource):
            def contribute(self, blackboard):
                ctx = blackboard.get_context()
                if ctx.has_all_required_data():
                    blackboard.propose_transition(
                        next_state="next_phase",
                        priority=Priority.NORMAL,
                        reason_code="data_complete",
                        source_name=self.name,
                    )

        source = TransitionSource()
        mock_bb = Mock()
        mock_ctx = Mock()
        mock_ctx.has_all_required_data.return_value = True
        mock_bb.get_context.return_value = mock_ctx

        source.contribute(mock_bb)

        mock_bb.propose_transition.assert_called_once()
        call_kwargs = mock_bb.propose_transition.call_args[1]
        assert call_kwargs["next_state"] == "next_phase"
        assert call_kwargs["reason_code"] == "data_complete"

    def test_source_proposes_data_update(self):
        """Source can propose data updates to blackboard."""
        from src.blackboard.knowledge_source import KnowledgeSource

        class DataSource(KnowledgeSource):
            def contribute(self, blackboard):
                blackboard.propose_data_update(
                    field="detected_value",
                    value="computed_result",
                    source_name=self.name,
                    reason_code="data_extraction",
                )

        source = DataSource()
        mock_bb = Mock()

        source.contribute(mock_bb)

        mock_bb.propose_data_update.assert_called_once_with(
            field="detected_value",
            value="computed_result",
            source_name="DataSource",
            reason_code="data_extraction",
        )

    def test_multiple_sources_contribute_independently(self):
        """Multiple sources can contribute independently."""
        from src.blackboard.knowledge_source import KnowledgeSource
        from src.blackboard.enums import Priority

        class Source1(KnowledgeSource):
            def contribute(self, blackboard):
                blackboard.propose_action(
                    action="action1",
                    priority=Priority.NORMAL,
                    source_name=self.name,
                    reason_code="reason1",
                )

        class Source2(KnowledgeSource):
            def contribute(self, blackboard):
                blackboard.propose_action(
                    action="action2",
                    priority=Priority.HIGH,
                    source_name=self.name,
                    reason_code="reason2",
                )

        source1 = Source1()
        source2 = Source2()
        mock_bb = Mock()

        source1.contribute(mock_bb)
        source2.contribute(mock_bb)

        assert mock_bb.propose_action.call_count == 2

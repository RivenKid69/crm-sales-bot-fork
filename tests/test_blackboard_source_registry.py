# tests/test_blackboard_source_registry.py

"""
Tests for Blackboard Stage 5: SourceRegistry (Plugin System).

These tests verify:
1. SourceRegistry - registration, unregistration, listing
2. create_sources - instance creation, config handling
3. freeze/reset functionality
4. @register_source decorator
"""

import pytest
from unittest.mock import Mock

from src.blackboard.source_registry import (
    SourceRegistry,
    SourceRegistration,
    register_source,
)
from src.blackboard.knowledge_source import KnowledgeSource

class TestSourceRegistry:
    """Test suite for SourceRegistry (Plugin System)."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before each test."""
        SourceRegistry.reset()
        yield
        SourceRegistry.reset()

    def test_register_source_class(self):
        """register should add source to registry."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(TestSource, name="TestSource")

        assert "TestSource" in SourceRegistry.list_registered()

    def test_register_with_priority_order(self):
        """Sources should be listed in priority_order."""
        class Source1(KnowledgeSource):
            def contribute(self, bb):
                pass

        class Source2(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(Source1, name="Source1", priority_order=20)
        SourceRegistry.register(Source2, name="Source2", priority_order=10)

        registered = SourceRegistry.list_registered()
        assert registered[0] == "Source2"  # Lower priority = earlier
        assert registered[1] == "Source1"

    def test_register_rejects_non_knowledge_source(self):
        """register should reject non-KnowledgeSource classes."""
        class NotASource:
            pass

        with pytest.raises(TypeError):
            SourceRegistry.register(NotASource)

    def test_register_rejects_duplicate_name_when_frozen(self):
        """register should reject duplicate names when frozen."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(TestSource, name="TestSource")
        SourceRegistry.freeze()

        with pytest.raises(ValueError):
            SourceRegistry.register(TestSource, name="TestSource")

    def test_register_allows_overwrite_when_not_frozen(self):
        """register should allow overwriting when not frozen."""
        class TestSource1(KnowledgeSource):
            def contribute(self, bb):
                pass

        class TestSource2(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(TestSource1, name="TestSource", priority_order=10)
        SourceRegistry.register(TestSource2, name="TestSource", priority_order=20)

        reg = SourceRegistry.get_registration("TestSource")
        assert reg.source_class == TestSource2
        assert reg.priority_order == 20

    def test_unregister_source(self):
        """unregister should remove source from registry."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(TestSource, name="TestSource")
        assert "TestSource" in SourceRegistry.list_registered()

        result = SourceRegistry.unregister("TestSource")

        assert result is True
        assert "TestSource" not in SourceRegistry.list_registered()

    def test_unregister_nonexistent_returns_false(self):
        """unregister should return False for nonexistent source."""
        result = SourceRegistry.unregister("NonExistent")
        assert result is False

    def test_unregister_raises_when_frozen(self):
        """unregister should raise RuntimeError when frozen."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(TestSource, name="TestSource")
        SourceRegistry.freeze()

        with pytest.raises(RuntimeError):
            SourceRegistry.unregister("TestSource")

    def test_get_registration_returns_registration(self):
        """get_registration should return SourceRegistration."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(
            TestSource,
            name="TestSource",
            priority_order=15,
            description="Test description"
        )

        reg = SourceRegistry.get_registration("TestSource")

        assert reg is not None
        assert reg.name == "TestSource"
        assert reg.source_class == TestSource
        assert reg.priority_order == 15
        assert reg.description == "Test description"

    def test_get_registration_returns_none_for_unknown(self):
        """get_registration should return None for unknown source."""
        reg = SourceRegistry.get_registration("Unknown")
        assert reg is None

    def test_list_registered_returns_sorted_names(self):
        """list_registered should return names sorted by priority_order."""
        class Source1(KnowledgeSource):
            def contribute(self, bb):
                pass

        class Source2(KnowledgeSource):
            def contribute(self, bb):
                pass

        class Source3(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(Source1, name="Source1", priority_order=30)
        SourceRegistry.register(Source2, name="Source2", priority_order=10)
        SourceRegistry.register(Source3, name="Source3", priority_order=20)

        names = SourceRegistry.list_registered()

        assert names == ["Source2", "Source3", "Source1"]

    def test_create_sources_returns_instances(self):
        """create_sources should return KnowledgeSource instances."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(TestSource, name="TestSource")

        sources = SourceRegistry.create_sources()

        assert len(sources) == 1
        assert isinstance(sources[0], TestSource)
        assert sources[0].name == "TestSource"

    def test_create_sources_respects_enabled_config(self):
        """create_sources should respect enabled flag in config."""
        class Source1(KnowledgeSource):
            def contribute(self, bb):
                pass

        class Source2(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(Source1, name="Source1")
        SourceRegistry.register(Source2, name="Source2")

        config = {
            "sources": {
                "Source1": {"enabled": True},
                "Source2": {"enabled": False},  # Disabled!
            }
        }

        sources = SourceRegistry.create_sources(config=config)

        assert len(sources) == 1
        assert sources[0].name == "Source1"

    def test_create_sources_uses_default_enabled(self):
        """create_sources should use enabled_by_default if not in config."""
        class EnabledSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        class DisabledSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(
            EnabledSource, name="EnabledSource", enabled_by_default=True
        )
        SourceRegistry.register(
            DisabledSource, name="DisabledSource", enabled_by_default=False
        )

        sources = SourceRegistry.create_sources()

        assert len(sources) == 1
        assert sources[0].name == "EnabledSource"

    def test_create_sources_passes_config_to_source(self):
        """create_sources should pass source_configs to source __init__."""
        class ConfigurableSource(KnowledgeSource):
            def __init__(self, name: str, custom_param: str = "default"):
                super().__init__(name)
                self.custom_param = custom_param

            def contribute(self, bb):
                pass

        SourceRegistry.register(ConfigurableSource, name="ConfigurableSource")

        source_configs = {
            "ConfigurableSource": {"custom_param": "custom_value"}
        }

        sources = SourceRegistry.create_sources(source_configs=source_configs)

        assert sources[0].custom_param == "custom_value"

    def test_create_sources_maintains_priority_order(self):
        """create_sources should return sources in priority_order."""
        class Source1(KnowledgeSource):
            def contribute(self, bb):
                pass

        class Source2(KnowledgeSource):
            def contribute(self, bb):
                pass

        class Source3(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(Source1, name="Source1", priority_order=30)
        SourceRegistry.register(Source2, name="Source2", priority_order=10)
        SourceRegistry.register(Source3, name="Source3", priority_order=20)

        sources = SourceRegistry.create_sources()

        assert sources[0].name == "Source2"  # priority 10
        assert sources[1].name == "Source3"  # priority 20
        assert sources[2].name == "Source1"  # priority 30

    def test_create_sources_empty_registry(self):
        """create_sources should return empty list for empty registry."""
        sources = SourceRegistry.create_sources()
        assert sources == []

    def test_create_sources_raises_on_init_error(self):
        """create_sources should raise if source __init__ fails."""
        class FailingSource(KnowledgeSource):
            def __init__(self, name: str):
                raise ValueError("Init failed")

            def contribute(self, bb):
                pass

        SourceRegistry.register(FailingSource, name="FailingSource")

        with pytest.raises(ValueError, match="Init failed"):
            SourceRegistry.create_sources()

    def test_freeze_prevents_registration(self):
        """freeze should prevent new registrations."""
        class Source1(KnowledgeSource):
            def contribute(self, bb):
                pass

        class Source2(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(Source1, name="Source1")
        SourceRegistry.freeze()

        # Trying to register with same name should fail
        with pytest.raises(ValueError):
            SourceRegistry.register(Source2, name="Source1")

    def test_reset_clears_registry(self):
        """reset should clear all registrations and unfreeze."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(TestSource, name="TestSource")
        SourceRegistry.freeze()

        SourceRegistry.reset()

        assert SourceRegistry.list_registered() == []
        # Should be able to register after reset
        SourceRegistry.register(TestSource, name="TestSource")
        assert "TestSource" in SourceRegistry.list_registered()

class TestSourceRegistration:
    """Test suite for SourceRegistration dataclass."""

    def test_source_registration_creation(self):
        """SourceRegistration should be created with all fields."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        reg = SourceRegistration(
            source_class=TestSource,
            name="TestSource",
            priority_order=15,
            enabled_by_default=False,
            config_key="test_source",
            description="Test description",
        )

        assert reg.source_class == TestSource
        assert reg.name == "TestSource"
        assert reg.priority_order == 15
        assert reg.enabled_by_default is False
        assert reg.config_key == "test_source"
        assert reg.description == "Test description"

    def test_source_registration_defaults(self):
        """SourceRegistration should have sensible defaults."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        reg = SourceRegistration(
            source_class=TestSource,
            name="TestSource",
        )

        assert reg.priority_order == 100
        assert reg.enabled_by_default is True
        assert reg.config_key is None
        assert reg.description == ""

    def test_source_registration_post_init_name(self):
        """SourceRegistration should use class name if name is empty."""
        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        reg = SourceRegistration(
            source_class=TestSource,
            name="",
        )

        assert reg.name == "TestSource"

class TestRegisterSourceDecorator:
    """Test suite for @register_source decorator."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before each test."""
        SourceRegistry.reset()
        yield
        SourceRegistry.reset()

    def test_decorator_registers_class(self):
        """@register_source should register the decorated class."""
        @register_source(priority_order=15)
        class DecoratedSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        assert "DecoratedSource" in SourceRegistry.list_registered()
        reg = SourceRegistry.get_registration("DecoratedSource")
        assert reg.priority_order == 15

    def test_decorator_with_custom_name(self):
        """@register_source should support custom name."""
        @register_source(name="CustomName", priority_order=25)
        class DecoratedSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        assert "CustomName" in SourceRegistry.list_registered()

    def test_decorator_preserves_class(self):
        """@register_source should return the original class."""
        @register_source()
        class DecoratedSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        # Should still be usable as a class
        instance = DecoratedSource(name="test")
        assert isinstance(instance, KnowledgeSource)

    def test_decorator_with_all_params(self):
        """@register_source should support all parameters."""
        @register_source(
            name="FullyConfigured",
            priority_order=42,
            enabled_by_default=False,
            config_key="full_config",
            description="Fully configured source",
        )
        class DecoratedSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        reg = SourceRegistry.get_registration("FullyConfigured")

        assert reg.name == "FullyConfigured"
        assert reg.priority_order == 42
        assert reg.enabled_by_default is False
        assert reg.config_key == "full_config"
        assert reg.description == "Fully configured source"

    def test_decorator_default_values(self):
        """@register_source should have sensible defaults."""
        @register_source()
        class DecoratedSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        reg = SourceRegistry.get_registration("DecoratedSource")

        assert reg.priority_order == 100
        assert reg.enabled_by_default is True
        assert reg.config_key is None
        assert reg.description == ""

class TestSourceRegistryIntegration:
    """Integration tests for SourceRegistry with real sources."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before each test."""
        SourceRegistry.reset()
        yield
        SourceRegistry.reset()

    def test_full_registration_workflow(self):
        """Test complete workflow: register -> create -> use."""
        class TestSource(KnowledgeSource):
            def should_contribute(self, blackboard):
                return blackboard.current_intent == "test_intent"

            def contribute(self, blackboard):
                blackboard.propose_action(
                    action="test_action",
                    source_name=self.name,
                    reason_code="test_reason",
                )

        # Register
        SourceRegistry.register(
            TestSource,
            name="TestSource",
            priority_order=10,
            description="Test source"
        )

        # Create
        sources = SourceRegistry.create_sources()

        # Use
        mock_bb = Mock()
        mock_bb.current_intent = "test_intent"

        assert len(sources) == 1
        source = sources[0]

        assert source.should_contribute(mock_bb) is True
        source.contribute(mock_bb)
        mock_bb.propose_action.assert_called_once()

    def test_multiple_sources_ordered_execution(self):
        """Test multiple sources execute in priority order."""
        execution_order = []

        class Source1(KnowledgeSource):
            def contribute(self, bb):
                execution_order.append(self.name)

        class Source2(KnowledgeSource):
            def contribute(self, bb):
                execution_order.append(self.name)

        class Source3(KnowledgeSource):
            def contribute(self, bb):
                execution_order.append(self.name)

        SourceRegistry.register(Source1, name="Source1", priority_order=30)
        SourceRegistry.register(Source2, name="Source2", priority_order=10)
        SourceRegistry.register(Source3, name="Source3", priority_order=20)

        sources = SourceRegistry.create_sources()
        mock_bb = Mock()

        # Execute in order
        for source in sources:
            source.contribute(mock_bb)

        assert execution_order == ["Source2", "Source3", "Source1"]

    def test_config_driven_source_selection(self):
        """Test configuration-driven source selection."""
        class ProdSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        class DebugSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        class TestSource(KnowledgeSource):
            def contribute(self, bb):
                pass

        SourceRegistry.register(ProdSource, name="ProdSource")
        SourceRegistry.register(DebugSource, name="DebugSource", enabled_by_default=False)
        SourceRegistry.register(TestSource, name="TestSource", enabled_by_default=False)

        # Production config
        prod_config = {
            "sources": {
                "ProdSource": {"enabled": True},
                "DebugSource": {"enabled": False},
            }
        }

        prod_sources = SourceRegistry.create_sources(config=prod_config)
        assert len(prod_sources) == 1
        assert prod_sources[0].name == "ProdSource"

        # Debug config
        debug_config = {
            "sources": {
                "DebugSource": {"enabled": True},
            }
        }

        debug_sources = SourceRegistry.create_sources(config=debug_config)
        # ProdSource enabled by default, DebugSource enabled by config
        assert len(debug_sources) == 2
        source_names = [s.name for s in debug_sources]
        assert "ProdSource" in source_names
        assert "DebugSource" in source_names

"""
Tests for multi-tenant configuration scenarios.

This module tests:
1. Separate configs for different tenants
2. Config inheritance between base and tenant
3. Tenant config isolation
4. Tenant config override patterns
5. Dynamic tenant config loading
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml
import sys
import copy
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# MULTI-TENANT CONFIG MANAGER
# =============================================================================

class TenantConfigManager:
    """
    Manages configurations for multiple tenants.

    Supports:
    - Base config with defaults
    - Per-tenant overrides
    - Config inheritance
    - Tenant isolation
    """

    def __init__(self, base_config: Dict[str, Any]):
        self.base_config = base_config
        self._tenant_configs: Dict[str, Dict[str, Any]] = {}
        self._tenant_overrides: Dict[str, Dict[str, Any]] = {}

    def register_tenant(self, tenant_id: str, overrides: Dict[str, Any] = None):
        """
        Register a tenant with optional config overrides.

        Args:
            tenant_id: Unique tenant identifier
            overrides: Config values to override from base
        """
        if overrides:
            self._tenant_overrides[tenant_id] = overrides
        self._tenant_configs[tenant_id] = self._build_tenant_config(tenant_id)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = copy.deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def _build_tenant_config(self, tenant_id: str) -> Dict[str, Any]:
        """Build complete config for a tenant."""
        config = copy.deepcopy(self.base_config)
        overrides = self._tenant_overrides.get(tenant_id, {})
        return self._deep_merge(config, overrides)

    def get_config(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get configuration for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Complete config for the tenant (deep copy for isolation)

        Raises:
            KeyError: If tenant not registered
        """
        if tenant_id not in self._tenant_configs:
            raise KeyError(f"Tenant '{tenant_id}' not registered")
        # Return deep copy to ensure isolation
        return copy.deepcopy(self._tenant_configs[tenant_id])

    def update_tenant_config(self, tenant_id: str, updates: Dict[str, Any]):
        """
        Update specific config values for a tenant.

        Args:
            tenant_id: Tenant identifier
            updates: Config updates to apply
        """
        if tenant_id not in self._tenant_configs:
            raise KeyError(f"Tenant '{tenant_id}' not registered")

        current_overrides = self._tenant_overrides.get(tenant_id, {})
        self._tenant_overrides[tenant_id] = self._deep_merge(current_overrides, updates)
        self._tenant_configs[tenant_id] = self._build_tenant_config(tenant_id)

    def reset_tenant_to_base(self, tenant_id: str):
        """Reset tenant config to base config."""
        if tenant_id in self._tenant_overrides:
            del self._tenant_overrides[tenant_id]
        self._tenant_configs[tenant_id] = copy.deepcopy(self.base_config)

    def list_tenants(self) -> list:
        """List all registered tenant IDs."""
        return list(self._tenant_configs.keys())

    def get_tenant_overrides(self, tenant_id: str) -> Dict[str, Any]:
        """Get only the override values for a tenant."""
        return self._tenant_overrides.get(tenant_id, {})


# =============================================================================
# BASIC MULTI-TENANT TESTS
# =============================================================================

class TestBasicMultiTenant:
    """Tests for basic multi-tenant config operations."""

    @pytest.fixture
    def base_config(self):
        """Base configuration for all tenants."""
        return {
            "guard": {
                "max_turns": 25,
                "max_phase_attempts": 3,
                "timeout_seconds": 1800
            },
            "limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5
            },
            "lead_scoring": {
                "thresholds": {
                    "cold": [0, 29],
                    "warm": [30, 49],
                    "hot": [50, 69],
                    "very_hot": [70, 100]
                }
            },
            "company": {
                "name": "Default Company",
                "product": "Default Product"
            }
        }

    @pytest.fixture
    def manager(self, base_config):
        """Tenant config manager with base config."""
        return TenantConfigManager(base_config)

    def test_register_tenant_with_no_overrides(self, manager, base_config):
        """Tenant with no overrides gets base config."""
        manager.register_tenant("tenant_a")

        config = manager.get_config("tenant_a")
        assert config == base_config

    def test_register_tenant_with_overrides(self, manager):
        """Tenant with overrides gets merged config."""
        manager.register_tenant("tenant_a", {
            "company": {
                "name": "Tenant A Corp"
            }
        })

        config = manager.get_config("tenant_a")
        assert config["company"]["name"] == "Tenant A Corp"
        assert config["company"]["product"] == "Default Product"  # From base

    def test_multiple_tenants_isolated(self, manager):
        """Changes to one tenant don't affect others."""
        manager.register_tenant("tenant_a", {"guard": {"max_turns": 10}})
        manager.register_tenant("tenant_b", {"guard": {"max_turns": 50}})

        config_a = manager.get_config("tenant_a")
        config_b = manager.get_config("tenant_b")

        assert config_a["guard"]["max_turns"] == 10
        assert config_b["guard"]["max_turns"] == 50

    def test_unregistered_tenant_raises(self, manager):
        """Getting config for unregistered tenant raises error."""
        with pytest.raises(KeyError):
            manager.get_config("nonexistent_tenant")

    def test_list_tenants(self, manager):
        """List all registered tenants."""
        manager.register_tenant("tenant_a")
        manager.register_tenant("tenant_b")
        manager.register_tenant("tenant_c")

        tenants = manager.list_tenants()
        assert set(tenants) == {"tenant_a", "tenant_b", "tenant_c"}


class TestTenantConfigInheritance:
    """Tests for config inheritance patterns."""

    @pytest.fixture
    def base_config(self):
        return {
            "guard": {
                "max_turns": 25,
                "max_phase_attempts": 3,
                "max_same_state": 4,
                "timeout_seconds": 1800
            },
            "frustration": {
                "max_level": 10,
                "thresholds": {
                    "warning": 4,
                    "high": 7,
                    "critical": 9
                }
            }
        }

    @pytest.fixture
    def manager(self, base_config):
        return TenantConfigManager(base_config)

    def test_partial_override_preserves_other_values(self, manager):
        """Partial override keeps other values from base."""
        manager.register_tenant("tenant_a", {
            "guard": {
                "max_turns": 10  # Override only this
            }
        })

        config = manager.get_config("tenant_a")

        assert config["guard"]["max_turns"] == 10  # Overridden
        assert config["guard"]["max_phase_attempts"] == 3  # From base
        assert config["guard"]["max_same_state"] == 4  # From base
        assert config["guard"]["timeout_seconds"] == 1800  # From base

    def test_nested_partial_override(self, manager):
        """Nested dict partial override."""
        manager.register_tenant("tenant_a", {
            "frustration": {
                "thresholds": {
                    "high": 5  # Only change high threshold
                }
            }
        })

        config = manager.get_config("tenant_a")
        thresholds = config["frustration"]["thresholds"]

        assert thresholds["warning"] == 4  # From base
        assert thresholds["high"] == 5  # Overridden
        assert thresholds["critical"] == 9  # From base

    def test_add_new_key_in_override(self, manager):
        """Override can add new keys not in base."""
        manager.register_tenant("tenant_a", {
            "custom_feature": {
                "enabled": True,
                "setting": "value"
            }
        })

        config = manager.get_config("tenant_a")

        assert "custom_feature" in config
        assert config["custom_feature"]["enabled"] is True


class TestTenantConfigIsolation:
    """Tests for tenant config isolation."""

    @pytest.fixture
    def base_config(self):
        return {
            "data": {"shared": "value"},
            "settings": {"param": 1}
        }

    @pytest.fixture
    def manager(self, base_config):
        return TenantConfigManager(base_config)

    def test_modifying_returned_config_doesnt_affect_stored(self, manager):
        """Modifying returned config doesn't affect stored config."""
        manager.register_tenant("tenant_a")

        config = manager.get_config("tenant_a")
        config["data"]["shared"] = "modified"

        # Get again - should be original
        config2 = manager.get_config("tenant_a")
        assert config2["data"]["shared"] == "value"

    def test_tenant_configs_are_independent_copies(self, manager):
        """Each tenant gets independent copy."""
        manager.register_tenant("tenant_a")
        manager.register_tenant("tenant_b")

        config_a = manager.get_config("tenant_a")
        config_b = manager.get_config("tenant_b")

        # Modify a
        config_a["data"]["shared"] = "modified_a"

        # b should be unaffected
        assert config_b["data"]["shared"] == "value"

    def test_base_config_not_modified_by_tenants(self, manager, base_config):
        """Base config is never modified by tenant operations."""
        original_value = base_config["data"]["shared"]

        manager.register_tenant("tenant_a", {"data": {"shared": "tenant_value"}})

        # Base config unchanged
        assert base_config["data"]["shared"] == original_value


class TestTenantConfigUpdates:
    """Tests for updating tenant configurations."""

    @pytest.fixture
    def base_config(self):
        return {
            "guard": {"max_turns": 25},
            "limits": {"max_objections": 5}
        }

    @pytest.fixture
    def manager(self, base_config):
        return TenantConfigManager(base_config)

    def test_update_tenant_config(self, manager):
        """Update specific tenant config values."""
        manager.register_tenant("tenant_a", {"guard": {"max_turns": 10}})

        manager.update_tenant_config("tenant_a", {"guard": {"max_turns": 15}})

        config = manager.get_config("tenant_a")
        assert config["guard"]["max_turns"] == 15

    def test_update_preserves_other_overrides(self, manager):
        """Update preserves other tenant overrides."""
        manager.register_tenant("tenant_a", {
            "guard": {"max_turns": 10},
            "limits": {"max_objections": 3}
        })

        manager.update_tenant_config("tenant_a", {"guard": {"max_turns": 20}})

        config = manager.get_config("tenant_a")
        assert config["guard"]["max_turns"] == 20
        assert config["limits"]["max_objections"] == 3  # Preserved

    def test_reset_tenant_to_base(self, manager, base_config):
        """Reset tenant to base config."""
        manager.register_tenant("tenant_a", {"guard": {"max_turns": 10}})

        manager.reset_tenant_to_base("tenant_a")

        config = manager.get_config("tenant_a")
        assert config["guard"]["max_turns"] == 25  # Base value

    def test_get_tenant_overrides_only(self, manager):
        """Get only the override values for a tenant."""
        overrides = {"guard": {"max_turns": 10}}
        manager.register_tenant("tenant_a", overrides)

        retrieved = manager.get_tenant_overrides("tenant_a")
        assert retrieved == overrides


class TestTenantSpecificFeatures:
    """Tests for tenant-specific feature configurations."""

    @pytest.fixture
    def base_config(self):
        return {
            "features": {
                "spin_enabled": True,
                "advanced_analytics": False,
                "custom_branding": False
            },
            "branding": {
                "primary_color": "#007bff",
                "logo_url": "/default-logo.png"
            }
        }

    @pytest.fixture
    def manager(self, base_config):
        return TenantConfigManager(base_config)

    def test_enable_feature_for_tenant(self, manager):
        """Enable optional feature for specific tenant."""
        manager.register_tenant("premium_tenant", {
            "features": {
                "advanced_analytics": True,
                "custom_branding": True
            }
        })
        manager.register_tenant("basic_tenant")

        premium = manager.get_config("premium_tenant")
        basic = manager.get_config("basic_tenant")

        assert premium["features"]["advanced_analytics"] is True
        assert basic["features"]["advanced_analytics"] is False

    def test_tenant_branding(self, manager):
        """Different branding per tenant."""
        manager.register_tenant("tenant_a", {
            "branding": {
                "primary_color": "#ff0000",
                "logo_url": "/tenant-a-logo.png"
            }
        })
        manager.register_tenant("tenant_b", {
            "branding": {
                "primary_color": "#00ff00",
                "logo_url": "/tenant-b-logo.png"
            }
        })

        config_a = manager.get_config("tenant_a")
        config_b = manager.get_config("tenant_b")

        assert config_a["branding"]["primary_color"] == "#ff0000"
        assert config_b["branding"]["primary_color"] == "#00ff00"


class TestTenantConfigValidation:
    """Tests for validating tenant configurations."""

    @pytest.fixture
    def base_config(self):
        return {
            "guard": {
                "max_turns": 25,
                "high_frustration_threshold": 7
            },
            "frustration": {
                "thresholds": {"high": 7}
            }
        }

    @pytest.fixture
    def manager(self, base_config):
        return TenantConfigManager(base_config)

    def test_validate_tenant_config_thresholds(self, manager):
        """Validate that tenant config maintains threshold sync."""
        manager.register_tenant("tenant_a", {
            "guard": {"high_frustration_threshold": 5},
            "frustration": {"thresholds": {"high": 5}}
        })

        config = manager.get_config("tenant_a")

        def validate_threshold_sync(config):
            guard_th = config["guard"]["high_frustration_threshold"]
            frust_th = config["frustration"]["thresholds"]["high"]
            return guard_th == frust_th

        assert validate_threshold_sync(config)

    def test_detect_invalid_tenant_config(self, manager):
        """Detect invalid tenant configuration."""
        # Register with mismatched thresholds
        manager.register_tenant("bad_tenant", {
            "guard": {"high_frustration_threshold": 5},
            "frustration": {"thresholds": {"high": 8}}  # Mismatch!
        })

        config = manager.get_config("bad_tenant")

        def validate_threshold_sync(config):
            guard_th = config["guard"]["high_frustration_threshold"]
            frust_th = config["frustration"]["thresholds"]["high"]
            return guard_th == frust_th

        assert not validate_threshold_sync(config)  # Should detect mismatch


class TestDynamicTenantLoading:
    """Tests for dynamically loading tenant configurations."""

    @pytest.fixture
    def base_config(self):
        return {"default": "value"}

    @pytest.fixture
    def manager(self, base_config):
        return TenantConfigManager(base_config)

    def test_load_tenant_from_yaml(self, manager, tmp_path):
        """Load tenant config from YAML file."""
        tenant_config_file = tmp_path / "tenant_a.yaml"
        tenant_config_file.write_text(yaml.dump({
            "custom_setting": "tenant_a_value"
        }), encoding='utf-8')

        with open(tenant_config_file, 'r', encoding='utf-8') as f:
            overrides = yaml.safe_load(f)

        manager.register_tenant("tenant_a", overrides)

        config = manager.get_config("tenant_a")
        assert config["custom_setting"] == "tenant_a_value"

    def test_load_multiple_tenants_from_directory(self, manager, tmp_path):
        """Load multiple tenant configs from directory."""
        # Create tenant config files
        (tmp_path / "tenant_a.yaml").write_text(yaml.dump({"name": "A"}))
        (tmp_path / "tenant_b.yaml").write_text(yaml.dump({"name": "B"}))
        (tmp_path / "tenant_c.yaml").write_text(yaml.dump({"name": "C"}))

        # Load all tenant configs
        for config_file in tmp_path.glob("*.yaml"):
            tenant_id = config_file.stem
            with open(config_file, 'r', encoding='utf-8') as f:
                overrides = yaml.safe_load(f)
            manager.register_tenant(tenant_id, overrides)

        assert len(manager.list_tenants()) == 3
        assert manager.get_config("tenant_a")["name"] == "A"
        assert manager.get_config("tenant_b")["name"] == "B"
        assert manager.get_config("tenant_c")["name"] == "C"


class TestTenantConfigCaching:
    """Tests for tenant config caching behavior."""

    @pytest.fixture
    def base_config(self):
        return {"value": 1}

    @pytest.fixture
    def manager(self, base_config):
        return TenantConfigManager(base_config)

    def test_config_built_once_per_registration(self, manager):
        """Config is built once when tenant is registered."""
        call_count = 0

        original_build = manager._build_tenant_config

        def counting_build(tenant_id):
            nonlocal call_count
            call_count += 1
            return original_build(tenant_id)

        manager._build_tenant_config = counting_build

        manager.register_tenant("tenant_a", {"value": 2})

        # Get config multiple times
        manager.get_config("tenant_a")
        manager.get_config("tenant_a")
        manager.get_config("tenant_a")

        # Build should only be called once (during registration)
        assert call_count == 1

    def test_config_rebuilt_on_update(self, manager):
        """Config is rebuilt when tenant is updated."""
        manager.register_tenant("tenant_a", {"value": 1})

        config1 = manager.get_config("tenant_a")
        assert config1["value"] == 1

        manager.update_tenant_config("tenant_a", {"value": 2})

        config2 = manager.get_config("tenant_a")
        assert config2["value"] == 2

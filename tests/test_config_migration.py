"""
Tests for configuration migration between versions.

This module tests:
1. Backwards compatibility with old config formats
2. Config version detection
3. Automatic migration scripts
4. Deprecation warnings
5. Migration validation
"""

import pytest
from pathlib import Path
import yaml
import sys
import copy
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

# =============================================================================
# CONFIG MIGRATION FRAMEWORK
# =============================================================================

@dataclass
class MigrationStep:
    """Represents a single migration step."""
    from_version: str
    to_version: str
    description: str
    migrate: Callable[[Dict[str, Any]], Dict[str, Any]]
    validate: Optional[Callable[[Dict[str, Any]], List[str]]] = None

class ConfigMigrator:
    """
    Manages configuration migrations between versions.

    Supports:
    - Version detection
    - Sequential migration steps
    - Backwards compatibility
    - Validation after migration
    """

    def __init__(self):
        self._migrations: List[MigrationStep] = []
        self._deprecations: Dict[str, str] = {}

    def register_migration(
        self,
        from_version: str,
        to_version: str,
        description: str,
        migrate_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        validate_fn: Optional[Callable[[Dict[str, Any]], List[str]]] = None
    ):
        """Register a migration step."""
        self._migrations.append(MigrationStep(
            from_version=from_version,
            to_version=to_version,
            description=description,
            migrate=migrate_fn,
            validate=validate_fn
        ))

    def register_deprecation(self, old_key: str, message: str):
        """Register a deprecation warning."""
        self._deprecations[old_key] = message

    def detect_version(self, config: Dict[str, Any]) -> str:
        """
        Detect config version.

        Returns:
            Version string (e.g., "1.0", "2.0")
        """
        # Check for explicit version
        if "version" in config:
            return str(config["version"])
        if "meta" in config and "version" in config["meta"]:
            return str(config["meta"]["version"])

        # Infer version from structure
        if self._is_v1_format(config):
            return "1.0"
        elif self._is_v2_format(config):
            return "2.0"

        return "unknown"

    def _is_v1_format(self, config: Dict[str, Any]) -> bool:
        """Check if config is v1 format."""
        # V1 had flat structure, some different key names
        return (
            "max_turns" in config or
            "conversation_guard" in config or
            "spin_phases" in config.get("spin", {})
        )

    def _is_v2_format(self, config: Dict[str, Any]) -> bool:
        """Check if config is v2 format."""
        # V2 has nested structure under guard, etc.
        return (
            "guard" in config and
            isinstance(config.get("guard"), dict) and
            "max_turns" in config.get("guard", {})
        )

    def get_migration_path(self, from_version: str, to_version: str) -> List[MigrationStep]:
        """
        Get sequence of migrations from one version to another.

        Args:
            from_version: Starting version
            to_version: Target version

        Returns:
            List of migration steps to apply in order
        """
        path = []
        current = from_version

        while current != to_version:
            found = False
            for migration in self._migrations:
                if migration.from_version == current:
                    path.append(migration)
                    current = migration.to_version
                    found = True
                    break

            if not found:
                if current == to_version:
                    break
                raise ValueError(f"No migration path from {current} to {to_version}")

        return path

    def migrate(
        self,
        config: Dict[str, Any],
        to_version: str = None
    ) -> tuple[Dict[str, Any], List[str]]:
        """
        Migrate config to target version.

        Args:
            config: Configuration to migrate
            to_version: Target version (default: latest)

        Returns:
            Tuple of (migrated_config, warnings)
        """
        warnings = []

        # Detect current version
        current_version = self.detect_version(config)

        if to_version is None:
            # Migrate to latest
            to_version = self._get_latest_version()

        if current_version == to_version:
            return config, ["Config already at target version"]

        # Get migration path
        try:
            path = self.get_migration_path(current_version, to_version)
        except ValueError as e:
            return config, [str(e)]

        # Apply migrations
        result = copy.deepcopy(config)
        for step in path:
            warnings.append(f"Applying migration: {step.description}")
            result = step.migrate(result)

            # Validate if validator provided
            if step.validate:
                errors = step.validate(result)
                if errors:
                    warnings.extend([f"Validation warning: {e}" for e in errors])

        # Check for deprecated keys
        deprecation_warnings = self._check_deprecations(result)
        warnings.extend(deprecation_warnings)

        # Update version
        result["version"] = to_version

        return result, warnings

    def _get_latest_version(self) -> str:
        """Get the latest version from registered migrations."""
        if not self._migrations:
            return "1.0"
        versions = set()
        for m in self._migrations:
            versions.add(m.from_version)
            versions.add(m.to_version)
        return max(versions, key=lambda v: [int(x) for x in v.split(".")])

    def _check_deprecations(self, config: Dict[str, Any]) -> List[str]:
        """Check for deprecated keys in config."""
        warnings = []

        def check_recursive(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    full_path = f"{path}.{key}" if path else key
                    if full_path in self._deprecations:
                        warnings.append(
                            f"Deprecated: {full_path} - {self._deprecations[full_path]}"
                        )
                    check_recursive(value, full_path)

        check_recursive(config)
        return warnings

# =============================================================================
# MIGRATION FUNCTIONS
# =============================================================================

def migrate_v1_to_v1_5(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate from v1.0 to v1.5.

    Changes:
    - Move flat guard params under 'guard' key
    - Rename 'conversation_guard' to 'guard'
    """
    result = copy.deepcopy(config)

    # Handle flat guard params
    guard_params = ['max_turns', 'max_phase_attempts', 'max_same_state', 'timeout_seconds']
    guard_config = {}

    for param in guard_params:
        if param in result:
            guard_config[param] = result.pop(param)

    # Handle old conversation_guard key
    if 'conversation_guard' in result:
        old_guard = result.pop('conversation_guard')
        guard_config.update(old_guard)

    if guard_config:
        result['guard'] = guard_config

    return result

def migrate_v1_5_to_v2(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate from v1.5 to v2.0.

    Changes:
    - spin.spin_phases -> spin.phases
    - spin.spin_states -> spin.states
    - Add lead_scoring.paths structure
    """
    result = copy.deepcopy(config)

    # Rename spin keys
    if 'spin' in result:
        spin = result['spin']

        if 'spin_phases' in spin:
            spin['phases'] = spin.pop('spin_phases')

        if 'spin_states' in spin:
            spin['states'] = spin.pop('spin_states')

    # Add default paths if not present
    if 'lead_scoring' in result:
        if 'paths' not in result['lead_scoring']:
            result['lead_scoring']['paths'] = {
                'cold': 'full_spin',
                'warm': 'short_spin',
                'hot': 'direct_present',
                'very_hot': 'direct_close'
            }

    return result

def migrate_v2_to_v2_1(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate from v2.0 to v2.1.

    Changes:
    - Add frustration.thresholds if missing
    - Sync guard.high_frustration_threshold with frustration.thresholds.high
    """
    result = copy.deepcopy(config)

    # Ensure frustration exists
    if 'frustration' not in result:
        result['frustration'] = {}

    # Ensure thresholds exist
    if 'thresholds' not in result['frustration']:
        result['frustration']['thresholds'] = {
            'warning': 4,
            'high': 7,
            'critical': 9
        }

    # Sync guard threshold
    if 'guard' in result:
        guard_threshold = result['guard'].get('high_frustration_threshold')
        if guard_threshold is not None:
            result['frustration']['thresholds']['high'] = guard_threshold
        else:
            # Set from frustration
            result['guard']['high_frustration_threshold'] = result['frustration']['thresholds']['high']

    return result

# =============================================================================
# MIGRATION TESTS
# =============================================================================

class TestVersionDetection:
    """Tests for config version detection."""

    @pytest.fixture
    def migrator(self):
        m = ConfigMigrator()
        m.register_migration("1.0", "1.5", "v1 to v1.5", migrate_v1_to_v1_5)
        m.register_migration("1.5", "2.0", "v1.5 to v2", migrate_v1_5_to_v2)
        m.register_migration("2.0", "2.1", "v2 to v2.1", migrate_v2_to_v2_1)
        return m

    def test_detect_explicit_version(self, migrator):
        """Detect version from explicit version field."""
        config = {"version": "2.0", "guard": {"max_turns": 25}}
        assert migrator.detect_version(config) == "2.0"

    def test_detect_meta_version(self, migrator):
        """Detect version from meta.version field."""
        config = {"meta": {"version": "1.5"}, "guard": {"max_turns": 25}}
        assert migrator.detect_version(config) == "1.5"

    def test_detect_v1_format(self, migrator):
        """Detect v1 format from structure."""
        config = {
            "max_turns": 25,
            "max_phase_attempts": 3
        }
        assert migrator.detect_version(config) == "1.0"

    def test_detect_v2_format(self, migrator):
        """Detect v2 format from structure."""
        config = {
            "guard": {
                "max_turns": 25,
                "max_phase_attempts": 3
            }
        }
        assert migrator.detect_version(config) == "2.0"

class TestMigrationPath:
    """Tests for migration path calculation."""

    @pytest.fixture
    def migrator(self):
        m = ConfigMigrator()
        m.register_migration("1.0", "1.5", "v1 to v1.5", migrate_v1_to_v1_5)
        m.register_migration("1.5", "2.0", "v1.5 to v2", migrate_v1_5_to_v2)
        m.register_migration("2.0", "2.1", "v2 to v2.1", migrate_v2_to_v2_1)
        return m

    def test_single_step_path(self, migrator):
        """Single migration step."""
        path = migrator.get_migration_path("1.0", "1.5")
        assert len(path) == 1
        assert path[0].from_version == "1.0"
        assert path[0].to_version == "1.5"

    def test_multi_step_path(self, migrator):
        """Multiple migration steps."""
        path = migrator.get_migration_path("1.0", "2.0")
        assert len(path) == 2
        assert path[0].from_version == "1.0"
        assert path[1].from_version == "1.5"

    def test_full_migration_path(self, migrator):
        """Full migration from v1 to v2.1."""
        path = migrator.get_migration_path("1.0", "2.1")
        assert len(path) == 3

    def test_no_path_for_same_version(self, migrator):
        """No migration needed for same version."""
        path = migrator.get_migration_path("2.0", "2.0")
        assert len(path) == 0

    def test_invalid_path_raises(self, migrator):
        """Invalid path raises error."""
        with pytest.raises(ValueError):
            migrator.get_migration_path("2.1", "1.0")  # Can't go backwards

class TestV1ToV15Migration:
    """Tests for v1.0 to v1.5 migration."""

    @pytest.fixture
    def migrator(self):
        m = ConfigMigrator()
        m.register_migration("1.0", "1.5", "v1 to v1.5", migrate_v1_to_v1_5)
        return m

    def test_migrate_flat_guard_params(self, migrator):
        """Flat guard params move under 'guard' key."""
        v1_config = {
            "max_turns": 25,
            "max_phase_attempts": 3,
            "max_same_state": 4,
            "timeout_seconds": 1800,
            "other_setting": "value"
        }

        result, warnings = migrator.migrate(v1_config, "1.5")

        assert "guard" in result
        assert result["guard"]["max_turns"] == 25
        assert result["guard"]["max_phase_attempts"] == 3
        assert "max_turns" not in result  # Moved
        assert result["other_setting"] == "value"  # Preserved

    def test_migrate_conversation_guard_key(self, migrator):
        """Old 'conversation_guard' key renamed to 'guard'."""
        v1_config = {
            "conversation_guard": {
                "max_turns": 25,
                "timeout_seconds": 1800
            }
        }

        result, warnings = migrator.migrate(v1_config, "1.5")

        assert "guard" in result
        assert "conversation_guard" not in result
        assert result["guard"]["max_turns"] == 25

class TestV15ToV2Migration:
    """Tests for v1.5 to v2.0 migration."""

    @pytest.fixture
    def migrator(self):
        m = ConfigMigrator()
        m.register_migration("1.5", "2.0", "v1.5 to v2", migrate_v1_5_to_v2)
        return m

    def test_migrate_spin_phases_key(self, migrator):
        """spin.spin_phases -> spin.phases."""
        v15_config = {
            "version": "1.5",
            "spin": {
                "spin_phases": ["situation", "problem", "implication", "need_payoff"]
            }
        }

        result, warnings = migrator.migrate(v15_config, "2.0")

        assert "phases" in result["spin"]
        assert "spin_phases" not in result["spin"]
        assert result["spin"]["phases"] == ["situation", "problem", "implication", "need_payoff"]

    def test_migrate_spin_states_key(self, migrator):
        """spin.spin_states -> spin.states."""
        v15_config = {
            "version": "1.5",
            "spin": {
                "spin_states": {
                    "situation": "spin_situation",
                    "problem": "spin_problem"
                }
            }
        }

        result, warnings = migrator.migrate(v15_config, "2.0")

        assert "states" in result["spin"]
        assert "spin_states" not in result["spin"]

    def test_add_lead_scoring_paths(self, migrator):
        """Default paths added to lead_scoring."""
        v15_config = {
            "version": "1.5",
            "lead_scoring": {
                "thresholds": {"cold": [0, 29]}
            }
        }

        result, warnings = migrator.migrate(v15_config, "2.0")

        assert "paths" in result["lead_scoring"]
        assert result["lead_scoring"]["paths"]["cold"] == "full_spin"

class TestV2ToV21Migration:
    """Tests for v2.0 to v2.1 migration."""

    @pytest.fixture
    def migrator(self):
        m = ConfigMigrator()
        m.register_migration("2.0", "2.1", "v2 to v2.1", migrate_v2_to_v2_1)
        return m

    def test_add_frustration_thresholds(self, migrator):
        """Add frustration.thresholds if missing."""
        v2_config = {
            "version": "2.0",
            "guard": {"max_turns": 25}
        }

        result, warnings = migrator.migrate(v2_config, "2.1")

        assert "frustration" in result
        assert "thresholds" in result["frustration"]
        assert result["frustration"]["thresholds"]["high"] == 7

    def test_sync_guard_frustration_threshold(self, migrator):
        """Sync guard.high_frustration_threshold with frustration."""
        v2_config = {
            "version": "2.0",
            "guard": {
                "max_turns": 25,
                "high_frustration_threshold": 5
            },
            "frustration": {
                "thresholds": {"warning": 4, "high": 7, "critical": 9}
            }
        }

        result, warnings = migrator.migrate(v2_config, "2.1")

        # Should sync from guard to frustration
        assert result["frustration"]["thresholds"]["high"] == 5

class TestFullMigration:
    """Tests for full migration from v1 to latest."""

    @pytest.fixture
    def migrator(self):
        m = ConfigMigrator()
        m.register_migration("1.0", "1.5", "v1 to v1.5", migrate_v1_to_v1_5)
        m.register_migration("1.5", "2.0", "v1.5 to v2", migrate_v1_5_to_v2)
        m.register_migration("2.0", "2.1", "v2 to v2.1", migrate_v2_to_v2_1)
        return m

    def test_migrate_v1_to_latest(self, migrator):
        """Full migration from v1 to v2.1."""
        v1_config = {
            "max_turns": 25,
            "max_phase_attempts": 3,
            "spin": {
                "spin_phases": ["situation", "problem"],
                "spin_states": {"situation": "spin_situation"}
            },
            "lead_scoring": {
                "thresholds": {"cold": [0, 29]}
            }
        }

        result, warnings = migrator.migrate(v1_config, "2.1")

        # Check v1.5 migrations applied
        assert "guard" in result
        assert result["guard"]["max_turns"] == 25

        # Check v2.0 migrations applied
        assert "phases" in result["spin"]
        assert "paths" in result["lead_scoring"]

        # Check v2.1 migrations applied
        assert "frustration" in result
        assert result["version"] == "2.1"

    def test_migration_warnings_collected(self, migrator):
        """All migration warnings are collected."""
        v1_config = {"max_turns": 25}

        result, warnings = migrator.migrate(v1_config, "2.1")

        assert len(warnings) >= 3  # At least one per migration step

class TestDeprecations:
    """Tests for deprecation warnings."""

    @pytest.fixture
    def migrator(self):
        m = ConfigMigrator()
        m.register_deprecation(
            "conversation_guard",
            "Use 'guard' instead. Will be removed in v3.0"
        )
        m.register_deprecation(
            "spin.spin_phases",
            "Use 'spin.phases' instead. Will be removed in v3.0"
        )
        return m

    def test_deprecation_warning_for_old_key(self, migrator):
        """Deprecation warning issued for old keys."""
        config = {
            "version": "2.0",
            "conversation_guard": {"max_turns": 25},
            "spin": {
                "spin_phases": ["situation"]
            }
        }

        # Check deprecations directly (migrate may skip if version matches)
        deprecation_warnings = migrator._check_deprecations(config)

        assert len(deprecation_warnings) >= 2
        assert any("conversation_guard" in w for w in deprecation_warnings)
        assert any("spin_phases" in w for w in deprecation_warnings)

class TestBackwardsCompatibility:
    """Tests for backwards compatibility."""

    def test_old_config_still_loads(self, config_factory):
        """Old config format can still be loaded."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()

        # Create old-style constants (simulating v1 format)
        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        # Add some old-style keys
        constants['conversation_guard'] = constants.get('guard', {})

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        # Should still load (ConfigLoader handles both)
        loader = ConfigLoader(config_dir)
        config = loader.load(validate=False)

        assert config is not None

    def test_missing_new_keys_use_defaults(self, config_factory):
        """Missing new keys get default values."""
        from src.settings import load_settings, DotDict, _deep_merge, DEFAULTS

        # Create minimal config
        minimal = DotDict({
            "llm": {"model": "test"}
        })

        # Merge with defaults
        merged = _deep_merge(DEFAULTS, dict(minimal))

        # New keys from defaults should be present
        assert "retriever" in merged
        assert "generator" in merged
        assert merged["llm"]["model"] == "test"  # Override preserved

    def test_extra_keys_preserved(self, config_factory):
        """Unknown/extra keys are preserved through migration."""
        migrator = ConfigMigrator()
        migrator.register_migration("1.0", "1.5", "test", lambda c: c)

        config = {
            "max_turns": 25,
            "custom_key": "custom_value",
            "another_custom": {"nested": "data"}
        }

        result, _ = migrator.migrate(config, "1.5")

        assert result["custom_key"] == "custom_value"
        assert result["another_custom"]["nested"] == "data"

class TestMigrationValidation:
    """Tests for migration validation."""

    def test_validate_after_migration(self):
        """Validation runs after migration."""

        def validator(config):
            errors = []
            if "guard" in config:
                if config["guard"].get("max_turns", 0) <= 0:
                    errors.append("max_turns must be positive")
            return errors

        migrator = ConfigMigrator()
        migrator.register_migration(
            "1.0", "1.5",
            "v1 to v1.5",
            migrate_v1_to_v1_5,
            validator
        )

        # Config with invalid value
        config = {"max_turns": -5}

        result, warnings = migrator.migrate(config, "1.5")

        # Warning should be present
        assert any("must be positive" in w for w in warnings)

    def test_migration_preserves_valid_config(self):
        """Valid config passes through migration unchanged (except version)."""
        migrator = ConfigMigrator()
        migrator.register_migration(
            "2.0", "2.1",
            "v2 to v2.1",
            migrate_v2_to_v2_1
        )

        config = {
            "version": "2.0",
            "guard": {
                "max_turns": 25,
                "high_frustration_threshold": 7
            },
            "frustration": {
                "thresholds": {"warning": 4, "high": 7, "critical": 9}
            }
        }

        result, warnings = migrator.migrate(config, "2.1")

        # Core values unchanged
        assert result["guard"]["max_turns"] == 25
        assert result["guard"]["high_frustration_threshold"] == 7
        assert result["version"] == "2.1"

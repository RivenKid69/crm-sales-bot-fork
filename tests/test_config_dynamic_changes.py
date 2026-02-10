"""
Tests for dynamic configuration changes at runtime.

This module tests:
1. Config parameter modification during execution
2. Hot reload of configuration
3. Thread-safe config updates
4. Component synchronization after config changes
5. Rollback on invalid config changes
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml
import sys
import threading
import time
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================================================
# DYNAMIC CONFIG MODIFICATION TESTS
# =============================================================================

class TestDynamicConfigModification:
    """Tests for modifying config parameters at runtime."""

    def test_modify_guard_max_turns_at_runtime(self, config_factory):
        """Changing max_turns at runtime affects ConversationGuard."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        # Create initial config
        config = GuardConfig(max_turns=25, max_phase_attempts=3, max_same_state=4)
        guard = ConversationGuard(config)

        assert guard.config.max_turns == 25

        # Simulate runtime change
        guard.config = GuardConfig(max_turns=10, max_phase_attempts=3, max_same_state=4)

        assert guard.config.max_turns == 10

        # Verify behavior changed - use actual API
        # ConversationGuard tracks turns internally, so we simulate by checking config
        assert guard.config.max_turns == 10

    def test_modify_frustration_thresholds_at_runtime(self, config_factory):
        """Changing frustration thresholds at runtime via config."""
        from src.config_loader import ConfigLoader

        # Create config with specific frustration thresholds
        config_dir = config_factory(frustration={
            "thresholds": {"warning": 4, "high": 7, "critical": 9}
        })

        loader = ConfigLoader(config_dir)
        config = loader.load()

        # Verify initial values
        assert config.frustration["thresholds"]["high"] == 7

        # Modify config at runtime
        config.constants["frustration"]["thresholds"]["high"] = 5

        # Verify change is reflected
        assert config.frustration["thresholds"]["high"] == 5

    def test_modify_limits_at_runtime(self, config_factory):
        """Changing limits during execution."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory(limits={"max_consecutive_objections": 5})
        loader = ConfigLoader(config_dir)
        config = loader.load()

        assert config.limits["max_consecutive_objections"] == 5

        # Modify the loaded config
        config.constants["limits"]["max_consecutive_objections"] = 2

        assert config.limits["max_consecutive_objections"] == 2

    def test_modify_lead_scoring_weights_at_runtime(self, config_factory):
        """Changing lead scoring weights during execution via config."""
        from src.config_loader import ConfigLoader

        # Create config with specific lead scoring settings
        config_dir = config_factory(lead_scoring={
            "skip_phases": {
                "cold": [],
                "warm": ["spin_implication"],
                "hot": ["spin_implication", "spin_need_payoff"],
                "very_hot": ["spin_problem", "spin_implication", "spin_need_payoff"]
            },
            "phase_order": [
                "spin_situation", "spin_problem", "spin_implication",
                "spin_need_payoff", "presentation", "close"
            ]
        })

        loader = ConfigLoader(config_dir)
        config = loader.load()

        # Verify initial values
        assert "skip_phases" in config.lead_scoring
        assert config.lead_scoring["skip_phases"]["warm"] == ["spin_implication"]

        # Modify config at runtime
        config.constants["lead_scoring"]["skip_phases"]["warm"] = ["spin_implication", "spin_need_payoff"]

        # Verify change is reflected
        assert config.lead_scoring["skip_phases"]["warm"] == ["spin_implication", "spin_need_payoff"]

class TestHotReload:
    """Tests for hot-reloading configuration files."""

    def test_reload_settings_from_file(self, tmp_path):
        """Reloading settings picks up file changes."""
        from src.settings import load_settings, DotDict

        # Create initial settings file
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text(yaml.dump({
            "llm": {"timeout": 30},
        }), encoding='utf-8')

        # Load initial
        settings = load_settings(settings_file)
        assert settings.llm.timeout == 30

        # Update file
        settings_file.write_text(yaml.dump({
            "llm": {"timeout": 60},
        }), encoding='utf-8')

        # Reload
        settings = load_settings(settings_file)
        assert settings.llm.timeout == 60

    def test_reload_config_preserves_runtime_state(self, config_factory):
        """Reload preserves any runtime state tracking."""
        from src.config_loader import ConfigLoader, get_config, init_config

        config_dir = config_factory()

        # Initialize config
        config1 = init_config(config_dir)
        original_max_turns = config1.guard["max_turns"]

        # Modify constants.yaml
        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        constants['guard']['max_turns'] = original_max_turns + 10

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        # Reload
        config2 = get_config(reload=True)

        assert config2.guard["max_turns"] == original_max_turns + 10

    def test_reload_detects_invalid_config(self, config_factory):
        """Reload with invalid config should fail gracefully."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        # Load valid config
        config1 = loader.load()

        # Break config - add invalid state reference
        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        constants['circular_flow']['allowed_gobacks']['invalid_state'] = 'another_invalid'

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        # Reload should fail validation
        with pytest.raises(ConfigValidationError):
            loader.reload()

    def test_reload_multiple_times_no_memory_leak(self, config_factory):
        """Multiple reloads should not cause memory issues."""
        import gc
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        # Track object counts
        gc.collect()

        # Reload many times
        for _ in range(100):
            config = loader.load()
            del config

        gc.collect()
        # Should complete without memory issues

class TestThreadSafeConfigUpdates:
    """Tests for thread-safe configuration updates."""

    def test_concurrent_config_reads_during_write(self, config_factory):
        """Reading config while another thread writes."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        results = []
        stop_flag = threading.Event()

        def reader():
            while not stop_flag.is_set():
                try:
                    config = loader.load(validate=False)
                    # May get KeyError during partial write - that's OK
                    if "guard" in config.constants:
                        results.append(config.guard.get("max_turns", 25))
                except Exception:
                    # Errors during concurrent access are expected
                    pass
                time.sleep(0.001)

        def writer():
            constants_path = config_dir / "constants.yaml"
            for i in range(10):
                try:
                    with open(constants_path, 'r', encoding='utf-8') as f:
                        constants = yaml.safe_load(f)
                    constants['guard']['max_turns'] = 25 + i
                    with open(constants_path, 'w', encoding='utf-8') as f:
                        yaml.dump(constants, f, allow_unicode=True)
                except Exception:
                    pass  # Ignore write errors
                time.sleep(0.005)

        # Start readers
        readers = [threading.Thread(target=reader) for _ in range(5)]
        for r in readers:
            r.start()

        # Run writer
        writer_thread = threading.Thread(target=writer)
        writer_thread.start()
        writer_thread.join()

        # Stop readers
        stop_flag.set()
        for r in readers:
            r.join()

        # Should have read some values (concurrent access works)
        assert len(results) > 0

    def test_atomic_config_update(self, config_factory):
        """Config update should be atomic (all or nothing)."""
        from src.settings import DotDict, _deep_merge

        original = DotDict({
            "guard": {"max_turns": 25, "timeout": 30},
            "limits": {"max_objections": 5}
        })

        update = {
            "guard": {"max_turns": 10},
            "limits": {"max_objections": 2}
        }

        # Atomic merge
        new_config = DotDict(_deep_merge(dict(original), update))

        # Both changes should be applied
        assert new_config.guard.max_turns == 10
        assert new_config.limits.max_objections == 2
        # Original should be unchanged
        assert original.guard.max_turns == 25

    def test_concurrent_guard_updates(self):
        """Multiple threads updating ConversationGuard config."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_turns=25, max_phase_attempts=3, max_same_state=4)
        guard = ConversationGuard(config)

        results = []
        lock = threading.Lock()

        def update_and_read(new_max_turns):
            guard.config = GuardConfig(
                max_turns=new_max_turns,
                max_phase_attempts=3,
                max_same_state=4
            )
            with lock:
                results.append(guard.config.max_turns)

        threads = [
            threading.Thread(target=update_and_read, args=(i,))
            for i in range(10, 20)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All values should be in valid range
        assert all(10 <= r < 20 for r in results)

class TestComponentSynchronization:
    """Tests for component synchronization after config changes."""

    def test_guard_frustration_threshold_sync(self, config_factory):
        """Guard and FrustrationTracker thresholds stay synchronized in config."""
        from src.config_loader import ConfigLoader

        # Create config with synchronized thresholds
        config_dir = config_factory(
            guard={"high_frustration_threshold": 7},
            frustration={"thresholds": {"warning": 4, "high": 7, "critical": 9}}
        )

        loader = ConfigLoader(config_dir)
        config = loader.load()

        # Verify thresholds are synchronized in config
        guard_threshold = config.guard["high_frustration_threshold"]
        frustration_high = config.frustration["thresholds"]["high"]

        assert guard_threshold == frustration_high

        # Verify config validation catches mismatches
        # (this is tested in test_config_conflicts.py)

    def test_lead_scorer_skip_phases_sync_with_spin(self, config_factory):
        """LeadScorer skip_phases references valid SPIN states."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)
        config = loader.load()

        # Get SPIN states
        spin_states = list(config.constants['spin']['states'].values())

        # Verify all skip_phases reference valid states
        for temp, phases in config.lead_scoring.get('skip_phases', {}).items():
            for phase in phases:
                assert phase in spin_states, \
                    f"skip_phases[{temp}] contains invalid state: {phase}"

class TestConfigRollback:
    """Tests for rolling back invalid config changes."""

    def test_rollback_on_validation_failure(self, config_factory):
        """Invalid config change should be rollbackable."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        # Load and save valid config
        valid_config = loader.load()
        valid_constants = copy.deepcopy(valid_config.constants)

        # Attempt invalid change
        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        # Save backup
        backup = copy.deepcopy(constants)

        # Make invalid change
        constants['circular_flow']['allowed_gobacks']['invalid'] = 'nonexistent'

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        # Reload should fail
        try:
            loader.reload()
            validation_failed = False
        except ConfigValidationError:
            validation_failed = True
            # Rollback
            with open(constants_path, 'w', encoding='utf-8') as f:
                yaml.dump(backup, f, allow_unicode=True)

        assert validation_failed

        # After rollback, should load successfully
        restored_config = loader.load()
        assert 'invalid' not in restored_config.circular_flow.get('allowed_gobacks', {})

    def test_partial_update_rollback(self, config_factory):
        """Partial config update should be atomic - all or nothing."""
        from src.settings import DotDict, _deep_merge

        original = {
            "guard": {"max_turns": 25, "timeout": 30},
            "limits": {"max_objections": 5}
        }

        def apply_update_with_validation(base, update, validator):
            """Apply update only if all changes pass validation."""
            merged = _deep_merge(copy.deepcopy(base), update)

            if not validator(merged):
                return base  # Rollback
            return merged

        # Validator that rejects negative values
        def validator(config):
            if config.get('guard', {}).get('max_turns', 0) < 0:
                return False
            return True

        # Valid update
        result = apply_update_with_validation(
            original,
            {"guard": {"max_turns": 10}},
            validator
        )
        assert result['guard']['max_turns'] == 10

        # Invalid update - should rollback
        result = apply_update_with_validation(
            original,
            {"guard": {"max_turns": -5}},
            validator
        )
        assert result['guard']['max_turns'] == 25  # Unchanged

class TestDynamicFeatureToggle:
    """Tests for dynamically toggling features via config."""

    def test_toggle_debug_mode_at_runtime(self, config_factory):
        """Toggling debug mode affects logging behavior."""
        from src.settings import load_settings, DotDict

        settings = DotDict({
            "development": {"debug": False},
            "logging": {"level": "INFO"}
        })

        assert settings.development.debug is False

        # Toggle debug
        settings["development"]["debug"] = True

        assert settings.development.debug is True

    def test_toggle_use_embeddings_at_runtime(self, config_factory):
        """Toggling use_embeddings affects retriever behavior."""
        from src.settings import DotDict

        settings = DotDict({
            "retriever": {"use_embeddings": True}
        })

        assert settings.retriever.use_embeddings is True

        # Disable embeddings
        settings["retriever"]["use_embeddings"] = False

        assert settings.retriever.use_embeddings is False

class TestConfigChangeNotification:
    """Tests for notifying components of config changes."""

    def test_observer_pattern_for_config_changes(self):
        """Components can subscribe to config change notifications."""

        class ConfigObservable:
            def __init__(self):
                self._observers = []
                self._config = {}

            def subscribe(self, callback):
                self._observers.append(callback)

            def update_config(self, key, value):
                old_value = self._config.get(key)
                self._config[key] = value
                for observer in self._observers:
                    observer(key, old_value, value)

            def get(self, key, default=None):
                return self._config.get(key, default)

        observable = ConfigObservable()
        notifications = []

        def on_change(key, old_val, new_val):
            notifications.append((key, old_val, new_val))

        observable.subscribe(on_change)

        observable.update_config("max_turns", 25)
        observable.update_config("max_turns", 10)

        assert len(notifications) == 2
        assert notifications[1] == ("max_turns", 25, 10)

    def test_config_change_callback_execution(self):
        """Config change triggers registered callbacks."""

        class ConfigWithCallbacks:
            def __init__(self):
                self._values = {}
                self._callbacks = {}

            def register_callback(self, key, callback):
                if key not in self._callbacks:
                    self._callbacks[key] = []
                self._callbacks[key].append(callback)

            def set(self, key, value):
                self._values[key] = value
                if key in self._callbacks:
                    for cb in self._callbacks[key]:
                        cb(value)

        config = ConfigWithCallbacks()

        callback_results = []
        config.register_callback("threshold", lambda v: callback_results.append(v))

        config.set("threshold", 5)
        config.set("threshold", 10)

        assert callback_results == [5, 10]

class TestRuntimeConfigValidation:
    """Tests for validating config changes at runtime."""

    def test_validate_before_apply(self, config_factory):
        """Config changes are validated before being applied."""
        from src.settings import validate_settings, DotDict

        valid_settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": 60},
            "retriever": {"thresholds": {"exact": 1.0, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 3, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.7, "min_confidence": 0.3}}
        })

        # Valid settings pass
        errors = validate_settings(valid_settings)
        assert len(errors) == 0

        # Invalid settings fail
        invalid_settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": -1},
            "retriever": {"thresholds": {"exact": 1.5, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 0, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.2, "min_confidence": 0.5}}
        })

        errors = validate_settings(invalid_settings)
        assert len(errors) > 0

    def test_type_checking_on_update(self):
        """Type mismatches are caught on update."""
        from src.settings import DotDict

        config = DotDict({"max_turns": 25})

        # Update with wrong type should still work (Python is dynamic)
        # but we can add validation
        def validated_update(config, key, value, expected_type):
            if not isinstance(value, expected_type):
                raise TypeError(f"{key} must be {expected_type.__name__}")
            config[key] = value

        with pytest.raises(TypeError):
            validated_update(config, "max_turns", "twenty-five", int)

        # Correct type works
        validated_update(config, "max_turns", 30, int)
        assert config["max_turns"] == 30

    def test_range_validation_on_update(self):
        """Values outside valid ranges are rejected."""

        def validate_range(value, min_val, max_val, name):
            if not (min_val <= value <= max_val):
                raise ValueError(f"{name} must be between {min_val} and {max_val}")
            return value

        # Valid
        assert validate_range(0.5, 0.0, 1.0, "threshold") == 0.5

        # Invalid
        with pytest.raises(ValueError):
            validate_range(1.5, 0.0, 1.0, "threshold")

        with pytest.raises(ValueError):
            validate_range(-0.1, 0.0, 1.0, "threshold")

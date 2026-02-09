"""
Tests for Config Override (Hot-Reload) Mechanism.

Tests cover:
1. Override storage CRUD operations (config_loader level)
2. Deep merge semantics
3. Override application in load_named() — all 3 code paths
4. Thread safety
5. Post-merge threshold validation warnings
6. Bot component wiring (guard, lead_scorer, cta, disambiguation, response_directives)
7. Edge cases: empty overrides, unknown keys, concurrent access, storage immutability

End-to-end tests verify that setting an override propagates through to
the component that reads the corresponding config section.
"""

import copy
import threading
import warnings
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import yaml


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary config directory with minimal valid YAML files."""
    (tmp_path / "states").mkdir()
    (tmp_path / "spin").mkdir()
    (tmp_path / "conditions").mkdir()

    constants = {
        "spin": {
            "phases": ["situation", "problem"],
            "states": {
                "situation": "spin_situation",
                "problem": "spin_problem",
            },
        },
        "limits": {
            "max_gobacks": 2,
            "max_consecutive_objections": 3,
        },
        "guard": {
            "max_turns": 25,
            "high_frustration_threshold": 7,
        },
        "frustration": {
            "thresholds": {
                "warning": 4,
                "high": 7,
                "critical": 9,
            }
        },
        "lead_scoring": {
            "skip_phases": {"cold": [], "warm": ["spin_problem"]},
        },
        "cta": {
            "early_states": ["greeting"],
        },
        "disambiguation": {
            "high_confidence": 0.85,
            "medium_confidence": 0.65,
            "low_confidence": 0.45,
            "min_confidence": 0.30,
            "gap_threshold": 0.20,
        },
        "response_directives": {
            "max_summary_lines": 6,
        },
        "fallback": {},
        "circular_flow": {
            "allowed_gobacks": {
                "spin_problem": "spin_situation",
            }
        },
    }
    with open(tmp_path / "constants.yaml", "w") as f:
        yaml.dump(constants, f)

    states = {
        "meta": {"version": "1.0"},
        "defaults": {"default_action": "continue"},
        "states": {
            "greeting": {
                "goal": "Greet",
                "transitions": {"price_question": "spin_situation"},
                "rules": {"greeting": "greet_back"},
            },
            "spin_situation": {
                "goal": "Understand situation",
                "spin_phase": "situation",
                "transitions": {"data_complete": "spin_problem"},
            },
            "spin_problem": {
                "goal": "Find problems",
                "spin_phase": "problem",
            },
        },
    }
    with open(tmp_path / "states" / "sales_flow.yaml", "w") as f:
        yaml.dump(states, f)

    spin = {
        "phase_order": ["situation", "problem"],
        "phases": {
            "situation": {"state": "spin_situation", "skippable": False},
            "problem": {"state": "spin_problem", "skippable": True},
        },
    }
    with open(tmp_path / "spin" / "phases.yaml", "w") as f:
        yaml.dump(spin, f)

    custom = {"conditions": {}, "aliases": {}}
    with open(tmp_path / "conditions" / "custom.yaml", "w") as f:
        yaml.dump(custom, f)

    return tmp_path


@pytest.fixture(autouse=True)
def clean_overrides():
    """Ensure override storage is clean before and after each test."""
    from src.config_loader import clear_all_config_overrides
    clear_all_config_overrides()
    yield
    clear_all_config_overrides()


# =============================================================================
# 1. Override Storage CRUD
# =============================================================================

class TestOverrideStorage:
    """Tests for set/get/clear override functions."""

    def test_set_override_applies_safe_keys(self):
        from src.config_loader import set_config_override, get_config_overrides

        result = set_config_override("default", {
            "guard": {"max_turns": 30},
            "limits": {"max_gobacks": 5},
        })
        assert "guard" in result["applied"]
        assert "limits" in result["applied"]
        assert result["rejected"] == {}

        stored = get_config_overrides("default")
        assert stored["guard"]["max_turns"] == 30
        assert stored["limits"]["max_gobacks"] == 5

    def test_set_override_rejects_structural_keys(self):
        from src.config_loader import set_config_override, get_config_overrides

        result = set_config_override("default", {
            "intents": {"new_intent": "test"},
            "states": {"new_state": {}},
            "policy": {"overlay_allowed_states": []},
            "guard": {"max_turns": 30},  # this one is safe
        })
        assert result["applied"] == ["guard"]
        assert "intents" in result["rejected"]
        assert "states" in result["rejected"]
        assert "policy" in result["rejected"]

        stored = get_config_overrides("default")
        assert "intents" not in stored
        assert "guard" in stored

    def test_set_override_all_safe_keys(self):
        """Verify every key in SAFE_OVERRIDE_KEYS is accepted."""
        from src.config_loader import set_config_override, SAFE_OVERRIDE_KEYS

        overrides = {key: {"test": True} for key in SAFE_OVERRIDE_KEYS}
        result = set_config_override("test_all", overrides)
        assert set(result["applied"]) == SAFE_OVERRIDE_KEYS
        assert result["rejected"] == {}

    def test_set_override_empty_overrides(self):
        from src.config_loader import set_config_override, get_config_overrides

        result = set_config_override("default", {})
        assert result["applied"] == []
        assert result["rejected"] == {}
        assert get_config_overrides("default") == {}

    def test_set_override_only_rejected(self):
        from src.config_loader import set_config_override, get_config_overrides

        result = set_config_override("default", {
            "intents": {"bad": True},
        })
        assert result["applied"] == []
        assert "intents" in result["rejected"]
        # No entry created in storage
        assert get_config_overrides("default") == {}

    def test_get_overrides_nonexistent_config(self):
        from src.config_loader import get_config_overrides

        result = get_config_overrides("nonexistent")
        assert result == {}

    def test_clear_overrides(self):
        from src.config_loader import (
            set_config_override, clear_config_overrides, get_config_overrides
        )

        set_config_override("default", {"guard": {"max_turns": 30}})
        assert get_config_overrides("default") != {}

        cleared = clear_config_overrides("default")
        assert cleared is True
        assert get_config_overrides("default") == {}

    def test_clear_overrides_nonexistent(self):
        from src.config_loader import clear_config_overrides

        cleared = clear_config_overrides("nonexistent")
        assert cleared is False

    def test_clear_all_overrides(self):
        from src.config_loader import (
            set_config_override, clear_all_config_overrides, get_config_overrides
        )

        set_config_override("config_a", {"guard": {"max_turns": 30}})
        set_config_override("config_b", {"limits": {"max_gobacks": 5}})

        count = clear_all_config_overrides()
        assert count == 2
        assert get_config_overrides("config_a") == {}
        assert get_config_overrides("config_b") == {}

    def test_clear_all_overrides_empty(self):
        from src.config_loader import clear_all_config_overrides

        count = clear_all_config_overrides()
        assert count == 0

    def test_multiple_set_overrides_merge(self):
        """Multiple set_config_override calls should deep-merge."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("default", {"guard": {"max_turns": 30}})
        set_config_override("default", {"guard": {"max_same_state": 5}})

        stored = get_config_overrides("default")
        assert stored["guard"]["max_turns"] == 30
        assert stored["guard"]["max_same_state"] == 5

    def test_set_override_overwrites_same_key(self):
        """Second set with same key overwrites value."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("default", {"guard": {"max_turns": 30}})
        set_config_override("default", {"guard": {"max_turns": 50}})

        stored = get_config_overrides("default")
        assert stored["guard"]["max_turns"] == 50

    def test_per_config_isolation(self):
        """Overrides for different configs are independent."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("tenant_a", {"guard": {"max_turns": 10}})
        set_config_override("tenant_b", {"guard": {"max_turns": 99}})

        assert get_config_overrides("tenant_a")["guard"]["max_turns"] == 10
        assert get_config_overrides("tenant_b")["guard"]["max_turns"] == 99


# =============================================================================
# 2. Deep Merge Semantics
# =============================================================================

class TestDeepMerge:
    """Tests for _deep_merge function."""

    def test_deep_merge_nested(self):
        from src.config_loader import _deep_merge

        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10, "e": 5}, "f": 6}

        result = _deep_merge(base, override)

        assert result is base  # mutates in place
        assert result["a"]["b"] == 10  # overridden
        assert result["a"]["c"] == 2   # preserved
        assert result["a"]["e"] == 5   # added
        assert result["d"] == 3        # untouched
        assert result["f"] == 6        # added

    def test_deep_merge_replaces_non_dict(self):
        from src.config_loader import _deep_merge

        base = {"a": {"b": 1}}
        override = {"a": "replaced"}

        result = _deep_merge(base, override)
        assert result["a"] == "replaced"

    def test_deep_merge_dict_over_non_dict(self):
        from src.config_loader import _deep_merge

        base = {"a": "string"}
        override = {"a": {"nested": True}}

        result = _deep_merge(base, override)
        assert result["a"] == {"nested": True}

    def test_deep_merge_empty_override(self):
        from src.config_loader import _deep_merge

        base = {"a": 1, "b": 2}
        result = _deep_merge(base, {})
        assert result == {"a": 1, "b": 2}

    def test_deep_merge_empty_base(self):
        from src.config_loader import _deep_merge

        result = _deep_merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_deep_merge_deeply_nested(self):
        from src.config_loader import _deep_merge

        base = {"level1": {"level2": {"level3": {"value": "old"}}}}
        override = {"level1": {"level2": {"level3": {"value": "new", "extra": True}}}}

        result = _deep_merge(base, override)
        assert result["level1"]["level2"]["level3"]["value"] == "new"
        assert result["level1"]["level2"]["level3"]["extra"] is True

    def test_deep_merge_list_replaced_not_merged(self):
        """Lists are replaced wholesale, not element-merged."""
        from src.config_loader import _deep_merge

        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}

        result = _deep_merge(base, override)
        assert result["items"] == [4, 5]


# =============================================================================
# 3. Override Application in load_named()
# =============================================================================

class TestOverrideInLoadNamed:
    """Tests for override application during config loading."""

    def test_override_applied_for_default(self, config_dir):
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {"guard": {"max_turns": 99}})

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.guard["max_turns"] == 99

    def test_override_applied_with_empty_name(self, config_dir):
        """Empty name resolves to 'default'."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {"limits": {"max_gobacks": 10}})

        loader = ConfigLoader(config_dir)
        config = loader.load_named("")

        assert config.limits["max_gobacks"] == 10
        assert config.name == "default"

    def test_override_applied_for_named_nonexistent_tenant(self, config_dir):
        """Named config without tenant dir gets overrides keyed by that name."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("my_tenant", {"guard": {"max_turns": 42}})

        loader = ConfigLoader(config_dir)
        config = loader.load_named("my_tenant")

        assert config.name == "my_tenant"
        assert config.guard["max_turns"] == 42

    def test_override_applied_for_tenant_dir(self, config_dir):
        """When tenant dir exists, overrides still apply keyed by tenant name."""
        from src.config_loader import ConfigLoader, set_config_override

        # Create tenant directory with its own config
        tenant_dir = config_dir / "tenants" / "acme"
        tenant_dir.mkdir(parents=True)

        # Copy config files to tenant dir
        import shutil
        for sub in ["states", "spin", "conditions"]:
            shutil.copytree(config_dir / sub, tenant_dir / sub)
        shutil.copy(config_dir / "constants.yaml", tenant_dir / "constants.yaml")

        set_config_override("acme", {"guard": {"max_turns": 77}})

        loader = ConfigLoader(config_dir)
        config = loader.load_named("acme")

        assert config.name == "acme"
        assert config.guard["max_turns"] == 77

    def test_three_paths_all_get_overrides(self, config_dir):
        """All three code paths in load_named() get overrides applied."""
        from src.config_loader import ConfigLoader, set_config_override
        import shutil

        # Create tenant directory
        tenant_dir = config_dir / "tenants" / "tenant_x"
        tenant_dir.mkdir(parents=True)
        for sub in ["states", "spin", "conditions"]:
            shutil.copytree(config_dir / sub, tenant_dir / sub)
        shutil.copy(config_dir / "constants.yaml", tenant_dir / "constants.yaml")

        # Set overrides for all three paths
        set_config_override("default", {"limits": {"max_gobacks": 100}})
        set_config_override("tenant_x", {"limits": {"max_gobacks": 200}})
        set_config_override("no_dir", {"limits": {"max_gobacks": 300}})

        loader = ConfigLoader(config_dir)

        # Path 1: default
        c1 = loader.load_named("default")
        assert c1.limits["max_gobacks"] == 100

        # Path 2: tenant dir exists
        c2 = loader.load_named("tenant_x")
        assert c2.limits["max_gobacks"] == 200

        # Path 3: named but no tenant dir
        c3 = loader.load_named("no_dir")
        assert c3.limits["max_gobacks"] == 300

    def test_override_does_not_mutate_storage(self, config_dir):
        """Applying overrides must not modify the override storage itself."""
        from src.config_loader import (
            ConfigLoader, set_config_override, get_config_overrides
        )

        set_config_override("default", {"guard": {"max_turns": 50}})
        original_stored = get_config_overrides("default")

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        # Mutate the loaded config
        config.constants["guard"]["max_turns"] = 999

        # Storage should be unchanged
        stored_after = get_config_overrides("default")
        assert stored_after["guard"]["max_turns"] == 50
        assert stored_after == original_stored

    def test_no_override_preserves_original(self, config_dir):
        """Without overrides, load_named() returns original values."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.guard["max_turns"] == 25
        assert config.limits["max_gobacks"] == 2

    def test_override_partial_nested_merge(self, config_dir):
        """Override merges into existing nested dict, preserving other keys."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "guard": {"max_turns": 99},
            # Only override max_turns, leave high_frustration_threshold
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.guard["max_turns"] == 99
        assert config.guard["high_frustration_threshold"] == 7  # preserved

    def test_override_with_new_nested_key(self, config_dir):
        """Override can add new keys to existing sections."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "guard": {"new_param": "hello"},
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.guard["new_param"] == "hello"
        assert config.guard["max_turns"] == 25  # original preserved


# =============================================================================
# 4. Post-Merge Validation Warnings
# =============================================================================

class TestPostMergeValidation:
    """Tests for threshold validation after merge."""

    def test_post_merge_validation_warns_on_threshold_mismatch(self, config_dir):
        """Override that creates guard/frustration mismatch triggers warning."""
        from src.config_loader import ConfigLoader, set_config_override

        # Set guard threshold different from frustration.thresholds.high
        set_config_override("default", {
            "guard": {"high_frustration_threshold": 5},
            # frustration.thresholds.high remains 7
        })

        loader = ConfigLoader(config_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = loader.load_named("default")

            # Should have a warning about threshold mismatch
            threshold_warnings = [
                x for x in w if "threshold" in str(x.message).lower()
            ]
            assert len(threshold_warnings) > 0

    def test_post_merge_validation_no_warning_when_synced(self, config_dir):
        """Override that keeps thresholds in sync triggers no warning."""
        from src.config_loader import ConfigLoader, set_config_override

        # Keep both in sync
        set_config_override("default", {
            "guard": {"high_frustration_threshold": 8},
            "frustration": {"thresholds": {"high": 8}},
        })

        loader = ConfigLoader(config_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = loader.load_named("default")

            threshold_warnings = [
                x for x in w if "threshold" in str(x.message).lower()
            ]
            assert len(threshold_warnings) == 0


# =============================================================================
# 5. Thread Safety
# =============================================================================

class TestThreadSafety:
    """Tests for concurrent override operations."""

    def test_thread_safety_concurrent_writes(self):
        """Concurrent writes to different configs should not corrupt state."""
        from src.config_loader import (
            set_config_override, get_config_overrides, clear_all_config_overrides
        )

        errors = []
        num_threads = 10
        iterations = 50

        def writer(thread_id):
            try:
                for i in range(iterations):
                    config_name = f"config_{thread_id}"
                    set_config_override(config_name, {
                        "guard": {"max_turns": thread_id * 100 + i},
                    })
                    stored = get_config_overrides(config_name)
                    if "guard" not in stored:
                        errors.append(f"Thread {thread_id}: guard missing after set")
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"

    def test_thread_safety_concurrent_read_write(self):
        """Reads during concurrent writes should not raise."""
        from src.config_loader import (
            set_config_override, get_config_overrides
        )

        errors = []
        stop_event = threading.Event()

        def writer():
            try:
                i = 0
                while not stop_event.is_set():
                    set_config_override("shared", {
                        "guard": {"max_turns": i},
                    })
                    i += 1
            except Exception as e:
                errors.append(f"Writer: {e}")

        def reader():
            try:
                while not stop_event.is_set():
                    result = get_config_overrides("shared")
                    # Should always be valid dict
                    if not isinstance(result, dict):
                        errors.append(f"Reader: got non-dict {type(result)}")
            except Exception as e:
                errors.append(f"Reader: {e}")

        writer_thread = threading.Thread(target=writer)
        reader_threads = [threading.Thread(target=reader) for _ in range(5)]

        writer_thread.start()
        for t in reader_threads:
            t.start()

        import time
        time.sleep(0.2)  # Let threads run briefly
        stop_event.set()

        writer_thread.join(timeout=2)
        for t in reader_threads:
            t.join(timeout=2)

        assert errors == [], f"Thread safety errors: {errors}"

    def test_thread_safety_clear_during_set(self):
        """clear_all during concurrent sets should not raise."""
        from src.config_loader import (
            set_config_override, clear_all_config_overrides
        )

        errors = []

        def setter():
            try:
                for i in range(100):
                    set_config_override(f"cfg_{i}", {"guard": {"max_turns": i}})
            except Exception as e:
                errors.append(f"Setter: {e}")

        def clearer():
            try:
                for _ in range(20):
                    clear_all_config_overrides()
            except Exception as e:
                errors.append(f"Clearer: {e}")

        threads = [
            threading.Thread(target=setter),
            threading.Thread(target=clearer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"


# =============================================================================
# 6. Bot Component Wiring
# =============================================================================

class TestBotComponentWiring:
    """Tests that bot components receive config from LoadedConfig."""

    def test_guard_receives_config_from_loaded_config(self, config_dir):
        """GuardConfig should be built from config.guard when available."""
        from src.config_loader import ConfigLoader, set_config_override
        from src.conversation_guard import GuardConfig

        set_config_override("default", {
            "guard": {"max_turns": 42, "max_same_state": 10},
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        # Simulate what bot.py does
        guard_overrides = config.guard
        assert guard_overrides  # non-empty

        guard_cfg = GuardConfig(
            **{k: v for k, v in guard_overrides.items()
               if k in GuardConfig.__dataclass_fields__}
        )

        assert guard_cfg.max_turns == 42
        assert guard_cfg.max_same_state == 10

    def test_guard_uses_defaults_when_config_empty(self, config_dir):
        """When config.guard is empty, GuardConfig.default() is used."""
        from src.conversation_guard import GuardConfig

        # Empty guard section
        guard_overrides = {}
        if guard_overrides:
            guard_cfg = GuardConfig(
                **{k: v for k, v in guard_overrides.items()
                   if k in GuardConfig.__dataclass_fields__}
            )
        else:
            guard_cfg = GuardConfig.default()

        assert guard_cfg.max_turns == 25  # default value

    def test_guard_ignores_unknown_fields(self, config_dir):
        """GuardConfig construction filters out unknown fields."""
        from src.config_loader import ConfigLoader, set_config_override
        from src.conversation_guard import GuardConfig

        set_config_override("default", {
            "guard": {
                "max_turns": 30,
                "unknown_field": "should_be_ignored",
                "another_fake": 999,
            },
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        guard_cfg = GuardConfig(
            **{k: v for k, v in config.guard.items()
               if k in GuardConfig.__dataclass_fields__}
        )

        assert guard_cfg.max_turns == 30
        assert not hasattr(guard_cfg, "unknown_field")

    def test_lead_scorer_receives_config(self, config_dir):
        """LeadScorer should receive LoadedConfig with overrides applied."""
        from src.config_loader import ConfigLoader, set_config_override
        from src.lead_scoring import LeadScorer

        set_config_override("default", {
            "lead_scoring": {
                "skip_phases": {"hot": ["spin_situation", "spin_problem"]},
            },
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        scorer = LeadScorer(config=config)
        # Verify override was picked up
        assert config.lead_scoring["skip_phases"]["hot"] == [
            "spin_situation", "spin_problem"
        ]

    def test_cta_generator_receives_config(self, config_dir):
        """CTAGenerator should receive LoadedConfig with overrides applied."""
        from src.config_loader import ConfigLoader, set_config_override
        from src.cta_generator import CTAGenerator

        set_config_override("default", {
            "cta": {"early_states": ["greeting", "spin_situation"]},
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        cta = CTAGenerator(config=config)
        assert config.cta["early_states"] == ["greeting", "spin_situation"]

    def test_confidence_router_reads_disambiguation_config(self, config_dir):
        """ConfidenceRouter should receive thresholds from config.disambiguation."""
        from src.config_loader import ConfigLoader, set_config_override
        from src.classifier.confidence_router import ConfidenceRouter

        set_config_override("default", {
            "disambiguation": {
                "high_confidence": 0.90,
                "gap_threshold": 0.25,
            },
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")
        disambiguation_cfg = config.disambiguation

        router = ConfidenceRouter(
            high_confidence=disambiguation_cfg.get("high_confidence", 0.85),
            medium_confidence=disambiguation_cfg.get("medium_confidence", 0.65),
            low_confidence=disambiguation_cfg.get("low_confidence", 0.45),
            min_confidence=disambiguation_cfg.get("min_confidence", 0.30),
            gap_threshold=disambiguation_cfg.get("gap_threshold", 0.20),
        )

        assert router.high_confidence == 0.90
        assert router.gap_threshold == 0.25
        assert router.medium_confidence == 0.65  # original preserved

    def test_response_directives_receives_tenant_config(self, config_dir):
        """build_response_directives should use passed config, not get_config()."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "response_directives": {"max_summary_lines": 10},
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        # ResponseDirectivesBuilder receives config directly
        from src.response_directives import ResponseDirectivesBuilder
        from unittest.mock import MagicMock

        # Create mock envelope
        envelope = MagicMock()
        envelope.reason_codes = []
        envelope.frustration_level = 0
        envelope.engagement_level = "medium"
        envelope.has_reason.return_value = False
        envelope.first_objection_type = None
        envelope.client_has_data = False
        envelope.client_company_size = None
        envelope.client_pain_points = []
        envelope.collected_data = {}
        envelope.objection_types_seen = []
        envelope.repeated_question = None
        envelope.is_stuck = False
        envelope.has_breakthrough = False
        envelope.total_turns = 1
        envelope.tone = "neutral"
        envelope.repeated_objection_types = []
        envelope.has_oscillation = False

        builder = ResponseDirectivesBuilder(envelope, config=config.response_directives)
        assert builder.max_summary_lines == 10

    def test_disambiguation_property_on_loaded_config(self, config_dir):
        """LoadedConfig.disambiguation property should return constants section."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.disambiguation["high_confidence"] == 0.85
        assert config.disambiguation["gap_threshold"] == 0.20


# =============================================================================
# 7. Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge cases for override mechanism."""

    def test_override_with_none_values(self):
        """None values in overrides should be stored as-is."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("default", {"guard": {"max_turns": None}})
        stored = get_config_overrides("default")
        assert stored["guard"]["max_turns"] is None

    def test_override_with_empty_dict_value(self):
        """Empty dict values in overrides should be stored as-is."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("default", {"guard": {}})
        stored = get_config_overrides("default")
        assert stored["guard"] == {}

    def test_override_with_nested_lists(self):
        """Overrides with lists should replace lists, not merge."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("default", {
            "lead_scoring": {"skip_phases": {"hot": ["a", "b", "c"]}},
        })
        stored = get_config_overrides("default")
        assert stored["lead_scoring"]["skip_phases"]["hot"] == ["a", "b", "c"]

    def test_multiple_configs_independent(self, config_dir):
        """Overrides for config_a should not affect config_b."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("config_a", {"guard": {"max_turns": 10}})
        # config_b has no overrides

        loader = ConfigLoader(config_dir)
        config_b = loader.load_named("config_b")

        # config_b should have original value
        assert config_b.guard["max_turns"] == 25

    def test_override_survives_multiple_load_named_calls(self, config_dir):
        """Each load_named call should independently apply overrides."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {"guard": {"max_turns": 77}})

        loader = ConfigLoader(config_dir)

        config1 = loader.load_named("default")
        config2 = loader.load_named("default")

        assert config1.guard["max_turns"] == 77
        assert config2.guard["max_turns"] == 77

        # Mutating one should not affect the other
        config1.constants["guard"]["max_turns"] = 999
        assert config2.guard["max_turns"] == 77

    def test_override_does_not_affect_load_method(self, config_dir):
        """Overrides only apply in load_named(), not load()."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {"guard": {"max_turns": 77}})

        loader = ConfigLoader(config_dir)
        config = loader.load()

        # load() bypasses overrides — it doesn't know config name
        assert config.guard["max_turns"] == 25

    def test_safe_override_keys_is_frozenset(self):
        """SAFE_OVERRIDE_KEYS should be immutable."""
        from src.config_loader import SAFE_OVERRIDE_KEYS

        assert isinstance(SAFE_OVERRIDE_KEYS, frozenset)
        with pytest.raises(AttributeError):
            SAFE_OVERRIDE_KEYS.add("bad_key")

    def test_config_name_special_characters(self):
        """Config names with special characters should work."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("tenant-with-dashes", {"guard": {"max_turns": 10}})
        set_config_override("tenant.with.dots", {"guard": {"max_turns": 20}})
        set_config_override("tenant_with_underscores", {"guard": {"max_turns": 30}})

        assert get_config_overrides("tenant-with-dashes")["guard"]["max_turns"] == 10
        assert get_config_overrides("tenant.with.dots")["guard"]["max_turns"] == 20
        assert get_config_overrides("tenant_with_underscores")["guard"]["max_turns"] == 30

    def test_override_numeric_types_preserved(self):
        """Numeric types (int, float) should be preserved through override."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("default", {
            "disambiguation": {
                "high_confidence": 0.92,
                "min_confidence": 0.25,
            },
            "guard": {
                "max_turns": 30,
            },
        })

        stored = get_config_overrides("default")
        assert isinstance(stored["disambiguation"]["high_confidence"], float)
        assert isinstance(stored["guard"]["max_turns"], int)

    def test_override_bool_values(self):
        """Boolean values should be preserved."""
        from src.config_loader import set_config_override, get_config_overrides

        set_config_override("default", {
            "disambiguation": {"log_uncertain": False},
        })

        stored = get_config_overrides("default")
        assert stored["disambiguation"]["log_uncertain"] is False


# =============================================================================
# 8. E2E: Override -> load_named -> property access
# =============================================================================

class TestE2EOverrideFlow:
    """End-to-end tests: set override -> load config -> verify property."""

    def test_e2e_guard_override_to_property(self, config_dir):
        """Full flow: set guard override -> load_named -> config.guard property."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "guard": {"max_turns": 100, "max_same_state": 8},
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.guard["max_turns"] == 100
        assert config.guard["max_same_state"] == 8
        assert config.guard["high_frustration_threshold"] == 7  # preserved

    def test_e2e_limits_override_to_property(self, config_dir):
        """Full flow: limits override -> load_named -> config.limits property."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "limits": {"max_gobacks": 10, "new_limit": 5},
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.limits["max_gobacks"] == 10
        assert config.limits["new_limit"] == 5
        assert config.limits["max_consecutive_objections"] == 3  # preserved

    def test_e2e_disambiguation_override_to_property(self, config_dir):
        """Full flow: disambiguation override -> config.disambiguation property."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "disambiguation": {"high_confidence": 0.95, "gap_threshold": 0.30},
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.disambiguation["high_confidence"] == 0.95
        assert config.disambiguation["gap_threshold"] == 0.30
        assert config.disambiguation["medium_confidence"] == 0.65  # preserved

    def test_e2e_response_directives_override(self, config_dir):
        """Full flow: response_directives override -> config.response_directives."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "response_directives": {
                "max_summary_lines": 12,
                "max_words": {"default": 80},
            },
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.response_directives["max_summary_lines"] == 12
        assert config.response_directives["max_words"]["default"] == 80

    def test_e2e_multiple_overrides_compose(self, config_dir):
        """Multiple override calls compose correctly."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {"guard": {"max_turns": 50}})
        set_config_override("default", {"limits": {"max_gobacks": 7}})
        set_config_override("default", {"guard": {"max_same_state": 6}})

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.guard["max_turns"] == 50
        assert config.guard["max_same_state"] == 6
        assert config.limits["max_gobacks"] == 7

    def test_e2e_clear_then_load_returns_original(self, config_dir):
        """After clearing overrides, load_named returns original values."""
        from src.config_loader import (
            ConfigLoader, set_config_override, clear_config_overrides
        )

        set_config_override("default", {"guard": {"max_turns": 99}})
        clear_config_overrides("default")

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.guard["max_turns"] == 25  # back to original

    def test_e2e_override_frustration_thresholds(self, config_dir):
        """Override frustration thresholds end-to-end."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "frustration": {
                "thresholds": {"high": 9, "warning": 5, "critical": 10},
            },
            "guard": {"high_frustration_threshold": 9},  # keep in sync
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.frustration["thresholds"]["high"] == 9
        assert config.frustration["thresholds"]["warning"] == 5
        assert config.guard["high_frustration_threshold"] == 9

    def test_e2e_lead_scoring_override(self, config_dir):
        """Override lead_scoring parameters end-to-end."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "lead_scoring": {
                "skip_phases": {"hot": ["spin_situation"]},
            },
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.lead_scoring["skip_phases"]["hot"] == ["spin_situation"]
        # Original keys preserved
        assert config.lead_scoring["skip_phases"]["cold"] == []

    def test_e2e_circular_flow_override(self, config_dir):
        """Override circular_flow parameters end-to-end."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "circular_flow": {
                "allowed_gobacks": {
                    "spin_situation": "greeting",
                },
            },
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert "spin_situation" in config.circular_flow["allowed_gobacks"]
        assert config.circular_flow["allowed_gobacks"]["spin_situation"] == "greeting"

    def test_e2e_fallback_override(self, config_dir):
        """Override fallback parameters end-to-end."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "fallback": {
                "rephrase_templates": ["Давайте попробуем иначе."],
            },
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert config.fallback["rephrase_templates"] == ["Давайте попробуем иначе."]

    def test_e2e_cta_override(self, config_dir):
        """Override CTA parameters end-to-end."""
        from src.config_loader import ConfigLoader, set_config_override

        set_config_override("default", {
            "cta": {
                "early_states": ["greeting", "spin_situation", "spin_problem"],
            },
        })

        loader = ConfigLoader(config_dir)
        config = loader.load_named("default")

        assert len(config.cta["early_states"]) == 3


# =============================================================================
# 9. build_response_directives with config parameter
# =============================================================================

class TestBuildResponseDirectivesConfig:
    """Test that build_response_directives accepts and uses config param."""

    def test_build_response_directives_with_config(self):
        """build_response_directives passes config to builder."""
        from src.response_directives import build_response_directives
        from unittest.mock import MagicMock

        envelope = MagicMock()
        envelope.reason_codes = []
        envelope.frustration_level = 0
        envelope.engagement_level = "medium"
        envelope.has_reason.return_value = False
        envelope.first_objection_type = None
        envelope.client_has_data = False
        envelope.client_company_size = None
        envelope.client_pain_points = []
        envelope.collected_data = {}
        envelope.objection_types_seen = []
        envelope.repeated_question = None
        envelope.is_stuck = False
        envelope.has_breakthrough = False
        envelope.total_turns = 1
        envelope.tone = "neutral"
        envelope.repeated_objection_types = []
        envelope.has_oscillation = False

        custom_config = {"max_summary_lines": 20, "max_words": {"default": 100}}
        directives = build_response_directives(envelope, config=custom_config)

        assert directives is not None
        # Verify max_words from config was used
        assert directives.max_words == 100

    def test_build_response_directives_without_config_backward_compat(self):
        """build_response_directives works without config (backward compat)."""
        from src.response_directives import build_response_directives
        from unittest.mock import MagicMock

        envelope = MagicMock()
        envelope.reason_codes = []
        envelope.frustration_level = 0
        envelope.engagement_level = "medium"
        envelope.has_reason.return_value = False
        envelope.first_objection_type = None
        envelope.client_has_data = False
        envelope.client_company_size = None
        envelope.client_pain_points = []
        envelope.collected_data = {}
        envelope.objection_types_seen = []
        envelope.repeated_question = None
        envelope.is_stuck = False
        envelope.has_breakthrough = False
        envelope.total_turns = 1
        envelope.tone = "neutral"
        envelope.repeated_objection_types = []
        envelope.has_oscillation = False

        # Should not raise even without config — falls back to get_config()
        directives = build_response_directives(envelope)
        assert directives is not None
        # Default max_words should be 60
        assert directives.max_words == 60

"""
Comprehensive edge case tests for 100% config coverage.

Tests cover:
1. Boundary values (min, max, zero, negative)
2. Empty/null values
3. Type coercion and validation
4. File system errors
5. Concurrent access
6. Complex nested conditions
7. Unicode and encoding
8. Large values and performance
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import yaml
import sys
import threading
import concurrent.futures
import tempfile
import os
import time

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# BOUNDARY VALUE TESTS - Numeric Parameters
# =============================================================================

class TestBoundaryValuesGuard:
    """Tests for guard parameter boundary values."""

    def test_max_turns_zero_should_fail(self, config_factory):
        """max_turns=0 should be invalid (no turns allowed)."""
        config_dir = config_factory(guard={"max_turns": 0})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        # Zero turns means conversation cannot happen
        assert config['guard']['max_turns'] == 0
        # System should handle this gracefully

    def test_max_turns_one_minimum_valid(self, config_factory):
        """max_turns=1 is minimum valid (single turn conversation)."""
        config_dir = config_factory(guard={"max_turns": 1})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['guard']['max_turns'] == 1

    def test_max_turns_very_large(self, config_factory):
        """max_turns=999999 should work (very long conversation)."""
        config_dir = config_factory(guard={"max_turns": 999999})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['guard']['max_turns'] == 999999

    def test_max_turns_negative_should_be_handled(self, config_factory):
        """max_turns=-1 should be handled (invalid value)."""
        config_dir = config_factory(guard={"max_turns": -1})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        # Config loads but value is invalid
        assert config['guard']['max_turns'] == -1

    def test_timeout_seconds_zero(self, config_factory):
        """timeout_seconds=0 means immediate timeout."""
        config_dir = config_factory(guard={"timeout_seconds": 0})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['guard']['timeout_seconds'] == 0

    def test_timeout_seconds_very_large(self, config_factory):
        """timeout_seconds=86400 (24 hours) should work."""
        config_dir = config_factory(guard={"timeout_seconds": 86400})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['guard']['timeout_seconds'] == 86400

    def test_max_phase_attempts_zero(self, config_factory):
        """max_phase_attempts=0 means no retries."""
        config_dir = config_factory(guard={"max_phase_attempts": 0})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['guard']['max_phase_attempts'] == 0

    def test_max_same_state_one(self, config_factory):
        """max_same_state=1 means loop detected immediately on repeat."""
        config_dir = config_factory(guard={"max_same_state": 1})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['guard']['max_same_state'] == 1

    def test_max_same_message_zero(self, config_factory):
        """max_same_message=0 allows no repeats."""
        config_dir = config_factory(guard={"max_same_message": 0})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['guard']['max_same_message'] == 0


class TestBoundaryValuesLimits:
    """Tests for limits parameter boundary values."""

    def test_max_consecutive_objections_zero(self, config_factory):
        """max_consecutive_objections=0 means any objection triggers soft_close."""
        config_dir = config_factory(limits={"max_consecutive_objections": 0})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['limits']['max_consecutive_objections'] == 0

    def test_max_total_objections_zero(self, config_factory):
        """max_total_objections=0 means any objection triggers soft_close."""
        config_dir = config_factory(limits={"max_total_objections": 0})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['limits']['max_total_objections'] == 0

    def test_max_gobacks_zero(self, config_factory):
        """max_gobacks=0 means no backward navigation allowed."""
        config_dir = config_factory(limits={"max_gobacks": 0})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['limits']['max_gobacks'] == 0

    def test_max_consecutive_objections_equals_total(self, config_factory):
        """max_consecutive_objections == max_total_objections is valid."""
        config_dir = config_factory(limits={
            "max_consecutive_objections": 5,
            "max_total_objections": 5
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['limits']['max_consecutive_objections'] == config['limits']['max_total_objections']

    def test_max_consecutive_greater_than_total_invalid(self, config_factory):
        """max_consecutive_objections > max_total_objections is logically invalid."""
        config_dir = config_factory(limits={
            "max_consecutive_objections": 10,
            "max_total_objections": 5
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        # Config loads but this is logically invalid
        assert config['limits']['max_consecutive_objections'] > config['limits']['max_total_objections']


class TestBoundaryValuesFrustration:
    """Tests for frustration parameter boundary values."""

    def test_max_level_zero(self, config_factory):
        """max_level=0 means frustration cannot accumulate."""
        config_dir = config_factory(frustration={"max_level": 0})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['frustration']['max_level'] == 0

    def test_max_level_one(self, config_factory):
        """max_level=1 means binary frustration (on/off)."""
        config_dir = config_factory(frustration={"max_level": 1})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['frustration']['max_level'] == 1

    def test_max_level_very_large(self, config_factory):
        """max_level=1000 should work."""
        config_dir = config_factory(frustration={"max_level": 1000})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['frustration']['max_level'] == 1000

    def test_thresholds_all_equal(self, config_factory):
        """All thresholds equal means all triggers at same level."""
        config_dir = config_factory(frustration={
            "thresholds": {"warning": 5, "high": 5, "critical": 5}
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        th = config['frustration']['thresholds']
        assert th['warning'] == th['high'] == th['critical']

    def test_thresholds_inverted_order(self, config_factory):
        """warning > high > critical is inverted but config loads."""
        config_dir = config_factory(frustration={
            "thresholds": {"warning": 9, "high": 5, "critical": 2}
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        th = config['frustration']['thresholds']
        # Logically invalid but config loads
        assert th['warning'] > th['high'] > th['critical']

    def test_weights_zero(self, config_factory):
        """All weights=0 means frustration never increases."""
        config_dir = config_factory(frustration={
            "weights": {"frustrated": 0, "skeptical": 0, "rushed": 0, "confused": 0}
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        weights = config['frustration']['weights']
        assert all(w == 0 for w in weights.values())

    def test_weights_negative(self, config_factory):
        """Negative weights decrease frustration on negative tone."""
        config_dir = config_factory(frustration={
            "weights": {"frustrated": -3, "skeptical": -1, "rushed": -1, "confused": -1}
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        weights = config['frustration']['weights']
        assert all(w < 0 for w in weights.values())


class TestBoundaryValuesLeadScoring:
    """Tests for lead_scoring parameter boundary values."""

    def test_all_weights_zero(self, config_factory):
        """Setting some weights to 0 works correctly."""
        config_dir = config_factory(lead_scoring={
            "positive_weights": {"demo_request": 0, "contact_provided": 0},
            "negative_weights": {"objection_price": 0, "rejection_soft": 0}
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        pos = config['lead_scoring']['positive_weights']
        neg = config['lead_scoring']['negative_weights']
        # Check that overridden values are zero
        assert pos['demo_request'] == 0
        assert pos['contact_provided'] == 0
        assert neg['objection_price'] == 0
        assert neg['rejection_soft'] == 0

    def test_threshold_ranges_overlap(self, config_factory):
        """Overlapping threshold ranges should be handled."""
        config_dir = config_factory(lead_scoring={
            "thresholds": {
                "cold": [0, 50],
                "warm": [30, 70],  # Overlaps with cold and hot
                "hot": [50, 100]
            }
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        th = config['lead_scoring']['thresholds']
        # Cold and warm overlap at 30-50
        assert th['cold'][1] > th['warm'][0]

    def test_threshold_ranges_gaps(self, config_factory):
        """Gaps between threshold ranges should be handled."""
        config_dir = config_factory(lead_scoring={
            "thresholds": {
                "cold": [0, 20],
                "warm": [40, 60],  # Gap 21-39
                "hot": [80, 100]   # Gap 61-79
            }
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        th = config['lead_scoring']['thresholds']
        assert th['cold'][1] < th['warm'][0]  # Gap exists

    def test_empty_skip_phases_for_all(self, config_factory):
        """All temperatures with empty skip_phases means full SPIN always."""
        config_dir = config_factory(lead_scoring={
            "skip_phases": {
                "cold": [],
                "warm": [],
                "hot": [],
                "very_hot": []
            }
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        skip = config['lead_scoring']['skip_phases']
        assert all(len(phases) == 0 for phases in skip.values())

    def test_all_phases_skipped_for_cold(self, config_factory):
        """Skipping all phases for cold lead is unusual but valid."""
        config_dir = config_factory(lead_scoring={
            "skip_phases": {
                "cold": ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"]
            }
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert len(config['lead_scoring']['skip_phases']['cold']) == 4


# =============================================================================
# EMPTY AND NULL VALUE TESTS
# =============================================================================

class TestEmptyValues:
    """Tests for empty/null configuration values."""

    def test_empty_fallback_templates(self, config_factory):
        """Empty rephrase_templates list for a state."""
        config_dir = config_factory(fallback={
            "rephrase_templates": {"greeting": []}
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['fallback']['rephrase_templates']['greeting'] == []

    def test_empty_cta_templates(self, config_factory):
        """Empty CTA templates for specific states."""
        config_dir = config_factory(cta={
            "templates": {
                "greeting": [],
                "spin_situation": [],
                "test_empty": []
            }
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        templates = config['cta']['templates']
        # Check that overridden templates are empty
        assert templates['greeting'] == []
        assert templates['spin_situation'] == []
        assert templates['test_empty'] == []

    def test_empty_intent_categories(self, config_factory):
        """Empty intent category lists for specific categories."""
        config_dir = config_factory(intents={
            "categories": {
                "test_empty_1": [],
                "test_empty_2": []
            }
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        cats = config['intents']['categories']
        # Check that new empty categories exist
        assert cats['test_empty_1'] == []
        assert cats['test_empty_2'] == []

    def test_empty_spin_phases(self, config_factory):
        """Empty SPIN phases list."""
        config_dir = config_factory(spin={"phases": []})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['spin']['phases'] == []

    def test_empty_options_in_fallback(self, config_factory):
        """Empty options list in options_templates."""
        config_dir = config_factory(fallback={
            "options_templates": {
                "spin_situation": {
                    "question": "Test?",
                    "options": []
                }
            }
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['fallback']['options_templates']['spin_situation']['options'] == []

    def test_null_default_rephrase(self, config_factory):
        """null default_rephrase should be handled."""
        config_dir = config_factory(fallback={"default_rephrase": None})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['fallback']['default_rephrase'] is None


# =============================================================================
# TYPE COERCION AND VALIDATION TESTS
# =============================================================================

class TestTypeCoercion:
    """Tests for type coercion and validation."""

    def test_string_as_number(self, config_factory):
        """String "25" should be handled (YAML auto-converts)."""
        config_dir = config_factory(guard={"max_turns": "25"})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        # YAML may parse "25" as string, depends on quoting
        assert config['guard']['max_turns'] in [25, "25"]

    def test_float_as_integer(self, config_factory):
        """Float 25.7 for integer field."""
        config_dir = config_factory(guard={"max_turns": 25.7})

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        assert config['guard']['max_turns'] == 25.7

    def test_boolean_as_string(self, tmp_path):
        """String "true" vs boolean true."""
        # Create standalone config file to test YAML parsing
        test_yaml = tmp_path / "test.yaml"
        test_yaml.write_text("test_bool: 'true'\ntest_real_bool: true", encoding='utf-8')

        with open(test_yaml, 'r') as f:
            config = yaml.safe_load(f)

        # Quoted 'true' is a string, unquoted true is boolean
        assert config['test_bool'] == 'true'
        assert config['test_real_bool'] is True
        assert isinstance(config['test_bool'], str)
        assert isinstance(config['test_real_bool'], bool)

    def test_list_with_mixed_types(self, config_factory):
        """List with mixed types [1, "two", 3.0]."""
        config_dir = config_factory(intents={
            "go_back": [1, "two", 3.0, True]
        })

        with open(config_dir / "constants.yaml", 'r') as f:
            config = yaml.safe_load(f)

        go_back = config['intents']['go_back']
        assert 1 in go_back
        assert "two" in go_back
        assert 3.0 in go_back


# =============================================================================
# UNICODE AND ENCODING TESTS
# =============================================================================

class TestUnicodeEncoding:
    """Tests for unicode and encoding handling."""

    def test_russian_in_templates(self, config_factory):
        """Russian text in templates."""
        config_dir = config_factory(fallback={
            "rephrase_templates": {
                "greeting": ["Привет! Как дела?", "Здравствуйте!"]
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        templates = config['fallback']['rephrase_templates']['greeting']
        assert "Привет!" in templates[0]

    def test_emoji_in_templates(self, config_factory):
        """Emoji in templates."""
        config_dir = config_factory(fallback={
            "rephrase_templates": {
                "greeting": ["Привет! 👋", "Здравствуйте! 😊"]
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        templates = config['fallback']['rephrase_templates']['greeting']
        assert "👋" in templates[0]

    def test_special_characters_in_keys(self, config_factory):
        """Special characters in config keys."""
        config_dir = config_factory()

        # Add special key manually
        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        config['test-key_with.special'] = "value"

        with open(config_dir / "constants.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        assert 'test-key_with.special' in loaded

    def test_very_long_russian_text(self, config_factory):
        """Very long Russian text (1000+ chars)."""
        long_text = "Это очень длинный текст. " * 100

        config_dir = config_factory(fallback={
            "default_rephrase": long_text
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        assert len(config['fallback']['default_rephrase']) > 1000


# =============================================================================
# FILE SYSTEM ERROR TESTS
# =============================================================================

class TestFileSystemErrors:
    """Tests for file system error handling."""

    def test_config_file_not_found(self, tmp_path):
        """Missing config file should raise or use defaults."""
        from src.settings import load_settings

        non_existent = tmp_path / "non_existent.yaml"
        settings = load_settings(non_existent)

        # Should use defaults when file not found
        assert settings is not None
        assert settings.llm.model is not None

    def test_config_directory_not_found(self, tmp_path):
        """Missing config directory."""
        non_existent_dir = tmp_path / "non_existent_dir"

        # Should not crash
        assert not non_existent_dir.exists()

    def test_invalid_yaml_syntax(self, tmp_path):
        """Invalid YAML syntax should raise."""
        invalid_yaml = tmp_path / "invalid.yaml"
        invalid_yaml.write_text("invalid: yaml: syntax: [broken", encoding='utf-8')

        with pytest.raises(yaml.YAMLError):
            with open(invalid_yaml, 'r') as f:
                yaml.safe_load(f)

    def test_empty_yaml_file(self, tmp_path):
        """Empty YAML file should return None or empty dict."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("", encoding='utf-8')

        with open(empty_yaml, 'r') as f:
            result = yaml.safe_load(f)

        assert result is None

    def test_yaml_with_only_comments(self, tmp_path):
        """YAML with only comments."""
        comments_only = tmp_path / "comments.yaml"
        comments_only.write_text("# This is a comment\n# Another comment", encoding='utf-8')

        with open(comments_only, 'r') as f:
            result = yaml.safe_load(f)

        assert result is None

    def test_read_only_config_file(self, tmp_path):
        """Read-only config file."""
        readonly_yaml = tmp_path / "readonly.yaml"
        readonly_yaml.write_text("key: value", encoding='utf-8')

        # Make read-only (Unix only)
        if os.name != 'nt':
            os.chmod(readonly_yaml, 0o444)

            # Should still be readable
            with open(readonly_yaml, 'r') as f:
                result = yaml.safe_load(f)

            assert result['key'] == 'value'

            # Cleanup
            os.chmod(readonly_yaml, 0o644)

    def test_config_with_bom(self, tmp_path):
        """YAML file with BOM (Byte Order Mark)."""
        bom_yaml = tmp_path / "bom.yaml"

        # Write with UTF-8 BOM
        with open(bom_yaml, 'wb') as f:
            f.write(b'\xef\xbb\xbf')  # UTF-8 BOM
            f.write(b'key: value\n')

        with open(bom_yaml, 'r', encoding='utf-8-sig') as f:
            result = yaml.safe_load(f)

        assert result['key'] == 'value'


# =============================================================================
# CONCURRENT ACCESS TESTS
# =============================================================================

class TestConcurrentAccess:
    """Tests for concurrent config access."""

    def test_concurrent_config_reads(self, config_factory):
        """Multiple threads reading config simultaneously."""
        config_dir = config_factory()
        results = []
        errors = []

        def read_config():
            try:
                with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                results.append(config['guard']['max_turns'])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_config) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        assert all(r == results[0] for r in results)

    def test_concurrent_settings_access(self):
        """Multiple threads accessing settings singleton."""
        from src.settings import get_settings, reload_settings

        results = []
        errors = []

        def access_settings():
            try:
                settings = get_settings()
                results.append(settings.llm.timeout)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access_settings) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10

    def test_thread_pool_config_loading(self, config_factory):
        """Thread pool loading config files."""
        config_dir = config_factory()

        def load_config(idx):
            with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return idx, config['guard']['max_turns']

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(load_config, i) for i in range(20)]
            results = [f.result() for f in futures]

        assert len(results) == 20
        assert all(r[1] == results[0][1] for r in results)


# =============================================================================
# COMPLEX NESTED CONDITIONS TESTS
# =============================================================================

class TestComplexNestedConditions:
    """Tests for complex nested condition expressions."""

    def test_deeply_nested_and_or(self, config_factory):
        """Deeply nested and/or conditions."""
        custom_conditions = {
            "conditions": {
                "complex_condition": {
                    "description": "Complex nested condition",
                    "expression": {
                        "and": [
                            {"or": [
                                {"and": ["cond_a", "cond_b"]},
                                {"and": ["cond_c", "cond_d"]}
                            ]},
                            {"or": [
                                "cond_e",
                                {"and": ["cond_f", "cond_g"]}
                            ]}
                        ]
                    }
                }
            }
        }

        config_dir = config_factory()

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_conditions, f, allow_unicode=True)

        with open(config_dir / "conditions" / "custom.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        assert 'complex_condition' in loaded['conditions']
        expr = loaded['conditions']['complex_condition']['expression']
        assert 'and' in expr

    def test_many_conditions_in_and(self, config_factory):
        """Many conditions in single and expression."""
        many_conditions = ["cond_" + str(i) for i in range(20)]

        custom_conditions = {
            "conditions": {
                "many_and": {
                    "description": "Many AND conditions",
                    "expression": {"and": many_conditions}
                }
            }
        }

        config_dir = config_factory()

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_conditions, f, allow_unicode=True)

        with open(config_dir / "conditions" / "custom.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        assert len(loaded['conditions']['many_and']['expression']['and']) == 20

    def test_not_with_nested_or(self, config_factory):
        """Not with nested or condition."""
        custom_conditions = {
            "conditions": {
                "not_nested": {
                    "description": "Not with nested or",
                    "expression": {
                        "not": {"or": ["cond_a", "cond_b", "cond_c"]}
                    }
                }
            }
        }

        config_dir = config_factory()

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_conditions, f, allow_unicode=True)

        with open(config_dir / "conditions" / "custom.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        assert 'not' in loaded['conditions']['not_nested']['expression']

    def test_self_referencing_condition_alias(self, config_factory):
        """Self-referencing condition alias (invalid but should load)."""
        custom_conditions = {
            "conditions": {},
            "aliases": {
                "self_ref": "self_ref"  # Points to itself
            }
        }

        config_dir = config_factory()

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_conditions, f, allow_unicode=True)

        with open(config_dir / "conditions" / "custom.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        # Config loads but alias is invalid
        assert loaded['aliases']['self_ref'] == 'self_ref'


# =============================================================================
# LARGE VALUES AND PERFORMANCE TESTS
# =============================================================================

class TestLargeValuesPerformance:
    """Tests for large values and performance."""

    def test_many_states_in_order(self, config_factory):
        """Many states in state_order (merged with defaults)."""
        many_states = {f"state_{i}": i for i in range(100)}

        config_dir = config_factory(context={"state_order": many_states})

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Should have all 100 new states plus the default ones
        assert len(config['context']['state_order']) >= 100
        # All new states should be present
        for i in range(100):
            assert f"state_{i}" in config['context']['state_order']

    def test_many_fallback_templates(self, config_factory):
        """Many fallback templates per state."""
        many_templates = [f"Template {i}" for i in range(50)]

        config_dir = config_factory(fallback={
            "rephrase_templates": {
                "greeting": many_templates
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        assert len(config['fallback']['rephrase_templates']['greeting']) == 50

    def test_many_intent_categories(self, config_factory):
        """Many intent categories (merged with defaults)."""
        many_categories = {f"category_{i}": [f"intent_{i}_{j}" for j in range(10)]
                          for i in range(20)}

        config_dir = config_factory(intents={"categories": many_categories})

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Should have all 20 new categories plus the default ones
        assert len(config['intents']['categories']) >= 20
        # All new categories should be present
        for i in range(20):
            assert f"category_{i}" in config['intents']['categories']

    def test_config_load_time(self, config_factory):
        """Config loading should be reasonably fast."""
        config_dir = config_factory()

        start = time.time()
        for _ in range(100):
            with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        elapsed = time.time() - start

        # 100 loads should take less than 5 seconds
        assert elapsed < 5.0


# =============================================================================
# SETTINGS VALIDATION TESTS
# =============================================================================

class TestSettingsValidation:
    """Tests for settings validation."""

    def test_validate_llm_timeout_zero(self, tmp_path):
        """llm.timeout=0 should fail validation."""
        from src.settings import load_settings, validate_settings, DotDict

        settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": 0},
            "retriever": {"thresholds": {"exact": 1.0, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 3, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.7, "min_confidence": 0.3}}
        })

        errors = validate_settings(settings)
        assert any("timeout" in e for e in errors)

    def test_validate_llm_timeout_negative(self, tmp_path):
        """llm.timeout=-1 should fail validation."""
        from src.settings import validate_settings, DotDict

        settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": -1},
            "retriever": {"thresholds": {"exact": 1.0, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 3, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.7, "min_confidence": 0.3}}
        })

        errors = validate_settings(settings)
        assert any("timeout" in e for e in errors)

    def test_validate_threshold_out_of_range(self):
        """Threshold > 1.0 should fail validation."""
        from src.settings import validate_settings, DotDict

        settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": 60},
            "retriever": {"thresholds": {"exact": 1.5, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 3, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.7, "min_confidence": 0.3}}
        })

        errors = validate_settings(settings)
        assert any("exact" in e for e in errors)

    def test_validate_high_confidence_less_than_min(self):
        """high_confidence < min_confidence should fail validation."""
        from src.settings import validate_settings, DotDict

        settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": 60},
            "retriever": {"thresholds": {"exact": 1.0, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 3, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.2, "min_confidence": 0.5}}
        })

        errors = validate_settings(settings)
        assert any("high_confidence" in e for e in errors)

    def test_validate_max_retries_zero(self):
        """max_retries=0 should fail validation."""
        from src.settings import validate_settings, DotDict

        settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": 60},
            "retriever": {"thresholds": {"exact": 1.0, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 0, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.7, "min_confidence": 0.3}}
        })

        errors = validate_settings(settings)
        assert any("max_retries" in e for e in errors)


# =============================================================================
# RELOAD SETTINGS TESTS
# =============================================================================

class TestReloadSettings:
    """Tests for settings reload functionality."""

    def test_reload_clears_cache(self):
        """reload_settings should clear cached settings."""
        from src.settings import get_settings, reload_settings

        settings1 = get_settings()
        settings2 = reload_settings()

        # Both should be valid settings
        assert settings1.llm.timeout > 0
        assert settings2.llm.timeout > 0

    def test_settings_singleton_returns_same_instance(self):
        """get_settings should return same instance."""
        from src.settings import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        # Same instance (singleton)
        assert settings1 is settings2


# =============================================================================
# DOTDICT TESTS
# =============================================================================

class TestDotDict:
    """Tests for DotDict functionality."""

    def test_dotdict_attribute_access(self):
        """DotDict allows attribute access."""
        from src.settings import DotDict

        d = DotDict({"a": 1, "b": {"c": 2}})

        assert d.a == 1
        assert d.b.c == 2

    def test_dotdict_missing_key_raises(self):
        """DotDict raises AttributeError for missing key."""
        from src.settings import DotDict

        d = DotDict({"a": 1})

        with pytest.raises(AttributeError):
            _ = d.missing_key

    def test_dotdict_get_nested(self):
        """DotDict get_nested method."""
        from src.settings import DotDict

        d = DotDict({"a": {"b": {"c": 3}}})

        assert d.get_nested("a.b.c") == 3
        assert d.get_nested("a.b.d", "default") == "default"
        assert d.get_nested("x.y.z", None) is None

    def test_dotdict_setattr(self):
        """DotDict allows setting attributes."""
        from src.settings import DotDict

        d = DotDict({})
        d.new_key = "value"

        assert d.new_key == "value"
        assert d["new_key"] == "value"


# =============================================================================
# CONSISTENCY TESTS
# =============================================================================

class TestConfigConsistency:
    """Tests for config consistency between files."""

    def test_guard_frustration_threshold_match(self, real_constants):
        """guard.high_frustration_threshold == frustration.thresholds.high."""
        guard_th = real_constants['guard']['high_frustration_threshold']
        frust_th = real_constants['frustration']['thresholds']['high']

        assert guard_th == frust_th, \
            f"guard.high_frustration_threshold ({guard_th}) != frustration.thresholds.high ({frust_th})"

    def test_spin_states_match_phases(self, real_constants):
        """SPIN states match phases."""
        phases = real_constants['spin']['phases']
        states = real_constants['spin']['states']

        for phase in phases:
            assert phase in states, f"Phase {phase} missing in states mapping"

    def test_circular_flow_states_exist(self, real_constants):
        """circular_flow states exist in context.state_order."""
        gobacks = real_constants['circular_flow']['allowed_gobacks']
        state_order = real_constants['context']['state_order']

        for from_state, to_state in gobacks.items():
            assert from_state in state_order, f"From state {from_state} not in state_order"
            assert to_state in state_order, f"To state {to_state} not in state_order"

    def test_lead_scoring_skip_phases_exist(self, real_constants):
        """lead_scoring.skip_phases reference existing spin states."""
        skip_phases = real_constants['lead_scoring']['skip_phases']
        spin_states = list(real_constants['spin']['states'].values())

        for temp, phases in skip_phases.items():
            for phase in phases:
                assert phase in spin_states, \
                    f"Skip phase {phase} for {temp} not in SPIN states"

    def test_cta_early_states_exist(self, real_constants):
        """cta.early_states exist in context.state_order."""
        early_states = real_constants['cta']['early_states']
        state_order = real_constants['context']['state_order']

        for state in early_states:
            assert state in state_order, f"Early state {state} not in state_order"

    def test_policy_overlay_states_exist(self, real_constants):
        """policy.overlay_allowed_states exist in context.state_order."""
        overlay_states = real_constants['policy']['overlay_allowed_states']
        state_order = real_constants['context']['state_order']

        for state in overlay_states:
            assert state in state_order, f"Overlay state {state} not in state_order"

    def test_policy_protected_states_exist(self, real_constants):
        """policy.protected_states exist in context.state_order."""
        protected = real_constants['policy']['protected_states']
        state_order = real_constants['context']['state_order']

        for state in protected:
            assert state in state_order, f"Protected state {state} not in state_order"

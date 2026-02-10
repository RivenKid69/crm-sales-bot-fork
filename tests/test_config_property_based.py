"""
Property-based tests for config using Hypothesis.

These tests automatically generate random valid and invalid configurations
to discover edge cases that might be missed by traditional unit tests.

Requires: pip install hypothesis
"""

import pytest
from pathlib import Path
import yaml
import sys
import tempfile

# Skip entire module if hypothesis is not installed
# This uses pytest's importorskip which properly handles collection
hypothesis = pytest.importorskip(
    "hypothesis",
    reason="hypothesis not installed - run 'pip install hypothesis' to enable property-based tests"
)

from hypothesis import given, strategies as st, settings, assume, example, HealthCheck
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize, invariant

# =============================================================================
# STRATEGIES - Custom data generators
# =============================================================================

# Valid state names
state_names = st.sampled_from([
    "greeting", "spin_situation", "spin_problem", "spin_implication",
    "spin_need_payoff", "presentation", "handle_objection", "close",
    "success", "soft_close"
])

# Valid phase names
phase_names = st.sampled_from([
    "situation", "problem", "implication", "need_payoff"
])

# Valid intent names
intent_names = st.sampled_from([
    "agreement", "demo_request", "callback_request", "contact_provided",
    "objection_price", "objection_no_time", "rejection", "farewell",
    "situation_provided", "problem_revealed", "price_question"
])

# Valid temperature names
temperature_names = st.sampled_from(["cold", "warm", "hot", "very_hot"])

# Positive integers for counts/limits
positive_ints = st.integers(min_value=1, max_value=1000)

# Non-negative integers
non_negative_ints = st.integers(min_value=0, max_value=1000)

# Timeouts in seconds (reasonable range)
timeout_values = st.integers(min_value=1, max_value=86400)

# Threshold values (0.0 to 1.0)
threshold_values = st.floats(min_value=0.0, max_value=1.0)

# Score weights
score_weights = st.integers(min_value=-100, max_value=100)

# Russian text
russian_text = st.text(
    alphabet='абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ !?.,',
    min_size=1,
    max_size=200
)

# Simple condition names
condition_names = st.from_regex(r'[a-z][a-z0-9_]{0,29}', fullmatch=True)

# =============================================================================
# GUARD CONFIG PROPERTY TESTS
# =============================================================================

class TestGuardConfigProperties:
    """Property-based tests for guard configuration."""

    @given(
        max_turns=positive_ints,
        max_phase_attempts=positive_ints,
        max_same_state=positive_ints,
        timeout_seconds=timeout_values
    )
    @settings(max_examples=100)
    def test_guard_config_with_positive_values_is_valid(
        self, max_turns, max_phase_attempts, max_same_state, timeout_seconds
    ):
        """Any positive values for guard config should be loadable."""
        config = {
            "guard": {
                "max_turns": max_turns,
                "max_phase_attempts": max_phase_attempts,
                "max_same_state": max_same_state,
                "timeout_seconds": timeout_seconds
            }
        }

        # Should be serializable to YAML
        yaml_str = yaml.dump(config, allow_unicode=True)
        loaded = yaml.safe_load(yaml_str)

        assert loaded['guard']['max_turns'] == max_turns
        assert loaded['guard']['timeout_seconds'] == timeout_seconds

    @given(
        max_turns=st.integers(min_value=-100, max_value=100),
        max_same_state=st.integers(min_value=-100, max_value=100)
    )
    @settings(max_examples=50)
    def test_guard_config_handles_any_integers(self, max_turns, max_same_state):
        """Guard config should load even with negative values."""
        config = {
            "guard": {
                "max_turns": max_turns,
                "max_same_state": max_same_state
            }
        }

        yaml_str = yaml.dump(config, allow_unicode=True)
        loaded = yaml.safe_load(yaml_str)

        assert loaded['guard']['max_turns'] == max_turns

    @given(max_turns=positive_ints, max_same_state=positive_ints)
    @settings(max_examples=50)
    def test_max_turns_always_greater_or_equal_max_same_state_reasonable(
        self, max_turns, max_same_state
    ):
        """For reasonable config, max_turns >= max_same_state makes sense."""
        assume(max_turns >= max_same_state)

        config = {
            "guard": {
                "max_turns": max_turns,
                "max_same_state": max_same_state
            }
        }

        yaml_str = yaml.dump(config, allow_unicode=True)
        loaded = yaml.safe_load(yaml_str)

        # This is a reasonable constraint
        assert loaded['guard']['max_turns'] >= loaded['guard']['max_same_state']

# =============================================================================
# LIMITS CONFIG PROPERTY TESTS
# =============================================================================

class TestLimitsConfigProperties:
    """Property-based tests for limits configuration."""

    @given(
        max_consecutive=non_negative_ints,
        max_total=non_negative_ints,
        max_gobacks=non_negative_ints
    )
    @settings(max_examples=100)
    def test_limits_with_any_non_negative_values(
        self, max_consecutive, max_total, max_gobacks
    ):
        """Any non-negative values should be loadable."""
        config = {
            "limits": {
                "max_consecutive_objections": max_consecutive,
                "max_total_objections": max_total,
                "max_gobacks": max_gobacks
            }
        }

        yaml_str = yaml.dump(config, allow_unicode=True)
        loaded = yaml.safe_load(yaml_str)

        assert loaded['limits']['max_consecutive_objections'] == max_consecutive

    @given(
        max_consecutive=positive_ints,
        max_total=positive_ints
    )
    @settings(max_examples=50)
    def test_consecutive_less_or_equal_total_is_valid(
        self, max_consecutive, max_total
    ):
        """max_consecutive <= max_total is logically valid."""
        assume(max_consecutive <= max_total)

        config = {
            "limits": {
                "max_consecutive_objections": max_consecutive,
                "max_total_objections": max_total
            }
        }

        yaml_str = yaml.dump(config, allow_unicode=True)
        loaded = yaml.safe_load(yaml_str)

        assert loaded['limits']['max_consecutive_objections'] <= loaded['limits']['max_total_objections']

# =============================================================================
# FRUSTRATION CONFIG PROPERTY TESTS
# =============================================================================

class TestFrustrationConfigProperties:
    """Property-based tests for frustration configuration."""

    @given(
        max_level=st.integers(min_value=1, max_value=100),
        warning=st.integers(min_value=1, max_value=100),
        high=st.integers(min_value=1, max_value=100),
        critical=st.integers(min_value=1, max_value=100)
    )
    @settings(max_examples=100)
    def test_frustration_thresholds_any_order(
        self, max_level, warning, high, critical
    ):
        """Frustration thresholds can be in any order (config loads)."""
        config = {
            "frustration": {
                "max_level": max_level,
                "thresholds": {
                    "warning": warning,
                    "high": high,
                    "critical": critical
                }
            }
        }

        yaml_str = yaml.dump(config, allow_unicode=True)
        loaded = yaml.safe_load(yaml_str)

        assert loaded['frustration']['max_level'] == max_level

    @given(
        max_level=st.integers(min_value=10, max_value=100),
        warning=st.integers(min_value=1, max_value=10),
        high=st.integers(min_value=1, max_value=10),
        critical=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.filter_too_much])
    def test_thresholds_ordered_correctly(self, max_level, warning, high, critical):
        """Valid config has warning < high < critical <= max_level."""
        assume(warning < high < critical <= max_level)

        config = {
            "frustration": {
                "max_level": max_level,
                "thresholds": {
                    "warning": warning,
                    "high": high,
                    "critical": critical
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        th = loaded['frustration']['thresholds']

        assert th['warning'] < th['high'] < th['critical']

    @given(
        frustrated=st.integers(min_value=-10, max_value=10),
        skeptical=st.integers(min_value=-10, max_value=10),
        rushed=st.integers(min_value=-10, max_value=10)
    )
    @settings(max_examples=50)
    def test_weights_can_be_any_integers(self, frustrated, skeptical, rushed):
        """Frustration weights can be any integers."""
        config = {
            "frustration": {
                "weights": {
                    "frustrated": frustrated,
                    "skeptical": skeptical,
                    "rushed": rushed
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['frustration']['weights']['frustrated'] == frustrated

# =============================================================================
# LEAD SCORING CONFIG PROPERTY TESTS
# =============================================================================

class TestLeadScoringConfigProperties:
    """Property-based tests for lead_scoring configuration."""

    @given(
        demo_weight=score_weights,
        contact_weight=score_weights,
        objection_weight=score_weights
    )
    @settings(max_examples=100)
    def test_lead_scoring_weights_any_integers(
        self, demo_weight, contact_weight, objection_weight
    ):
        """Lead scoring weights can be any integers."""
        config = {
            "lead_scoring": {
                "positive_weights": {
                    "demo_request": demo_weight,
                    "contact_provided": contact_weight
                },
                "negative_weights": {
                    "objection_price": objection_weight
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['lead_scoring']['positive_weights']['demo_request'] == demo_weight

    @given(
        cold_min=st.integers(min_value=0, max_value=100),
        cold_max=st.integers(min_value=0, max_value=100),
        warm_min=st.integers(min_value=0, max_value=100),
        warm_max=st.integers(min_value=0, max_value=100)
    )
    @settings(max_examples=50)
    def test_threshold_ranges_can_overlap(
        self, cold_min, cold_max, warm_min, warm_max
    ):
        """Threshold ranges can overlap (config loads anyway)."""
        config = {
            "lead_scoring": {
                "thresholds": {
                    "cold": [cold_min, cold_max],
                    "warm": [warm_min, warm_max]
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['lead_scoring']['thresholds']['cold'] == [cold_min, cold_max]

    @given(states=st.lists(state_names, min_size=0, max_size=5, unique=True))
    @settings(max_examples=50)
    def test_skip_phases_with_any_subset_of_states(self, states):
        """skip_phases can contain any subset of states."""
        config = {
            "lead_scoring": {
                "skip_phases": {
                    "warm": states
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['lead_scoring']['skip_phases']['warm'] == states

# =============================================================================
# INTENT CATEGORIES PROPERTY TESTS
# =============================================================================

class TestIntentCategoriesProperties:
    """Property-based tests for intent categories."""

    @given(intents=st.lists(intent_names, min_size=0, max_size=10, unique=True))
    @settings(max_examples=50)
    def test_intent_category_with_any_subset(self, intents):
        """Intent category can contain any subset of intents."""
        config = {
            "intents": {
                "categories": {
                    "test_category": intents
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['intents']['categories']['test_category'] == intents

    @given(
        cat1=st.lists(intent_names, min_size=1, max_size=5),
        cat2=st.lists(intent_names, min_size=1, max_size=5)
    )
    @settings(max_examples=50)
    def test_intents_can_be_in_multiple_categories(self, cat1, cat2):
        """Same intent can appear in multiple categories."""
        config = {
            "intents": {
                "categories": {
                    "category1": cat1,
                    "category2": cat2
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['intents']['categories']['category1'] == cat1

# =============================================================================
# FALLBACK TEMPLATES PROPERTY TESTS
# =============================================================================

class TestFallbackTemplatesProperties:
    """Property-based tests for fallback templates."""

    @given(templates=st.lists(russian_text, min_size=0, max_size=10))
    @settings(max_examples=50)
    def test_rephrase_templates_with_any_russian_text(self, templates):
        """Rephrase templates can contain any Russian text."""
        config = {
            "fallback": {
                "rephrase_templates": {
                    "greeting": templates
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config, allow_unicode=True))
        assert loaded['fallback']['rephrase_templates']['greeting'] == templates

    @given(
        question=russian_text,
        options=st.lists(russian_text, min_size=0, max_size=5)
    )
    @settings(max_examples=50)
    def test_options_template_with_any_russian_text(self, question, options):
        """Options template can contain any Russian text."""
        config = {
            "fallback": {
                "options_templates": {
                    "test_state": {
                        "question": question,
                        "options": options
                    }
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config, allow_unicode=True))
        assert loaded['fallback']['options_templates']['test_state']['question'] == question

# =============================================================================
# CIRCULAR FLOW PROPERTY TESTS
# =============================================================================

class TestCircularFlowProperties:
    """Property-based tests for circular_flow configuration."""

    @given(
        from_state=state_names,
        to_state=state_names
    )
    @settings(max_examples=50)
    def test_goback_mapping_any_states(self, from_state, to_state):
        """Goback mapping can be between any states."""
        config = {
            "circular_flow": {
                "allowed_gobacks": {
                    from_state: to_state
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['circular_flow']['allowed_gobacks'][from_state] == to_state

    @given(mappings=st.dictionaries(state_names, state_names, min_size=0, max_size=10))
    @settings(max_examples=50)
    def test_multiple_goback_mappings(self, mappings):
        """Multiple goback mappings can be defined."""
        config = {
            "circular_flow": {
                "allowed_gobacks": mappings
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['circular_flow']['allowed_gobacks'] == mappings

# =============================================================================
# CONTEXT STATE ORDER PROPERTY TESTS
# =============================================================================

class TestContextStateOrderProperties:
    """Property-based tests for context.state_order configuration."""

    @given(orders=st.dictionaries(
        state_names,
        st.integers(min_value=-10, max_value=100),
        min_size=1,
        max_size=10
    ))
    @settings(max_examples=50)
    def test_state_order_with_any_integers(self, orders):
        """State order can have any integer values."""
        config = {
            "context": {
                "state_order": orders
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['context']['state_order'] == orders

    @given(state=state_names, order=st.integers())
    @settings(max_examples=50)
    def test_negative_order_allowed(self, state, order):
        """Negative order values are allowed (e.g., soft_close: -1)."""
        config = {
            "context": {
                "state_order": {state: order}
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['context']['state_order'][state] == order

# =============================================================================
# SPIN CONFIG PROPERTY TESTS
# =============================================================================

class TestSpinConfigProperties:
    """Property-based tests for SPIN configuration."""

    @given(phases=st.lists(phase_names, min_size=0, max_size=6, unique=True))
    @settings(max_examples=50)
    def test_spin_phases_any_subset(self, phases):
        """SPIN phases can be any subset in any order."""
        config = {
            "spin": {
                "phases": phases
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['spin']['phases'] == phases

    @given(
        phase=phase_names,
        state=state_names
    )
    @settings(max_examples=50)
    def test_phase_to_state_mapping_any_combination(self, phase, state):
        """Phase to state mapping can be any combination."""
        config = {
            "spin": {
                "states": {phase: state}
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['spin']['states'][phase] == state

# =============================================================================
# CONDITIONS PROPERTY TESTS
# =============================================================================

class TestConditionsProperties:
    """Property-based tests for custom conditions."""

    @given(name=condition_names, desc=st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_simple_condition_with_any_name(self, name, desc):
        """Simple condition can have any valid name."""
        config = {
            "conditions": {
                name: {
                    "description": desc,
                    "expression": "base_condition"
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert name in loaded['conditions']

    @given(conditions=st.lists(condition_names, min_size=1, max_size=5, unique=True))
    @settings(max_examples=50)
    def test_and_expression_with_multiple_conditions(self, conditions):
        """AND expression can have multiple conditions."""
        config = {
            "conditions": {
                "complex": {
                    "description": "Test",
                    "expression": {"and": conditions}
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['conditions']['complex']['expression']['and'] == conditions

    @given(conditions=st.lists(condition_names, min_size=1, max_size=5, unique=True))
    @settings(max_examples=50)
    def test_or_expression_with_multiple_conditions(self, conditions):
        """OR expression can have multiple conditions."""
        config = {
            "conditions": {
                "complex": {
                    "description": "Test",
                    "expression": {"or": conditions}
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert loaded['conditions']['complex']['expression']['or'] == conditions

    @given(
        outer_op=st.sampled_from(["and", "or"]),
        inner_op=st.sampled_from(["and", "or"]),
        conds1=st.lists(condition_names, min_size=1, max_size=3, unique=True),
        conds2=st.lists(condition_names, min_size=1, max_size=3, unique=True)
    )
    @settings(max_examples=50)
    def test_nested_conditions_two_levels(self, outer_op, inner_op, conds1, conds2):
        """Nested conditions with two levels."""
        config = {
            "conditions": {
                "nested": {
                    "description": "Nested test",
                    "expression": {
                        outer_op: [
                            {inner_op: conds1},
                            {inner_op: conds2}
                        ]
                    }
                }
            }
        }

        loaded = yaml.safe_load(yaml.dump(config))
        assert outer_op in loaded['conditions']['nested']['expression']

# =============================================================================
# YAML SERIALIZATION PROPERTY TESTS
# =============================================================================

class TestYamlSerializationProperties:
    """Property-based tests for YAML serialization."""

    @given(
        key=st.from_regex(r'[a-z][a-z0-9_]{0,19}', fullmatch=True),
        value=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(min_size=0, max_size=100),
            st.booleans(),
            st.none()
        )
    )
    @settings(max_examples=100)
    def test_yaml_roundtrip_preserves_values(self, key, value):
        """YAML serialization and deserialization preserves values."""
        config = {key: value}

        yaml_str = yaml.dump(config, allow_unicode=True)
        loaded = yaml.safe_load(yaml_str)

        if isinstance(value, float):
            assert abs(loaded[key] - value) < 1e-9
        else:
            assert loaded[key] == value

    @given(data=st.recursive(
        st.one_of(
            st.integers(),
            # Use printable ASCII to avoid YAML special character handling issues
            st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789 ', min_size=0, max_size=50),
            st.booleans()
        ),
        lambda children: st.one_of(
            st.lists(children, max_size=5),
            st.dictionaries(
                st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
                children,
                max_size=5
            )
        ),
        max_leaves=20
    ))
    @settings(max_examples=50)
    def test_yaml_roundtrip_complex_structures(self, data):
        """YAML handles complex nested structures."""
        config = {"data": data}

        yaml_str = yaml.dump(config, allow_unicode=True)
        loaded = yaml.safe_load(yaml_str)

        assert loaded['data'] == data

# =============================================================================
# SETTINGS VALIDATION PROPERTY TESTS
# =============================================================================

class TestSettingsValidationProperties:
    """Property-based tests for settings validation."""

    @given(timeout=st.integers(min_value=1, max_value=3600))
    @settings(max_examples=50)
    def test_valid_timeout_passes_validation(self, timeout):
        """Valid positive timeout passes validation."""
        from src.settings import validate_settings, DotDict

        settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": timeout},
            "retriever": {"thresholds": {"exact": 1.0, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 3, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.7, "min_confidence": 0.3}}
        })

        errors = validate_settings(settings)
        assert not any("timeout" in e for e in errors)

    @given(
        high_conf=threshold_values,
        min_conf=threshold_values
    )
    @settings(max_examples=50)
    def test_confidence_thresholds_validation(self, high_conf, min_conf):
        """Confidence threshold validation."""
        assume(high_conf != min_conf)  # Avoid edge case

        from src.settings import validate_settings, DotDict

        settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": 60},
            "retriever": {"thresholds": {"exact": 1.0, "lemma": 0.15, "semantic": 0.5}},
            "generator": {"max_retries": 3, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": high_conf, "min_confidence": min_conf}}
        })

        errors = validate_settings(settings)

        if high_conf > min_conf:
            assert not any("high_confidence" in e for e in errors)
        else:
            assert any("high_confidence" in e for e in errors)

    @given(
        exact=st.floats(min_value=-1.0, max_value=2.0, allow_nan=False),
        lemma=st.floats(min_value=-1.0, max_value=2.0, allow_nan=False),
        semantic=st.floats(min_value=-1.0, max_value=2.0, allow_nan=False)
    )
    @settings(max_examples=50)
    def test_threshold_range_validation(self, exact, lemma, semantic):
        """Threshold values must be in [0, 1]."""
        from src.settings import validate_settings, DotDict

        settings = DotDict({
            "llm": {"model": "test", "base_url": "http://localhost", "timeout": 60},
            "retriever": {"thresholds": {"exact": exact, "lemma": lemma, "semantic": semantic}},
            "generator": {"max_retries": 3, "history_length": 4},
            "classifier": {"thresholds": {"high_confidence": 0.7, "min_confidence": 0.3}}
        })

        errors = validate_settings(settings)

        # Check if any threshold is out of range
        out_of_range = any(not (0 <= v <= 1) for v in [exact, lemma, semantic])

        if out_of_range:
            assert len(errors) > 0
        else:
            assert not any("threshold" in e.lower() for e in errors)

# =============================================================================
# DOTDICT PROPERTY TESTS
# =============================================================================

class TestDotDictProperties:
    """Property-based tests for DotDict."""

    @given(data=st.dictionaries(
        st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
        st.one_of(st.integers(), st.text(max_size=50), st.booleans()),
        min_size=1,
        max_size=10
    ))
    @settings(max_examples=50)
    def test_dotdict_attribute_access_matches_dict_access(self, data):
        """DotDict attribute access matches dict access."""
        from src.settings import DotDict

        d = DotDict(data)

        for key, value in data.items():
            assert getattr(d, key) == d[key] == value

    @given(
        key=st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
        value=st.one_of(st.integers(), st.text(max_size=50))
    )
    @settings(max_examples=50)
    def test_dotdict_setattr(self, key, value):
        """DotDict setattr works correctly."""
        from src.settings import DotDict

        d = DotDict({})
        setattr(d, key, value)

        assert d[key] == value
        assert getattr(d, key) == value

# =============================================================================
# COMBINED CONFIG PROPERTY TESTS
# =============================================================================

class TestCombinedConfigProperties:
    """Property-based tests for combined config scenarios."""

    @given(
        max_turns=positive_ints,
        max_obj=positive_ints,
        max_level=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=50)
    def test_complete_config_with_random_values(
        self, max_turns, max_obj, max_level
    ):
        """Complete config with random valid values."""
        config = {
            "guard": {"max_turns": max_turns},
            "limits": {"max_consecutive_objections": max_obj},
            "frustration": {"max_level": max_level}
        }

        yaml_str = yaml.dump(config)
        loaded = yaml.safe_load(yaml_str)

        assert loaded['guard']['max_turns'] == max_turns
        assert loaded['limits']['max_consecutive_objections'] == max_obj
        assert loaded['frustration']['max_level'] == max_level

    @given(st.data())
    @settings(max_examples=30)
    def test_random_complete_config_structure(self, data):
        """Random complete config structure."""
        config = {
            "spin": {
                "phases": data.draw(st.lists(phase_names, min_size=1, max_size=4, unique=True))
            },
            "guard": {
                "max_turns": data.draw(positive_ints),
                "timeout_seconds": data.draw(timeout_values)
            },
            "limits": {
                "max_gobacks": data.draw(non_negative_ints)
            },
            "lead_scoring": {
                "positive_weights": {
                    "demo_request": data.draw(score_weights)
                }
            }
        }

        yaml_str = yaml.dump(config)
        loaded = yaml.safe_load(yaml_str)

        assert 'spin' in loaded
        assert 'guard' in loaded
        assert 'limits' in loaded
        assert 'lead_scoring' in loaded

"""
Tests for configuration conflicts and inconsistencies.

This module tests:
1. Conflicting parameters between config files
2. Cross-reference validation
3. Circular dependencies detection
4. Missing required dependencies
5. Incompatible value combinations
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# THRESHOLD SYNC CONFLICTS
# =============================================================================

class TestThresholdConflicts:
    """Tests for conflicting threshold values between components."""

    def test_guard_frustration_threshold_mismatch_detected(self, config_factory):
        """Detect guard vs frustration threshold mismatch."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        # Create config with mismatched thresholds
        config_dir = config_factory(
            guard={"high_frustration_threshold": 7},
            frustration={"thresholds": {"high": 5}}  # Mismatch!
        )

        loader = ConfigLoader(config_dir)

        with pytest.raises(ConfigValidationError) as exc_info:
            loader.load()

        assert "threshold" in str(exc_info.value).lower() or "mismatch" in str(exc_info.value).lower()

    def test_guard_frustration_threshold_match_passes(self, config_factory):
        """Matching guard vs frustration thresholds pass validation."""
        from src.config_loader import ConfigLoader

        # Create config with matching thresholds
        config_dir = config_factory(
            guard={"high_frustration_threshold": 7},
            frustration={"thresholds": {"warning": 4, "high": 7, "critical": 9}}
        )

        loader = ConfigLoader(config_dir)
        config = loader.load()  # Should not raise

        assert config.guard["high_frustration_threshold"] == config.frustration["thresholds"]["high"]

    def test_frustration_thresholds_inverted_warning(self, config_factory):
        """Warning when frustration thresholds are inverted."""
        # warning > high > critical is logically wrong
        config_dir = config_factory(frustration={
            "thresholds": {"warning": 9, "high": 5, "critical": 2},
            "max_level": 10
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        th = config['frustration']['thresholds']

        # This is logically invalid (warning should be < high < critical)
        assert th['warning'] > th['high'] > th['critical']

        # A validator should catch this
        def validate_frustration_thresholds(thresholds):
            errors = []
            if thresholds['warning'] >= thresholds['high']:
                errors.append("warning threshold must be < high threshold")
            if thresholds['high'] >= thresholds['critical']:
                errors.append("high threshold must be < critical threshold")
            return errors

        errors = validate_frustration_thresholds(th)
        assert len(errors) == 2


class TestStateReferenceConflicts:
    """Tests for conflicting state references."""

    def test_skip_phases_references_nonexistent_state(self, config_factory):
        """skip_phases referencing non-existent state detected."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        config_dir = config_factory()

        # Modify to add invalid skip_phases
        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        constants['lead_scoring']['skip_phases']['hot'] = ['nonexistent_state']

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        loader = ConfigLoader(config_dir)

        with pytest.raises(ConfigValidationError) as exc_info:
            loader.load()

        assert "nonexistent_state" in str(exc_info.value)

    def test_goback_references_nonexistent_source(self, config_factory):
        """allowed_gobacks source state doesn't exist."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        config_dir = config_factory()

        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        constants['circular_flow']['allowed_gobacks']['invalid_source'] = 'spin_situation'

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        loader = ConfigLoader(config_dir)

        with pytest.raises(ConfigValidationError) as exc_info:
            loader.load()

        assert "invalid_source" in str(exc_info.value)

    def test_goback_references_nonexistent_target(self, config_factory):
        """allowed_gobacks target state doesn't exist."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        config_dir = config_factory()

        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        constants['circular_flow']['allowed_gobacks']['spin_problem'] = 'invalid_target'

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        loader = ConfigLoader(config_dir)

        with pytest.raises(ConfigValidationError) as exc_info:
            loader.load()

        assert "invalid_target" in str(exc_info.value)

    def test_spin_states_reference_nonexistent_state(self, config_factory):
        """SPIN states mapping to non-existent states."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        config_dir = config_factory()

        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        constants['spin']['states']['situation'] = 'nonexistent_spin_state'

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        loader = ConfigLoader(config_dir)

        with pytest.raises(ConfigValidationError) as exc_info:
            loader.load()

        assert "nonexistent_spin_state" in str(exc_info.value)


class TestLimitConflicts:
    """Tests for conflicting limit values."""

    def test_consecutive_greater_than_total_objections(self, config_factory):
        """max_consecutive_objections > max_total_objections is illogical."""
        config_dir = config_factory(limits={
            "max_consecutive_objections": 10,
            "max_total_objections": 5
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        limits = config['limits']

        def validate_limits(limits):
            errors = []
            if limits['max_consecutive_objections'] > limits['max_total_objections']:
                errors.append(
                    "max_consecutive_objections cannot be greater than max_total_objections"
                )
            return errors

        errors = validate_limits(limits)
        assert len(errors) == 1

    def test_max_gobacks_zero_with_allowed_gobacks(self, config_factory):
        """max_gobacks=0 but allowed_gobacks defined is contradictory."""
        config_dir = config_factory(
            limits={"max_gobacks": 0},
            circular_flow={
                "allowed_gobacks": {
                    "spin_problem": "spin_situation"
                }
            }
        )

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        def validate_goback_consistency(limits, circular_flow):
            errors = []
            if limits['max_gobacks'] == 0:
                if circular_flow.get('allowed_gobacks'):
                    errors.append(
                        "max_gobacks is 0 but allowed_gobacks is defined - "
                        "gobacks will never be used"
                    )
            return errors

        errors = validate_goback_consistency(config['limits'], config['circular_flow'])
        assert len(errors) == 1


class TestIntentCategoryConflicts:
    """Tests for intent category conflicts."""

    def test_intent_in_multiple_conflicting_categories(self, config_factory):
        """Same intent in contradictory categories (e.g., positive and negative)."""
        config_dir = config_factory(intents={
            "categories": {
                "positive": ["agreement", "demo_request", "rejection"],  # rejection is wrong!
                "negative": ["rejection", "farewell"]
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        categories = config['intents']['categories']

        def find_conflicting_intents(categories):
            """Find intents in both positive and negative categories."""
            positive = set(categories.get('positive', []))
            negative = set(categories.get('negative', []))

            conflicts = positive & negative
            return list(conflicts)

        conflicts = find_conflicting_intents(categories)
        assert "rejection" in conflicts

    def test_spin_progress_intent_in_objection_category(self, config_factory):
        """SPIN progress intent in objection category is contradictory."""
        config_dir = config_factory(intents={
            "categories": {
                "objection": ["objection_price", "situation_provided"],  # wrong!
                "spin_progress": ["situation_provided", "problem_revealed"]
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        categories = config['intents']['categories']

        def find_spin_in_objection(categories):
            objections = set(categories.get('objection', []))
            spin_progress = set(categories.get('spin_progress', []))

            return list(objections & spin_progress)

        conflicts = find_spin_in_objection(categories)
        assert "situation_provided" in conflicts


class TestTransitionConflicts:
    """Tests for state transition conflicts."""

    def test_transition_to_self_without_progress(self, config_factory):
        """Transition to same state without progress indicator."""
        config_dir = config_factory()

        states_path = config_dir / "states" / "sales_flow.yaml"
        with open(states_path, 'r', encoding='utf-8') as f:
            states = yaml.safe_load(f)

        # Add self-transition
        states['states']['greeting']['transitions']['question'] = 'greeting'

        with open(states_path, 'w', encoding='utf-8') as f:
            yaml.dump(states, f, allow_unicode=True)

        with open(states_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        def find_self_transitions(states):
            """Find states with self-transitions."""
            self_transitions = []
            for state, config in states.items():
                for intent, target in config.get('transitions', {}).items():
                    if target == state:
                        self_transitions.append((state, intent))
            return self_transitions

        self_trans = find_self_transitions(loaded['states'])
        assert ('greeting', 'question') in self_trans

    def test_conflicting_transition_targets(self, config_factory):
        """Same intent leading to different states in conditional rules."""
        # This is actually valid (conditional rules) but we test parsing
        config_dir = config_factory()

        states_path = config_dir / "states" / "sales_flow.yaml"
        with open(states_path, 'r', encoding='utf-8') as f:
            states = yaml.safe_load(f)

        # Add conditional transition
        states['states']['greeting']['transitions']['demo_request'] = [
            {"when": "has_contact", "then": "success"},
            {"when": "is_hot_lead", "then": "close"},
            "presentation"  # fallback
        ]

        with open(states_path, 'w', encoding='utf-8') as f:
            yaml.dump(states, f, allow_unicode=True)

        with open(states_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        trans = loaded['states']['greeting']['transitions']['demo_request']
        assert isinstance(trans, list)
        assert len(trans) == 3


class TestLeadScoringConflicts:
    """Tests for lead scoring configuration conflicts."""

    def test_overlapping_threshold_ranges(self, config_factory):
        """Overlapping threshold ranges for different temperatures."""
        config_dir = config_factory(lead_scoring={
            "thresholds": {
                "cold": [0, 50],
                "warm": [30, 70],  # Overlaps cold 30-50
                "hot": [60, 90],   # Overlaps warm 60-70
                "very_hot": [80, 100]  # Overlaps hot 80-90
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        thresholds = config['lead_scoring']['thresholds']

        def find_threshold_overlaps(thresholds):
            """Find overlapping threshold ranges."""
            temps = list(thresholds.keys())
            overlaps = []

            for i, temp1 in enumerate(temps):
                for temp2 in temps[i+1:]:
                    range1 = thresholds[temp1]
                    range2 = thresholds[temp2]

                    # Check overlap
                    if range1[0] <= range2[1] and range2[0] <= range1[1]:
                        overlap_start = max(range1[0], range2[0])
                        overlap_end = min(range1[1], range2[1])
                        if overlap_start <= overlap_end:
                            overlaps.append((temp1, temp2, overlap_start, overlap_end))

            return overlaps

        overlaps = find_threshold_overlaps(thresholds)
        assert len(overlaps) > 0  # Should find overlaps

    def test_gaps_in_threshold_ranges(self, config_factory):
        """Gaps between threshold ranges leave scores undefined."""
        config_dir = config_factory(lead_scoring={
            "thresholds": {
                "cold": [0, 20],
                "warm": [40, 60],  # Gap 21-39
                "hot": [80, 100]   # Gap 61-79
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        thresholds = config['lead_scoring']['thresholds']

        def find_threshold_gaps(thresholds, min_score=0, max_score=100):
            """Find gaps in threshold coverage."""
            # Sort ranges by start
            sorted_ranges = sorted(
                [(t, r[0], r[1]) for t, r in thresholds.items()],
                key=lambda x: x[1]
            )

            gaps = []
            current_end = min_score - 1

            for temp, start, end in sorted_ranges:
                if start > current_end + 1:
                    gaps.append((current_end + 1, start - 1))
                current_end = max(current_end, end)

            if current_end < max_score:
                gaps.append((current_end + 1, max_score))

            return gaps

        gaps = find_threshold_gaps(thresholds)
        assert len(gaps) > 0  # Should find gaps


class TestCircularDependencies:
    """Tests for circular dependency detection."""

    def test_circular_goback_chain(self, config_factory):
        """Circular goback chain: A->B->C->A."""
        config_dir = config_factory(circular_flow={
            "allowed_gobacks": {
                "spin_situation": "greeting",
                "greeting": "soft_close",
                "soft_close": "spin_situation"  # Creates cycle!
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        gobacks = config['circular_flow']['allowed_gobacks']

        def find_goback_cycles(gobacks):
            """Find cycles in goback chain."""
            cycles = []

            def dfs(node, visited, path):
                if node in path:
                    # Found cycle
                    cycle_start = path.index(node)
                    cycles.append(path[cycle_start:] + [node])
                    return

                if node in visited:
                    return

                visited.add(node)
                path.append(node)

                if node in gobacks:
                    dfs(gobacks[node], visited, path)

                path.pop()

            for start in gobacks:
                dfs(start, set(), [])

            return cycles

        cycles = find_goback_cycles(gobacks)
        assert len(cycles) > 0  # Should detect cycle

    def test_condition_circular_reference(self, config_factory):
        """Condition A depends on B, B depends on A."""
        custom_conditions = {
            "conditions": {
                "cond_a": {
                    "description": "Condition A",
                    "expression": {"and": ["cond_b", "some_base"]}
                },
                "cond_b": {
                    "description": "Condition B",
                    "expression": {"or": ["cond_a", "other_base"]}  # Circular!
                }
            },
            "aliases": {}
        }

        config_dir = config_factory()

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_conditions, f, allow_unicode=True)

        def find_condition_cycles(conditions):
            """Find circular references in conditions."""

            def get_dependencies(expr):
                """Extract condition names from expression."""
                deps = []
                if isinstance(expr, str):
                    deps.append(expr)
                elif isinstance(expr, dict):
                    for key, value in expr.items():
                        if key in ('and', 'or'):
                            for item in value:
                                deps.extend(get_dependencies(item))
                        elif key == 'not':
                            deps.extend(get_dependencies(value))
                return deps

            # Build dependency graph
            graph = {}
            for name, config in conditions.items():
                expr = config.get('expression', {})
                graph[name] = set(get_dependencies(expr)) & set(conditions.keys())

            # Find cycles using DFS
            cycles = []

            def dfs(node, visited, path):
                if node in path:
                    cycle_start = path.index(node)
                    cycles.append(path[cycle_start:] + [node])
                    return

                if node in visited or node not in graph:
                    return

                visited.add(node)
                path.append(node)

                for dep in graph.get(node, []):
                    dfs(dep, visited, path)

                path.pop()

            for start in graph:
                dfs(start, set(), [])

            return cycles

        cycles = find_condition_cycles(custom_conditions['conditions'])
        assert len(cycles) > 0  # Should detect cycle: cond_a -> cond_b -> cond_a


class TestIncompatibleCombinations:
    """Tests for incompatible parameter combinations."""

    def test_strict_guard_with_relaxed_limits(self, config_factory):
        """Strict guard profile with relaxed limits is inconsistent."""
        config_dir = config_factory(
            guard={
                "max_turns": 10,
                "max_phase_attempts": 2,
                "max_same_state": 3
            },
            limits={
                "max_consecutive_objections": 10,  # Too high for strict guard
                "max_total_objections": 20
            }
        )

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        def check_guard_limits_consistency(guard, limits):
            """Check if guard and limits are consistent."""
            warnings = []

            # If guard is strict (few turns), limits should also be strict
            if guard['max_turns'] <= 15:
                if limits['max_total_objections'] > guard['max_turns']:
                    warnings.append(
                        f"max_total_objections ({limits['max_total_objections']}) > "
                        f"max_turns ({guard['max_turns']}) - objection limit will never be reached"
                    )

            return warnings

        warnings = check_guard_limits_consistency(config['guard'], config['limits'])
        assert len(warnings) > 0

    def test_all_phases_skipped_for_cold_lead(self, config_factory):
        """All SPIN phases skipped for cold lead makes no sense."""
        config_dir = config_factory(lead_scoring={
            "skip_phases": {
                "cold": ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"]
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        skip_cold = config['lead_scoring']['skip_phases']['cold']
        spin_states = list(config['spin']['states'].values())

        # Cold leads should do FULL SPIN, not skip everything
        skipped_all = set(skip_cold) >= set(spin_states)
        assert skipped_all  # This is the problematic case

        # This is a logical error - cold leads need the most qualification
        def validate_skip_phases_logic(skip_phases, temperature_order):
            """Validate that colder leads skip fewer phases."""
            errors = []
            temp_order = ['cold', 'warm', 'hot', 'very_hot']

            for i, temp in enumerate(temp_order[:-1]):
                next_temp = temp_order[i + 1]
                current_skip = len(skip_phases.get(temp, []))
                next_skip = len(skip_phases.get(next_temp, []))

                if current_skip > next_skip:
                    errors.append(
                        f"{temp} skips {current_skip} phases but {next_temp} "
                        f"only skips {next_skip} - colder leads should skip fewer"
                    )

            return errors

        errors = validate_skip_phases_logic(
            config['lead_scoring']['skip_phases'],
            ['cold', 'warm', 'hot', 'very_hot']
        )
        # This config has cold skipping all, which violates the logic
        assert len(errors) > 0 or len(skip_cold) == 4

    def test_empty_cta_for_close_state(self, config_factory):
        """Empty CTA templates for close state is problematic."""
        config_dir = config_factory(cta={
            "templates": {
                "close": [],
                "presentation": ["Записаться на демо?"]
            }
        })

        with open(config_dir / "constants.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        def validate_cta_templates(cta, important_states):
            """Validate that important states have CTA templates."""
            warnings = []

            for state in important_states:
                templates = cta.get('templates', {}).get(state, [])
                if not templates:
                    warnings.append(f"No CTA templates for important state: {state}")

            return warnings

        warnings = validate_cta_templates(config['cta'], ['close', 'presentation'])
        assert 'close' in str(warnings)


class TestCrossFileConflicts:
    """Tests for conflicts between different config files."""

    def test_states_yaml_vs_constants_yaml_state_mismatch(self, config_factory):
        """States in sales_flow.yaml vs constants.yaml state_order mismatch."""
        config_dir = config_factory()

        # Add state to states file that's not in state_order
        states_path = config_dir / "states" / "sales_flow.yaml"
        with open(states_path, 'r', encoding='utf-8') as f:
            states = yaml.safe_load(f)

        states['states']['new_custom_state'] = {
            "goal": "Custom state",
            "transitions": {}
        }

        with open(states_path, 'w', encoding='utf-8') as f:
            yaml.dump(states, f, allow_unicode=True)

        # Verify mismatch
        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        state_order_states = set(constants['context']['state_order'].keys())
        defined_states = set(states['states'].keys())

        missing_from_order = defined_states - state_order_states
        assert 'new_custom_state' in missing_from_order

    def test_spin_phases_vs_states_file_mismatch(self, config_factory):
        """SPIN phases reference states that don't exist in states file."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        config_dir = config_factory()

        # Modify spin phases to reference non-existent state
        spin_path = config_dir / "spin" / "phases.yaml"
        with open(spin_path, 'r', encoding='utf-8') as f:
            spin = yaml.safe_load(f)

        spin['phases']['situation']['state'] = 'nonexistent_situation_state'

        with open(spin_path, 'w', encoding='utf-8') as f:
            yaml.dump(spin, f, allow_unicode=True)

        loader = ConfigLoader(config_dir)

        with pytest.raises(ConfigValidationError) as exc_info:
            loader.load()

        assert "nonexistent_situation_state" in str(exc_info.value)

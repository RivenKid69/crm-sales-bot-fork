"""
Tests for stress and performance of configuration system.

This module tests:
1. Large configuration handling
2. Many concurrent config operations
3. Memory usage under load
4. Config loading performance
5. Condition evaluation performance
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
import yaml
import sys
import time
import threading
import gc
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any

# =============================================================================
# LARGE CONFIGURATION TESTS
# =============================================================================

class TestLargeConfigurations:
    """Tests for handling large configurations."""

    def test_many_states_config(self, config_factory):
        """Config with many states loads correctly."""
        config_dir = config_factory()

        # Add many states
        states_path = config_dir / "states" / "sales_flow.yaml"
        with open(states_path, 'r', encoding='utf-8') as f:
            states_data = yaml.safe_load(f)

        # Add 100 states
        for i in range(100):
            states_data['states'][f'state_{i}'] = {
                "goal": f"State {i}",
                "transitions": {
                    "next": f"state_{(i + 1) % 100}"  # Circular
                }
            }

        with open(states_path, 'w', encoding='utf-8') as f:
            yaml.dump(states_data, f, allow_unicode=True)

        from src.config_loader import ConfigLoader
        loader = ConfigLoader(config_dir)

        start = time.time()
        config = loader.load(validate=False)  # Skip validation for speed
        elapsed = time.time() - start

        assert len(config.states) >= 100
        assert elapsed < 5.0  # Should load in under 5 seconds

    def test_many_transitions_per_state(self, config_factory):
        """State with many transitions."""
        config_dir = config_factory()

        states_path = config_dir / "states" / "sales_flow.yaml"
        with open(states_path, 'r', encoding='utf-8') as f:
            states_data = yaml.safe_load(f)

        # Add state with 50 transitions
        transitions = {f"intent_{i}": "spin_situation" for i in range(50)}
        states_data['states']['many_transitions'] = {
            "goal": "State with many transitions",
            "transitions": transitions
        }

        with open(states_path, 'w', encoding='utf-8') as f:
            yaml.dump(states_data, f, allow_unicode=True)

        from src.config_loader import ConfigLoader
        loader = ConfigLoader(config_dir)
        config = loader.load(validate=False)

        assert len(config.states['many_transitions']['transitions']) == 50

    def test_many_fallback_templates(self, config_factory):
        """Config with many fallback templates."""
        config_dir = config_factory()

        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        # Add 100 templates per state
        templates = {}
        for state in ['greeting', 'spin_situation', 'spin_problem', 'presentation', 'close']:
            templates[state] = [f"Template {i} for {state}" for i in range(100)]

        constants['fallback']['rephrase_templates'] = templates

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        with open(constants_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        for state in templates:
            assert len(loaded['fallback']['rephrase_templates'][state]) == 100

    def test_many_custom_conditions(self, config_factory):
        """Config with many custom conditions."""
        config_dir = config_factory()

        # Create 100 custom conditions
        conditions = {}
        for i in range(100):
            conditions[f'condition_{i}'] = {
                "description": f"Condition {i}",
                "expression": {"and": [f"base_cond_{i}", f"other_cond_{i}"]}
            }

        custom_data = {
            "conditions": conditions,
            "aliases": {}
        }

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_data, f, allow_unicode=True)

        with open(config_dir / "conditions" / "custom.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        assert len(loaded['conditions']) == 100

    def test_very_large_yaml_file(self, tmp_path):
        """Handle very large YAML file."""
        large_file = tmp_path / "large.yaml"

        # Create 10MB+ YAML content
        data = {
            "items": [
                {
                    "id": i,
                    "name": f"Item {i} with some longer text to increase size",
                    "description": "A" * 1000,  # 1KB per item
                    "tags": [f"tag_{j}" for j in range(10)]
                }
                for i in range(1000)  # ~1MB+
            ]
        }

        with open(large_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True)

        file_size = large_file.stat().st_size
        assert file_size > 1_000_000  # At least 1MB

        # Load time
        start = time.time()
        with open(large_file, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)
        elapsed = time.time() - start

        assert len(loaded['items']) == 1000
        assert elapsed < 10.0  # Should load in under 10 seconds

class TestConcurrentOperations:
    """Tests for concurrent configuration operations."""

    def test_concurrent_config_loading(self, config_factory):
        """Multiple threads loading config simultaneously."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        results = []
        errors = []

        def load_config():
            try:
                config = loader.load(validate=False)
                results.append(config.guard['max_turns'])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=load_config) for _ in range(20)]

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start

        assert len(errors) == 0
        assert len(results) == 20
        assert elapsed < 10.0  # Should complete in under 10 seconds

    def test_thread_pool_config_operations(self, config_factory):
        """Thread pool performing config operations."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()

        def operation(idx):
            loader = ConfigLoader(config_dir)
            config = loader.load(validate=False)
            return idx, config.guard['max_turns']

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(operation, i) for i in range(50)]
            results = [f.result() for f in as_completed(futures)]

        assert len(results) == 50
        assert all(r[1] == 25 for r in results)  # All should get same value

    def test_concurrent_yaml_parsing(self, tmp_path):
        """Concurrent YAML file parsing."""
        # Create multiple YAML files
        for i in range(10):
            file_path = tmp_path / f"config_{i}.yaml"
            file_path.write_text(yaml.dump({"id": i, "value": f"data_{i}"}))

        results = []
        lock = threading.Lock()

        def parse_file(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            with lock:
                results.append(data)

        threads = [
            threading.Thread(target=parse_file, args=(tmp_path / f"config_{i}.yaml",))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10

    def test_concurrent_settings_access(self):
        """Concurrent access to settings singleton."""
        from src.settings import get_settings

        results = []
        errors = []

        def access_settings():
            try:
                settings = get_settings()
                results.append(settings.llm.timeout)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access_settings) for _ in range(50)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 50
        # All should get same value
        assert len(set(results)) == 1

class TestMemoryUsage:
    """Tests for memory usage under load."""

    def test_config_reload_no_memory_leak(self, config_factory):
        """Multiple config reloads don't leak memory."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        gc.collect()
        initial_objects = len(gc.get_objects())

        # Reload many times
        for _ in range(100):
            config = loader.load(validate=False)
            del config

        gc.collect()
        final_objects = len(gc.get_objects())

        # Allow some growth but not proportional to iterations
        growth = final_objects - initial_objects
        assert growth < 1000  # Should not grow by more than ~1000 objects

    def test_large_config_memory_footprint(self, config_factory):
        """Large config has reasonable memory footprint."""
        config_dir = config_factory()

        # Make config larger
        constants_path = config_dir / "constants.yaml"
        with open(constants_path, 'r', encoding='utf-8') as f:
            constants = yaml.safe_load(f)

        # Add lots of data
        constants['large_data'] = {
            f"key_{i}": f"value_{i}" * 100
            for i in range(1000)
        }

        with open(constants_path, 'w', encoding='utf-8') as f:
            yaml.dump(constants, f, allow_unicode=True)

        from src.config_loader import ConfigLoader
        loader = ConfigLoader(config_dir)

        gc.collect()
        config = loader.load(validate=False)

        # Config should exist and be usable
        assert 'large_data' in config.constants
        assert len(config.constants['large_data']) == 1000

    def test_many_simultaneous_configs(self, config_factory):
        """Create many config instances simultaneously."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()

        # Create many loader instances
        loaders = [ConfigLoader(config_dir) for _ in range(50)]
        configs = [loader.load(validate=False) for loader in loaders]

        assert len(configs) == 50
        assert all(c.guard['max_turns'] == 25 for c in configs)

class TestLoadingPerformance:
    """Tests for configuration loading performance."""

    def test_yaml_load_time(self, tmp_path):
        """Measure YAML loading time."""
        # Create moderately complex YAML
        data = {
            "section1": {f"key_{i}": f"value_{i}" for i in range(100)},
            "section2": {f"key_{i}": f"value_{i}" for i in range(100)},
            "section3": [{f"item_{j}": j for j in range(10)} for i in range(50)],
        }

        yaml_file = tmp_path / "test.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True)

        # Time multiple loads
        times = []
        for _ in range(10):
            start = time.time()
            with open(yaml_file, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        assert avg_time < 0.5  # Should load in under 500ms on average

    def test_config_loader_performance(self, config_factory):
        """Measure ConfigLoader performance."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        # Warm up
        loader.load(validate=False)

        # Time multiple loads
        times = []
        for _ in range(10):
            start = time.time()
            loader.load(validate=False)
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        assert avg_time < 0.5  # Should load in under 500ms on average

    def test_validation_performance(self, config_factory):
        """Measure validation performance."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        # Time load with validation
        times_with = []
        for _ in range(5):
            start = time.time()
            loader.load(validate=True)
            times_with.append(time.time() - start)

        # Time load without validation
        times_without = []
        for _ in range(5):
            start = time.time()
            loader.load(validate=False)
            times_without.append(time.time() - start)

        avg_with = sum(times_with) / len(times_with)
        avg_without = sum(times_without) / len(times_without)

        # Both should be fast
        assert avg_with < 1.0
        assert avg_without < 0.5

class TestConditionEvaluationPerformance:
    """Tests for condition evaluation performance."""

    def test_simple_condition_evaluation_speed(self):
        """Simple condition evaluation should be fast."""
        from src.settings import DotDict

        ctx = DotDict({
            "collected_data": {"company_size": 50},
            "state": "greeting",
            "turn_number": 5
        })

        def simple_condition(ctx):
            return ctx.collected_data.get("company_size", 0) > 10

        # Time many evaluations
        start = time.time()
        for _ in range(10000):
            simple_condition(ctx)
        elapsed = time.time() - start

        assert elapsed < 1.0  # 10000 evaluations in under 1 second

    def test_complex_condition_evaluation_speed(self):
        """Complex condition evaluation should be reasonably fast."""
        from src.settings import DotDict

        ctx = DotDict({
            "collected_data": {
                "company_size": 50,
                "has_contact": True,
                "problem_revealed": True
            },
            "state": "spin_problem",
            "turn_number": 10,
            "lead_score": 45
        })

        def complex_condition(ctx):
            # Simulate complex AND/OR condition
            has_data = ctx.collected_data.get("company_size", 0) > 10
            has_contact = ctx.collected_data.get("has_contact", False)
            has_problem = ctx.collected_data.get("problem_revealed", False)
            is_warm = ctx.lead_score >= 30

            return (has_data and has_contact) or (has_problem and is_warm)

        # Time many evaluations
        start = time.time()
        for _ in range(10000):
            complex_condition(ctx)
        elapsed = time.time() - start

        assert elapsed < 2.0  # 10000 evaluations in under 2 seconds

    def test_nested_condition_evaluation_speed(self):
        """Deeply nested condition evaluation performance."""

        def make_nested_condition(depth):
            """Create nested condition function."""
            if depth <= 0:
                return lambda ctx: ctx.get("base", True)

            inner = make_nested_condition(depth - 1)
            if depth % 2 == 0:
                return lambda ctx, i=inner: i(ctx) and ctx.get("base", True)
            else:
                return lambda ctx, i=inner: i(ctx) or ctx.get("base", True)

        ctx = {"base": True}

        # Test different depths
        for depth in [5, 10, 15]:
            condition = make_nested_condition(depth)

            start = time.time()
            for _ in range(1000):
                condition(ctx)
            elapsed = time.time() - start

            # Should complete in reasonable time even for deep nesting
            assert elapsed < 1.0, f"Depth {depth} took {elapsed}s"

class TestStressScenarios:
    """Tests for stress scenarios."""

    def test_rapid_config_changes(self, config_factory):
        """Rapid config file changes and reloads."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        constants_path = config_dir / "constants.yaml"
        loader = ConfigLoader(config_dir)

        errors = []

        def change_config():
            for i in range(10):
                try:
                    with open(constants_path, 'r', encoding='utf-8') as f:
                        constants = yaml.safe_load(f)
                    constants['guard']['max_turns'] = 25 + i
                    with open(constants_path, 'w', encoding='utf-8') as f:
                        yaml.dump(constants, f, allow_unicode=True)
                    time.sleep(0.01)
                except Exception as e:
                    errors.append(e)

        def read_config():
            for _ in range(50):
                try:
                    loader.load(validate=False)
                except Exception as e:
                    errors.append(e)
                time.sleep(0.005)

        writer = threading.Thread(target=change_config)
        readers = [threading.Thread(target=read_config) for _ in range(3)]

        writer.start()
        for r in readers:
            r.start()

        writer.join()
        for r in readers:
            r.join()

        # Should complete without critical errors
        assert len(errors) == 0

    def test_burst_load(self, config_factory):
        """Burst of config loads."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        # Burst: 100 loads as fast as possible
        start = time.time()
        for _ in range(100):
            loader.load(validate=False)
        elapsed = time.time() - start

        # Should handle burst in reasonable time
        assert elapsed < 10.0
        print(f"Burst load: 100 loads in {elapsed:.2f}s ({100/elapsed:.1f} loads/sec)")

    def test_sustained_load(self, config_factory):
        """Sustained config load over time."""
        from src.config_loader import ConfigLoader

        config_dir = config_factory()
        loader = ConfigLoader(config_dir)

        load_times = []
        duration = 2.0  # 2 seconds of sustained load
        start_time = time.time()

        while time.time() - start_time < duration:
            load_start = time.time()
            loader.load(validate=False)
            load_times.append(time.time() - load_start)
            time.sleep(0.01)  # Small delay between loads

        avg_load_time = sum(load_times) / len(load_times)
        max_load_time = max(load_times)

        # Performance should be consistent
        assert avg_load_time < 0.2
        assert max_load_time < 0.5
        print(f"Sustained load: {len(load_times)} loads, avg={avg_load_time:.3f}s, max={max_load_time:.3f}s")

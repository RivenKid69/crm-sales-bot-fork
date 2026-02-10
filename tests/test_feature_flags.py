"""
Тесты для модуля feature flags (feature_flags.py).
"""

import pytest
import os
import sys
from pathlib import Path

from src.feature_flags import FeatureFlags, feature_flag

class TestFeatureFlagsBasic:
    """Базовые тесты FeatureFlags"""

    def test_create_feature_flags(self):
        """Создание экземпляра FeatureFlags"""
        ff = FeatureFlags()
        assert ff is not None

    def test_default_values_exist(self):
        """Дефолтные значения существуют"""
        assert "tone_analysis" in FeatureFlags.DEFAULTS
        assert "lead_scoring" in FeatureFlags.DEFAULTS
        assert "response_variations" in FeatureFlags.DEFAULTS
        assert "multi_tier_fallback" in FeatureFlags.DEFAULTS

    def test_is_enabled_returns_bool(self):
        """is_enabled возвращает boolean"""
        ff = FeatureFlags()
        result = ff.is_enabled("tone_analysis")
        assert isinstance(result, bool)

    def test_unknown_flag_returns_false(self):
        """Неизвестный флаг возвращает False"""
        ff = FeatureFlags()
        result = ff.is_enabled("nonexistent_flag_xyz")
        assert result is False

class TestFeatureFlagsProperties:
    """Тесты для типизированных property"""

    def test_tone_analysis_property(self):
        """Property tone_analysis работает"""
        ff = FeatureFlags()
        assert isinstance(ff.tone_analysis, bool)

    def test_lead_scoring_property(self):
        """Property lead_scoring работает"""
        ff = FeatureFlags()
        assert isinstance(ff.lead_scoring, bool)

    def test_response_variations_property(self):
        """Property response_variations работает"""
        ff = FeatureFlags()
        assert isinstance(ff.response_variations, bool)

    def test_multi_tier_fallback_property(self):
        """Property multi_tier_fallback работает"""
        ff = FeatureFlags()
        assert isinstance(ff.multi_tier_fallback, bool)

    def test_circular_flow_property(self):
        """Property circular_flow работает"""
        ff = FeatureFlags()
        assert isinstance(ff.circular_flow, bool)

    def test_conversation_guard_property(self):
        """Property conversation_guard работает"""
        ff = FeatureFlags()
        assert isinstance(ff.conversation_guard, bool)

    def test_structured_logging_property(self):
        """Property structured_logging работает"""
        ff = FeatureFlags()
        assert isinstance(ff.structured_logging, bool)

    def test_metrics_tracking_property(self):
        """Property metrics_tracking работает"""
        ff = FeatureFlags()
        assert isinstance(ff.metrics_tracking, bool)

    def test_personalization_property(self):
        """Property personalization работает"""
        ff = FeatureFlags()
        assert isinstance(ff.personalization, bool)

    def test_objection_handler_property(self):
        """Property objection_handler работает"""
        ff = FeatureFlags()
        assert isinstance(ff.objection_handler, bool)

    def test_cta_generator_property(self):
        """Property cta_generator работает"""
        ff = FeatureFlags()
        assert isinstance(ff.cta_generator, bool)

class TestFeatureFlagsOverrides:
    """Тесты для runtime overrides"""

    def test_set_override(self):
        """Установка override"""
        ff = FeatureFlags()
        original = ff.is_enabled("tone_analysis")

        ff.set_override("tone_analysis", not original)
        assert ff.is_enabled("tone_analysis") == (not original)

        ff.clear_override("tone_analysis")
        assert ff.is_enabled("tone_analysis") == original

    def test_override_takes_precedence(self):
        """Override имеет приоритет над settings"""
        ff = FeatureFlags()

        # Устанавливаем override на True
        ff.set_override("tone_analysis", True)
        assert ff.tone_analysis is True

        # Устанавливаем override на False
        ff.set_override("tone_analysis", False)
        assert ff.tone_analysis is False

        # Очищаем — возвращается к дефолту
        ff.clear_override("tone_analysis")

    def test_clear_all_overrides(self):
        """Очистка всех overrides"""
        ff = FeatureFlags()

        ff.set_override("tone_analysis", True)
        ff.set_override("lead_scoring", True)
        ff.set_override("circular_flow", True)

        ff.clear_all_overrides()

        assert ff._overrides == {}

    def test_override_for_nonexistent_flag(self):
        """Override для несуществующего флага"""
        ff = FeatureFlags()

        ff.set_override("custom_flag_123", True)
        assert ff.is_enabled("custom_flag_123") is True

        ff.set_override("custom_flag_123", False)
        assert ff.is_enabled("custom_flag_123") is False

class TestFeatureFlagsGroups:
    """Тесты для групп флагов"""

    def test_groups_exist(self):
        """Группы определены"""
        assert "phase_0" in FeatureFlags.GROUPS
        assert "phase_1" in FeatureFlags.GROUPS
        assert "phase_2" in FeatureFlags.GROUPS
        assert "phase_3" in FeatureFlags.GROUPS
        assert "safe" in FeatureFlags.GROUPS
        assert "risky" in FeatureFlags.GROUPS

    def test_is_group_enabled_any(self):
        """is_group_enabled с require_all=False"""
        ff = FeatureFlags()

        # Phase 0 flags должны быть включены по дефолту
        ff.set_override("structured_logging", True)
        ff.set_override("metrics_tracking", False)

        # Хотя бы один включён
        assert ff.is_group_enabled("phase_0", require_all=False) is True

    def test_is_group_enabled_all(self):
        """is_group_enabled с require_all=True"""
        ff = FeatureFlags()

        ff.set_override("structured_logging", True)
        ff.set_override("metrics_tracking", True)
        assert ff.is_group_enabled("phase_0", require_all=True) is True

        ff.set_override("metrics_tracking", False)
        assert ff.is_group_enabled("phase_0", require_all=True) is False

    def test_nonexistent_group(self):
        """Несуществующая группа возвращает False"""
        ff = FeatureFlags()
        assert ff.is_group_enabled("nonexistent_group") is False

    def test_enable_group(self):
        """Включение группы"""
        ff = FeatureFlags()

        ff.enable_group("phase_0")

        assert ff.is_enabled("structured_logging") is True
        assert ff.is_enabled("metrics_tracking") is True

    def test_disable_group(self):
        """Выключение группы"""
        ff = FeatureFlags()

        ff.enable_group("phase_0")
        ff.disable_group("phase_0")

        assert ff.is_enabled("structured_logging") is False
        assert ff.is_enabled("metrics_tracking") is False

class TestFeatureFlagsGetters:
    """Тесты для методов получения флагов"""

    def test_get_all_flags(self):
        """get_all_flags возвращает все флаги"""
        ff = FeatureFlags()
        all_flags = ff.get_all_flags()

        assert isinstance(all_flags, dict)
        assert "tone_analysis" in all_flags
        assert "lead_scoring" in all_flags

    def test_get_all_flags_includes_overrides(self):
        """get_all_flags включает overrides"""
        ff = FeatureFlags()
        ff.set_override("custom_test_flag", True)

        all_flags = ff.get_all_flags()
        assert "custom_test_flag" in all_flags
        assert all_flags["custom_test_flag"] is True

    def test_get_enabled_flags(self):
        """get_enabled_flags возвращает включённые флаги"""
        ff = FeatureFlags()
        ff.set_override("test_enabled", True)
        ff.set_override("test_disabled", False)

        enabled = ff.get_enabled_flags()
        assert "test_enabled" in enabled
        assert "test_disabled" not in enabled

    def test_get_disabled_flags(self):
        """get_disabled_flags возвращает выключенные флаги"""
        ff = FeatureFlags()
        ff.set_override("test_enabled", True)
        ff.set_override("test_disabled", False)

        disabled = ff.get_disabled_flags()
        assert "test_disabled" in disabled
        assert "test_enabled" not in disabled

class TestFeatureFlagsEnvironment:
    """Тесты для переопределения через environment"""

    def test_env_override_true(self):
        """Переопределение через env = true"""
        os.environ["FF_TONE_ANALYSIS"] = "true"

        try:
            ff = FeatureFlags()
            assert ff.is_enabled("tone_analysis") is True
        finally:
            del os.environ["FF_TONE_ANALYSIS"]

    def test_env_override_false(self):
        """Переопределение через env = false"""
        os.environ["FF_RESPONSE_VARIATIONS"] = "false"

        try:
            ff = FeatureFlags()
            assert ff.is_enabled("response_variations") is False
        finally:
            del os.environ["FF_RESPONSE_VARIATIONS"]

    def test_env_override_1(self):
        """Переопределение через env = 1"""
        os.environ["FF_LEAD_SCORING"] = "1"

        try:
            ff = FeatureFlags()
            assert ff.is_enabled("lead_scoring") is True
        finally:
            del os.environ["FF_LEAD_SCORING"]

    def test_env_override_yes(self):
        """Переопределение через env = yes"""
        os.environ["FF_CIRCULAR_FLOW"] = "yes"

        try:
            ff = FeatureFlags()
            assert ff.is_enabled("circular_flow") is True
        finally:
            del os.environ["FF_CIRCULAR_FLOW"]

    def test_env_override_on(self):
        """Переопределение через env = on"""
        os.environ["FF_PERSONALIZATION"] = "on"

        try:
            ff = FeatureFlags()
            assert ff.is_enabled("personalization") is True
        finally:
            del os.environ["FF_PERSONALIZATION"]

class TestFeatureFlagsReload:
    """Тесты для reload"""

    def test_reload_clears_overrides(self):
        """reload очищает overrides"""
        ff = FeatureFlags()

        ff.set_override("test_flag", True)
        assert ff.is_enabled("test_flag") is True

        ff.reload()
        assert ff.is_enabled("test_flag") is False  # Возвращается к дефолту

class TestFeatureFlagDecorator:
    """Тесты для декоратора feature_flag"""

    def test_decorator_enabled(self):
        """Декоратор выполняет функцию если флаг включён"""
        from src.feature_flags import flags

        flags.set_override("test_decorator_flag", True)

        @feature_flag("test_decorator_flag")
        def test_function():
            return "executed"

        result = test_function()
        assert result == "executed"

        flags.clear_override("test_decorator_flag")

    def test_decorator_disabled(self):
        """Декоратор возвращает default если флаг выключен"""
        from src.feature_flags import flags

        flags.set_override("test_decorator_flag_disabled", False)

        @feature_flag("test_decorator_flag_disabled", default_return="not_executed")
        def test_function():
            return "executed"

        result = test_function()
        assert result == "not_executed"

        flags.clear_override("test_decorator_flag_disabled")

    def test_decorator_default_none(self):
        """Декоратор возвращает None по умолчанию"""
        from src.feature_flags import flags

        flags.set_override("test_decorator_none", False)

        @feature_flag("test_decorator_none")
        def test_function():
            return "executed"

        result = test_function()
        assert result is None

        flags.clear_override("test_decorator_none")

    def test_decorator_preserves_function_name(self):
        """Декоратор сохраняет имя функции"""
        @feature_flag("some_flag")
        def my_function():
            pass

        assert my_function.__name__ == "my_function"

class TestSingletonFlags:
    """Тесты для singleton экземпляра"""

    def test_global_flags_exists(self):
        """Глобальный flags существует"""
        from src.feature_flags import flags
        assert flags is not None
        assert isinstance(flags, FeatureFlags)

    def test_global_flags_has_properties(self):
        """Глобальный flags имеет все property"""
        from src.feature_flags import flags

        assert hasattr(flags, "tone_analysis")
        assert hasattr(flags, "lead_scoring")
        assert hasattr(flags, "response_variations")
        assert hasattr(flags, "multi_tier_fallback")
        assert hasattr(flags, "circular_flow")

class TestFeatureFlagsFromSettings:
    """Тесты загрузки из settings.yaml"""

    def test_loads_from_settings(self):
        """Флаги загружаются из settings.yaml"""
        ff = FeatureFlags()

        # Эти флаги должны быть True в settings.yaml
        assert ff.is_enabled("structured_logging") is True
        assert ff.is_enabled("metrics_tracking") is True
        assert ff.is_enabled("multi_tier_fallback") is True
        assert ff.is_enabled("conversation_guard") is True
        assert ff.is_enabled("response_variations") is True

        # Эти флаги должны быть False в settings.yaml
        assert ff.is_enabled("tone_analysis") is False
        assert ff.is_enabled("lead_scoring") is False
        assert ff.is_enabled("circular_flow") is False

class TestFeatureFlagsThreadSafety:
    """Тесты потокобезопасности"""

    def test_concurrent_access(self):
        """Одновременный доступ из нескольких потоков"""
        import threading
        import time

        ff = FeatureFlags()
        errors = []
        results = []

        def reader(thread_id):
            try:
                for i in range(50):
                    result = ff.is_enabled("tone_analysis")
                    results.append(result)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def writer(thread_id):
            try:
                for i in range(50):
                    ff.set_override("tone_analysis", i % 2 == 0)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(3):
            threads.append(threading.Thread(target=reader, args=(i,)))
            threads.append(threading.Thread(target=writer, args=(i,)))

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
        # Результаты должны быть boolean
        for r in results:
            assert isinstance(r, bool)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

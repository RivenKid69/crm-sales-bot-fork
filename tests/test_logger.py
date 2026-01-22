"""
Тесты для модуля структурированного логирования (logger.py).
"""

import pytest
import json
import logging
import os
import sys
from pathlib import Path
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logger import StructuredLogger, create_test_logger


class TestStructuredLoggerBasic:
    """Базовые тесты StructuredLogger"""

    def test_create_logger(self):
        """Создание логгера"""
        log = create_test_logger("basic")
        assert log is not None
        assert log.name == "crm_sales_bot.basic"

    def test_set_conversation_id(self):
        """Установка conversation_id"""
        log = create_test_logger("conv_id")
        assert log.conversation_id is None

        log.set_conversation("test_123")
        assert log.conversation_id == "test_123"

        log.clear_conversation()
        assert log.conversation_id is None

    def test_set_context(self):
        """Установка дополнительного контекста"""
        log = create_test_logger("context")

        log.set_context(user_id="u123", session="s456")
        assert log._extra_context == {"user_id": "u123", "session": "s456"}

        log.clear_context()
        assert log._extra_context == {}

    def test_format_structured(self):
        """Форматирование структурированного лога"""
        log = create_test_logger("format")
        log.set_conversation("conv_999")

        result = log._format_structured("INFO", "Test message", key="value")

        assert "timestamp" in result
        assert result["level"] == "INFO"
        assert result["message"] == "Test message"
        assert result["conversation_id"] == "conv_999"
        assert result["key"] == "value"
        assert result["logger"] == "crm_sales_bot.format"


class TestStructuredLoggerOutput:
    """Тесты вывода логов"""

    @pytest.fixture
    def capture_logs(self):
        """Fixture для захвата логов"""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        return log_capture, handler

    def test_info_readable_format(self, capture_logs):
        """Вывод info в readable формате"""
        log_capture, handler = capture_logs

        # Убираем LOG_FORMAT если установлен
        env_backup = os.environ.pop("LOG_FORMAT", None)

        try:
            log = create_test_logger("readable_info")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.info("Test message", key="value")

            output = log_capture.getvalue()
            assert "Test message" in output
            assert "key=value" in output
        finally:
            if env_backup:
                os.environ["LOG_FORMAT"] = env_backup

    def test_info_with_conversation_id_readable(self, capture_logs):
        """Вывод с conversation_id в readable формате"""
        log_capture, handler = capture_logs
        env_backup = os.environ.pop("LOG_FORMAT", None)

        try:
            log = create_test_logger("readable_conv")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.set_conversation("test_conv_123")
            log.info("Message with conv id")

            output = log_capture.getvalue()
            assert "[test_conv_123]" in output
            assert "Message with conv id" in output
        finally:
            if env_backup:
                os.environ["LOG_FORMAT"] = env_backup

    def test_info_json_format(self, capture_logs):
        """Вывод info в JSON формате"""
        log_capture, handler = capture_logs
        os.environ["LOG_FORMAT"] = "json"

        try:
            log = create_test_logger("json_info")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.set_conversation("json_conv")
            log.info("JSON test", extra_key="extra_value")

            output = log_capture.getvalue().strip()
            data = json.loads(output)

            assert data["level"] == "INFO"
            assert data["message"] == "JSON test"
            assert data["conversation_id"] == "json_conv"
            assert data["extra_key"] == "extra_value"
            assert "timestamp" in data
        finally:
            del os.environ["LOG_FORMAT"]

    def test_all_log_levels(self, capture_logs):
        """Все уровни логирования работают"""
        log_capture, handler = capture_logs
        env_backup = os.environ.pop("LOG_FORMAT", None)

        try:
            log = create_test_logger("levels")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.debug("Debug message")
            log.info("Info message")
            log.warning("Warning message")
            log.error("Error message")
            log.critical("Critical message")

            output = log_capture.getvalue()
            assert "Debug message" in output
            assert "Info message" in output
            assert "Warning message" in output
            assert "Error message" in output
            assert "Critical message" in output
        finally:
            if env_backup:
                os.environ["LOG_FORMAT"] = env_backup


class TestStructuredLoggerMetrics:
    """Тесты для метрик"""

    @pytest.fixture
    def capture_logs(self):
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        return log_capture, handler

    def test_metric_readable(self, capture_logs):
        """Метрика в readable формате"""
        log_capture, handler = capture_logs
        env_backup = os.environ.pop("LOG_FORMAT", None)

        try:
            log = create_test_logger("metric_readable")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.metric("response_time", 0.5, state="spin_situation")

            output = log_capture.getvalue()
            assert "response_time" in output
            assert "value=0.5" in output
            assert "state=spin_situation" in output
        finally:
            if env_backup:
                os.environ["LOG_FORMAT"] = env_backup

    def test_metric_json(self, capture_logs):
        """Метрика в JSON формате"""
        log_capture, handler = capture_logs
        os.environ["LOG_FORMAT"] = "json"

        try:
            log = create_test_logger("metric_json")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.metric("fallback_triggered", 1, tier="tier_2", state="spin_problem")

            output = log_capture.getvalue().strip()
            data = json.loads(output)

            assert data["level"] == "METRIC"
            assert data["message"] == "fallback_triggered"
            assert data["value"] == 1
            assert data["tier"] == "tier_2"
            assert data["state"] == "spin_problem"
        finally:
            del os.environ["LOG_FORMAT"]

    def test_event_json(self, capture_logs):
        """Event в JSON формате"""
        log_capture, handler = capture_logs
        os.environ["LOG_FORMAT"] = "json"

        try:
            log = create_test_logger("event_json")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.event("state_transition", from_state="greeting", to_state="spin_situation")

            output = log_capture.getvalue().strip()
            data = json.loads(output)

            assert data["level"] == "EVENT"
            assert data["message"] == "state_transition"
            assert data["from_state"] == "greeting"
            assert data["to_state"] == "spin_situation"
        finally:
            del os.environ["LOG_FORMAT"]


class TestStructuredLoggerException:
    """Тесты для логирования исключений"""

    @pytest.fixture
    def capture_logs(self):
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        return log_capture, handler

    def test_exception_readable(self, capture_logs):
        """Исключение в readable формате"""
        log_capture, handler = capture_logs
        env_backup = os.environ.pop("LOG_FORMAT", None)

        try:
            log = create_test_logger("exc_readable")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            try:
                raise ValueError("Test error")
            except ValueError:
                log.exception("Error occurred", action="test_action")

            output = log_capture.getvalue()
            assert "Error occurred" in output
            assert "ValueError" in output
            assert "Test error" in output
        finally:
            if env_backup:
                os.environ["LOG_FORMAT"] = env_backup

    def test_exception_json(self, capture_logs):
        """Исключение в JSON формате"""
        log_capture, handler = capture_logs
        os.environ["LOG_FORMAT"] = "json"

        try:
            log = create_test_logger("exc_json")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            try:
                raise RuntimeError("JSON test error")
            except RuntimeError:
                log.exception("JSON error occurred")

            output = log_capture.getvalue().strip()
            data = json.loads(output)

            assert data["level"] == "ERROR"
            assert data["message"] == "JSON error occurred"
            assert "traceback" in data
            assert "RuntimeError" in data["traceback"]
        finally:
            del os.environ["LOG_FORMAT"]


class TestStructuredLoggerContext:
    """Тесты для контекста"""

    @pytest.fixture
    def capture_logs(self):
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        return log_capture, handler

    def test_extra_context_in_logs(self, capture_logs):
        """Extra context добавляется в логи"""
        log_capture, handler = capture_logs
        os.environ["LOG_FORMAT"] = "json"

        try:
            log = create_test_logger("extra_context")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.set_context(service="sales_bot", version="1.0")
            log.info("Test with context")

            output = log_capture.getvalue().strip()
            data = json.loads(output)

            assert data["service"] == "sales_bot"
            assert data["version"] == "1.0"
        finally:
            del os.environ["LOG_FORMAT"]

    def test_context_persistence(self, capture_logs):
        """Контекст сохраняется между вызовами"""
        log_capture, handler = capture_logs
        os.environ["LOG_FORMAT"] = "json"

        try:
            log = create_test_logger("context_persist")
            log.logger.handlers.clear()
            log.logger.addHandler(handler)
            log.logger.setLevel(logging.DEBUG)

            log.set_context(user="test_user")
            log.info("First message")
            log.info("Second message")

            lines = log_capture.getvalue().strip().split("\n")
            assert len(lines) == 2

            for line in lines:
                data = json.loads(line)
                assert data["user"] == "test_user"
        finally:
            del os.environ["LOG_FORMAT"]


class TestSingletonLogger:
    """Тесты для singleton экземпляра"""

    def test_global_logger_exists(self):
        """Глобальный логгер существует"""
        from logger import logger
        assert logger is not None
        assert logger.name == "crm_sales_bot"

    def test_global_logger_methods(self):
        """Глобальный логгер имеет все методы"""
        from logger import logger

        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "critical")
        assert hasattr(logger, "exception")
        assert hasattr(logger, "metric")
        assert hasattr(logger, "event")
        assert hasattr(logger, "set_conversation")
        assert hasattr(logger, "set_context")


class TestLoggerThreadSafety:
    """Тесты потокобезопасности"""

    def test_concurrent_logging(self):
        """Логирование из нескольких потоков"""
        import threading
        import time

        log = create_test_logger("thread_safe")
        log.set_conversation("thread_test")
        errors = []

        def log_messages(thread_id):
            try:
                for i in range(10):
                    log.info(f"Thread {thread_id} message {i}")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=log_messages, args=(i,))
            for i in range(5)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent logging: {errors}"


class TestLoggerContextIsolation:
    """
    Tests for thread-safe context isolation using ContextVar.

    These tests verify that conversation_id and extra_context are isolated
    between threads, preventing race conditions in parallel batch runs.
    """

    def test_conversation_id_isolated_between_threads(self):
        """Each thread has its own conversation_id"""
        import threading
        import time

        log = create_test_logger("isolation_conv")
        results = {}
        errors = []

        def set_and_check_conversation(thread_id):
            try:
                conv_id = f"conv_{thread_id}"
                log.set_conversation(conv_id)
                time.sleep(0.01)  # Give other threads a chance to interfere
                # Verify our conversation_id wasn't overwritten by another thread
                actual = log.conversation_id
                results[thread_id] = actual
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=set_and_check_conversation, args=(i,))
            for i in range(10)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"

        # Each thread should have its own conversation_id preserved
        for thread_id, actual in results.items():
            expected = f"conv_{thread_id}"
            assert actual == expected, (
                f"Thread {thread_id} expected '{expected}' but got '{actual}'. "
                "Race condition detected - conversation_id not isolated."
            )

    def test_context_isolated_between_threads(self):
        """Each thread has its own extra_context"""
        import threading
        import time

        log = create_test_logger("isolation_ctx")
        results = {}
        errors = []

        def set_and_check_context(thread_id):
            try:
                log.set_context(thread_id=thread_id, unique_key=f"value_{thread_id}")
                time.sleep(0.01)  # Give other threads a chance to interfere
                # Verify our context wasn't overwritten by another thread
                ctx = log._extra_context
                results[thread_id] = ctx.copy()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=set_and_check_context, args=(i,))
            for i in range(10)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"

        # Each thread should have its own context preserved
        for thread_id, ctx in results.items():
            assert ctx.get("thread_id") == thread_id, (
                f"Thread {thread_id} context corrupted: {ctx}. "
                "Race condition detected - extra_context not isolated."
            )
            assert ctx.get("unique_key") == f"value_{thread_id}", (
                f"Thread {thread_id} context corrupted: {ctx}. "
                "Race condition detected - extra_context not isolated."
            )

    def test_clear_only_affects_current_thread(self):
        """clear_conversation only clears current thread's conversation_id"""
        import threading
        import time

        log = create_test_logger("isolation_clear")
        barrier = threading.Barrier(2)
        results = {"thread_0": None, "thread_1": None}
        errors = []

        def thread_0_clears():
            try:
                log.set_conversation("conv_0")
                barrier.wait()  # Wait for thread_1 to set its conversation
                time.sleep(0.005)  # Small delay
                log.clear_conversation()
                barrier.wait()  # Wait for thread_1 to check
                results["thread_0"] = log.conversation_id
            except Exception as e:
                errors.append(e)

        def thread_1_keeps():
            try:
                log.set_conversation("conv_1")
                barrier.wait()  # Signal thread_0
                barrier.wait()  # Wait for thread_0 to clear
                time.sleep(0.005)
                # Our conversation_id should NOT be affected by thread_0's clear
                results["thread_1"] = log.conversation_id
            except Exception as e:
                errors.append(e)

        t0 = threading.Thread(target=thread_0_clears)
        t1 = threading.Thread(target=thread_1_keeps)

        t0.start()
        t1.start()

        t0.join()
        t1.join()

        assert len(errors) == 0, f"Errors: {errors}"

        # thread_0 should have None after clearing
        assert results["thread_0"] is None, (
            f"Thread 0 should have None after clear, got {results['thread_0']}"
        )

        # thread_1's conversation_id should be preserved
        assert results["thread_1"] == "conv_1", (
            f"Thread 1's conversation_id was affected by thread 0's clear. "
            f"Expected 'conv_1', got '{results['thread_1']}'. "
            "Race condition detected - clear affected other thread."
        )

    def test_clear_context_only_affects_current_thread(self):
        """clear_context only clears current thread's extra_context"""
        import threading
        import time

        log = create_test_logger("isolation_clear_ctx")
        barrier = threading.Barrier(2)
        results = {"thread_0": None, "thread_1": None}
        errors = []

        def thread_0_clears():
            try:
                log.set_context(user="user_0")
                barrier.wait()
                time.sleep(0.005)
                log.clear_context()
                barrier.wait()
                results["thread_0"] = log._extra_context.copy()
            except Exception as e:
                errors.append(e)

        def thread_1_keeps():
            try:
                log.set_context(user="user_1")
                barrier.wait()
                barrier.wait()
                time.sleep(0.005)
                results["thread_1"] = log._extra_context.copy()
            except Exception as e:
                errors.append(e)

        t0 = threading.Thread(target=thread_0_clears)
        t1 = threading.Thread(target=thread_1_keeps)

        t0.start()
        t1.start()

        t0.join()
        t1.join()

        assert len(errors) == 0, f"Errors: {errors}"

        # thread_0 should have empty context after clearing
        assert results["thread_0"] == {}, (
            f"Thread 0 should have empty context after clear, got {results['thread_0']}"
        )

        # thread_1's context should be preserved
        assert results["thread_1"].get("user") == "user_1", (
            f"Thread 1's context was affected by thread 0's clear. "
            f"Expected user='user_1', got '{results['thread_1']}'. "
            "Race condition detected - clear_context affected other thread."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Tests for LLM Resilience features.

Tests cover:
- Retry with exponential backoff
- Circuit breaker pattern
- Fallback responses
- Statistics tracking
- Configuration options
- Error handling
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm import OllamaLLM, CircuitBreakerState, LLMStats


class TestLLMStats:
    """Tests for LLMStats dataclass"""

    def test_initial_values(self):
        """Initial values are zero"""
        stats = LLMStats()
        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.failed_requests == 0
        assert stats.fallback_used == 0
        assert stats.total_retries == 0
        assert stats.circuit_breaker_trips == 0
        assert stats.total_response_time_ms == 0.0

    def test_success_rate_no_requests(self):
        """Success rate is 100% with no requests"""
        stats = LLMStats()
        assert stats.success_rate == 100.0

    def test_success_rate_calculation(self):
        """Success rate calculated correctly"""
        stats = LLMStats(total_requests=10, successful_requests=8)
        assert stats.success_rate == 80.0

    def test_average_response_time_no_requests(self):
        """Average response time is 0 with no successful requests"""
        stats = LLMStats()
        assert stats.average_response_time_ms == 0.0

    def test_average_response_time_calculation(self):
        """Average response time calculated correctly"""
        stats = LLMStats(successful_requests=5, total_response_time_ms=500.0)
        assert stats.average_response_time_ms == 100.0


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState dataclass"""

    def test_initial_state(self):
        """Initial state is closed"""
        state = CircuitBreakerState()
        assert state.failures == 0
        assert state.is_open is False
        assert state.open_until == 0.0


class TestOllamaLLMBasic:
    """Basic tests for OllamaLLM"""

    def test_initialization_defaults(self):
        """Initialization uses settings defaults"""
        llm = OllamaLLM()
        assert llm.model is not None
        assert llm.base_url is not None
        assert llm.timeout is not None

    def test_initialization_custom(self):
        """Initialization with custom values"""
        llm = OllamaLLM(
            model="custom-model",
            base_url="http://custom:8080",
            timeout=30
        )
        assert llm.model == "custom-model"
        assert llm.base_url == "http://custom:8080"
        assert llm.timeout == 30

    def test_initialization_flags(self):
        """Initialization with feature flags"""
        llm = OllamaLLM(
            enable_circuit_breaker=False,
            enable_retry=False
        )
        assert llm._enable_circuit_breaker is False
        assert llm._enable_retry is False

    def test_reset(self):
        """Reset clears stats"""
        llm = OllamaLLM()
        llm._stats.total_requests = 10
        llm._stats.failed_requests = 5

        llm.reset()

        assert llm._stats.total_requests == 0
        assert llm._stats.failed_requests == 0


class TestFallbackResponses:
    """Tests for fallback response handling"""

    def test_fallback_for_known_states(self):
        """Fallback exists for known states"""
        llm = OllamaLLM()

        states = [
            "greeting",
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
            "presentation",
            "close",
            "soft_close",
            "handle_objection"
        ]

        for state in states:
            fallback = llm._get_fallback(state)
            assert fallback, f"No fallback for state: {state}"
            assert len(fallback) > 10, f"Fallback too short for state: {state}"

    def test_fallback_for_unknown_state(self):
        """Default fallback for unknown state"""
        llm = OllamaLLM()
        fallback = llm._get_fallback("unknown_state")
        assert fallback == llm.DEFAULT_FALLBACK

    def test_fallback_for_none_state(self):
        """Default fallback for None state"""
        llm = OllamaLLM()
        fallback = llm._get_fallback(None)
        assert fallback == llm.DEFAULT_FALLBACK

    def test_fallback_messages_are_russian(self):
        """Fallback messages are in Russian"""
        llm = OllamaLLM()

        russian_indicators = ["а", "е", "о", "и", "у", "ы"]

        for state, message in llm.FALLBACK_RESPONSES.items():
            has_russian = any(char in message.lower() for char in russian_indicators)
            assert has_russian, f"Message for {state} might not be Russian"


class TestRetryMechanism:
    """Tests for retry with exponential backoff"""

    @patch.object(OllamaLLM, '_call_llm')
    def test_success_on_first_try(self, mock_call):
        """No retry needed on success"""
        mock_call.return_value = "Success response"
        llm = OllamaLLM(enable_circuit_breaker=False)

        response = llm.generate("test prompt")

        assert response == "Success response"
        assert mock_call.call_count == 1
        assert llm._stats.total_retries == 0

    @patch.object(OllamaLLM, '_call_llm')
    def test_retry_on_failure(self, mock_call):
        """Retries on transient failure"""
        mock_call.side_effect = [
            requests.exceptions.ConnectionError("Connection failed"),
            "Success response"
        ]
        llm = OllamaLLM(enable_circuit_breaker=False)
        llm.INITIAL_DELAY = 0.01  # Speed up test

        response = llm.generate("test prompt")

        assert response == "Success response"
        assert mock_call.call_count == 2
        assert llm._stats.total_retries == 1

    @patch.object(OllamaLLM, '_call_llm')
    def test_max_retries_exhausted(self, mock_call):
        """Falls back after max retries"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Connection failed")
        llm = OllamaLLM(enable_circuit_breaker=False)
        llm.INITIAL_DELAY = 0.01
        llm.MAX_RETRIES = 2

        response = llm.generate("test prompt", state="greeting")

        assert response == llm.FALLBACK_RESPONSES["greeting"]
        assert mock_call.call_count == 2
        assert llm._stats.failed_requests == 1
        assert llm._stats.fallback_used == 1

    @patch.object(OllamaLLM, '_call_llm')
    def test_no_retry_when_disabled(self, mock_call):
        """No retry when disabled"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Connection failed")
        llm = OllamaLLM(enable_retry=False, enable_circuit_breaker=False)

        response = llm.generate("test prompt", state="greeting")

        assert mock_call.call_count == 1
        assert llm._stats.total_retries == 0

    @patch.object(OllamaLLM, '_call_llm')
    def test_different_exception_types(self, mock_call):
        """Handles different exception types"""
        exceptions = [
            requests.exceptions.Timeout("Timeout"),
            requests.exceptions.ConnectionError("Connection error"),
            requests.exceptions.RequestException("General error"),
        ]

        for exc in exceptions:
            mock_call.reset_mock()
            mock_call.side_effect = exc
            llm = OllamaLLM(enable_retry=False, enable_circuit_breaker=False)

            response = llm.generate("test", state="greeting")
            assert response  # Should return fallback


class TestCircuitBreaker:
    """Tests for circuit breaker pattern"""

    @patch.object(OllamaLLM, '_call_llm')
    def test_circuit_opens_after_threshold(self, mock_call):
        """Circuit opens after threshold failures"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM(enable_retry=False)
        llm.CIRCUIT_BREAKER_THRESHOLD = 3
        llm.INITIAL_DELAY = 0.001

        # Cause failures to open circuit
        for _ in range(3):
            llm.generate("test", state="greeting")

        assert llm.is_circuit_open is True
        assert llm._stats.circuit_breaker_trips == 1

    @patch.object(OllamaLLM, '_call_llm')
    def test_circuit_returns_fallback_when_open(self, mock_call):
        """Returns fallback immediately when circuit is open"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM(enable_retry=False)
        llm.CIRCUIT_BREAKER_THRESHOLD = 2

        # Open the circuit
        for _ in range(2):
            llm.generate("test")

        mock_call.reset_mock()

        # Should not call LLM when circuit is open
        response = llm.generate("test", state="greeting")

        assert mock_call.call_count == 0  # No new calls
        assert response == llm.FALLBACK_RESPONSES["greeting"]

    @patch.object(OllamaLLM, '_call_llm')
    def test_circuit_recovery_after_timeout(self, mock_call):
        """Circuit attempts recovery after timeout"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM(enable_retry=False)
        llm.CIRCUIT_BREAKER_THRESHOLD = 2
        llm.CIRCUIT_BREAKER_TIMEOUT = 0.01  # Very short for test

        # Open the circuit
        for _ in range(2):
            llm.generate("test")

        assert llm.is_circuit_open is True

        # Wait for timeout
        time.sleep(0.02)

        # Circuit should attempt recovery (half-open)
        assert llm.is_circuit_open is False

    @patch.object(OllamaLLM, '_call_llm')
    def test_circuit_closes_on_success(self, mock_call):
        """Circuit closes after successful request"""
        llm = OllamaLLM(enable_retry=False)

        # Manually open circuit
        llm._circuit_breaker.is_open = True
        llm._circuit_breaker.failures = 5
        llm._circuit_breaker.open_until = time.time() - 1  # Already expired

        mock_call.return_value = "Success"

        response = llm.generate("test")

        assert response == "Success"
        assert llm._circuit_breaker.is_open is False
        assert llm._circuit_breaker.failures == 0

    def test_reset_circuit_breaker(self):
        """Can manually reset circuit breaker"""
        llm = OllamaLLM()

        # Manually open circuit
        llm._circuit_breaker.is_open = True
        llm._circuit_breaker.failures = 10

        llm.reset_circuit_breaker()

        assert llm._circuit_breaker.is_open is False
        assert llm._circuit_breaker.failures == 0

    @patch.object(OllamaLLM, '_call_llm')
    def test_circuit_breaker_disabled(self, mock_call):
        """Circuit breaker can be disabled"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM(enable_circuit_breaker=False, enable_retry=False)

        # Many failures shouldn't open circuit
        for _ in range(10):
            llm.generate("test")

        assert llm.is_circuit_open is False


class TestStatistics:
    """Tests for statistics tracking"""

    @patch.object(OllamaLLM, '_call_llm')
    def test_stats_successful_request(self, mock_call):
        """Stats track successful requests"""
        mock_call.return_value = "Success"
        llm = OllamaLLM()

        llm.generate("test")

        assert llm._stats.total_requests == 1
        assert llm._stats.successful_requests == 1
        assert llm._stats.failed_requests == 0
        assert llm._stats.total_response_time_ms > 0

    @patch.object(OllamaLLM, '_call_llm')
    def test_stats_failed_request(self, mock_call):
        """Stats track failed requests"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM(enable_retry=False, enable_circuit_breaker=False)

        llm.generate("test")

        assert llm._stats.total_requests == 1
        assert llm._stats.successful_requests == 0
        assert llm._stats.failed_requests == 1
        assert llm._stats.fallback_used == 1

    @patch.object(OllamaLLM, '_call_llm')
    def test_stats_success_rate(self, mock_call):
        """Success rate calculated correctly"""
        llm = OllamaLLM(enable_retry=False, enable_circuit_breaker=False)

        # 3 successes
        mock_call.return_value = "Success"
        for _ in range(3):
            llm.generate("test")

        # 2 failures
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        for _ in range(2):
            llm.generate("test")

        assert llm._stats.success_rate == 60.0  # 3/5 = 60%

    def test_get_stats_dict(self):
        """get_stats_dict returns correct structure"""
        llm = OllamaLLM()
        llm._stats.total_requests = 10
        llm._stats.successful_requests = 8
        llm._stats.failed_requests = 2
        llm._stats.fallback_used = 2
        llm._stats.total_retries = 3
        llm._stats.circuit_breaker_trips = 1
        llm._stats.total_response_time_ms = 1000.0

        stats = llm.get_stats_dict()

        assert stats["total_requests"] == 10
        assert stats["successful_requests"] == 8
        assert stats["failed_requests"] == 2
        assert stats["fallback_used"] == 2
        assert stats["total_retries"] == 3
        assert stats["circuit_breaker_trips"] == 1
        assert stats["success_rate"] == 80.0
        assert stats["average_response_time_ms"] == 125.0  # 1000/8
        assert "circuit_breaker_open" in stats


class TestGenerateOptions:
    """Tests for generate method options"""

    @patch.object(OllamaLLM, '_call_llm')
    def test_allow_fallback_true(self, mock_call):
        """Returns fallback when allowed"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM(enable_retry=False, enable_circuit_breaker=False)

        response = llm.generate("test", state="greeting", allow_fallback=True)

        assert response == llm.FALLBACK_RESPONSES["greeting"]

    @patch.object(OllamaLLM, '_call_llm')
    def test_allow_fallback_false(self, mock_call):
        """Returns empty string when fallback disabled"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM(enable_retry=False, enable_circuit_breaker=False)

        response = llm.generate("test", allow_fallback=False)

        assert response == ""

    @patch.object(OllamaLLM, '_call_llm')
    def test_state_passed_to_fallback(self, mock_call):
        """State determines fallback message"""
        mock_call.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM(enable_retry=False, enable_circuit_breaker=False)

        r1 = llm.generate("test", state="greeting")
        llm.reset()
        r2 = llm.generate("test", state="presentation")

        assert r1 != r2
        assert r1 == llm.FALLBACK_RESPONSES["greeting"]
        assert r2 == llm.FALLBACK_RESPONSES["presentation"]


class TestHealthCheck:
    """Tests for health check functionality"""

    @patch('requests.get')
    def test_health_check_success(self, mock_get):
        """Health check returns True when LLM is available"""
        mock_get.return_value.status_code = 200
        llm = OllamaLLM()

        assert llm.health_check() is True

    @patch('requests.get')
    def test_health_check_failure_status(self, mock_get):
        """Health check returns False on non-200 status"""
        mock_get.return_value.status_code = 500
        llm = OllamaLLM()

        assert llm.health_check() is False

    @patch('requests.get')
    def test_health_check_exception(self, mock_get):
        """Health check returns False on exception"""
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed")
        llm = OllamaLLM()

        assert llm.health_check() is False

    @patch('requests.get')
    def test_health_check_timeout(self, mock_get):
        """Health check has timeout"""
        mock_get.side_effect = requests.exceptions.Timeout("Timeout")
        llm = OllamaLLM()

        assert llm.health_check() is False


class TestExponentialBackoff:
    """Tests for exponential backoff timing"""

    @patch.object(OllamaLLM, '_call_llm')
    @patch('time.sleep')
    def test_backoff_doubles(self, mock_sleep, mock_call):
        """Delay doubles with each retry"""
        mock_call.side_effect = [
            requests.exceptions.ConnectionError("Failed"),
            requests.exceptions.ConnectionError("Failed"),
            "Success"
        ]
        llm = OllamaLLM(enable_circuit_breaker=False)
        llm.INITIAL_DELAY = 1.0
        llm.BACKOFF_MULTIPLIER = 2.0
        llm.MAX_RETRIES = 3

        llm.generate("test")

        # Should have slept twice (before 2nd and 3rd attempts)
        assert mock_sleep.call_count == 2
        # First delay: 1.0, Second delay: 2.0
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

    @patch.object(OllamaLLM, '_call_llm')
    @patch('time.sleep')
    def test_backoff_max_delay(self, mock_sleep, mock_call):
        """Delay capped at MAX_DELAY"""
        mock_call.side_effect = [
            requests.exceptions.ConnectionError("Failed"),
            requests.exceptions.ConnectionError("Failed"),
            requests.exceptions.ConnectionError("Failed"),
            requests.exceptions.ConnectionError("Failed"),
        ]
        llm = OllamaLLM(enable_circuit_breaker=False)
        llm.INITIAL_DELAY = 5.0
        llm.MAX_DELAY = 8.0
        llm.BACKOFF_MULTIPLIER = 2.0
        llm.MAX_RETRIES = 4

        llm.generate("test", state="greeting")

        # All delays should be <= MAX_DELAY
        for call in mock_sleep.call_args_list:
            delay = call[0][0]
            assert delay <= llm.MAX_DELAY


class TestMultipleInstances:
    """Tests for multiple LLM client instances"""

    def test_independent_stats(self):
        """Multiple clients have independent stats"""
        llm1 = OllamaLLM()
        llm2 = OllamaLLM()

        llm1._stats.total_requests = 10
        llm1._stats.failed_requests = 5

        assert llm2._stats.total_requests == 0
        assert llm2._stats.failed_requests == 0

    def test_independent_circuit_breakers(self):
        """Multiple clients have independent circuit breakers"""
        llm1 = OllamaLLM()
        llm2 = OllamaLLM()

        llm1._circuit_breaker.is_open = True
        llm1._circuit_breaker.failures = 10

        assert llm2._circuit_breaker.is_open is False
        assert llm2._circuit_breaker.failures == 0


class TestEdgeCases:
    """Edge case tests"""

    @patch.object(OllamaLLM, '_call_llm')
    def test_empty_prompt(self, mock_call):
        """Handles empty prompt"""
        mock_call.return_value = "Response"
        llm = OllamaLLM()

        response = llm.generate("")
        assert response == "Response"

    @patch.object(OllamaLLM, '_call_llm')
    def test_very_long_prompt(self, mock_call):
        """Handles very long prompt"""
        mock_call.return_value = "Response"
        llm = OllamaLLM()

        long_prompt = "A" * 100000
        response = llm.generate(long_prompt)
        assert response == "Response"

    @patch.object(OllamaLLM, '_call_llm')
    def test_unicode_prompt(self, mock_call):
        """Handles unicode prompt"""
        mock_call.return_value = "Ответ"
        llm = OllamaLLM()

        response = llm.generate("Привет! Как дела? 🎉")
        assert response == "Ответ"

    @patch.object(OllamaLLM, '_call_llm')
    def test_response_with_special_characters(self, mock_call):
        """Handles response with special characters"""
        mock_call.return_value = "Response with 'quotes' and \"double quotes\" and \n newlines"
        llm = OllamaLLM()

        response = llm.generate("test")
        assert "quotes" in response
        assert "\n" in response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

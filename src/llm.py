"""
vLLM Client для CRM Sales Bot.

Использует vLLM OpenAI-compatible API с native structured output.

Возможности:
- Native Structured Output: response_format с json_schema (vLLM 0.6+)
- Circuit Breaker: open/closed/half-open состояния
- LLMStats: success_rate, avg_response_time
- Retry: exponential backoff при ошибках
- Fallback: graceful degradation при сбоях

Запуск vLLM сервера:
    vllm serve Qwen/Qwen3-4B-AWQ --port 8000 --quantization awq

Примечание:
    Этот проект использует ТОЛЬКО vLLM. Ollama не поддерживается.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type, TypeVar

import requests
from pydantic import BaseModel

from logger import logger
from settings import settings
from src.yaml_config.constants import LLM_FALLBACK_RESPONSES, LLM_DEFAULT_FALLBACK

T = TypeVar('T', bound=BaseModel)


@dataclass
class CircuitBreakerState:
    """Состояние circuit breaker"""
    failures: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False
    open_until: float = 0.0


@dataclass
class LLMStats:
    """Статистика LLM клиента"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    fallback_used: int = 0
    total_retries: int = 0
    circuit_breaker_trips: int = 0
    total_response_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Процент успешных запросов"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def average_response_time_ms(self) -> float:
        """Среднее время ответа"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time_ms / self.successful_requests


class VLLMClient:
    """
    vLLM клиент для CRM Sales Bot.

    Использует vLLM OpenAI-compatible API с native structured output.
    Structured output гарантирует 100% валидный JSON через json_schema.

    Требования:
        - vLLM сервер запущен на указанном URL
        - Модель поддерживает structured output (Qwen, Llama, etc.)

    Пример запуска vLLM:
        vllm serve Qwen/Qwen3-4B-AWQ --port 8000 --quantization awq
    """

    # Настройки retry
    MAX_RETRIES: int = 3
    INITIAL_DELAY: float = 1.0
    MAX_DELAY: float = 10.0
    BACKOFF_MULTIPLIER: float = 2.0

    # Настройки circuit breaker
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 60

    # Fallback responses по состояниям (загружаются из YAML конфига)
    FALLBACK_RESPONSES: Dict[str, str] = LLM_FALLBACK_RESPONSES or {}

    DEFAULT_FALLBACK: str = LLM_DEFAULT_FALLBACK or "Произошла техническая ошибка."

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        enable_circuit_breaker: bool = True,
        enable_retry: bool = True
    ):
        """
        Инициализация vLLM клиента.

        Args:
            model: Название модели (из settings если не указано)
            base_url: URL vLLM API (из settings если не указано)
            timeout: Таймаут запроса в секундах
            enable_circuit_breaker: Включить circuit breaker
            enable_retry: Включить retry с exponential backoff
        """
        self.model = model or settings.llm.model
        self.base_url = base_url or settings.llm.base_url
        self.timeout = timeout or settings.llm.timeout

        self._enable_circuit_breaker = enable_circuit_breaker
        self._enable_retry = enable_retry

        self._circuit_breaker = CircuitBreakerState()
        self._stats = LLMStats()

    def reset(self) -> None:
        """Сбросить состояние для нового диалога"""
        self._stats = LLMStats()

    def reset_circuit_breaker(self) -> None:
        """Сбросить circuit breaker"""
        self._circuit_breaker = CircuitBreakerState()
        logger.info("Circuit breaker reset")

    @property
    def stats(self) -> LLMStats:
        """Статистика запросов"""
        return self._stats

    @property
    def is_circuit_open(self) -> bool:
        """Проверка открыт ли circuit breaker"""
        return self._is_circuit_open()

    # =========================================================================
    # STRUCTURED OUTPUT (НОВОЕ)
    # =========================================================================

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        allow_fallback: bool = True
    ) -> Optional[T]:
        """
        Генерация с гарантированным JSON через vLLM native structured output.

        Использует response_format с json_schema для 100% валидного JSON.
        vLLM гарантирует что ответ соответствует схеме.

        Args:
            prompt: Промпт для LLM
            schema: Pydantic модель для валидации
            allow_fallback: Игнорируется (для совместимости)

        Returns:
            Экземпляр schema или None при ошибке
        """
        import json

        self._stats.total_requests += 1
        start_time = time.time()

        # Circuit breaker check
        if self._enable_circuit_breaker and self._is_circuit_open():
            logger.warning("Circuit breaker open for structured generation")
            self._stats.fallback_used += 1
            return None

        last_error: Optional[Exception] = None
        delay = self.INITIAL_DELAY
        max_attempts = self.MAX_RETRIES if self._enable_retry else 1

        # Получаем JSON schema из Pydantic модели
        json_schema = schema.model_json_schema()
        schema_name = schema.__name__

        for attempt in range(max_attempts):
            try:
                base_url_normalized = self.base_url.rstrip("/")

                # vLLM native structured output через response_format
                response = requests.post(
                    f"{base_url_normalized}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 512,
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": schema_name,
                                "schema": json_schema,
                                "strict": True
                            }
                        }
                    },
                    timeout=self.timeout
                )
                response.raise_for_status()

                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise ValueError("Empty response from vLLM")

                message = choices[0].get("message", {})
                content = message.get("content", "")

                if not content:
                    raise ValueError("Empty content in response from vLLM")

                # vLLM гарантирует валидный JSON, но проверяем на всякий случай
                elapsed_ms = (time.time() - start_time) * 1000
                self._stats.successful_requests += 1
                self._stats.total_response_time_ms += elapsed_ms
                self._reset_failures()

                return schema.model_validate_json(content)

            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"vLLM structured timeout (attempt {attempt + 1}/{max_attempts})")
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(f"vLLM structured error (attempt {attempt + 1}/{max_attempts}): {str(e)[:100]}")
            except Exception as e:
                last_error = e
                logger.error(f"vLLM structured unexpected error (attempt {attempt + 1}/{max_attempts}): {str(e)[:100]}")

            # Retry с backoff
            if attempt < max_attempts - 1:
                self._stats.total_retries += 1
                time.sleep(delay)
                delay = min(delay * self.BACKOFF_MULTIPLIER, self.MAX_DELAY)

        # Все попытки провалились
        self._stats.failed_requests += 1
        if self._enable_circuit_breaker:
            self._record_failure()

        logger.error(f"vLLM structured all retries failed: {str(last_error)[:100] if last_error else 'unknown'}")
        return None

    # =========================================================================
    # FREE-FORM GENERATION (как в OllamaLLM)
    # =========================================================================

    def generate(
        self,
        prompt: str,
        state: Optional[str] = None,
        allow_fallback: bool = True
    ) -> str:
        """
        Сгенерировать ответ с resilience.

        Args:
            prompt: Промпт для LLM
            state: Текущее состояние FSM (для fallback)
            allow_fallback: Разрешить fallback при ошибке

        Returns:
            Ответ LLM или fallback
        """
        self._stats.total_requests += 1
        start_time = time.time()

        # Circuit breaker check
        if self._enable_circuit_breaker and self._is_circuit_open():
            logger.warning("Circuit breaker open, using fallback", state=state)
            self._stats.fallback_used += 1
            return self._get_fallback(state) if allow_fallback else ""

        last_error: Optional[Exception] = None
        delay = self.INITIAL_DELAY
        max_attempts = self.MAX_RETRIES if self._enable_retry else 1

        for attempt in range(max_attempts):
            try:
                # Используем _call_llm для совместимости с тестами
                response_text = self._call_llm(prompt)

                # Успех
                elapsed_ms = (time.time() - start_time) * 1000
                self._stats.successful_requests += 1
                self._stats.total_response_time_ms += elapsed_ms
                self._reset_failures()

                logger.debug(
                    "vLLM request successful",
                    attempt=attempt + 1,
                    elapsed_ms=round(elapsed_ms, 1)
                )

                return response_text

            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"vLLM timeout (attempt {attempt + 1}/{max_attempts})")
            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(f"vLLM connection error (attempt {attempt + 1}/{max_attempts})")
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(f"vLLM request failed (attempt {attempt + 1}/{max_attempts})")
            except Exception as e:
                last_error = e
                logger.error(f"vLLM unexpected error (attempt {attempt + 1}/{max_attempts})")

            # Retry с backoff
            if attempt < max_attempts - 1:
                self._stats.total_retries += 1
                logger.debug(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay = min(delay * self.BACKOFF_MULTIPLIER, self.MAX_DELAY)

        # Все попытки провалились
        self._stats.failed_requests += 1
        if self._enable_circuit_breaker:
            self._record_failure()

        logger.error(
            "vLLM all retries failed",
            error=str(last_error)[:100] if last_error else "unknown",
            state=state
        )

        if allow_fallback:
            self._stats.fallback_used += 1
            return self._get_fallback(state)

        return ""

    # =========================================================================
    # LEGACY METHOD FOR TEST COMPATIBILITY
    # =========================================================================

    def _call_llm(self, prompt: str) -> str:
        """
        Вызов vLLM API (для совместимости с тестами).

        Внутренний метод без retry/circuit breaker.
        Тесты могут мокать этот метод.
        """
        base_url_normalized = self.base_url.rstrip("/")

        # vLLM OpenAI-compatible API
        response = requests.post(
            f"{base_url_normalized}/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 256,
            },
            timeout=self.timeout
        )
        response.raise_for_status()

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("Empty response from vLLM")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        if not content:
            raise ValueError("Empty content in response from vLLM")

        return content

    # =========================================================================
    # CIRCUIT BREAKER
    # =========================================================================

    def _is_circuit_open(self) -> bool:
        """Проверка открыт ли circuit breaker"""
        if not self._circuit_breaker.is_open:
            return False

        # Проверяем не пора ли попробовать восстановиться
        if time.time() >= self._circuit_breaker.open_until:
            logger.info("Circuit breaker attempting recovery (half-open state)")
            self._circuit_breaker.is_open = False
            return False

        return True

    def _record_failure(self) -> None:
        """Записать ошибку для circuit breaker"""
        self._circuit_breaker.failures += 1
        self._circuit_breaker.last_failure_time = time.time()

        if self._circuit_breaker.failures >= self.CIRCUIT_BREAKER_THRESHOLD:
            self._circuit_breaker.is_open = True
            self._circuit_breaker.open_until = time.time() + self.CIRCUIT_BREAKER_TIMEOUT
            self._stats.circuit_breaker_trips += 1

            logger.error(
                "Circuit breaker opened",
                failures=self._circuit_breaker.failures,
                timeout=self.CIRCUIT_BREAKER_TIMEOUT
            )

    def _reset_failures(self) -> None:
        """Сбросить счётчик ошибок после успеха"""
        self._circuit_breaker.failures = 0
        if self._circuit_breaker.is_open:
            logger.info("Circuit breaker closed after successful request")
            self._circuit_breaker.is_open = False

    def _get_fallback(self, state: Optional[str]) -> str:
        """Получить fallback ответ для состояния"""
        if state and state in self.FALLBACK_RESPONSES:
            return self.FALLBACK_RESPONSES[state]
        return self.DEFAULT_FALLBACK

    # =========================================================================
    # STATS & HEALTH
    # =========================================================================

    def get_stats_dict(self) -> Dict[str, Any]:
        """Получить статистику в виде словаря"""
        return {
            "total_requests": self._stats.total_requests,
            "successful_requests": self._stats.successful_requests,
            "failed_requests": self._stats.failed_requests,
            "fallback_used": self._stats.fallback_used,
            "total_retries": self._stats.total_retries,
            "circuit_breaker_trips": self._stats.circuit_breaker_trips,
            "success_rate": round(self._stats.success_rate, 1),
            "average_response_time_ms": round(self._stats.average_response_time_ms, 1),
            "circuit_breaker_open": self._circuit_breaker.is_open,
        }

    def health_check(self) -> bool:
        """
        Проверка доступности vLLM.

        Returns:
            True если vLLM доступен
        """
        try:
            # vLLM health endpoint
            health_url = self.base_url.rstrip("/v1").rstrip("/") + "/health"
            response = requests.get(health_url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False


# =============================================================================
# АЛИАС ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ
# =============================================================================
# OllamaLLM - устаревший алиас, используйте VLLMClient напрямую
OllamaLLM = VLLMClient


# =============================================================================
# CLI для демонстрации
# =============================================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("vLLM CLIENT DEMO")
    print("=" * 60)
    print("\nЭтот проект использует ТОЛЬКО vLLM.")
    print("Запуск vLLM: vllm serve Qwen/Qwen3-4B-AWQ --port 8000 --quantization awq")

    llm = VLLMClient()

    print(f"\nModel: {llm.model}")
    print(f"URL: {llm.base_url}")
    print(f"Timeout: {llm.timeout}s")

    # Health check
    print("\n--- Health Check ---")
    is_healthy = llm.health_check()
    print(f"vLLM available: {is_healthy}")

    if is_healthy:
        print("\n--- Test Generation ---")
        response = llm.generate(
            "Привет! Ты работаешь?",
            state="greeting"
        )
        print(f"Response: {response[:100]}...")

        # Structured output demo
        print("\n--- Structured Output Demo ---")
        from classifier.llm.schemas import ClassificationResult
        result = llm.generate_structured(
            "Классифицируй сообщение: 'Сколько стоит ваша система?'",
            ClassificationResult
        )
        if result:
            print(f"Intent: {result.intent}")
            print(f"Confidence: {result.confidence}")
        else:
            print("Structured output failed (vLLM not running?)")

    print("\n--- Fallback Demo ---")
    for state in ["greeting", "spin_situation", "spin_problem", "unknown"]:
        fallback = llm._get_fallback(state)
        print(f"{state}: {fallback[:50]}...")

    print("\n--- Stats ---")
    print(json.dumps(llm.get_stats_dict(), indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)

"""
Resilient LLM Client для CRM Sales Bot.

Устойчивый LLM клиент с:
- Exponential backoff retry
- Circuit breaker
- Fallback responses
- Request timeout handling
- Structured logging

Использование:
    from llm import OllamaLLM

    llm = OllamaLLM()
    response = llm.generate(prompt, state="spin_situation")

    # С circuit breaker
    llm.reset_circuit_breaker()
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests

from logger import logger
from settings import settings


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


class OllamaLLM:
    """
    Resilient LLM client с:
    - Exponential backoff retry
    - Circuit breaker
    - Fallback responses
    """

    # Настройки retry
    MAX_RETRIES: int = 3
    INITIAL_DELAY: float = 1.0
    MAX_DELAY: float = 10.0
    BACKOFF_MULTIPLIER: float = 2.0

    # Настройки circuit breaker
    CIRCUIT_BREAKER_THRESHOLD: int = 5  # Сколько ошибок до открытия
    CIRCUIT_BREAKER_TIMEOUT: int = 60   # Секунд до попытки восстановления

    # Fallback responses по состояниям (если LLM недоступен)
    FALLBACK_RESPONSES: Dict[str, str] = {
        "greeting": "Здравствуйте! Чем могу помочь?",
        "spin_situation": "Расскажите, сколько человек работает в вашей команде?",
        "spin_problem": "С какими сложностями сталкиваетесь сейчас?",
        "spin_implication": "Как это влияет на бизнес?",
        "spin_need_payoff": "Что было бы идеальным решением?",
        "presentation": "Wipon помогает автоматизировать работу с клиентами. Хотите узнать подробнее?",
        "close": "Оставьте контакт — свяжусь с деталями.",
        "soft_close": "Спасибо за разговор! Если вопросы появятся — пишите.",
        "handle_objection": "Понимаю ваши сомнения. Давайте разберём подробнее?",
    }

    DEFAULT_FALLBACK: str = "Произошла техническая ошибка. Попробуйте ещё раз или оставьте контакт."

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        enable_circuit_breaker: bool = True,
        enable_retry: bool = True
    ):
        """
        Инициализация LLM клиента.

        Args:
            model: Название модели (из settings если не указано)
            base_url: URL Ollama API (из settings если не указано)
            timeout: Таймаут запроса в секундах (из settings если не указано)
            enable_circuit_breaker: Включить circuit breaker
            enable_retry: Включить retry с exponential backoff
        """
        self.model = model or settings.llm.model
        self.base_url = base_url or settings.llm.base_url
        self.timeout = timeout or settings.llm.timeout
        self.stream = settings.llm.stream
        self.think = settings.llm.think

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
            logger.warning(
                "Circuit breaker open, using fallback",
                state=state
            )
            self._stats.fallback_used += 1
            return self._get_fallback(state) if allow_fallback else ""

        # Попытка с retry
        last_error: Optional[Exception] = None
        delay = self.INITIAL_DELAY

        max_attempts = self.MAX_RETRIES if self._enable_retry else 1

        for attempt in range(max_attempts):
            try:
                response = self._call_llm(prompt)

                # Успех
                elapsed_ms = (time.time() - start_time) * 1000
                self._stats.successful_requests += 1
                self._stats.total_response_time_ms += elapsed_ms
                self._reset_failures()

                logger.debug(
                    "LLM request successful",
                    attempt=attempt + 1,
                    elapsed_ms=round(elapsed_ms, 1)
                )

                return response

            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(
                    f"LLM timeout (attempt {attempt + 1}/{max_attempts})",
                    timeout=self.timeout
                )
            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(
                    f"LLM connection error (attempt {attempt + 1}/{max_attempts})",
                    error=str(e)[:100]
                )
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(
                    f"LLM request failed (attempt {attempt + 1}/{max_attempts})",
                    error=str(e)[:100]
                )
            except Exception as e:
                last_error = e
                logger.error(
                    f"LLM unexpected error (attempt {attempt + 1}/{max_attempts})",
                    error=str(e)[:100]
                )

            # Retry с exponential backoff (кроме последней попытки)
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
            "LLM all retries failed",
            error=str(last_error)[:100] if last_error else "unknown",
            state=state
        )

        if allow_fallback:
            self._stats.fallback_used += 1
            return self._get_fallback(state)

        return ""

    def _call_llm(self, prompt: str) -> str:
        """Вызов LLM API"""
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": self.stream,
                "think": self.think,
            },
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()["response"]

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
        Проверка доступности LLM.

        Returns:
            True если LLM доступен
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False


# =============================================================================
# CLI для демонстрации
# =============================================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("RESILIENT LLM CLIENT DEMO")
    print("=" * 60)

    llm = OllamaLLM()

    print(f"\nModel: {llm.model}")
    print(f"URL: {llm.base_url}")
    print(f"Timeout: {llm.timeout}s")

    # Health check
    print("\n--- Health Check ---")
    is_healthy = llm.health_check()
    print(f"LLM available: {is_healthy}")

    if is_healthy:
        print("\n--- Test Generation ---")
        response = llm.generate(
            "Привет! Ты работаешь?",
            state="greeting"
        )
        print(f"Response: {response[:100]}...")

    print("\n--- Fallback Demo ---")
    for state in ["greeting", "spin_situation", "spin_problem", "unknown"]:
        fallback = llm._get_fallback(state)
        print(f"{state}: {fallback[:50]}...")

    print("\n--- Stats ---")
    print(json.dumps(llm.get_stats_dict(), indent=2, ensure_ascii=False))

    # Circuit breaker demo
    print("\n--- Circuit Breaker Demo ---")
    # Создаём клиент с несуществующим URL
    bad_llm = OllamaLLM(base_url="http://localhost:99999", timeout=1)
    bad_llm.CIRCUIT_BREAKER_THRESHOLD = 2  # Быстрее для демо

    for i in range(3):
        print(f"\nAttempt {i + 1}:")
        response = bad_llm.generate("test", state="greeting")
        print(f"  Response: {response[:40]}...")
        print(f"  Circuit open: {bad_llm.is_circuit_open}")

    print("\n" + "=" * 60)

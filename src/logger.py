"""
Structured Logging для CRM Sales Bot.

JSON-логи для production, readable для dev.
Включает conversation_id для трейсинга.

Использование:
    from logger import logger

    logger.set_conversation("conv_123")
    logger.info("User message received", intent="greeting")
    logger.metric("response_time", 0.5, state="spin_situation")
"""

import logging
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from settings import settings


class StructuredLogger:
    """
    Структурированный логгер с поддержкой JSON и conversation tracing.

    Особенности:
    - JSON формат для production (LOG_FORMAT=json)
    - Readable формат для development (по умолчанию)
    - Автоматический conversation_id в каждом логе
    - Метод metric() для аналитики
    """

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
        self._conversation_id: Optional[str] = None
        self._extra_context: Dict[str, Any] = {}

        # Настройка логгера (только если еще не настроен)
        if not self.logger.handlers:
            self._setup_logger()

    def _setup_logger(self) -> None:
        """Настройка логгера на основе settings и environment"""
        # Определяем уровень логирования
        level_name = settings.get_nested("logging.level", "INFO")
        level = getattr(logging, level_name.upper(), logging.INFO)
        self.logger.setLevel(level)

        # Создаем handler
        handler = logging.StreamHandler()
        handler.setLevel(level)

        # Формат зависит от окружения
        log_format = os.environ.get("LOG_FORMAT", "readable")

        if log_format == "json":
            # JSON формат для production
            formatter = logging.Formatter("%(message)s")
        else:
            # Readable формат для development
            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)s - %(message)s",
                datefmt="%H:%M:%S"
            )

        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # Предотвращаем дублирование логов
        self.logger.propagate = False

    @property
    def conversation_id(self) -> Optional[str]:
        """Текущий conversation_id"""
        return self._conversation_id

    def set_conversation(self, conv_id: str) -> None:
        """Установить conversation_id для трейсинга"""
        self._conversation_id = conv_id

    def clear_conversation(self) -> None:
        """Очистить conversation_id"""
        self._conversation_id = None

    def set_context(self, **kwargs: Any) -> None:
        """Установить дополнительный контекст для всех логов"""
        self._extra_context.update(kwargs)

    def clear_context(self) -> None:
        """Очистить дополнительный контекст"""
        self._extra_context.clear()

    def _format_structured(self, level: str, message: str, **kwargs: Any) -> Dict[str, Any]:
        """Форматирование структурированного лога"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": level,
            "logger": self.name,
            "message": message,
        }

        # Добавляем conversation_id если есть
        if self._conversation_id:
            log_entry["conversation_id"] = self._conversation_id

        # Добавляем постоянный контекст
        if self._extra_context:
            log_entry.update(self._extra_context)

        # Добавляем переданные kwargs
        if kwargs:
            log_entry.update(kwargs)

        return log_entry

    def _should_use_json(self) -> bool:
        """Проверка нужно ли использовать JSON формат"""
        return os.environ.get("LOG_FORMAT", "readable") == "json"

    def _log(self, level: str, message: str, log_method, **kwargs: Any) -> None:
        """Общий метод логирования"""
        if self._should_use_json():
            structured = self._format_structured(level, message, **kwargs)
            log_method(json.dumps(structured, ensure_ascii=False))
        else:
            # Readable формат
            if kwargs:
                extras = ", ".join(f"{k}={v}" for k, v in kwargs.items())
                full_message = f"{message} [{extras}]"
            else:
                full_message = message

            if self._conversation_id:
                full_message = f"[{self._conversation_id}] {full_message}"

            log_method(full_message)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message"""
        self._log("DEBUG", message, self.logger.debug, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message"""
        self._log("INFO", message, self.logger.info, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message"""
        self._log("WARNING", message, self.logger.warning, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message"""
        self._log("ERROR", message, self.logger.error, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message"""
        self._log("CRITICAL", message, self.logger.critical, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception with traceback"""
        if self._should_use_json():
            import traceback
            kwargs["traceback"] = traceback.format_exc()
            structured = self._format_structured("ERROR", message, **kwargs)
            self.logger.error(json.dumps(structured, ensure_ascii=False))
        else:
            if kwargs:
                extras = ", ".join(f"{k}={v}" for k, v in kwargs.items())
                full_message = f"{message} [{extras}]"
            else:
                full_message = message

            if self._conversation_id:
                full_message = f"[{self._conversation_id}] {full_message}"

            self.logger.exception(full_message)

    def metric(self, name: str, value: Any, **kwargs: Any) -> None:
        """
        Structured metric for analytics.

        Args:
            name: Название метрики (например, "response_time", "fallback_triggered")
            value: Значение метрики
            **kwargs: Дополнительные измерения (state, intent, etc.)

        Example:
            logger.metric("response_time", 0.5, state="spin_situation")
            logger.metric("fallback_triggered", 1, tier="tier_2", state="spin_problem")
        """
        self._log("METRIC", name, self.logger.info, value=value, **kwargs)

    def event(self, event_type: str, **kwargs: Any) -> None:
        """
        Log business event for analytics.

        Args:
            event_type: Тип события (например, "state_transition", "intent_classified")
            **kwargs: Данные события

        Example:
            logger.event("state_transition", from_state="greeting", to_state="spin_situation")
            logger.event("objection_detected", type="price", attempts=1)
        """
        self._log("EVENT", event_type, self.logger.info, **kwargs)


# Singleton экземпляр логгера
logger = StructuredLogger("crm_sales_bot")


# =============================================================================
# Утилиты для тестирования
# =============================================================================

def create_test_logger(name: str = "test") -> StructuredLogger:
    """Создать изолированный логгер для тестов"""
    return StructuredLogger(f"crm_sales_bot.{name}")


# =============================================================================
# CLI для проверки логгера
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("ДЕМО STRUCTURED LOGGER")
    print("=" * 60)

    # Демонстрация readable формата
    print("\n--- Readable Format (default) ---")
    logger.info("Application started")
    logger.set_conversation("conv_abc123")
    logger.info("User message received", intent="greeting")
    logger.warning("Slow response", response_time=2.5)
    logger.metric("response_time", 0.5, state="spin_situation")
    logger.event("state_transition", from_state="greeting", to_state="spin_situation")

    # Демонстрация JSON формата
    print("\n--- JSON Format (set LOG_FORMAT=json) ---")
    os.environ["LOG_FORMAT"] = "json"
    json_logger = StructuredLogger("crm_sales_bot.demo")
    json_logger.set_conversation("conv_xyz789")
    json_logger.info("Application started")
    json_logger.info("User message received", intent="greeting", user_id="u123")
    json_logger.metric("response_time", 0.5, state="spin_situation")

    print("\n" + "=" * 60)
    print("Логгер работает корректно!")

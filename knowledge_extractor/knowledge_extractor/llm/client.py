"""Ollama client with structured output support."""

import json
import logging
import time
from typing import Any, Dict, Optional, Type, TypeVar

import requests
from pydantic import BaseModel

from ..config import LLMConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base LLM error."""
    pass


class LLMTimeoutError(LLMError):
    """LLM timeout error."""
    pass


class LLMConnectionError(LLMError):
    """LLM connection error."""
    pass


class LLMValidationError(LLMError):
    """LLM response validation error."""
    pass


class LLMClient:
    """Ollama client with structured output support."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._request_count = 0
        self._total_tokens = 0

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text completion."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return self._call_api(
            messages=messages,
            temperature=temperature or self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> T:
        """Generate structured output using JSON schema."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Get JSON schema from Pydantic model
        json_schema = schema.model_json_schema()

        response_text = self._call_api(
            messages=messages,
            temperature=temperature or self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
            format_schema=json_schema,  # Ollama native format
        )

        # Parse and validate response
        try:
            data = json.loads(response_text)
            return schema.model_validate(data)
        except json.JSONDecodeError as e:
            raise LLMValidationError(f"Failed to parse JSON: {e}\nResponse: {response_text}")
        except Exception as e:
            raise LLMValidationError(f"Failed to validate schema: {e}\nResponse: {response_text}")

    def _call_api(
        self,
        messages: list,
        temperature: float,
        max_tokens: int,
        format_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Call Ollama API with retry logic."""
        last_error = None
        base_url = self.config.base_url.rstrip("/")

        for attempt in range(self.config.max_retries):
            try:
                payload = {
                    "model": self.config.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                }

                # Ollama native structured output via format parameter
                if format_schema:
                    payload["format"] = format_schema

                start_time = time.time()
                response = requests.post(
                    f"{base_url}/api/chat",
                    json=payload,
                    timeout=self.config.timeout,
                )
                response.raise_for_status()
                elapsed = time.time() - start_time

                data = response.json()
                self._request_count += 1

                # Ollama returns token counts in eval_count and prompt_eval_count
                eval_count = data.get("eval_count", 0)
                prompt_eval_count = data.get("prompt_eval_count", 0)
                total_tokens = eval_count + prompt_eval_count
                self._total_tokens += total_tokens

                logger.debug(
                    f"LLM request #{self._request_count}: {elapsed:.2f}s, "
                    f"tokens: {total_tokens}"
                )

                message = data.get("message", {})
                content = message.get("content", "")

                # Qwen3 may return response in "thinking" field when in thinking mode
                if not content:
                    content = message.get("thinking", "")

                if not content:
                    raise LLMError("Empty content in response from Ollama")

                return content

            except requests.exceptions.Timeout as e:
                last_error = LLMTimeoutError(f"Request timed out: {e}")
                logger.warning(f"Timeout on attempt {attempt + 1}/{self.config.max_retries}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.ConnectionError as e:
                last_error = LLMConnectionError(f"Connection error: {e}")
                logger.warning(f"Connection error on attempt {attempt + 1}/{self.config.max_retries}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** (attempt + 1))

            except Exception as e:
                last_error = LLMError(f"Unexpected error: {e}")
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(1)

        raise last_error

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return {
            "request_count": self._request_count,
            "total_tokens": self._total_tokens,
        }

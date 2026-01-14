"""vLLM client with structured output support via Outlines."""

import json
import logging
import time
from typing import Any, Dict, Optional, Type, TypeVar

from openai import OpenAI
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
    """vLLM client with structured output support."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = OpenAI(
            base_url=config.base_url,
            api_key="not-needed",  # vLLM doesn't require API key
            timeout=config.timeout,
        )
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
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": json_schema,
                    "strict": True,
                },
            },
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
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Call LLM API with retry logic."""
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                kwargs = {
                    "model": self.config.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                start_time = time.time()
                response = self.client.chat.completions.create(**kwargs)
                elapsed = time.time() - start_time

                self._request_count += 1
                if response.usage:
                    self._total_tokens += response.usage.total_tokens

                logger.debug(
                    f"LLM request #{self._request_count}: {elapsed:.2f}s, "
                    f"tokens: {response.usage.total_tokens if response.usage else 'N/A'}"
                )

                return response.choices[0].message.content

            except TimeoutError as e:
                last_error = LLMTimeoutError(f"Request timed out: {e}")
                logger.warning(f"Timeout on attempt {attempt + 1}/{self.config.max_retries}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

            except ConnectionError as e:
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

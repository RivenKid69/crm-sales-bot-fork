"""vLLM client for LLM inference."""

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ...config import LLMConfig, get_config
from ...utils.logging import get_logger
from ...utils.metrics import get_operation_metrics, timed_operation

logger = get_logger("llm_client")


@dataclass
class LLMResponse:
    """Response from LLM inference."""

    text: str
    input_tokens: int
    output_tokens: int
    finish_reason: str = "stop"
    model: str = ""


@dataclass
class Message:
    """A chat message."""

    role: str  # "system", "user", "assistant"
    content: str


class VLLMClient:
    """Client for vLLM OpenAI-compatible API.

    Supports both synchronous and asynchronous inference.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or get_config().llm
        self._client: httpx.AsyncClient | None = None
        self._sync_client: httpx.Client | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.api_base,
                timeout=httpx.Timeout(300.0),  # 5 minute timeout for long generations
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
        return self._client

    def _get_sync_client(self) -> httpx.Client:
        """Get or create sync HTTP client."""
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self.config.api_base,
                timeout=httpx.Timeout(300.0),
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
        return self._sync_client

    async def close(self) -> None:
        """Close the HTTP clients."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters

        Returns:
            LLMResponse with generated text and usage info
        """
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return await self.chat(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def chat(
        self,
        messages: list[dict[str, str] | Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Chat completion with multiple messages.

        Args:
            messages: List of messages
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters

        Returns:
            LLMResponse with generated text and usage info
        """
        client = await self._get_client()
        metrics = get_operation_metrics()

        # Convert Message objects to dicts
        msg_dicts = []
        for msg in messages:
            if isinstance(msg, Message):
                msg_dicts.append({"role": msg.role, "content": msg.content})
            else:
                msg_dicts.append(msg)

        request_body = {
            "model": self.config.model_name,
            "messages": msg_dicts,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "top_p": self.config.top_p,
            **kwargs,
        }

        with timed_operation("llm_inference"):
            response = await client.post("/chat/completions", json=request_body)
            response.raise_for_status()

        data = response.json()

        # Extract response
        choice = data["choices"][0]
        usage = data.get("usage", {})

        # Track token usage
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        metrics.tokens.add_usage(input_tokens, output_tokens)

        return LLMResponse(
            text=choice["message"]["content"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=choice.get("finish_reason", "stop"),
            model=data.get("model", self.config.model_name),
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Generate a streaming response.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            **kwargs: Additional parameters

        Yields:
            Text chunks as they are generated
        """
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        client = await self._get_client()

        request_body = {
            "model": self.config.model_name,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": True,
        }

        async with client.stream("POST", "/chat/completions", json=request_body) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        import json

                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue

    def generate_sync(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Synchronous generation (blocking).

        For use when async is not available.
        """
        return asyncio.run(
            self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        )


class BatchProcessor:
    """Batch processor for efficient LLM inference.

    Implements ReWOO-style batch processing for better throughput.
    """

    def __init__(
        self,
        client: VLLMClient,
        batch_size: int = 10,
        max_concurrent: int = 5,
    ):
        self.client = client
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def process_batch(
        self,
        prompts: list[tuple[str, str | None]],  # (prompt, system_prompt)
        **kwargs: Any,
    ) -> list[LLMResponse | None]:
        """Process a batch of prompts concurrently.

        Args:
            prompts: List of (prompt, system_prompt) tuples
            **kwargs: Additional parameters for generation

        Returns:
            List of responses (None for failed items)
        """
        results: list[LLMResponse | None] = [None] * len(prompts)

        async def process_one(idx: int, prompt: str, system_prompt: str | None) -> None:
            async with self._semaphore:
                try:
                    response = await self.client.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        **kwargs,
                    )
                    results[idx] = response
                except Exception as e:
                    logger.warning(f"Batch item {idx} failed: {e}")
                    results[idx] = None

        tasks = [
            process_one(idx, prompt, system_prompt)
            for idx, (prompt, system_prompt) in enumerate(prompts)
        ]

        await asyncio.gather(*tasks)
        return results

    async def process_items(
        self,
        items: list[Any],
        prompt_fn: callable,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> list[tuple[Any, LLMResponse | None]]:
        """Process items with a prompt function.

        Args:
            items: List of items to process
            prompt_fn: Function that takes an item and returns a prompt
            system_prompt: Optional system prompt for all items
            **kwargs: Additional parameters

        Returns:
            List of (item, response) tuples
        """
        results: list[tuple[Any, LLMResponse | None]] = []

        # Process in batches
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            prompts = [(prompt_fn(item), system_prompt) for item in batch]

            responses = await self.process_batch(prompts, **kwargs)

            for item, response in zip(batch, responses):
                results.append((item, response))

        return results


def create_client(config: LLMConfig | None = None) -> VLLMClient:
    """Create a vLLM client instance.

    Args:
        config: Optional LLM configuration

    Returns:
        Configured client instance
    """
    return VLLMClient(config)


def create_batch_processor(
    client: VLLMClient | None = None,
    batch_size: int = 10,
    max_concurrent: int = 5,
) -> BatchProcessor:
    """Create a batch processor instance.

    Args:
        client: Optional vLLM client (creates new if not provided)
        batch_size: Number of items per batch
        max_concurrent: Max concurrent requests

    Returns:
        Configured batch processor
    """
    if client is None:
        client = create_client()
    return BatchProcessor(client, batch_size, max_concurrent)

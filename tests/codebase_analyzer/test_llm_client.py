"""Tests for codebase_analyzer/analyzer/llm/client.py - vLLM client."""

import asyncio
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codebase_analyzer.analyzer.llm.client import (
    BatchProcessor,
    LLMResponse,
    Message,
    VLLMClient,
    create_batch_processor,
    create_client,
)
from codebase_analyzer.config import LLMConfig


# ============================================================================
# LLMResponse Tests
# ============================================================================


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_basic_creation(self):
        """Test creating a basic LLMResponse."""
        response = LLMResponse(
            text="Generated text",
            input_tokens=100,
            output_tokens=50,
        )

        assert response.text == "Generated text"
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.finish_reason == "stop"
        assert response.model == ""

    def test_with_all_fields(self):
        """Test LLMResponse with all fields."""
        response = LLMResponse(
            text="Complete response",
            input_tokens=500,
            output_tokens=200,
            finish_reason="length",
            model="Qwen/Qwen3-30B",
        )

        assert response.finish_reason == "length"
        assert response.model == "Qwen/Qwen3-30B"


# ============================================================================
# Message Tests
# ============================================================================


class TestMessage:
    """Tests for Message dataclass."""

    def test_user_message(self):
        """Test creating a user message."""
        msg = Message(role="user", content="Hello, world!")

        assert msg.role == "user"
        assert msg.content == "Hello, world!"

    def test_assistant_message(self):
        """Test creating an assistant message."""
        msg = Message(role="assistant", content="How can I help?")

        assert msg.role == "assistant"

    def test_system_message(self):
        """Test creating a system message."""
        msg = Message(role="system", content="You are a helpful assistant.")

        assert msg.role == "system"


# ============================================================================
# VLLMClient Tests
# ============================================================================


class TestVLLMClient:
    """Tests for VLLMClient."""

    @pytest.fixture
    def config(self):
        """Create LLM config for testing."""
        return LLMConfig(
            model_name="test-model",
            temperature=0.5,
            max_tokens=1024,
            api_base="http://localhost:8000/v1",
            api_key="test-key",
        )

    @pytest.fixture
    def client(self, config):
        """Create VLLMClient for testing."""
        return VLLMClient(config)

    def test_client_creation(self, client, config):
        """Test VLLMClient creation."""
        assert client is not None
        assert client.config is config

    def test_client_creation_default_config(self):
        """Test VLLMClient with default config."""
        client = VLLMClient()
        assert client is not None
        assert client.config is not None

    def test_create_client_factory(self, config):
        """Test create_client factory function."""
        client = create_client(config)
        assert isinstance(client, VLLMClient)

    @pytest.mark.asyncio
    async def test_generate_mock(self, client):
        """Test generate method with mocked HTTP client."""
        mock_response = {
            "choices": [
                {
                    "message": {"content": "Generated response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 30,
            },
            "model": "test-model",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_response = MagicMock()
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = MagicMock()
            mock_http_client.post = AsyncMock(return_value=mock_http_response)
            mock_get_client.return_value = mock_http_client

            response = await client.generate("Test prompt")

            assert response.text == "Generated response"
            assert response.input_tokens == 50
            assert response.output_tokens == 30

    @pytest.mark.asyncio
    async def test_chat_mock(self, client):
        """Test chat method with mocked HTTP client."""
        mock_response = {
            "choices": [
                {
                    "message": {"content": "Chat response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
            },
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_response = MagicMock()
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = MagicMock()
            mock_http_client.post = AsyncMock(return_value=mock_http_response)
            mock_get_client.return_value = mock_http_client

            messages = [
                {"role": "user", "content": "Hello"},
            ]
            response = await client.chat(messages)

            assert response.text == "Chat response"

    @pytest.mark.asyncio
    async def test_chat_with_message_objects(self, client):
        """Test chat method with Message objects."""
        mock_response = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 25},
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_response = MagicMock()
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = MagicMock()
            mock_http_client.post = AsyncMock(return_value=mock_http_response)
            mock_get_client.return_value = mock_http_client

            messages = [
                Message(role="system", content="You are helpful"),
                Message(role="user", content="Hello"),
            ]
            response = await client.chat(messages)

            assert response.text == "Response"

    def test_generate_sync(self, client):
        """Test synchronous generate method."""
        mock_response = {
            "choices": [{"message": {"content": "Sync response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 20},
        }

        # generate_sync calls asyncio.run(self.generate(...)) which uses _get_client
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_response = MagicMock()
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = MagicMock()
            mock_http_client.post = AsyncMock(return_value=mock_http_response)
            mock_get_client.return_value = mock_http_client

            response = client.generate_sync("Test prompt")

            assert response.text == "Sync response"

    def test_generate_sync_with_system_prompt(self, client):
        """Test synchronous generate with system prompt."""
        mock_response = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 30},
        }

        # generate_sync calls asyncio.run(self.generate(...)) which uses _get_client
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_response = MagicMock()
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = MagicMock()
            mock_http_client.post = AsyncMock(return_value=mock_http_response)
            mock_get_client.return_value = mock_http_client

            response = client.generate_sync(
                prompt="Analyze this code",
                system_prompt="You are a code analyst",
            )

            assert response.text == "Response"

    @pytest.mark.asyncio
    async def test_generate_with_custom_params(self, client):
        """Test generate with custom parameters."""
        mock_response = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 100},
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_response = MagicMock()
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = MagicMock()
            mock_http_client.post = AsyncMock(return_value=mock_http_response)
            mock_get_client.return_value = mock_http_client

            response = await client.generate(
                prompt="Test",
                max_tokens=2048,
                temperature=0.8,
            )

            assert response is not None

    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test closing the client."""
        # Should not raise
        await client.close()


# ============================================================================
# BatchProcessor Tests
# ============================================================================


class TestBatchProcessor:
    """Tests for BatchProcessor."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock VLLMClient."""
        client = MagicMock(spec=VLLMClient)
        client.generate = AsyncMock(
            return_value=LLMResponse(
                text="Response",
                input_tokens=50,
                output_tokens=25,
            )
        )
        return client

    @pytest.fixture
    def processor(self, mock_client):
        """Create BatchProcessor for testing."""
        return BatchProcessor(mock_client, batch_size=5, max_concurrent=2)

    def test_processor_creation(self, processor, mock_client):
        """Test BatchProcessor creation."""
        assert processor is not None
        assert processor.client is mock_client
        assert processor.batch_size == 5
        assert processor.max_concurrent == 2

    def test_create_batch_processor_factory(self, mock_client):
        """Test create_batch_processor factory."""
        processor = create_batch_processor(mock_client, batch_size=10)
        assert isinstance(processor, BatchProcessor)

    @pytest.mark.asyncio
    async def test_process_batch(self, processor, mock_client):
        """Test processing a batch of prompts."""
        prompts = [
            ("Prompt 1", None),
            ("Prompt 2", "System"),
            ("Prompt 3", None),
        ]

        results = await processor.process_batch(prompts)

        assert len(results) == 3
        assert all(r is not None for r in results)
        assert mock_client.generate.call_count == 3

    @pytest.mark.asyncio
    async def test_process_batch_empty(self, processor):
        """Test processing empty batch."""
        results = await processor.process_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_process_batch_with_errors(self, mock_client):
        """Test batch processing handles errors gracefully."""
        call_count = [0]

        async def mock_generate(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("API error")
            return LLMResponse(text="Success", input_tokens=10, output_tokens=5)

        mock_client.generate = mock_generate

        processor = BatchProcessor(mock_client, batch_size=5)
        prompts = [("P1", None), ("P2", None), ("P3", None)]

        results = await processor.process_batch(prompts)

        # Should have 3 results, one may be None due to error
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_process_items(self, processor, mock_client):
        """Test processing items with custom prompt function."""
        items = ["item1", "item2", "item3"]

        def prompt_fn(item):
            return f"Process: {item}"

        results = await processor.process_items(items, prompt_fn)

        assert len(results) == 3
        # Results are tuples of (item, response)
        for item, response in results:
            assert item in items
            assert response is not None

    @pytest.mark.asyncio
    async def test_process_items_with_system_prompt(self, processor, mock_client):
        """Test processing items with system prompt."""
        items = ["a", "b"]

        results = await processor.process_items(
            items,
            lambda x: f"Item: {x}",
            system_prompt="You are a processor",
        )

        assert len(results) == 2


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling in LLM client."""

    @pytest.fixture
    def client(self):
        return VLLMClient(
            LLMConfig(
                api_base="http://localhost:8000/v1",
                max_tokens=100,
            )
        )

    @pytest.mark.asyncio
    async def test_connection_error(self, client):
        """Test handling connection errors."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(side_effect=ConnectionError("Failed"))
            mock_get_client.return_value = mock_http_client

            # Should raise after retries
            with pytest.raises(Exception):
                await client.generate("Test")

    @pytest.mark.asyncio
    async def test_invalid_response(self, client):
        """Test handling invalid API response."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_response = MagicMock()
            mock_http_response.json.return_value = {"invalid": "response"}
            mock_http_response.raise_for_status = MagicMock()
            mock_http_client.post = AsyncMock(return_value=mock_http_response)
            mock_get_client.return_value = mock_http_client

            # Should handle gracefully
            with pytest.raises(Exception):
                await client.generate("Test")


# ============================================================================
# Configuration Tests
# ============================================================================


class TestConfiguration:
    """Tests for client configuration."""

    def test_custom_config(self):
        """Test client with custom configuration."""
        config = LLMConfig(
            model_name="custom-model",
            temperature=0.3,
            top_p=0.95,
            max_tokens=2048,
            api_base="http://custom:9000/v1",
            api_key="custom-key",
        )

        client = VLLMClient(config)

        assert client.config.model_name == "custom-model"
        assert client.config.temperature == 0.3
        assert client.config.api_base == "http://custom:9000/v1"

    def test_default_config_values(self):
        """Test client uses config defaults."""
        config = LLMConfig()
        client = VLLMClient(config)

        assert client.config.temperature == 0.1
        assert client.config.max_tokens == 4096
        assert "localhost:8000" in client.config.api_base


# ============================================================================
# Integration-like Tests (with mocks)
# ============================================================================


class TestIntegration:
    """Integration-like tests with comprehensive mocking."""

    @pytest.mark.asyncio
    async def test_analyze_code_workflow(self):
        """Test typical code analysis workflow."""
        config = LLMConfig(
            model_name="Qwen/Qwen3-30B",
            temperature=0.1,
        )
        client = VLLMClient(config)

        mock_responses = [
            {
                "choices": [{"message": {"content": "Analysis 1"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
            {
                "choices": [{"message": {"content": "Analysis 2"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 150, "completion_tokens": 75},
            },
        ]

        response_index = [0]

        def get_next_response():
            resp = mock_responses[response_index[0] % len(mock_responses)]
            response_index[0] += 1
            return resp

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_response = MagicMock()
            mock_http_response.json.side_effect = lambda: get_next_response()
            mock_http_response.raise_for_status = MagicMock()
            mock_http_client.post = AsyncMock(return_value=mock_http_response)
            mock_get_client.return_value = mock_http_client

            # Simulate analyzing multiple code pieces
            code_pieces = [
                "func main() { println('hello') }",
                "class User { getName() { return this.name; } }",
            ]

            results = []
            for code in code_pieces:
                response = await client.generate(
                    prompt=f"Analyze this code:\n{code}",
                    system_prompt="You are a code analyst.",
                )
                results.append(response)

            assert len(results) == 2
            assert all(r.text for r in results)

        await client.close()

    @pytest.mark.asyncio
    async def test_batch_analysis_workflow(self):
        """Test batch analysis workflow."""
        client = VLLMClient()

        mock_response = {
            "choices": [{"message": {"content": "Batch response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 25},
        }

        with patch.object(client, "generate") as mock_generate:
            mock_generate.return_value = LLMResponse(
                text="Batch response",
                input_tokens=50,
                output_tokens=25,
            )

            processor = BatchProcessor(client, batch_size=5)

            functions = [
                {"name": "func1", "code": "..."},
                {"name": "func2", "code": "..."},
                {"name": "func3", "code": "..."},
            ]

            results = await processor.process_items(
                functions,
                lambda f: f"Analyze function {f['name']}:\n{f['code']}",
                system_prompt="Analyze the function.",
            )

            assert len(results) == 3
            assert mock_generate.call_count == 3

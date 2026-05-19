"""Testes do OllamaClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from miner_harness.connectors.ollama.client import (
    ChatMessage,
    ChatResponse,
    OllamaClient,
)
from miner_harness.core.config import OrchestratorConfig
from miner_harness.core.exceptions import InferenceError, OllamaNotRunningError


@pytest.fixture()
def fast_config() -> OrchestratorConfig:
    return OrchestratorConfig(ollama_timeout_s=5)


class TestOllamaClient:
    """Testes do cliente Ollama."""

    async def test_health_ok(self, fast_config: OrchestratorConfig) -> None:
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            200,
            text="Ollama is running",
            request=httpx.Request("GET", "http://localhost:11434/"),
        )
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            assert await client.health() is True
        await client.close()

    async def test_health_down(self, fast_config: OrchestratorConfig) -> None:
        client = OllamaClient(fast_config)
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("refused")
            assert await client.health() is False
        await client.close()

    async def test_chat_success(self, fast_config: OrchestratorConfig) -> None:
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Analysis result"},
                "model": "qwen3:8b",
                "total_duration": 5000000000,
                "prompt_eval_count": 100,
                "eval_count": 50,
            },
            request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        )
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            messages = [
                ChatMessage(role="system", content="You are a geologist."),
                ChatMessage(role="user", content="Analyze this region."),
            ]
            result = await client.chat("qwen3:8b", messages)
            assert isinstance(result, ChatResponse)
            assert result.content == "Analysis result"
            assert result.eval_count == 50
        await client.close()

    async def test_generate_success(self, fast_config: OrchestratorConfig) -> None:
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            200,
            json={"response": "Generated text here"},
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
        )
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.generate("qwen3:8b", "Hello")
            assert result == "Generated text here"
        await client.close()

    async def test_embeddings_success(self, fast_config: OrchestratorConfig) -> None:
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2, 0.3]]},
            request=httpx.Request("POST", "http://localhost:11434/api/embed"),
        )
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.embeddings("nomic-embed-text", "test text")
            assert result == [0.1, 0.2, 0.3]
        await client.close()

    async def test_list_models(self, fast_config: OrchestratorConfig) -> None:
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3:8b", "size": 5000000000},
                    {"name": "nomic-embed-text", "size": 270000000},
                ]
            },
            request=httpx.Request("GET", "http://localhost:11434/api/tags"),
        )
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            models = await client.list_models()
            assert len(models) == 2
            assert models[0].name == "qwen3:8b"
        await client.close()

    async def test_connection_error_raises(self, fast_config: OrchestratorConfig) -> None:
        client = OllamaClient(fast_config)
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("refused")
            with pytest.raises(OllamaNotRunningError):
                await client.generate("qwen3:8b", "test")
        await client.close()

    async def test_inference_error_on_400(self, fast_config: OrchestratorConfig) -> None:
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            400,
            text="model not found",
            request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        )
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            with pytest.raises(InferenceError):
                await client.chat("bad_model", [ChatMessage(role="user", content="hi")])
        await client.close()

    async def test_context_manager(self, fast_config: OrchestratorConfig) -> None:
        async with OllamaClient(fast_config) as client:
            assert client is not None

    async def test_generate_with_system_prompt(self, fast_config: OrchestratorConfig) -> None:
        """generate() com system inclui payload system (linha 152)."""
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            200,
            json={"response": "text"},
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
        )
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.generate("qwen3:8b", "Hello", system="Be concise")
            assert result == "text"
            assert mock_post.call_args.kwargs["json"]["system"] == "Be concise"
        await client.close()

    async def test_embeddings_empty_response_returns_empty(
        self, fast_config: OrchestratorConfig
    ) -> None:
        """Embeddings vazio retorna lista vazia (linha 175)."""
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            200,
            json={"embeddings": [[]]},
            request=httpx.Request("POST", "http://localhost:11434/api/embed"),
        )
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.embeddings("nomic-embed-text", "test")
            assert result == []
        await client.close()

    async def test_list_models_connect_error_raises(self, fast_config: OrchestratorConfig) -> None:
        """ConnectError em list_models levanta OllamaNotRunningError (linhas 193-194)."""
        client = OllamaClient(fast_config)
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("refused")
            with pytest.raises(OllamaNotRunningError):
                await client.list_models()
        await client.close()

    async def test_pull_model_success(self, fast_config: OrchestratorConfig) -> None:
        """pull_model() completa sem erro (linhas 208-209)."""
        client = OllamaClient(fast_config)
        mock_response = httpx.Response(
            200,
            json={},
            request=httpx.Request("POST", "http://localhost:11434/api/pull"),
        )
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            await client.pull_model("qwen3:8b")
        await client.close()

    async def test_timeout_raises_inference_error(self, fast_config: OrchestratorConfig) -> None:
        """TimeoutException em _post levanta InferenceError (linha 239)."""
        client = OllamaClient(fast_config)
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("timeout")
            with pytest.raises(InferenceError):
                await client.generate("qwen3:8b", "test")
        await client.close()

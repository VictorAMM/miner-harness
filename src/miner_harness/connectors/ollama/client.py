"""OllamaClient — cliente async para a API REST do Ollama.

Provê interface tipada para chat, generate, embeddings e
operações administrativas (health, list_models, pull).

Ref: RFC-002 §5.1
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from pydantic import BaseModel

from miner_harness.core.config import OrchestratorConfig
from miner_harness.core.exceptions import (
    InferenceError,
    OllamaNotRunningError,
)

logger = structlog.get_logger(__name__)


class ChatMessage(BaseModel):
    """Mensagem de chat para o LLM."""

    role: str  # "system", "user", "assistant"
    content: str


class ChatResponse(BaseModel):
    """Resposta de uma chamada de chat."""

    content: str
    model: str
    total_duration_ns: int = 0
    prompt_eval_count: int = 0
    eval_count: int = 0  # Tokens gerados


class ModelInfo(BaseModel):
    """Informações de um modelo disponível no Ollama."""

    name: str
    size: int = 0  # bytes
    modified_at: str = ""


class OllamaClient:
    """Cliente async para a API REST local do Ollama.

    Usage:
        client = OllamaClient()
        if await client.health():
            response = await client.chat("qwen3:8b", messages)
    """

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        self._config = config or OrchestratorConfig()
        self._base_url = self._config.ollama_base_url
        self._timeout = self._config.ollama_timeout_s
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init do httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def health(self) -> bool:
        """Verifica se o Ollama está rodando e acessível."""
        try:
            client = await self._get_client()
            response = await client.get("/")
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Chama o endpoint /api/chat do Ollama.

        Args:
            model: Nome do modelo (ex: "qwen3:8b").
            messages: Lista de mensagens de chat.
            temperature: Temperatura de geração. None = config default.
            max_tokens: Máximo de tokens. None = config default.

        Returns:
            Resposta estruturada do LLM.

        Raises:
            OllamaNotRunningError: Ollama não está acessível.
            InferenceError: Erro durante inferência.
        """
        temp = temperature if temperature is not None else self._config.temperature
        tokens = max_tokens if max_tokens is not None else self._config.max_tokens_per_step

        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": False,
            "options": {
                "temperature": temp,
                "num_predict": tokens,
            },
        }

        data = await self._post("/api/chat", payload)
        message = data.get("message", {})

        return ChatResponse(
            content=message.get("content", ""),
            model=data.get("model", model),
            total_duration_ns=data.get("total_duration", 0),
            prompt_eval_count=data.get("prompt_eval_count", 0),
            eval_count=data.get("eval_count", 0),
        )

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
    ) -> str:
        """Chama o endpoint /api/generate do Ollama.

        Args:
            model: Nome do modelo.
            prompt: Prompt do usuário.
            system: System prompt opcional.

        Returns:
            Texto gerado.
        """
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system is not None:
            payload["system"] = system

        data = await self._post("/api/generate", payload)
        return str(data.get("response", ""))

    async def embeddings(self, model: str, text: str) -> list[float]:
        """Gera embedding de um texto via /api/embed.

        Args:
            model: Modelo de embedding (ex: "nomic-embed-text").
            text: Texto a embutir.

        Returns:
            Vetor de embedding.
        """
        payload: dict[str, Any] = {
            "model": model,
            "input": text,
        }
        data = await self._post("/api/embed", payload)
        embeddings = data.get("embeddings", [[]])
        if embeddings and len(embeddings) > 0:
            return list(embeddings[0])
        return []

    async def list_models(self) -> list[ModelInfo]:
        """Lista modelos disponíveis no Ollama."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            return [
                ModelInfo(
                    name=m.get("name", ""),
                    size=m.get("size", 0),
                    modified_at=m.get("modified_at", ""),
                )
                for m in models
            ]
        except httpx.ConnectError as exc:
            raise OllamaNotRunningError(
                f"Cannot connect to Ollama at {self._base_url}: {exc}"
            ) from exc

    async def pull_model(self, name: str) -> None:
        """Inicia download de um modelo no Ollama.

        Args:
            name: Nome do modelo (ex: "qwen3:8b").

        Raises:
            OllamaNotRunningError: Ollama não está acessível.
            InferenceError: Erro durante o pull.
        """
        await self._post("/api/pull", {"name": name, "stream": False})
        logger.info("model_pulled", model=name)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST genérico com error handling."""
        try:
            client = await self._get_client()
            response = await client.post(path, json=payload)

            if response.status_code >= 400:
                error_text = response.text[:200]
                raise InferenceError(
                    f"Ollama error on {path}: [{response.status_code}] {error_text}"
                )

            result: dict[str, Any] = response.json()

            logger.debug(
                "ollama_request",
                path=path,
                model=payload.get("model", "unknown"),
                status=response.status_code,
            )
            return result

        except httpx.ConnectError as exc:
            raise OllamaNotRunningError(
                f"Cannot connect to Ollama at {self._base_url}: {exc}"
            ) from exc

        except httpx.TimeoutException as exc:
            raise InferenceError(f"Ollama timeout on {path} after {self._timeout}s") from exc

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> OllamaClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

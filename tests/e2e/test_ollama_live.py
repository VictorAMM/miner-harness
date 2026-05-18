"""Testes e2e — Ollama local.

Verifica que o Ollama está rodando, tem modelos disponíveis e
responde a prompts simples dentro do tempo esperado.

Executar com: MINER_E2E=1 uv run pytest tests/e2e/test_ollama_live.py -v
"""

from __future__ import annotations

import pytest

from miner_harness.connectors.ollama.client import ChatMessage, OllamaClient
from miner_harness.core.config import OrchestratorConfig

from .conftest import skip_no_ollama

# ---------------------------------------------------------------------------
# Conectividade
# ---------------------------------------------------------------------------


@skip_no_ollama
@pytest.mark.asyncio
async def test_ollama_health(ollama_url: str) -> None:
    """Ollama responde ao health check."""
    config = OrchestratorConfig(ollama_base_url=ollama_url)
    client = OllamaClient(config)
    try:
        ok = await client.health()
        assert ok, "Ollama health check retornou False"
    finally:
        await client.close()


@skip_no_ollama
@pytest.mark.asyncio
async def test_ollama_list_models(ollama_url: str) -> None:
    """Ollama tem pelo menos um modelo disponível."""
    config = OrchestratorConfig(ollama_base_url=ollama_url)
    client = OllamaClient(config)
    try:
        models = await client.list_models()
        assert len(models) > 0, (
            "Nenhum modelo encontrado no Ollama. Execute: ollama pull qwen3:8b"
        )
    finally:
        await client.close()


@skip_no_ollama
@pytest.mark.asyncio
async def test_ollama_model_available(ollama_url: str, ollama_model: str) -> None:
    """Modelo configurado está disponível no Ollama."""
    config = OrchestratorConfig(ollama_base_url=ollama_url)
    client = OllamaClient(config)
    try:
        models = await client.list_models()
        names = [m.name for m in models]
        # Aceita match parcial (ex: "qwen3:8b" bate com "qwen3:8b:latest")
        found = any(ollama_model in name or name in ollama_model for name in names)
        assert found, f"Modelo '{ollama_model}' não encontrado. Modelos disponíveis: {names}"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Inferência básica
# ---------------------------------------------------------------------------


@skip_no_ollama
@pytest.mark.asyncio
async def test_ollama_chat_responde(ollama_url: str, ollama_model: str) -> None:
    """Modelo responde a um prompt simples e não retorna string vazia."""
    config = OrchestratorConfig(
        ollama_base_url=ollama_url,
        model=ollama_model,
        ollama_timeout_s=60,
    )
    client = OllamaClient(config)
    try:
        messages = [
            ChatMessage(role="user", content="Diga apenas 'ok' em resposta a esta mensagem."),
        ]
        response = await client.chat(ollama_model, messages)
        assert response.content.strip() != "", "Modelo retornou resposta vazia"
        assert response.model != ""
        assert response.eval_count > 0
    finally:
        await client.close()


@skip_no_ollama
@pytest.mark.asyncio
async def test_ollama_chat_geologico(ollama_url: str, ollama_model: str) -> None:
    """Modelo responde a um prompt geológico com conteúdo relevante."""
    config = OrchestratorConfig(
        ollama_base_url=ollama_url,
        model=ollama_model,
        ollama_timeout_s=120,
    )
    client = OllamaClient(config)
    try:
        messages = [
            ChatMessage(
                role="system",
                content="Você é um geólogo especialista. Responda de forma concisa.",
            ),
            ChatMessage(
                role="user",
                content=(
                    "Qual o principal minério da região de Carajás no Pará, Brasil? "
                    "Responda em uma frase."
                ),
            ),
        ]
        response = await client.chat(ollama_model, messages)
        content_lower = response.content.lower()
        # Deve mencionar ferro, minério de ferro, hematita ou magnetita
        has_relevant = any(
            kw in content_lower
            for kw in ["ferro", "hematita", "magnetita", "iron", "carajás", "carajas"]
        )
        assert has_relevant, (
            f"Resposta geológica não menciona ferro/Carajás: {response.content[:300]}"
        )
    finally:
        await client.close()

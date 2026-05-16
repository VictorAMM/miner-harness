"""Exceções de domínio do miner-harness.

Hierarquia de exceções organizada por subsistema.
Todas herdam de MinerHarnessError para facilitar catch genérico.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class MinerHarnessError(Exception):
    """Exceção base de todas as exceções do miner-harness."""


# ---------------------------------------------------------------------------
# GeoSGB Connector (RFC-001)
# ---------------------------------------------------------------------------


class GeoSGBError(MinerHarnessError):
    """Erro genérico do connector GeoSGB."""


class GeoSGBConnectionError(GeoSGBError):
    """Falha de conexão com a API do GeoSGB."""


class GeoSGBQueryError(GeoSGBError):
    """Erro ao executar query (ex: FeatureServer retornou 400)."""

    def __init__(self, service: str, error_code: int, message: str) -> None:
        self.service = service
        self.error_code = error_code
        super().__init__(f"GeoSGB query error on {service}: [{error_code}] {message}")


class GeoSGBRateLimitError(GeoSGBError):
    """Rate limiting detectado na API."""


class GeoSGBTimeoutError(GeoSGBError):
    """Timeout na comunicação com a API."""


# ---------------------------------------------------------------------------
# LLM Engine (RFC-002)
# ---------------------------------------------------------------------------


class LLMError(MinerHarnessError):
    """Erro genérico do LLM Engine."""


class OllamaNotRunningError(LLMError):
    """Ollama não está rodando ou não está acessível."""


class ModelNotAvailableError(LLMError):
    """Modelo LLM solicitado não está baixado."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"Model '{model}' not available. Run: ollama pull {model}")


class InferenceError(LLMError):
    """Erro durante inferência do LLM."""


class ResponseParseError(LLMError):
    """Resposta do LLM não pôde ser parseada no formato esperado."""


# ---------------------------------------------------------------------------
# Agents (RFC-002)
# ---------------------------------------------------------------------------


class AgentError(MinerHarnessError):
    """Erro genérico de um agente."""


class InsufficientDataError(AgentError):
    """Dados insuficientes para o agente realizar análise."""

    def __init__(self, agent: str, missing: list[str]) -> None:
        self.agent = agent
        self.missing = missing
        super().__init__(f"Agent '{agent}' has insufficient data. Missing: {', '.join(missing)}")


class EvaluationFailedError(AgentError):
    """Evaluator-Optimizer rejeitou o resultado de um agente."""


# ---------------------------------------------------------------------------
# Cache / Storage (RFC-003)
# ---------------------------------------------------------------------------


class StorageError(MinerHarnessError):
    """Erro genérico de storage."""


class CacheCorruptedError(StorageError):
    """Cache SQLite corrompido ou schema incompatível."""


class IndexError(StorageError):
    """Erro no índice vetorial."""


class EmbeddingError(StorageError):
    """Erro ao gerar embeddings."""

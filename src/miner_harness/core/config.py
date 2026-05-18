"""Configuração centralizada do miner-harness.

Usa Pydantic Settings para carregar configuração de:
1. Valores default (definidos aqui)
2. Arquivo config.toml em MINER_HOME
3. Variáveis de ambiente (prefixo MINER_)

Refs: RFC-002 §10, RFC-003 §5
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from miner_harness.core.types import AnalysisStep

# ---------------------------------------------------------------------------
# Storage (RFC-003 §5)
# ---------------------------------------------------------------------------


class StorageConfig(BaseModel):
    """Configuração do subsistema de storage local."""

    miner_home: Path = Field(
        default_factory=lambda: Path.home() / ".miner-harness",
        description="Diretório raiz do miner-harness",
    )
    max_cache_size_gb: float = 5.0
    auto_evict: bool = True
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    max_index_size: int = 100_000
    default_srid: int = 4326
    log_level: str = "INFO"
    log_max_size_mb: int = 50
    log_rotation: int = 5

    @property
    def cache_dir(self) -> Path:
        """Diretório de cache."""
        return self.miner_home / "cache"

    @property
    def regions_dir(self) -> Path:
        """Diretório de GeoPackages regionais."""
        return self.miner_home / "cache" / "regions"

    @property
    def index_dir(self) -> Path:
        """Diretório do índice vetorial."""
        return self.miner_home / "index"

    @property
    def exports_dir(self) -> Path:
        """Diretório de relatórios exportados."""
        return self.miner_home / "exports"

    @property
    def logs_dir(self) -> Path:
        """Diretório de logs."""
        return self.miner_home / "logs"

    def ensure_dirs(self) -> None:
        """Cria diretórios necessários se não existirem."""
        for d in [
            self.miner_home,
            self.cache_dir,
            self.regions_dir,
            self.index_dir,
            self.exports_dir,
            self.exports_dir / "reports",
            self.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Orchestrator (RFC-002 §10)
# ---------------------------------------------------------------------------


class OrchestratorConfig(BaseModel):
    """Configuração do orquestrador de agentes."""

    model: str = "qwen3:8b-q4_K_M"
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens_per_step: int = 4096
    max_data_records_per_prompt: int = 50
    max_data_chars_per_prompt: int = 8000
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_s: int = 120
    enabled_steps: list[AnalysisStep] = Field(
        default_factory=lambda: list(AnalysisStep),
    )


# ---------------------------------------------------------------------------
# GeoSGB Connector (RFC-001 §6)
# ---------------------------------------------------------------------------


class GeoSGBConfig(BaseModel):
    """Configuração do connector GeoSGB."""

    base_url: str = "https://geoportal.sgb.gov.br/server/rest/services"
    min_delay_ms: int = 500
    max_concurrent: int = 3
    max_retries: int = 3
    backoff_factor: float = 2.0
    timeout_s: int = 90


# ---------------------------------------------------------------------------
# Config raiz
# ---------------------------------------------------------------------------


class MinerHarnessConfig(BaseModel):
    """Configuração raiz do miner-harness."""

    storage: StorageConfig = Field(default_factory=StorageConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    geosgb: GeoSGBConfig = Field(default_factory=GeoSGBConfig)

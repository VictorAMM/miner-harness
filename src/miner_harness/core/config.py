"""Configuração centralizada do miner-harness.

Usa Pydantic Settings para carregar configuração de:
1. Valores default (definidos aqui)
2. Arquivo config.toml em MINER_HOME
3. Variáveis de ambiente (prefixo MINER_)

Refs: RFC-002 §10, RFC-003 §5
"""

from __future__ import annotations

import math
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

    model: str = "qwen3:8b"
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens_per_step: int = 4096
    max_data_records_per_prompt: int = 50
    max_data_chars_per_prompt: int = 8000
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_s: int = 120
    num_ctx: int = Field(
        default=4096,
        ge=512,
        description="Janela de contexto do LLM em tokens. Use KV cache Q4 para ctx ≥ 32k.",
    )
    enabled_steps: list[AnalysisStep] = Field(
        default_factory=lambda: list(AnalysisStep),
    )
    use_rag: bool = True
    min_data_sources: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Mínimo de fontes de dados ativas para prosseguir com a análise (RFC-002 §6)",
    )

    @property
    def _ctx_scale(self) -> float:
        """Fator de escala √(num_ctx / 4096) — cresce suavemente com o contexto."""
        return math.sqrt(max(self.num_ctx, 1) / 4096)

    @property
    def effective_max_records(self) -> int:
        """Máximo de registros por dataset no prompt, escalado com num_ctx."""
        return min(int(self.max_data_records_per_prompt * self._ctx_scale), 500)

    @property
    def effective_max_chars(self) -> int:
        """Máximo de chars por dataset no prompt, escalado com num_ctx."""
        return min(int(self.max_data_chars_per_prompt * self._ctx_scale), 40_000)

    @property
    def effective_max_prev_chars(self) -> int:
        """Máximo de chars para resumo de resultados anteriores, escalado com num_ctx."""
        return min(int(2000 * self._ctx_scale), 8_000)


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
# ANM SIGMINE Connector
# ---------------------------------------------------------------------------


class ANMConfig(BaseModel):
    """Configuração do conector ANM/SIGMINE."""

    enabled: bool = True
    base_url: str = "https://app.anm.gov.br/sigmine_opc/ows"
    timeout_s: int = 60
    max_features: int = 500


# ---------------------------------------------------------------------------
# USGS Earthquake Connector
# ---------------------------------------------------------------------------


class USGSConfig(BaseModel):
    """Configuração do conector USGS Earthquake Hazards."""

    enabled: bool = True
    base_url: str = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    timeout_s: int = 30
    min_magnitude: float = 2.0
    max_events: int = 100


# ---------------------------------------------------------------------------
# Copernicus Data Space Ecosystem (Sentinel-2)
# ---------------------------------------------------------------------------


class CopernicusConfig(BaseModel):
    """Configuração do conector Sentinel-2 via CDSE Statistics API.

    Credenciais obtidas em https://dataspace.copernicus.eu/ (registro gratuito).
    Defina via env: MINER_COPERNICUS__CLIENT_ID e MINER_COPERNICUS__CLIENT_SECRET.
    """

    enabled: bool = True
    client_id: str = ""
    client_secret: str = ""
    max_cloud_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    days_back: int = Field(default=90, ge=1, le=365)
    timeout_s: int = 60
    ttl_days: int = 30


# ---------------------------------------------------------------------------
# ML — RandomForest de prospectividade (PRD-002 F8)
# ---------------------------------------------------------------------------


class MLConfig(BaseModel):
    """Configuração do modelo de Machine Learning de prospectividade.

    Por padrão usa o modelo pré-treinado incluído no pacote.
    Defina model_path para substituir por um modelo treinado com dados próprios.
    """

    enabled: bool = True
    model_path: str = Field(
        default="",
        description=(
            "Caminho para modelo .joblib alternativo. "
            "Vazio = usa rf_prospectivity_v1.joblib incluído no pacote."
        ),
    )


# ---------------------------------------------------------------------------
# Config raiz
# ---------------------------------------------------------------------------


class MinerHarnessConfig(BaseModel):
    """Configuração raiz do miner-harness."""

    storage: StorageConfig = Field(default_factory=StorageConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    geosgb: GeoSGBConfig = Field(default_factory=GeoSGBConfig)
    anm: ANMConfig = Field(default_factory=ANMConfig)
    usgs: USGSConfig = Field(default_factory=USGSConfig)
    copernicus: CopernicusConfig = Field(default_factory=CopernicusConfig)
    ml: MLConfig = Field(default_factory=MLConfig)

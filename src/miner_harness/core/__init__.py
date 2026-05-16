"""Core — tipos compartilhados, configuração e exceções do domínio."""

from miner_harness.core.config import (
    GeoSGBConfig,
    MinerHarnessConfig,
    OrchestratorConfig,
    StorageConfig,
)
from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    Coordenada,
    MineralTarget,
    ProspectionReport,
    StepResult,
)

__all__ = [
    "AnalysisStep",
    "BoundingBox",
    "Confidence",
    "Coordenada",
    "GeoSGBConfig",
    "MineralTarget",
    "MinerHarnessConfig",
    "OrchestratorConfig",
    "ProspectionReport",
    "StepResult",
    "StorageConfig",
]

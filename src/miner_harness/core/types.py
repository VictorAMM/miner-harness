"""Tipos de domínio compartilhados pelo miner-harness.

Define os modelos Pydantic centrais: coordenadas, bounding boxes,
features geológicas e resultados de análise. Todos os módulos
importam daqui — nunca definem tipos de domínio localmente.

Refs: RFC-001 §4.1, RFC-002 §4.1, RFC-003 §3.1
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime  # noqa: TCH003
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# StrEnum: use stdlib on 3.11+, fallback for older runtimes (dev/CI only)
if sys.version_info >= (3, 11):  # noqa: UP036
    from enum import StrEnum  # noqa: F811
else:  # pragma: no cover

    class StrEnum(str, Enum):  # noqa: UP042
        """Compatibility shim — project requires 3.11+ but CI sandbox may differ."""


# ---------------------------------------------------------------------------
# Geoespacial
# ---------------------------------------------------------------------------


class Coordenada(BaseModel):
    """Coordenada geográfica WGS84."""

    longitude: float = Field(ge=-74, le=-29, description="Longitude (limites do Brasil)")
    latitude: float = Field(ge=-34, le=6, description="Latitude (limites do Brasil)")
    datum: str = "WGS84"


class BoundingBox(BaseModel):
    """Retângulo envolvente para consultas espaciais."""

    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    srid: int = 4326

    @model_validator(mode="after")
    def _check_coordinate_order(self) -> BoundingBox:
        if self.lon_min >= self.lon_max:
            raise ValueError(f"lon_min ({self.lon_min}) deve ser < lon_max ({self.lon_max})")
        if self.lat_min >= self.lat_max:
            raise ValueError(f"lat_min ({self.lat_min}) deve ser < lat_max ({self.lat_max})")
        return self

    @property
    def width(self) -> float:
        """Largura em graus."""
        return self.lon_max - self.lon_min

    @property
    def height(self) -> float:
        """Altura em graus."""
        return self.lat_max - self.lat_min

    @property
    def center(self) -> tuple[float, float]:
        """Centro (lon, lat) do bbox."""
        return (
            (self.lon_min + self.lon_max) / 2,
            (self.lat_min + self.lat_max) / 2,
        )

    def hash(self) -> str:
        """Hash determinístico do bbox (normalizado a 6 casas decimais)."""
        normalized = f"{self.lon_min:.6f},{self.lat_min:.6f},{self.lon_max:.6f},{self.lat_max:.6f}"
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def contains_point(self, lon: float, lat: float) -> bool:
        """Verifica se um ponto está dentro do bbox."""
        return self.lon_min <= lon <= self.lon_max and self.lat_min <= lat <= self.lat_max

    def as_tuple(self) -> tuple[float, float, float, float]:
        """Retorna como (lon_min, lat_min, lon_max, lat_max)."""
        return (self.lon_min, self.lat_min, self.lon_max, self.lat_max)


# ---------------------------------------------------------------------------
# GeoSGB — Modelos de dados (RFC-001 §4.1)
# ---------------------------------------------------------------------------


class OcorrenciaMineral(BaseModel):
    """Ocorrência mineral do GeoSGB (36 campos, principais mapeados)."""

    objectid: int
    substancias: str = Field(description='Ex: "Cobre, Ouro"')
    municipio: str
    uf: str = Field(max_length=2, description='Ex: "PA"')
    provincia: str | None = Field(default=None, description="Província mineral")
    status_economico: str | None = None
    importancia: str | None = None
    rochas_hospedeiras: str | None = None
    rochas_encaixantes: str | None = None
    tipos_alteracao: str | None = None
    morfologia: str | None = None
    texturas: str | None = None
    coordenada: Coordenada


class DadoGravimetrico(BaseModel):
    """Dado gravimétrico — único endpoint com FeatureServer/query funcional."""

    objectid: int
    coordenada: Coordenada
    altitude_ortometrica: float
    gravidade: float
    anomalia_ar_livre: float
    anomalia_bouguer: float


class AmostraGeoquimica(BaseModel):
    """Amostra geoquímica — 9 layers, 51 campos."""

    objectid: int
    projeto: str
    classe: str = Field(description='Ex: "Sedimento de Corrente", "Rocha"')
    material_coletado: str | None = None
    rocha_matriz: str | None = None
    coordenada: Coordenada
    analises: dict[str, float | str | None] = Field(
        default_factory=dict,
        description="Campos analíticos variáveis por layer",
    )


class DatacaoGeocronologica(BaseModel):
    """Datação geocronológica — idade de rochas e eventos."""

    objectid: int
    metodo: str | None = Field(default=None, description='Ex: "U-Pb", "Ar-Ar"')
    idade_ma: float | None = Field(default=None, description="Idade em milhões de anos")
    erro_ma: float | None = None
    material: str | None = None
    unidade_geologica: str | None = None
    coordenada: Coordenada


class UnidadeLitoestratigrafica(BaseModel):
    """Unidade litoestratigráfica — polígonos de formações geológicas."""

    objectid: int
    sigla: str | None = None
    nome: str | None = None
    hierarquia: str | None = Field(default=None, description='Ex: "Formação", "Grupo"')
    litologia_principal: str | None = None
    idade: str | None = None
    coordenada: Coordenada | None = None


class ProjetoAerogeofisico(BaseModel):
    """Projeto aerogeofísico — metadados de levantamentos."""

    objectid: int
    nome_projeto: str | None = None
    ano: int | None = None
    tipo_levantamento: str | None = Field(
        default=None, description='Ex: "Magnetometria", "Gamaespectrometria"'
    )
    area_km2: float | None = None
    coordenada: Coordenada


# ---------------------------------------------------------------------------
# ANM SIGMINE — Concessões minerárias
# ---------------------------------------------------------------------------


class ConcessaoMineira(BaseModel):
    """Concessão minerária do ANM/SIGMINE."""

    objectid: int
    processo: str | None = Field(default=None, description='Ex: "860384/2007"')
    fase: str | None = Field(
        default=None,
        description='Ex: "Concessão de Lavra", "Autorização de Pesquisa"',
    )
    nome_titular: str | None = None
    substancias: str | None = Field(default=None, description='Ex: "FERRO, MANGANÊS"')
    uf: str | None = Field(default=None, max_length=2)
    area_ha: float | None = Field(default=None, description="Área em hectares")
    ano: int | None = None
    coordenada: Coordenada


# ---------------------------------------------------------------------------
# USGS — Eventos sísmicos
# ---------------------------------------------------------------------------


class EventoSismico(BaseModel):
    """Evento sísmico do catálogo USGS Earthquake Hazards."""

    objectid: int
    magnitude: float = Field(description="Magnitude Richter/Mw")
    profundidade_km: float = Field(description="Profundidade do foco em km")
    lugar: str | None = Field(default=None, description="Descrição geográfica do evento")
    timestamp_ms: int = Field(description="Tempo do evento em ms desde epoch Unix")
    coordenada: Coordenada


# ---------------------------------------------------------------------------
# Análise — Modelos de resultado (RFC-002 §4.1)
# ---------------------------------------------------------------------------


class AnalysisStep(StrEnum):
    """Passos do framework analítico Dr. Augusto Valen."""

    TECTONIC_HISTORY = "tectonic_history"
    STRUCTURAL_ARCHITECTURE = "structural_architecture"
    MAGMATIC_FERTILITY = "magmatic_fertility"
    INDIRECT_EVIDENCE = "indirect_evidence"
    TOTAL_INTEGRATION = "total_integration"


class Confidence(StrEnum):
    """Nível de confiança de uma análise."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class StepResult(BaseModel):
    """Resultado de um passo individual da análise."""

    step: AnalysisStep
    agent: str
    summary: str
    findings: list[str]
    confidence: Confidence
    data_sources_used: list[str]
    data_gaps: list[str]
    raw_reasoning: str
    duration_ms: int
    targets: list[MineralTarget] = Field(default_factory=list)


class MineralTarget(BaseModel):
    """Alvo de prospecção mineral identificado."""

    name: str
    longitude: float
    latitude: float
    radius_km: float
    commodities: list[str]
    mineral_system: str = Field(description='Ex: "IOCG", "Ouro Orogênico"')
    confidence: Confidence
    priority: int = Field(ge=1, le=5, description="1=máxima, 5=mínima")
    rationale: str
    recommended_followup: list[str]

    @model_validator(mode="before")
    @classmethod
    def _normalize_field_aliases(cls, data: Any) -> Any:
        """Normaliza variantes de nomes de campos retornadas pelo LLM.

        O LLM às vezes retorna 'mineralization_system' ou 'system' em vez de
        'mineral_system'. Este validator copia o valor para o nome canônico
        antes da validação Pydantic, evitando descartar alvos válidos.
        """
        if not isinstance(data, dict):
            return data
        # Variantes conhecidas de mineral_system
        if "mineral_system" not in data or not data["mineral_system"]:
            for alias in ("mineralization_system", "mineralization_type", "system", "tipo_sistema"):
                if alias in data and data[alias]:
                    data = dict(data)
                    data["mineral_system"] = data[alias]
                    break
        return data


class ProspectionReport(BaseModel):
    """Relatório final de prospecção mineral."""

    region_name: str
    bbox: BoundingBox
    analysis_date: datetime
    steps: list[StepResult]
    targets: list[MineralTarget]
    integrated_summary: str
    caveats: list[str]
    data_quality_score: float = Field(ge=0, le=1)
    total_duration_ms: int
    model_used: str
    missing_sources: list[str] = Field(
        default_factory=list,
        description="Fontes de dados que não retornaram registros para esta análise",
    )
    geological_data: dict[str, list[dict[str, Any]]] | None = Field(
        default=None,
        description="Dados brutos usados na análise (opcional, para visualização no dashboard)",
    )

"""Registry de serviços e endpoints do GeoSGB.

Define URLs, layers e configurações de cada serviço
do geoportal do Serviço Geológico do Brasil.

Ref: RFC-001 §2, Discovery Report (Fase 1)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Base URL do ArcGIS Server do GeoSGB
BASE_URL = "https://geoportal.sgb.gov.br/server/rest/services"


@dataclass(frozen=True)
class ServiceEndpoint:
    """Definição de um endpoint do GeoSGB."""

    name: str
    path: str
    server_type: str  # "MapServer" ou "FeatureServer"
    default_layers: list[int] = field(default_factory=list)
    supports_query: bool = False

    @property
    def url(self) -> str:
        """URL completa do serviço."""
        return f"{BASE_URL}/{self.path}/{self.server_type}"

    @property
    def identify_url(self) -> str:
        """URL do endpoint identify (MapServer apenas)."""
        if self.server_type != "MapServer":
            msg = f"identify not available on {self.server_type}"
            raise ValueError(msg)
        return f"{self.url}/identify"

    def query_url(self, layer: int) -> str:
        """URL do endpoint query para uma layer específica."""
        return f"{self.url}/{layer}/query"


# ---------------------------------------------------------------------------
# Serviços — caminhos verificados via catalog REST em 2026-05-17
# Todos migrados para FeatureServer (mais estável que MapServer/identify)
# ---------------------------------------------------------------------------

OCORRENCIAS = ServiceEndpoint(
    name="ocorrencias",
    path="geologia/ocorrencias",
    server_type="FeatureServer",
    default_layers=[0],  # "Ocorrências minerais"
    supports_query=True,
)

GRAVIMETRIA = ServiceEndpoint(
    name="gravimetria",
    path="geofisica/gravimetria",
    server_type="FeatureServer",
    default_layers=[0],  # "Dados gravimétricos"
    supports_query=True,
)

# Layers relevantes para prospecção mineral:
# 2=Sedimento de Corrente, 4=Rocha, 5=Solo
GEOQUIMICA = ServiceEndpoint(
    name="geoquimica",
    path="geoquimica/geoquimica_integrada",
    server_type="FeatureServer",
    default_layers=[2, 4, 5],
    supports_query=True,
)

GEOCRONOLOGIA = ServiceEndpoint(
    name="geocronologia",
    path="geologia/geocronologia",
    server_type="FeatureServer",
    default_layers=[0],  # "Datações geocronológicas"
    supports_query=True,
)

# Escala 1:1.000.000 — adequada para análise regional de prospecção
LITOESTRATIGRAFIA = ServiceEndpoint(
    name="litoestratigrafia",
    path="geologia/litoestratigrafia_1000000",
    server_type="FeatureServer",
    default_layers=[0],  # "Unidades litoestratigráficas - 1:1.000.000 [2004]"
    supports_query=True,
)

# 4 séries históricas de levantamentos aerogeofísicos
AEROGEOFISICA = ServiceEndpoint(
    name="aerogeofisica",
    path="geofisica/aerogeofisica",
    server_type="FeatureServer",
    default_layers=[0, 1, 2, 3],
    supports_query=True,
)

# Furos de sondagem históricos — evidência direta de mineralização
# ADR-002: "furos_sondagem: MapServer/identify | MapServer only"
# Tentativa via FeatureServer primeiro; fallback para MapServer/identify no connector.
FUROS_SONDAGEM = ServiceEndpoint(
    name="furos",
    path="geologia/furos_sondagem",
    server_type="FeatureServer",
    default_layers=[0],
    supports_query=True,
)

# Registry indexado por nome
SERVICE_REGISTRY: dict[str, ServiceEndpoint] = {
    ep.name: ep
    for ep in [
        OCORRENCIAS,
        GRAVIMETRIA,
        GEOQUIMICA,
        GEOCRONOLOGIA,
        LITOESTRATIGRAFIA,
        AEROGEOFISICA,
        FUROS_SONDAGEM,
    ]
}

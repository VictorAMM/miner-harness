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
# Serviços conhecidos — descobertos na Fase 1 (Discovery)
# ---------------------------------------------------------------------------

OCORRENCIAS = ServiceEndpoint(
    name="ocorrencias",
    path="GEOSGB/ocorrencias_minerais",
    server_type="MapServer",
    default_layers=[0],
    supports_query=False,
)

GRAVIMETRIA = ServiceEndpoint(
    name="gravimetria",
    path="GEOSGB/dados_gravimetricos",
    server_type="FeatureServer",
    default_layers=[0],
    supports_query=True,  # Único FeatureServer funcional no GeoSGB
)

GEOQUIMICA = ServiceEndpoint(
    name="geoquimica",
    path="GEOSGB/geoquimica",
    server_type="MapServer",
    default_layers=list(range(9)),  # 9 layers (tipos de amostra)
    supports_query=False,
)

GEOCRONOLOGIA = ServiceEndpoint(
    name="geocronologia",
    path="GEOSGB/geocronologia",
    server_type="MapServer",
    default_layers=[0],
    supports_query=False,
)

LITOESTRATIGRAFIA = ServiceEndpoint(
    name="litoestratigrafia",
    path="GEOSGB/unidades_litoestratigraficas",
    server_type="MapServer",
    default_layers=[0],
    supports_query=False,
)

AEROGEOFISICA = ServiceEndpoint(
    name="aerogeofisica",
    path="GEOSGB/projetos_aerogeofisicos",
    server_type="MapServer",
    default_layers=[0],
    supports_query=False,
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
    ]
}

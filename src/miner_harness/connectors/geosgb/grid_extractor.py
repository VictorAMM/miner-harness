"""Extração por grid de pontos via MapServer/identify.

O MapServer/identify retorna features em torno de um ponto.
Para cobrir uma região, geramos um grid de pontos e
consolidamos resultados com deduplicação por objectid.

Ref: RFC-001 §3.1 (Grid adaptativo)
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox

logger = structlog.get_logger(__name__)


class GridDensity(Enum):
    """Densidade do grid de extração."""

    LOW = "low"  # ~5 pontos por grau
    MEDIUM = "medium"  # ~10 pontos por grau — default
    HIGH = "high"  # ~20 pontos por grau

    @property
    def points_per_degree(self) -> float:
        """Pontos por grau de longitude/latitude."""
        return {
            GridDensity.LOW: 2.0,
            GridDensity.MEDIUM: 4.0,
            GridDensity.HIGH: 8.0,
        }[self]

    @property
    def tolerance(self) -> int:
        """Tolerance para MapServer/identify (pixels)."""
        return {
            GridDensity.LOW: 100,
            GridDensity.MEDIUM: 50,
            GridDensity.HIGH: 25,
        }[self]


def generate_grid(
    bbox: BoundingBox,
    density: GridDensity = GridDensity.MEDIUM,
) -> list[tuple[float, float]]:
    """Gera grid regular de pontos sobre um bounding box.

    Args:
        bbox: Bounding box da região.
        density: Densidade do grid.

    Returns:
        Lista de (longitude, latitude) para cada ponto do grid.
    """
    ppd = density.points_per_degree

    # Calcular número de pontos em cada eixo (mínimo 2)
    n_lon = max(2, int(bbox.width * ppd) + 1)
    n_lat = max(2, int(bbox.height * ppd) + 1)

    # Gerar pontos uniformemente distribuídos
    step_lon = bbox.width / (n_lon - 1) if n_lon > 1 else 0
    step_lat = bbox.height / (n_lat - 1) if n_lat > 1 else 0

    points: list[tuple[float, float]] = []
    for i in range(n_lon):
        lon = bbox.lon_min + i * step_lon
        for j in range(n_lat):
            lat = bbox.lat_min + j * step_lat
            points.append((round(lon, 6), round(lat, 6)))

    logger.debug(
        "grid_generated",
        bbox=bbox.as_tuple(),
        density=density.value,
        n_lon=n_lon,
        n_lat=n_lat,
        total_points=len(points),
    )
    return points


def deduplicate_features(
    features: list[dict[str, Any]],
    key: str = "objectid",
) -> list[dict[str, Any]]:
    """Remove features duplicadas por chave.

    MapServer/identify com pontos próximos retorna os mesmos objetos.
    Deduplicar por objectid garante contagem correta.

    Args:
        features: Lista de features brutas (dicts).
        key: Campo usado como chave de deduplicação.

    Returns:
        Lista sem duplicatas, preservando a primeira ocorrência.
    """
    seen: set[int | str] = set()
    unique: list[dict[str, Any]] = []

    for feat in features:
        feat_id = feat.get(key)
        if feat_id is None:
            # Sem chave -> manter (pode ser feature sem objectid)
            unique.append(feat)
            continue
        if feat_id not in seen:
            seen.add(feat_id)
            unique.append(feat)

    removed = len(features) - len(unique)
    if removed > 0:
        logger.debug(
            "features_deduplicated",
            total=len(features),
            unique=len(unique),
            removed=removed,
            key=key,
        )
    return unique


def build_identify_params(
    point: tuple[float, float],
    bbox: BoundingBox,
    layers: list[int] | None = None,
    tolerance: int = 50,
    image_size: tuple[int, int] = (800, 600),
) -> dict[str, str]:
    """Constrói parâmetros para MapServer/identify.

    Args:
        point: (longitude, latitude) do ponto de consulta.
        bbox: Bounding box da região (para mapExtent).
        layers: Lista de layer IDs. None = todas visíveis.
        tolerance: Raio de busca em pixels.
        image_size: Tamanho virtual da imagem (para cálculo de pixel/grau).

    Returns:
        Dict de query parameters para a URL.
    """
    layer_spec = f"visible:{','.join(str(lid) for lid in layers)}" if layers else "all"

    return {
        "f": "json",
        "geometry": f"{point[0]},{point[1]}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": layer_spec,
        "tolerance": str(tolerance),
        "mapExtent": (f"{bbox.lon_min},{bbox.lat_min},{bbox.lon_max},{bbox.lat_max}"),
        "imageDisplay": f"{image_size[0]},{image_size[1]},96",
        "returnGeometry": "true",
        "returnFieldName": "false",
    }

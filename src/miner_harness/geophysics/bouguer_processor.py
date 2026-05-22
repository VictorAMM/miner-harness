"""BouguerProcessor — derivadas gravimétricas a partir de dados pontuais.

Processa medições Bouguer do GeoSGB para produzir derivadas interpretáveis:

  1. Interpolação IDW (Inverse Distance Weighting) dos valores Bouguer
     sobre uma grade de células de ~11 km — sem dependência de rasterio.

  2. Gradiente Horizontal Total (HGM) em mGal/km — identificador de
     contatos litológicos e falhas (máximos de gradiente coincidem com
     bordas de corpos geológicos).

  3. Detecção automática de lineamentos inferidos: células com HGM acima
     de (média + 1σ) são marcadas como candidatos a contato/falha.

O resultado substitui o envio de valores brutos de Bouguer ao agente
GeophysicistAgent, que passa a receber métricas computadas interpretáveis.

Ref: PRD-002 F5 (implementação parcial — derivadas de dados pontuais;
     processamento de grids raster pendente investigação de endpoints SGB)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox

# Raio de busca IDW (graus, ≈55 km) — maior que o prospectivity scorer
# porque levantamentos gravimétricos regionais têm espaçamento de 5–15 km.
_IDW_RADIUS_DEG: float = 0.50

# Resolução da grade (mesma do ProspectivityScorer)
_GRID_STEP: float = 0.10

# Limite de células por dimensão
_MAX_CELLS_PER_DIM: int = 30

# Mínimo de pontos para cálculo confiável do gradiente
_MIN_POINTS_GRADIENT: int = 4


@dataclass
class BouguerCell:
    """Célula da grade gravimétrica."""

    lon: float
    lat: float
    bouguer: float  # valor IDW interpolado (mGal)
    hgm: float  # Horizontal Gradient Magnitude (mGal/km)
    is_lineament: bool  # HGM > limiar de lineamento


@dataclass
class BouguerGrid:
    """Grade de derivadas gravimétricas calculadas para um bbox."""

    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    step_deg: float
    cells: list[BouguerCell]
    n_source_points: int
    bouguer_mean: float
    bouguer_std: float
    hgm_threshold: float  # limiar de detecção de lineamento (mGal/km)

    @property
    def lineament_cells(self) -> list[BouguerCell]:
        return sorted([c for c in self.cells if c.is_lineament], key=lambda c: -c.hgm)

    @property
    def positive_anomaly_cells(self) -> list[BouguerCell]:
        """Células com Bouguer positivo (corpos densos — possíveis intrusivos)."""
        return sorted([c for c in self.cells if c.bouguer > 0], key=lambda c: -c.bouguer)

    @property
    def negative_anomaly_cells(self) -> list[BouguerCell]:
        """Células com Bouguer fortemente negativo (bacias, granitos)."""
        if not self.cells:
            return []
        min_b = min(c.bouguer for c in self.cells)
        threshold = min_b * 0.5  # metade do mínimo = anomalia negativa forte
        return sorted([c for c in self.cells if c.bouguer <= threshold], key=lambda c: c.bouguer)

    def format_for_prompt(self) -> str:
        """Formata as derivadas como texto para injeção no prompt."""
        if not self.cells:
            return "Derivadas gravimétricas: sem dados suficientes."

        lines: list[str] = [
            "=== DERIVADAS GRAVIMÉTRICAS (Anomalia Bouguer) ===",
            f"N={self.n_source_points} medições; background regional:"
            f" {self.bouguer_mean:.1f} ± {self.bouguer_std:.1f} mGal\n",
        ]

        # Anomalias positivas (corpos densos)
        pos = self.positive_anomaly_cells[:3]
        if pos:
            max_c = pos[0]
            lines.append("ANOMALIAS POSITIVAS (corpos densos — intrusivos, mineralização):")
            lines.append(
                f"  máx={max_c.bouguer:.1f} mGal"
                f" em lon={max_c.lon:.3f}, lat={max_c.lat:.3f}"
                f"  ({len(self.positive_anomaly_cells)} células acima de 0 mGal)"
            )

        # Anomalias negativas (bacias, granitos)
        neg = self.negative_anomaly_cells[:2]
        if neg:
            min_c = neg[0]
            lines.append("ANOMALIAS NEGATIVAS (bacias sedimentares ou granitos):")
            lines.append(
                f"  mín={min_c.bouguer:.1f} mGal em lon={min_c.lon:.3f}, lat={min_c.lat:.3f}"
            )

        # Lineamentos inferidos
        lins = self.lineament_cells[:5]
        if lins:
            lines.append(
                f"\nLINEAMENTOS ESTRUTURAIS INFERIDOS (HGM > {self.hgm_threshold:.1f} mGal/km):"
            )
            for i, c in enumerate(lins, 1):
                lines.append(
                    f"  #{i}  lon={c.lon:.3f} lat={c.lat:.3f}"
                    f"  HGM={c.hgm:.1f} mGal/km → contato/falha inferido"
                )
        else:
            lines.append(f"\nNenhum lineamento acima do limiar ({self.hgm_threshold:.1f} mGal/km).")

        # Síntese
        n_lin = len(self.lineament_cells)
        hgm_vals = [c.hgm for c in self.cells]
        hgm_max = max(hgm_vals) if hgm_vals else 0.0
        hgm_mean = statistics.mean(hgm_vals) if hgm_vals else 0.0
        lines.append(
            f"\nSíntese: gradiente médio={hgm_mean:.1f} mGal/km"
            f" | máximo={hgm_max:.1f} mGal/km"
            f" | lineamentos inferidos={n_lin}"
        )

        return "\n".join(lines)

    def to_geojson(self) -> dict[str, Any]:
        """Converte a grade para GeoJSON FeatureCollection."""
        half = self.step_deg / 2
        features: list[dict[str, Any]] = []
        for cell in self.cells:
            lon, lat = cell.lon, cell.lat
            coords = [
                [lon - half, lat - half],
                [lon + half, lat - half],
                [lon + half, lat + half],
                [lon - half, lat + half],
                [lon - half, lat - half],
            ]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {
                        "bouguer": round(cell.bouguer, 2),
                        "hgm": round(cell.hgm, 3),
                        "is_lineament": cell.is_lineament,
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}


class BouguerProcessor:
    """Processa medições Bouguer para derivadas gravimétricas interpretáveis.

    Não requer geopandas/rasterio — puro Python + stdlib.

    Usage:
        processor = BouguerProcessor()
        grid = processor.process(records, bbox)
        if grid:
            text = grid.format_for_prompt()
    """

    def process(
        self,
        records: list[dict[str, Any]],
        bbox: BoundingBox,
    ) -> BouguerGrid | None:
        """Processa registros gravimétricos e calcula derivadas.

        Args:
            records: Lista de DadoGravimetrico como dicts.
            bbox: Bounding box da região de análise.

        Returns:
            BouguerGrid ou None se dados insuficientes.
        """
        pts = self._extract_points(records)
        if len(pts) < _MIN_POINTS_GRADIENT:
            return None

        # Estatísticas da fonte
        bouguer_vals = [v for _, _, v in pts]
        b_mean = statistics.mean(bouguer_vals)
        b_std = statistics.stdev(bouguer_vals) if len(bouguer_vals) > 1 else 0.0

        # Grade de células
        width = bbox.lon_max - bbox.lon_min
        height = bbox.lat_max - bbox.lat_min
        ncols = max(2, min(_MAX_CELLS_PER_DIM, round(width / _GRID_STEP)))
        nrows = max(2, min(_MAX_CELLS_PER_DIM, round(height / _GRID_STEP)))
        step_lon = width / ncols
        step_lat = height / nrows

        cell_centers = [
            (
                bbox.lon_min + (i + 0.5) * step_lon,
                bbox.lat_min + (j + 0.5) * step_lat,
            )
            for j in range(nrows)
            for i in range(ncols)
        ]

        # IDW interpolação dos valores Bouguer
        lat_center = (bbox.lat_min + bbox.lat_max) / 2
        bouguer_grid = [self._idw(lon, lat, pts) for lon, lat in cell_centers]

        # Gradiente horizontal (mGal/km)
        hgm_grid = _compute_hgm(bouguer_grid, ncols, nrows, step_lon, step_lat, lat_center)

        # Limiar de lineamento: média + 1σ do HGM
        hgm_mean = statistics.mean(hgm_grid)
        hgm_std = statistics.stdev(hgm_grid) if len(hgm_grid) > 1 else 0.0
        hgm_threshold = hgm_mean + hgm_std

        cells = [
            BouguerCell(
                lon=lon,
                lat=lat,
                bouguer=b,
                hgm=h,
                is_lineament=(h > hgm_threshold),
            )
            for (lon, lat), b, h in zip(cell_centers, bouguer_grid, hgm_grid, strict=False)
        ]

        return BouguerGrid(
            lon_min=bbox.lon_min,
            lat_min=bbox.lat_min,
            lon_max=bbox.lon_max,
            lat_max=bbox.lat_max,
            step_deg=max(step_lon, step_lat),
            cells=cells,
            n_source_points=len(pts),
            bouguer_mean=b_mean,
            bouguer_std=b_std,
            hgm_threshold=hgm_threshold,
        )

    @staticmethod
    def _extract_points(
        records: list[dict[str, Any]],
    ) -> list[tuple[float, float, float]]:
        """Extrai (lon, lat, bouguer) de registros gravimétricos."""
        pts: list[tuple[float, float, float]] = []
        for rec in records:
            coord = rec.get("coordenada")
            if not isinstance(coord, dict):
                continue
            bouguer = rec.get("anomalia_bouguer")
            if bouguer is None:
                continue
            try:
                lon = float(coord["longitude"])
                lat = float(coord["latitude"])
                val = float(bouguer)
                pts.append((lon, lat, val))
            except (KeyError, TypeError, ValueError):
                pass
        return pts

    @staticmethod
    def _dist_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        """Distância equiretangular em graus."""
        cos_lat = math.cos(math.radians((lat1 + lat2) / 2))
        return math.sqrt((lat2 - lat1) ** 2 + ((lon2 - lon1) * cos_lat) ** 2)

    def _idw(
        self,
        lon: float,
        lat: float,
        pts: list[tuple[float, float, float]],
    ) -> float:
        """IDW interpolação do valor Bouguer (power=2).

        Se nenhum ponto estiver dentro do raio, usa o ponto mais próximo.
        """
        weighted_sum = 0.0
        total_weight = 0.0
        for p_lon, p_lat, val in pts:
            dist = self._dist_deg(lon, lat, p_lon, p_lat)
            if dist <= _IDW_RADIUS_DEG:
                w = 1.0 / (dist**2 + 1e-9)
                weighted_sum += w * val
                total_weight += w

        if total_weight > 0:
            return weighted_sum / total_weight

        # Fallback: ponto mais próximo
        nearest = min(pts, key=lambda p: self._dist_deg(lon, lat, p[0], p[1]))
        return nearest[2]


def _compute_hgm(
    grid: list[float],
    ncols: int,
    nrows: int,
    step_lon: float,
    step_lat: float,
    lat_center: float,
) -> list[float]:
    """Calcula Horizontal Gradient Magnitude em mGal/km.

    Usa diferenças finitas centrais no interior e diferenças
    avançadas/recuadas nas bordas. Unidade: mGal/km.
    """
    km_per_lon = step_lon * 111.0 * math.cos(math.radians(lat_center))
    km_per_lat = step_lat * 111.0

    hgm: list[float] = []

    for j in range(nrows):
        for i in range(ncols):
            idx = j * ncols + i

            # Gradiente em x (lon)
            if ncols == 1:
                dx = 0.0
            elif i == 0:
                dx = (grid[idx + 1] - grid[idx]) / km_per_lon
            elif i == ncols - 1:
                dx = (grid[idx] - grid[idx - 1]) / km_per_lon
            else:
                dx = (grid[idx + 1] - grid[idx - 1]) / (2 * km_per_lon)

            # Gradiente em y (lat)
            if nrows == 1:
                dy = 0.0
            elif j == 0:
                dy = (grid[(j + 1) * ncols + i] - grid[idx]) / km_per_lat
            elif j == nrows - 1:
                dy = (grid[idx] - grid[(j - 1) * ncols + i]) / km_per_lat
            else:
                dy = (grid[(j + 1) * ncols + i] - grid[(j - 1) * ncols + i]) / (2 * km_per_lat)

            hgm.append(math.sqrt(dx**2 + dy**2))

    return hgm

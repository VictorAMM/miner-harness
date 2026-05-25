"""AeromagProcessor — derivadas de anomalia magnética total.

Processa amostras TMA do Atlas Aerogeofísico SGB (grid regular N×N)
para produzir derivadas interpretáveis pelo GeophysicistAgent:

  1. Estatísticas TMA: média, desvio, percentis, min/max.

  2. Gradiente Horizontal Total (HGM) — sqrt((∂TMA/∂x)² + (∂TMA/∂y)²)
     em nT/km. Máximos de HGM delimitam bordas de corpos magnéticos
     (contatos litológicos, falhas, bordas de intrusivos).

  3. Detecção de anomalias: células com |TMA − média| > 2σ são marcadas
     como candidatos a corpos anômalos (possíveis intrusivos magnéticos
     ou zonas de alteração com magnetita).

  4. Proxy K/eTh: se pontos de geoquímica normalizada disponíveis,
     calcula razão K/eTh regional; caso contrário, deixa None.

Ref: PRD-003 F10 — Aeromagnética Real
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox

logger = structlog.get_logger(__name__)

# Raio terrestre médio (km)
_R_EARTH_KM = 6371.0

# Mínimo de pontos válidos para calcular HGM
_MIN_POINTS_HGM = 4

# Limiar de anomalia em múltiplos de desvio padrão
_ANOMALY_SIGMA = 2.0


@dataclass
class AeromagCell:
    """Célula da grade de anomalia magnética."""

    lon: float
    lat: float
    tma_nt: float  # Total Magnetic Anomaly (nT)
    hgm: float  # Horizontal Gradient Magnitude (nT/km)
    is_anomaly: bool  # |TMA − média| > 2σ


@dataclass
class AeromagGrid:
    """Grade de derivadas magnéticas calculadas para um bbox."""

    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    cells: list[AeromagCell]
    n_source_points: int
    tma_mean: float
    tma_std: float
    hgm_threshold: float  # limiar de detecção de anomalia HGM (nT/km)

    @property
    def anomaly_cells(self) -> list[AeromagCell]:
        """Células com anomalia TMA significativa (ordenadas por |TMA|)."""
        return sorted(
            [c for c in self.cells if c.is_anomaly],
            key=lambda c: abs(c.tma_nt - self.tma_mean),
            reverse=True,
        )

    @property
    def high_hgm_cells(self) -> list[AeromagCell]:
        """Células com HGM acima do limiar (possíveis lineamentos/contatos)."""
        return sorted(
            [c for c in self.cells if c.hgm >= self.hgm_threshold],
            key=lambda c: -c.hgm,
        )

    def format_for_prompt(self) -> str:
        """Formata resultados para injeção no prompt do GeophysicistAgent."""
        lines: list[str] = [
            "═══ Anomalia Magnética Total (Atlas Aerogeofísico SGB/CPRM) ═══",
            "Fonte: geoportal.sgb.gov.br/Mapas_Tern_Mag_MIL1 (escala 1:1.000.000)",
            f"Amostras válidas: {self.n_source_points} pontos em grid regular",
            "",
            "Estatísticas TMA:",
            f"  Média   : {self.tma_mean:+.1f} nT",
            f"  Desvio σ: {self.tma_std:.1f} nT",
        ]
        if self.cells:
            vals = [c.tma_nt for c in self.cells]
            lines.append(f"  Mínimo  : {min(vals):+.1f} nT")
            lines.append(f"  Máximo  : {max(vals):+.1f} nT")

        n_anom = len(self.anomaly_cells)
        lines += [
            "",
            f"Anomalias TMA (|TMA − média| > {_ANOMALY_SIGMA:.0f}σ = "
            f"±{_ANOMALY_SIGMA * self.tma_std:.1f} nT): {n_anom} célula(s)",
        ]
        for i, cell in enumerate(self.anomaly_cells[:5], 1):
            sign = "+" if cell.tma_nt >= self.tma_mean else "−"
            lines.append(
                f"  {i}. ({cell.lon:.3f}, {cell.lat:.3f}) "
                f"TMA = {cell.tma_nt:+.1f} nT  "
                f"[{sign}{abs(cell.tma_nt - self.tma_mean):.1f} nT acima da média]  "
                f"HGM = {cell.hgm:.2f} nT/km"
            )

        high_hgm = self.high_hgm_cells
        lines += [
            "",
            f"Gradiente Horizontal (HGM) — limiar de lineamento: {self.hgm_threshold:.2f} nT/km",
            f"Células acima do limiar: {len(high_hgm)}",
        ]
        for i, cell in enumerate(high_hgm[:5], 1):
            lines.append(
                f"  {i}. ({cell.lon:.3f}, {cell.lat:.3f}) "
                f"HGM = {cell.hgm:.2f} nT/km  TMA = {cell.tma_nt:+.1f} nT"
            )

        lines.append("═══════════════════════════════════════════════════════════════")
        return "\n".join(lines)

    def to_geojson(self) -> dict[str, Any]:
        """Serializa pontos como GeoJSON para exportação."""
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c.lon, c.lat]},
                "properties": {
                    "tma_nt": round(c.tma_nt, 2),
                    "hgm": round(c.hgm, 3),
                    "is_anomaly": c.is_anomaly,
                    "tma_mean": round(self.tma_mean, 2),
                    "tma_std": round(self.tma_std, 2),
                },
            }
            for c in self.cells
        ]
        return {"type": "FeatureCollection", "features": features}


class AeromagProcessor:
    """Processa amostras TMA para derivadas interpretáveis.

    Fluxo de processamento:
    1. Filtrar pontos inválidos (NaN, None)
    2. Calcular estatísticas TMA (média, σ, min, max)
    3. Calcular HGM via diferenças finitas sobre grade regular
    4. Detectar anomalias (|TMA − média| > 2σ)
    5. Retornar AeromagGrid com format_for_prompt() e to_geojson()

    Usage:
        processor = AeromagProcessor()
        grid = processor.process(points, bbox)
        # grid.format_for_prompt() → string injetada no prompt do geofísico
    """

    def process(
        self,
        points: list[dict[str, Any]],
        bbox: BoundingBox,
    ) -> AeromagGrid | None:
        """Processa lista de pontos TMA e retorna grid com derivadas.

        Args:
            points: Lista de dicts ``{lon, lat, tma_nt}`` do AeromagConnector.
            bbox: Bounding box da região.

        Returns:
            AeromagGrid ou None se dados insuficientes.
        """
        valid = [
            p
            for p in points
            if isinstance(p.get("tma_nt"), (int, float)) and math.isfinite(float(p["tma_nt"]))
        ]
        if len(valid) < 3:
            logger.warning(
                "aeromag_insufficient_points",
                total=len(points),
                valid=len(valid),
            )
            return None

        tma_vals = [float(p["tma_nt"]) for p in valid]
        tma_mean = statistics.mean(tma_vals)
        tma_std = statistics.pstdev(tma_vals) if len(tma_vals) > 1 else 0.0

        # HGM sobre grade (diferenças finitas)
        hgm_values = _compute_hgm(valid, bbox)

        # Limiar de lineamento = média + 1σ (mais conservador que anomalia TMA)
        hgm_vals_list = list(hgm_values.values())
        hgm_threshold = (
            statistics.mean(hgm_vals_list) + statistics.pstdev(hgm_vals_list)
            if len(hgm_vals_list) > 1
            else 0.0
        )

        cells: list[AeromagCell] = []
        for p in valid:
            lon, lat, tma = float(p["lon"]), float(p["lat"]), float(p["tma_nt"])
            key = (round(lon, 6), round(lat, 6))
            hgm = hgm_values.get(key, 0.0)
            is_anomaly = abs(tma - tma_mean) > _ANOMALY_SIGMA * tma_std
            cells.append(AeromagCell(lon=lon, lat=lat, tma_nt=tma, hgm=hgm, is_anomaly=is_anomaly))

        grid = AeromagGrid(
            lon_min=bbox.lon_min,
            lat_min=bbox.lat_min,
            lon_max=bbox.lon_max,
            lat_max=bbox.lat_max,
            cells=cells,
            n_source_points=len(valid),
            tma_mean=tma_mean,
            tma_std=tma_std,
            hgm_threshold=hgm_threshold,
        )
        logger.info(
            "aeromag_grid_computed",
            n_cells=len(cells),
            tma_mean=round(tma_mean, 1),
            tma_std=round(tma_std, 1),
            n_anomalies=len(grid.anomaly_cells),
            n_lineaments=len(grid.high_hgm_cells),
        )
        return grid


# ---------------------------------------------------------------------------
# Funções de cálculo de HGM
# ---------------------------------------------------------------------------


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Distância em km entre dois pontos geográficos (fórmula de Haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * _R_EARTH_KM * math.asin(math.sqrt(max(0.0, a)))


def _compute_hgm(
    points: list[dict[str, Any]],
    bbox: BoundingBox,
) -> dict[tuple[float, float], float]:
    """Calcula HGM por diferenças finitas para cada ponto.

    Para cada ponto, procura os vizinhos mais próximos em direção x (lon)
    e y (lat) e estima os gradientes parciais:

        ∂TMA/∂x ≈ (TMA_leste − TMA_oeste) / (2 * Δx_km)
        ∂TMA/∂y ≈ (TMA_norte − TMA_sul) / (2 * Δy_km)
        HGM = sqrt((∂TMA/∂x)² + (∂TMA/∂y)²)

    Em bordas (sem vizinhos em ambas as direções), usa diferença unilateral.

    Args:
        points: Lista de dicts ``{lon, lat, tma_nt}``.
        bbox: Bounding box (para referência de escala).

    Returns:
        Dict (lon, lat) → HGM em nT/km.
    """
    if len(points) < _MIN_POINTS_HGM:
        return {(round(p["lon"], 6), round(p["lat"], 6)): 0.0 for p in points}

    # Indexar por (lon_rounded, lat_rounded)
    tma_index: dict[tuple[float, float], float] = {
        (round(float(p["lon"]), 6), round(float(p["lat"]), 6)): float(p["tma_nt"]) for p in points
    }

    lons = sorted({k[0] for k in tma_index})
    lats = sorted({k[1] for k in tma_index})

    hgm: dict[tuple[float, float], float] = {}

    for lon in lons:
        lon_idx = lons.index(lon)
        for lat in lats:
            lat_idx = lats.index(lat)
            key = (lon, lat)
            if key not in tma_index:
                continue
            tma0 = tma_index[key]

            # Gradiente em x (longitude)
            dx_km: float | None = None
            grad_x = 0.0
            if lon_idx > 0 and lon_idx < len(lons) - 1:
                # Diferença centrada
                k_west = (lons[lon_idx - 1], lat)
                k_east = (lons[lon_idx + 1], lat)
                if k_west in tma_index and k_east in tma_index:
                    dx_km = _haversine_km(lons[lon_idx - 1], lat, lons[lon_idx + 1], lat)
                    if dx_km > 0:
                        grad_x = (tma_index[k_east] - tma_index[k_west]) / dx_km
            elif lon_idx == 0 and len(lons) > 1:
                # Diferença progressiva
                k_east = (lons[1], lat)
                if k_east in tma_index:
                    dx_km = _haversine_km(lon, lat, lons[1], lat)
                    if dx_km > 0:
                        grad_x = (tma_index[k_east] - tma0) / dx_km
            elif lon_idx == len(lons) - 1 and len(lons) > 1:
                # Diferença regressiva
                k_west = (lons[-2], lat)
                if k_west in tma_index:
                    dx_km = _haversine_km(lons[-2], lat, lon, lat)
                    if dx_km > 0:
                        grad_x = (tma0 - tma_index[k_west]) / dx_km

            # Gradiente em y (latitude)
            dy_km: float | None = None
            grad_y = 0.0
            if lat_idx > 0 and lat_idx < len(lats) - 1:
                # Diferença centrada
                k_south = (lon, lats[lat_idx - 1])
                k_north = (lon, lats[lat_idx + 1])
                if k_south in tma_index and k_north in tma_index:
                    dy_km = _haversine_km(lon, lats[lat_idx - 1], lon, lats[lat_idx + 1])
                    if dy_km > 0:
                        grad_y = (tma_index[k_north] - tma_index[k_south]) / dy_km
            elif lat_idx == 0 and len(lats) > 1:
                k_north = (lon, lats[1])
                if k_north in tma_index:
                    dy_km = _haversine_km(lon, lat, lon, lats[1])
                    if dy_km > 0:
                        grad_y = (tma_index[k_north] - tma0) / dy_km
            elif lat_idx == len(lats) - 1 and len(lats) > 1:
                k_south = (lon, lats[-2])
                if k_south in tma_index:
                    dy_km = _haversine_km(lon, lats[-2], lon, lat)
                    if dy_km > 0:
                        grad_y = (tma0 - tma_index[k_south]) / dy_km

            hgm[key] = math.sqrt(grad_x**2 + grad_y**2)

    return hgm

"""ProspectivityScorer — weighted overlay de prospectividade mineral.

Calcula score de 0–100 por célula de grade (~11 km) sobre o bbox,
combinando quatro componentes geoespaciais:

  1. Densidade de ocorrências minerais   (peso: 0.35)
  2. Anomalia Bouguer (gravimetria)       (peso: 0.25)
  3. Densidade de anomalias geoquímicas  (peso: 0.25)
  4. Indicador estrutural (prox. a ocorrências) (peso: 0.15)

Cada componente é normalizado pelo seu máximo antes da combinação, de
modo que a célula com a maior evidência em cada fonte receba score 1.0.
O resultado final é multiplicado por 100 para o intervalo 0–100.

Ref: PRD-002 F3
"""

from __future__ import annotations

import contextlib
import math
import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox

# Pesos do weighted overlay (soma = 1.0)
_WEIGHTS: dict[str, float] = {
    "occurrence_density": 0.35,
    "bouguer_anomaly": 0.25,
    "geochemical_anomaly": 0.25,
    "structural_indicator": 0.15,
}

_RADIUS_DEG: float = 0.20  # raio de busca por célula (graus, ≈22 km)
_GRID_STEP: float = 0.10  # resolução da grade (graus, ≈11 km)
_MAX_CELLS_PER_DIM: int = 30  # limite de células por dimensão
_CF_THRESHOLD: float = 2.0  # mesmo threshold do normalizer


@dataclass
class GridCell:
    """Célula da grade de prospectividade."""

    lon: float
    lat: float
    score: float  # 0–100
    components: dict[str, float] = field(default_factory=dict)  # 0–1 cada


@dataclass
class ProspectivityGrid:
    """Grade de prospectividade calculada para um bbox."""

    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    step_deg: float
    cells: list[GridCell]
    weights: dict[str, float]

    @property
    def top_cells(self) -> list[GridCell]:
        return sorted(self.cells, key=lambda c: -c.score)[:5]

    def format_for_prompt(self) -> str:
        """Formata o score como texto para injeção no prompt."""
        if not self.cells:
            return "Score de prospectividade: sem dados suficientes para calcular."

        max_score = max(c.score for c in self.cells)
        mean_score = statistics.mean(c.score for c in self.cells)
        n_high = sum(1 for c in self.cells if c.score >= 70)
        n_medium = sum(1 for c in self.cells if 40 <= c.score < 70)

        lines: list[str] = [
            "=== SCORE DE PROSPECTIVIDADE (Weighted Overlay) ===",
            f"Grade: {len(self.cells)} células de {self.step_deg:.2f}°"
            f" (~{self.step_deg * 111:.0f} km)\n",
            f"Score máximo: {max_score:.1f}/100  |  Média: {mean_score:.1f}/100",
            f"Células ALTA prospectividade (≥70): {n_high}",
            f"Células MÉDIA prospectividade (40–69): {n_medium}",
        ]

        top = self.top_cells
        if top:
            lines.append("\nTOP CÉLULAS (candidatos a alvo):")
            for i, c in enumerate(top, 1):
                comps = ", ".join(f"{k[:8]}={v:.2f}" for k, v in sorted(c.components.items()))
                lines.append(
                    f"  #{i}  lon={c.lon:.3f} lat={c.lat:.3f}"
                    f"  score={c.score:.1f}/100\n       [{comps}]"
                )

        w = self.weights
        lines.append(
            f"\nPesos: ocorrências={w.get('occurrence_density', 0):.0%}, "
            f"Bouguer={w.get('bouguer_anomaly', 0):.0%}, "
            f"geoquímica={w.get('geochemical_anomaly', 0):.0%}, "
            f"estrutural={w.get('structural_indicator', 0):.0%}"
        )

        return "\n".join(lines)

    def to_geojson(self) -> dict[str, Any]:
        """Converte a grade para GeoJSON FeatureCollection (retângulos)."""
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
                        "score": round(cell.score, 1),
                        "occurrence_density": round(
                            cell.components.get("occurrence_density", 0), 3
                        ),
                        "bouguer_anomaly": round(cell.components.get("bouguer_anomaly", 0), 3),
                        "geochemical_anomaly": round(
                            cell.components.get("geochemical_anomaly", 0), 3
                        ),
                        "structural_indicator": round(
                            cell.components.get("structural_indicator", 0), 3
                        ),
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}


class ProspectivityScorer:
    """Calcula grade de prospectividade por weighted overlay.

    Requer apenas dados geoespaciais já presentes no contexto —
    sem dependências externas além da stdlib.

    Usage:
        scorer = ProspectivityScorer()
        grid = scorer.score(bbox, context)
        if grid:
            text = grid.format_for_prompt()
            geojson = grid.to_geojson()
    """

    def score(
        self,
        bbox: BoundingBox,
        context: dict[str, list[dict[str, Any]]],
    ) -> ProspectivityGrid | None:
        """Calcula o score de prospectividade por célula.

        Args:
            bbox: Bounding box da região de análise.
            context: Contexto geológico (ocorrencias, gravimetria, geoquimica…).

        Returns:
            ProspectivityGrid ou None se não houver dados suficientes.
        """
        occ_pts = self._extract_coords(context.get("ocorrencias", []))
        grav_pts = self._extract_gravity(context.get("gravimetria", []))
        geo_pts = self._extract_geochem(context.get("geoquimica", []))

        if not occ_pts and not grav_pts and not geo_pts:
            return None

        # Grade de células sobre o bbox
        width = bbox.lon_max - bbox.lon_min
        height = bbox.lat_max - bbox.lat_min
        ncols = max(1, min(_MAX_CELLS_PER_DIM, round(width / _GRID_STEP)))
        nrows = max(1, min(_MAX_CELLS_PER_DIM, round(height / _GRID_STEP)))
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

        # Raw scores por componente
        raw: dict[str, list[float]] = {
            "occurrence_density": [
                self._occurrence_score(lon, lat, occ_pts) for lon, lat in cell_centers
            ],
            "bouguer_anomaly": [
                self._bouguer_score(lon, lat, grav_pts) for lon, lat in cell_centers
            ],
            "geochemical_anomaly": [
                self._geochem_score(lon, lat, geo_pts) for lon, lat in cell_centers
            ],
            "structural_indicator": [
                self._structural_score(lon, lat, occ_pts) for lon, lat in cell_centers
            ],
        }

        # Normalizar por máximo de cada componente
        normalized: dict[str, list[float]] = {}
        for key, vals in raw.items():
            mx = max(vals) if vals else 0.0
            normalized[key] = [v / mx for v in vals] if mx > 0 else [0.0] * len(vals)

        # Score final = soma ponderada × 100
        cells: list[GridCell] = []
        for idx, (lon, lat) in enumerate(cell_centers):
            comps = {k: normalized[k][idx] for k in normalized}
            final = sum(_WEIGHTS.get(k, 0) * v for k, v in comps.items()) * 100
            cells.append(GridCell(lon=lon, lat=lat, score=final, components=comps))

        return ProspectivityGrid(
            lon_min=bbox.lon_min,
            lat_min=bbox.lat_min,
            lon_max=bbox.lon_max,
            lat_max=bbox.lat_max,
            step_deg=max(step_lon, step_lat),
            cells=cells,
            weights=dict(_WEIGHTS),
        )

    @staticmethod
    def _dist_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        """Distância equiretangular em graus (suficiente para ranking)."""
        cos_lat = math.cos(math.radians((lat1 + lat2) / 2))
        dlat = lat2 - lat1
        dlon = (lon2 - lon1) * cos_lat
        return math.sqrt(dlat**2 + dlon**2)

    @staticmethod
    def _extract_coords(
        records: list[dict[str, Any]],
    ) -> list[tuple[float, float]]:
        """Extrai (lon, lat) de registros com campo coordenada."""
        pts: list[tuple[float, float]] = []
        for rec in records:
            coord = rec.get("coordenada")
            if not isinstance(coord, dict):
                continue
            with contextlib.suppress(KeyError, TypeError, ValueError):
                pts.append((float(coord["longitude"]), float(coord["latitude"])))
        return pts

    @staticmethod
    def _extract_gravity(
        records: list[dict[str, Any]],
    ) -> list[tuple[float, float, float]]:
        """Extrai (lon, lat, abs_bouguer) de registros gravimétricos."""
        pts: list[tuple[float, float, float]] = []
        for rec in records:
            coord = rec.get("coordenada")
            if not isinstance(coord, dict):
                continue
            try:
                lon = float(coord["longitude"])
                lat = float(coord["latitude"])
                bouguer = rec.get("anomalia_bouguer")
                val = abs(float(bouguer)) if bouguer is not None else 0.0
                pts.append((lon, lat, val))
            except (KeyError, TypeError, ValueError):
                pass
        return pts

    @staticmethod
    def _extract_geochem(
        records: list[dict[str, Any]],
    ) -> list[tuple[float, float, bool]]:
        """Extrai (lon, lat, is_anomalous) de registros geoquímicos.

        Anomalia: ao menos um elemento com valor > _CF_THRESHOLD × mediana global.
        Requer ≥2 amostras por elemento para calcular a mediana.
        """
        by_element: dict[str, list[float]] = {}
        for rec in records:
            analises = rec.get("analises")
            if not isinstance(analises, dict):
                continue
            for key, val in analises.items():
                try:
                    fval = float(val)
                    if fval >= 0:
                        by_element.setdefault(key, []).append(fval)
                except (TypeError, ValueError):
                    pass

        medians = {k: statistics.median(v) for k, v in by_element.items() if len(v) >= 2}

        pts: list[tuple[float, float, bool]] = []
        for rec in records:
            coord = rec.get("coordenada")
            if not isinstance(coord, dict):
                continue
            try:
                lon = float(coord["longitude"])
                lat = float(coord["latitude"])
            except (KeyError, TypeError, ValueError):
                continue

            is_anom = False
            analises = rec.get("analises")
            if isinstance(analises, dict):
                for key, val in analises.items():
                    med = medians.get(key, 0.0)
                    if med > 0:
                        try:
                            if float(val) >= _CF_THRESHOLD * med:
                                is_anom = True
                                break
                        except (TypeError, ValueError):
                            pass

            pts.append((lon, lat, is_anom))
        return pts

    def _occurrence_score(
        self,
        lon: float,
        lat: float,
        occ_pts: list[tuple[float, float]],
    ) -> float:
        """Contagem de ocorrências dentro do raio de busca."""
        return sum(
            1.0 for p_lon, p_lat in occ_pts if self._dist_deg(lon, lat, p_lon, p_lat) <= _RADIUS_DEG
        )

    def _bouguer_score(
        self,
        lon: float,
        lat: float,
        grav_pts: list[tuple[float, float, float]],
    ) -> float:
        """Anomalia Bouguer média ponderada por distância (IDW, power=2)."""
        weighted_sum = 0.0
        total_weight = 0.0
        for p_lon, p_lat, val in grav_pts:
            dist = self._dist_deg(lon, lat, p_lon, p_lat)
            if dist <= _RADIUS_DEG:
                w = 1.0 / (dist**2 + 1e-9)
                weighted_sum += w * val
                total_weight += w
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _geochem_score(
        self,
        lon: float,
        lat: float,
        geo_pts: list[tuple[float, float, bool]],
    ) -> float:
        """Contagem de pontos geoquímicos anômalos dentro do raio."""
        return sum(
            1.0
            for p_lon, p_lat, is_anom in geo_pts
            if is_anom and self._dist_deg(lon, lat, p_lon, p_lat) <= _RADIUS_DEG
        )

    def _structural_score(
        self,
        lon: float,
        lat: float,
        occ_pts: list[tuple[float, float]],
    ) -> float:
        """Indicador estrutural: inverso da distância à ocorrência mais próxima.

        Proxy para controle estrutural — ocorrências tendem a se localizar
        ao longo de estruturas geológicas (falhas, contatos, shear zones).
        """
        if not occ_pts:
            return 0.0
        min_dist = min(self._dist_deg(lon, lat, p_lon, p_lat) for p_lon, p_lat in occ_pts)
        return 1.0 / (min_dist + 0.01)

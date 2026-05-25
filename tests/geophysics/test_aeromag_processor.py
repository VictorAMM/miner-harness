"""Testes para AeromagProcessor — derivadas de anomalia magnética total."""

from __future__ import annotations

import math
from typing import Any

import pytest

from miner_harness.core.types import BoundingBox
from miner_harness.geophysics.aeromag_processor import (
    AeromagCell,
    AeromagGrid,
    AeromagProcessor,
    _compute_hgm,
    _haversine_km,
)

# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------


def _make_bbox(
    lon_min: float = -51.5,
    lat_min: float = -7.0,
    lon_max: float = -49.5,
    lat_max: float = -5.0,
) -> BoundingBox:
    return BoundingBox(lon_min=lon_min, lat_min=lat_min, lon_max=lon_max, lat_max=lat_max)


def _make_grid_points(
    bbox: BoundingBox,
    n: int = 4,
    base_tma: float = 0.0,
) -> list[dict[str, Any]]:
    """Gera grid N×N de pontos TMA uniformes."""
    step_lon = bbox.width / (n - 1)
    step_lat = bbox.height / (n - 1)
    pts = []
    for i in range(n):
        lon = bbox.lon_min + i * step_lon
        for j in range(n):
            lat = bbox.lat_min + j * step_lat
            pts.append({"lon": round(lon, 6), "lat": round(lat, 6), "tma_nt": base_tma})
    return pts


# ---------------------------------------------------------------------------
# _haversine_km
# ---------------------------------------------------------------------------


class TestHaversineKm:
    def test_same_point_is_zero(self) -> None:
        assert _haversine_km(-50.0, -6.0, -50.0, -6.0) == pytest.approx(0.0, abs=1e-6)

    def test_approx_one_degree_lat(self) -> None:
        # 1 grau de latitude ≈ 111 km
        d = _haversine_km(-50.0, -7.0, -50.0, -6.0)
        assert 108 < d < 114

    def test_approx_one_degree_lon_at_equator(self) -> None:
        # 1 grau de longitude no equador ≈ 111 km
        d = _haversine_km(-50.0, 0.0, -49.0, 0.0)
        assert 108 < d < 114

    def test_symmetric(self) -> None:
        d1 = _haversine_km(-51.0, -7.0, -49.0, -5.0)
        d2 = _haversine_km(-49.0, -5.0, -51.0, -7.0)
        assert d1 == pytest.approx(d2, rel=1e-9)


# ---------------------------------------------------------------------------
# _compute_hgm
# ---------------------------------------------------------------------------


class TestComputeHgm:
    def test_uniform_field_has_zero_gradient(self) -> None:
        """Campo uniforme → HGM = 0 em todos os pontos."""
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=100.0)
        hgm = _compute_hgm(pts, bbox)
        for v in hgm.values():
            assert v == pytest.approx(0.0, abs=1e-6)

    def test_linear_x_gradient_is_nonzero(self) -> None:
        """Campo que aumenta linearmente em x → HGM > 0.

        Usa 4 pontos (>= _MIN_POINTS_HGM) para que o cálculo seja executado.
        """
        bbox = _make_bbox()
        pts = [
            {"lon": -51.5, "lat": -6.0, "tma_nt": 0.0},
            {"lon": -50.5, "lat": -6.0, "tma_nt": 100.0},
            {"lon": -49.5, "lat": -6.0, "tma_nt": 200.0},
            {"lon": -48.5, "lat": -6.0, "tma_nt": 300.0},
        ]
        hgm = _compute_hgm(pts, bbox)
        for v in hgm.values():
            assert v > 0.0

    def test_returns_dict_keyed_by_lon_lat_tuple(self) -> None:
        """Chaves do dict são tuplas (lon, lat) arredondadas."""
        bbox = _make_bbox()
        pts = [
            {"lon": -51.5, "lat": -6.0, "tma_nt": 10.0},
            {"lon": -50.5, "lat": -6.0, "tma_nt": 20.0},
            {"lon": -49.5, "lat": -6.0, "tma_nt": 30.0},
        ]
        hgm = _compute_hgm(pts, bbox)
        for key in hgm:
            assert isinstance(key, tuple)
            assert len(key) == 2

    def test_fewer_than_min_points_returns_zeros(self) -> None:
        """Menos de 4 pontos → HGM = 0 para todos."""
        bbox = _make_bbox()
        pts = [
            {"lon": -50.5, "lat": -6.0, "tma_nt": 50.0},
            {"lon": -50.3, "lat": -6.0, "tma_nt": 80.0},
        ]
        hgm = _compute_hgm(pts, bbox)
        for v in hgm.values():
            assert v == pytest.approx(0.0)

    def test_sparse_grid_skips_missing_combinations(self) -> None:
        """Grade esparsa (nem todos (lon,lat) têm dado) → continue no loop interno."""
        bbox = _make_bbox()
        # 2 lons × 2 lats = 4 combinações possíveis, mas apenas 4 pontos reais
        # em diagonal — (lon0,lat0), (lon0,lat1), (lon1,lat0), (lon1,lat1) presentes
        # adicionamos um 5º ponto em lon extra sem contrapartida lat extra
        pts = [
            {"lon": -51.5, "lat": -6.5, "tma_nt": 10.0},
            {"lon": -51.5, "lat": -5.5, "tma_nt": 20.0},
            {"lon": -50.5, "lat": -6.5, "tma_nt": 30.0},
            {"lon": -50.5, "lat": -5.5, "tma_nt": 40.0},
            # Ponto extra: lon=-49.5 existe, lat=-6.5 existe na lista,
            # mas (-49.5, -5.5) NÃO existe → tma_index miss → continue (linha 296)
            {"lon": -49.5, "lat": -6.5, "tma_nt": 50.0},
        ]
        hgm = _compute_hgm(pts, bbox)
        # Deve retornar valores para os pontos presentes; não falhar
        assert len(hgm) == 5
        for v in hgm.values():
            assert math.isfinite(v)
            assert v >= 0.0

    def test_single_row_dy_zero(self) -> None:
        """Somente 1 linha de pontos (N_lat=1) → gradiente-y = 0."""
        bbox = _make_bbox()
        pts = [
            {"lon": -51.5, "lat": -6.0, "tma_nt": 0.0},
            {"lon": -50.5, "lat": -6.0, "tma_nt": 100.0},
            {"lon": -49.5, "lat": -6.0, "tma_nt": 200.0},
            {"lon": -51.5, "lat": -5.0, "tma_nt": 0.0},
            {"lon": -50.5, "lat": -5.0, "tma_nt": 100.0},
            {"lon": -49.5, "lat": -5.0, "tma_nt": 200.0},
        ]
        hgm = _compute_hgm(pts, bbox)
        # HGM deve ser finito e não-negativo
        for v in hgm.values():
            assert v >= 0.0
            assert math.isfinite(v)


# ---------------------------------------------------------------------------
# AeromagProcessor.process
# ---------------------------------------------------------------------------


class TestAeromagProcessorProcess:
    def test_returns_none_with_fewer_than_3_valid_points(self) -> None:
        bbox = _make_bbox()
        pts = [
            {"lon": -50.5, "lat": -6.0, "tma_nt": 100.0},
            {"lon": -50.3, "lat": -6.0, "tma_nt": 200.0},
        ]
        result = AeromagProcessor().process(pts, bbox)
        assert result is None

    def test_returns_none_with_empty_list(self) -> None:
        bbox = _make_bbox()
        result = AeromagProcessor().process([], bbox)
        assert result is None

    def test_returns_grid_with_valid_points(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=50.0)
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert isinstance(grid, AeromagGrid)

    def test_tma_mean_correct(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=100.0)
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert grid.tma_mean == pytest.approx(100.0)

    def test_uniform_field_no_anomalies(self) -> None:
        """Campo uniforme → std=0 → nenhuma célula é anomalia."""
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=100.0)
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert len(grid.anomaly_cells) == 0

    def test_anomaly_detected_when_outlier_present(self) -> None:
        """Ponto muito acima da média é detectado como anomalia."""
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=10.0)
        # Adicionar outlier muito acima da média
        pts.append({"lon": -50.5, "lat": -6.0, "tma_nt": 1000.0})
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert len(grid.anomaly_cells) >= 1

    def test_n_source_points_matches_valid_input(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=0.0)  # 9 pontos
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert grid.n_source_points == 9

    def test_nan_values_filtered_out(self) -> None:
        """Pontos com NaN são removidos antes do processamento."""
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=2, base_tma=50.0)  # 4 válidos
        pts.append({"lon": -50.0, "lat": -6.0, "tma_nt": float("nan")})
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert grid.n_source_points == 4

    def test_non_numeric_tma_filtered_out(self) -> None:
        """Pontos com tma_nt não-numérico (None, str) são removidos."""
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=2, base_tma=50.0)  # 4 válidos
        pts.append({"lon": -50.0, "lat": -6.0, "tma_nt": None})
        pts.append({"lon": -50.0, "lat": -6.5, "tma_nt": "invalid"})
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert grid.n_source_points == 4

    def test_cells_count_matches_valid_points(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=100.0)  # 9 pontos
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert len(grid.cells) == 9

    def test_bbox_coordinates_stored(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=0.0)
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert grid.lon_min == bbox.lon_min
        assert grid.lat_max == bbox.lat_max

    def test_hgm_threshold_is_positive(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=0.0)
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        assert grid.hgm_threshold >= 0.0


# ---------------------------------------------------------------------------
# AeromagGrid properties
# ---------------------------------------------------------------------------


class TestAeromagGridProperties:
    def _make_grid(self, tma_vals: list[float], mean: float, std: float) -> AeromagGrid:
        cells = [
            AeromagCell(
                lon=-50.0 + i * 0.1,
                lat=-6.0,
                tma_nt=v,
                hgm=abs(v - mean) / 10,
                is_anomaly=abs(v - mean) > 2 * std,
            )
            for i, v in enumerate(tma_vals)
        ]
        return AeromagGrid(
            lon_min=-51.5,
            lat_min=-7.0,
            lon_max=-49.5,
            lat_max=-5.0,
            cells=cells,
            n_source_points=len(cells),
            tma_mean=mean,
            tma_std=std,
            hgm_threshold=0.5,
        )

    def test_anomaly_cells_returns_only_anomalies(self) -> None:
        # Criar células diretamente com is_anomaly definido
        cells = [
            AeromagCell(lon=-50.0, lat=-6.0, tma_nt=100.0, hgm=1.0, is_anomaly=True),
            AeromagCell(lon=-50.1, lat=-6.0, tma_nt=10.0, hgm=0.1, is_anomaly=False),
            AeromagCell(lon=-50.2, lat=-6.0, tma_nt=200.0, hgm=2.0, is_anomaly=True),
        ]
        grid = AeromagGrid(
            lon_min=-51.5,
            lat_min=-7.0,
            lon_max=-49.5,
            lat_max=-5.0,
            cells=cells,
            n_source_points=3,
            tma_mean=103.3,
            tma_std=80.0,
            hgm_threshold=0.5,
        )
        anomalies = grid.anomaly_cells
        assert len(anomalies) == 2
        assert all(c.is_anomaly for c in anomalies)

    def test_high_hgm_cells_returns_cells_above_threshold(self) -> None:
        cells = [
            AeromagCell(lon=-50.0, lat=-6.0, tma_nt=100.0, hgm=0.3, is_anomaly=False),
            AeromagCell(lon=-50.1, lat=-6.0, tma_nt=100.0, hgm=1.5, is_anomaly=False),
            AeromagCell(lon=-50.2, lat=-6.0, tma_nt=100.0, hgm=0.8, is_anomaly=False),
        ]
        grid = AeromagGrid(
            lon_min=-51.5,
            lat_min=-7.0,
            lon_max=-49.5,
            lat_max=-5.0,
            cells=cells,
            n_source_points=3,
            tma_mean=100.0,
            tma_std=0.0,
            hgm_threshold=0.7,
        )
        high = grid.high_hgm_cells
        assert len(high) == 2
        assert all(c.hgm >= 0.7 for c in high)

    def test_anomaly_cells_sorted_by_deviation(self) -> None:
        """anomaly_cells deve estar em ordem decrescente de |TMA - mean|."""
        cells = [
            AeromagCell(lon=-50.0, lat=-6.0, tma_nt=200.0, hgm=1.0, is_anomaly=True),  # dev=100
            AeromagCell(lon=-50.1, lat=-6.0, tma_nt=400.0, hgm=2.0, is_anomaly=True),  # dev=300
            AeromagCell(lon=-50.2, lat=-6.0, tma_nt=250.0, hgm=1.5, is_anomaly=True),  # dev=150
        ]
        grid = AeromagGrid(
            lon_min=-51.5,
            lat_min=-7.0,
            lon_max=-49.5,
            lat_max=-5.0,
            cells=cells,
            n_source_points=3,
            tma_mean=100.0,
            tma_std=0.0,
            hgm_threshold=0.5,
        )
        anomalies = grid.anomaly_cells
        devs = [abs(c.tma_nt - 100.0) for c in anomalies]
        assert devs == sorted(devs, reverse=True)


# ---------------------------------------------------------------------------
# AeromagGrid.format_for_prompt
# ---------------------------------------------------------------------------


class TestAeromagGridFormatForPrompt:
    def _make_simple_grid(self) -> AeromagGrid:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=3, base_tma=50.0)
        return AeromagProcessor().process(pts, bbox)

    def test_contains_header(self) -> None:
        grid = self._make_simple_grid()
        text = grid.format_for_prompt()
        assert "Anomalia Magnética Total" in text

    def test_contains_tma_mean(self) -> None:
        grid = self._make_simple_grid()
        text = grid.format_for_prompt()
        assert "Média" in text
        assert "50" in text  # tma_mean = 50.0

    def test_contains_n_source_points(self) -> None:
        grid = self._make_simple_grid()
        text = grid.format_for_prompt()
        assert "9" in text  # 3×3 pontos

    def test_no_anomalies_message_for_uniform_field(self) -> None:
        """Campo uniforme → 0 anomalias reportado."""
        grid = self._make_simple_grid()
        text = grid.format_for_prompt()
        assert "0 célula" in text

    def test_anomaly_listed_when_present(self) -> None:
        """Célula anômala é listada no prompt."""
        cells = [
            AeromagCell(lon=-50.0, lat=-6.0, tma_nt=500.0, hgm=2.0, is_anomaly=True),
            AeromagCell(lon=-50.1, lat=-6.0, tma_nt=10.0, hgm=0.1, is_anomaly=False),
            AeromagCell(lon=-50.2, lat=-6.0, tma_nt=10.0, hgm=0.1, is_anomaly=False),
        ]
        grid = AeromagGrid(
            lon_min=-51.5,
            lat_min=-7.0,
            lon_max=-49.5,
            lat_max=-5.0,
            cells=cells,
            n_source_points=3,
            tma_mean=173.3,
            tma_std=200.0,
            hgm_threshold=0.5,
        )
        text = grid.format_for_prompt()
        assert "-50.000" in text or "-50.0" in text

    def test_ends_with_separator(self) -> None:
        grid = self._make_simple_grid()
        text = grid.format_for_prompt()
        assert "═" in text


# ---------------------------------------------------------------------------
# AeromagGrid.to_geojson
# ---------------------------------------------------------------------------


class TestAeromagGridToGeojson:
    def test_returns_feature_collection(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=2, base_tma=100.0)
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        gj = grid.to_geojson()
        assert gj["type"] == "FeatureCollection"
        assert len(gj["features"]) == 4  # 2×2

    def test_features_have_correct_geometry_type(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=2, base_tma=100.0)
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        for feat in grid.to_geojson()["features"]:
            assert feat["geometry"]["type"] == "Point"
            assert len(feat["geometry"]["coordinates"]) == 2

    def test_properties_include_tma_and_hgm(self) -> None:
        bbox = _make_bbox()
        pts = _make_grid_points(bbox, n=2, base_tma=100.0)
        grid = AeromagProcessor().process(pts, bbox)
        assert grid is not None
        for feat in grid.to_geojson()["features"]:
            props = feat["properties"]
            assert "tma_nt" in props
            assert "hgm" in props
            assert "is_anomaly" in props

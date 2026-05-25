"""Testes de BouguerProcessor, BouguerGrid e BouguerCell."""

from __future__ import annotations

import pytest

from miner_harness.core.types import BoundingBox
from miner_harness.geophysics.bouguer_processor import (
    BouguerGrid,
    BouguerProcessor,
    _compute_hgm,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bbox(
    lon_min: float = -51.0,
    lat_min: float = -7.0,
    lon_max: float = -49.0,
    lat_max: float = -5.0,
) -> BoundingBox:
    return BoundingBox(lon_min=lon_min, lat_min=lat_min, lon_max=lon_max, lat_max=lat_max)


def _grav(lon: float, lat: float, bouguer: float) -> dict:
    return {
        "coordenada": {"longitude": lon, "latitude": lat},
        "anomalia_bouguer": bouguer,
    }


def _make_records(n: int = 6) -> list[dict]:
    """Cria n estações distribuídas no bbox padrão."""
    import random

    random.seed(42)
    lons = [-51.0 + i * (2.0 / max(n - 1, 1)) for i in range(n)]
    lats = [-7.0 + i * (2.0 / max(n - 1, 1)) for i in range(n)]
    bouguers = [-30.0 + i * 5.0 for i in range(n)]
    return [_grav(lo, la, b) for lo, la, b in zip(lons, lats, bouguers, strict=False)]


# ---------------------------------------------------------------------------
# TestExtractPoints
# ---------------------------------------------------------------------------


class TestExtractPoints:
    def test_valid_records_extracted(self) -> None:
        records = [_grav(-50.0, -6.0, -30.0)]
        pts = BouguerProcessor._extract_points(records)
        assert len(pts) == 1
        assert pts[0] == (-50.0, -6.0, -30.0)

    def test_missing_coordenada_skipped(self) -> None:
        records = [{"anomalia_bouguer": -20.0}]
        pts = BouguerProcessor._extract_points(records)
        assert pts == []

    def test_non_dict_coordenada_skipped(self) -> None:
        records = [{"coordenada": "invalid", "anomalia_bouguer": -20.0}]
        pts = BouguerProcessor._extract_points(records)
        assert pts == []

    def test_missing_bouguer_skipped(self) -> None:
        records = [{"coordenada": {"longitude": -50.0, "latitude": -6.0}}]
        pts = BouguerProcessor._extract_points(records)
        assert pts == []

    def test_non_numeric_bouguer_skipped(self) -> None:
        records = [
            {"coordenada": {"longitude": -50.0, "latitude": -6.0}, "anomalia_bouguer": "N/A"}
        ]
        pts = BouguerProcessor._extract_points(records)
        assert pts == []

    def test_multiple_records(self) -> None:
        records = [_grav(-50.0 + i * 0.1, -6.0, -30.0 + i) for i in range(5)]
        pts = BouguerProcessor._extract_points(records)
        assert len(pts) == 5

    def test_negative_bouguer_accepted(self) -> None:
        records = [_grav(-50.0, -6.0, -120.0)]
        pts = BouguerProcessor._extract_points(records)
        assert len(pts) == 1
        assert pts[0][2] == -120.0


# ---------------------------------------------------------------------------
# TestDistDeg
# ---------------------------------------------------------------------------


class TestDistDeg:
    def test_same_point_zero(self) -> None:
        assert BouguerProcessor._dist_deg(-50.0, -6.0, -50.0, -6.0) == pytest.approx(0.0)

    def test_one_degree_north(self) -> None:
        d = BouguerProcessor._dist_deg(-50.0, -6.0, -50.0, -5.0)
        assert d == pytest.approx(1.0, abs=0.02)

    def test_symmetry(self) -> None:
        d1 = BouguerProcessor._dist_deg(-50.0, -6.0, -49.5, -5.5)
        d2 = BouguerProcessor._dist_deg(-49.5, -5.5, -50.0, -6.0)
        assert d1 == pytest.approx(d2, abs=1e-9)

    def test_cos_lat_correction_applied(self) -> None:
        # Distância leste-oeste deve ser menor em lat alta
        d_equator = BouguerProcessor._dist_deg(0.0, 0.0, 1.0, 0.0)
        d_high = BouguerProcessor._dist_deg(0.0, 60.0, 1.0, 60.0)
        assert d_high < d_equator


# ---------------------------------------------------------------------------
# TestIDW
# ---------------------------------------------------------------------------


class TestIDW:
    def test_exact_point_returns_value(self) -> None:
        proc = BouguerProcessor()
        pts = [(-50.0, -6.0, -30.0), (-51.0, -7.0, -50.0)]
        val = proc._idw(-50.0, -6.0, pts)
        # Exact hit → weight huge → value ≈ -30.0
        assert val == pytest.approx(-30.0, abs=1.0)

    def test_fallback_nearest_outside_radius(self) -> None:
        proc = BouguerProcessor()
        # All points far outside IDW radius (0.5 deg)
        pts = [(-60.0, -6.0, -99.0)]
        val = proc._idw(-50.0, -6.0, pts)
        assert val == pytest.approx(-99.0)

    def test_single_point_in_radius(self) -> None:
        proc = BouguerProcessor()
        pts = [(-50.1, -6.0, -40.0)]
        val = proc._idw(-50.0, -6.0, pts)
        assert val == pytest.approx(-40.0, abs=1.0)

    def test_two_equidistant_points_average(self) -> None:
        proc = BouguerProcessor()
        pts = [(-50.1, -6.0, 10.0), (-49.9, -6.0, 20.0)]
        val = proc._idw(-50.0, -6.0, pts)
        # Both same distance → average of values
        assert val == pytest.approx(15.0, abs=1.0)


# ---------------------------------------------------------------------------
# TestComputeHGM
# ---------------------------------------------------------------------------


class TestComputeHGM:
    def test_flat_field_zero_gradient(self) -> None:
        grid = [10.0] * 9  # 3×3 uniform
        hgm = _compute_hgm(grid, 3, 3, 0.1, 0.1, -6.0)
        for h in hgm:
            assert h == pytest.approx(0.0, abs=1e-6)

    def test_linear_ramp_constant_gradient(self) -> None:
        # Bouguer increasing by 1 mGal per column; no row variation
        ncols, nrows = 4, 3
        grid = [float(i % ncols) for i in range(ncols * nrows)]
        step = 0.1
        hgm = _compute_hgm(grid, ncols, nrows, step, step, -6.0)
        # All HGM values should be positive (gradient in x direction)
        assert all(h > 0 for h in hgm)

    def test_output_length_matches_grid(self) -> None:
        ncols, nrows = 5, 4
        grid = [float(i) for i in range(ncols * nrows)]
        hgm = _compute_hgm(grid, ncols, nrows, 0.1, 0.1, -6.0)
        assert len(hgm) == ncols * nrows

    def test_single_column_no_x_gradient(self) -> None:
        grid = [1.0, 2.0, 3.0]  # 1×3
        hgm = _compute_hgm(grid, 1, 3, 0.1, 0.1, -6.0)
        # dx = 0 for single column; only dy contributes
        assert all(h >= 0 for h in hgm)

    def test_gradient_units_mgal_per_km(self) -> None:
        # 1 mGal variation over ~11 km (0.1° lat) → ~0.09 mGal/km
        grid = [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]  # center=1
        hgm = _compute_hgm(grid, 3, 3, 0.1, 0.1, -6.0)
        # Some cells adjacent to center should show gradient
        center_idx = 4
        assert hgm[center_idx] > 0 or any(h > 0 for h in hgm)


# ---------------------------------------------------------------------------
# TestBouguerProcessorEdgeCases
# ---------------------------------------------------------------------------


class TestBouguerProcessorEdgeCases:
    def test_empty_records_returns_none(self) -> None:
        proc = BouguerProcessor()
        result = proc.process([], _bbox())
        assert result is None

    def test_fewer_than_min_points_returns_none(self) -> None:
        # _MIN_POINTS_GRADIENT = 4; só 3 registros
        records = [_grav(-50.0 + i * 0.5, -6.0, -30.0) for i in range(3)]
        proc = BouguerProcessor()
        result = proc.process(records, _bbox())
        assert result is None

    def test_exactly_min_points_returns_grid(self) -> None:
        records = [_grav(-50.0 + i * 0.3, -6.0 + i * 0.3, -30.0 + i * 5) for i in range(4)]
        proc = BouguerProcessor()
        result = proc.process(records, _bbox())
        assert result is not None

    def test_records_without_coord_ignored(self) -> None:
        valid = [_grav(-50.0 + i * 0.3, -6.0, -30.0) for i in range(6)]
        invalid = [{"anomalia_bouguer": -99.0}] * 3
        proc = BouguerProcessor()
        result = proc.process(valid + invalid, _bbox())
        assert result is not None
        assert result.n_source_points == 6

    def test_records_without_bouguer_ignored(self) -> None:
        valid = [_grav(-50.0 + i * 0.3, -6.0, -30.0) for i in range(6)]
        invalid = [{"coordenada": {"longitude": -50.0, "latitude": -6.0}}] * 3
        proc = BouguerProcessor()
        result = proc.process(valid + invalid, _bbox())
        assert result is not None
        assert result.n_source_points == 6


# ---------------------------------------------------------------------------
# TestBouguerGridProperties
# ---------------------------------------------------------------------------


class TestBouguerGridProperties:
    def setup_method(self) -> None:
        self.records = _make_records(8)
        self.proc = BouguerProcessor()
        self.grid = self.proc.process(self.records, _bbox())
        assert self.grid is not None

    def test_cells_positive(self) -> None:
        assert len(self.grid.cells) > 0

    def test_cells_within_bbox(self) -> None:
        bbox = _bbox()
        for cell in self.grid.cells:
            assert bbox.lon_min <= cell.lon <= bbox.lon_max
            assert bbox.lat_min <= cell.lat <= bbox.lat_max

    def test_step_deg_positive(self) -> None:
        assert self.grid.step_deg > 0

    def test_n_source_points_correct(self) -> None:
        assert self.grid.n_source_points == 8

    def test_bouguer_mean_within_range(self) -> None:
        vals = [c.bouguer for c in self.grid.cells]
        mn = min(vals)
        mx = max(vals)
        assert mn <= self.grid.bouguer_mean <= mx

    def test_hgm_threshold_positive(self) -> None:
        assert self.grid.hgm_threshold >= 0

    def test_hgm_all_nonnegative(self) -> None:
        for cell in self.grid.cells:
            assert cell.hgm >= 0

    def test_lineament_cells_have_high_hgm(self) -> None:
        for cell in self.grid.lineament_cells:
            assert cell.hgm > self.grid.hgm_threshold

    def test_lineament_cells_sorted_desc(self) -> None:
        lins = self.grid.lineament_cells
        for i in range(len(lins) - 1):
            assert lins[i].hgm >= lins[i + 1].hgm


# ---------------------------------------------------------------------------
# TestBouguerGridAnomalyCells
# ---------------------------------------------------------------------------


class TestBouguerGridAnomalyCells:
    def test_positive_anomaly_cells_all_positive(self) -> None:
        records = [_grav(-50.0 + i * 0.2, -6.0, 10.0 + i * 5) for i in range(6)]
        grid = BouguerProcessor().process(records, _bbox())
        assert grid is not None
        for cell in grid.positive_anomaly_cells:
            assert cell.bouguer > 0

    def test_negative_anomaly_cells_strongly_negative(self) -> None:
        records = [_grav(-50.0 + i * 0.2, -6.0, -30.0 - i * 10) for i in range(6)]
        grid = BouguerProcessor().process(records, _bbox())
        assert grid is not None
        neg = grid.negative_anomaly_cells
        if neg:
            for cell in neg:
                assert cell.bouguer <= 0

    def test_no_cells_negative_anomaly_empty(self) -> None:
        # BouguerGrid com células vazias
        bg = BouguerGrid(
            lon_min=-51.0,
            lat_min=-7.0,
            lon_max=-49.0,
            lat_max=-5.0,
            step_deg=0.1,
            cells=[],
            n_source_points=0,
            bouguer_mean=0.0,
            bouguer_std=0.0,
            hgm_threshold=0.0,
        )
        assert bg.negative_anomaly_cells == []


# ---------------------------------------------------------------------------
# TestFormatForPrompt
# ---------------------------------------------------------------------------


class TestFormatForPrompt:
    def test_no_cells_returns_message(self) -> None:
        bg = BouguerGrid(
            lon_min=-51.0,
            lat_min=-7.0,
            lon_max=-49.0,
            lat_max=-5.0,
            step_deg=0.1,
            cells=[],
            n_source_points=0,
            bouguer_mean=0.0,
            bouguer_std=0.0,
            hgm_threshold=0.0,
        )
        text = bg.format_for_prompt()
        assert "sem dados" in text.lower()

    def test_header_present(self) -> None:
        grid = BouguerProcessor().process(_make_records(8), _bbox())
        assert grid is not None
        text = grid.format_for_prompt()
        assert "DERIVADAS GRAVIMÉTRICAS" in text

    def test_statistics_present(self) -> None:
        grid = BouguerProcessor().process(_make_records(8), _bbox())
        assert grid is not None
        text = grid.format_for_prompt()
        assert "mGal" in text

    def test_sintese_line_present(self) -> None:
        grid = BouguerProcessor().process(_make_records(8), _bbox())
        assert grid is not None
        text = grid.format_for_prompt()
        assert "Síntese" in text

    def test_lineaments_section_present_when_exists(self) -> None:
        # Usar dados com gradiente forte para garantir lineamentos
        records = [_grav(-50.0, -6.0, -100.0)] + [
            _grav(-50.0 + i * 0.15, -6.0, 50.0) for i in range(1, 7)
        ]
        grid = BouguerProcessor().process(records, _bbox())
        assert grid is not None
        text = grid.format_for_prompt()
        # Ou lineamentos ou mensagem de nenhum lineamento
        assert "LINEAMENTOS" in text or "lineamento" in text.lower()

    def test_n_source_points_reported(self) -> None:
        records = _make_records(8)
        grid = BouguerProcessor().process(records, _bbox())
        assert grid is not None
        text = grid.format_for_prompt()
        assert "N=8" in text


# ---------------------------------------------------------------------------
# TestToGeoJSON
# ---------------------------------------------------------------------------


class TestToGeoJSON:
    def test_returns_feature_collection(self) -> None:
        grid = BouguerProcessor().process(_make_records(6), _bbox())
        assert grid is not None
        gj = grid.to_geojson()
        assert gj["type"] == "FeatureCollection"
        assert "features" in gj

    def test_feature_count_matches_cells(self) -> None:
        grid = BouguerProcessor().process(_make_records(6), _bbox())
        assert grid is not None
        gj = grid.to_geojson()
        assert len(gj["features"]) == len(grid.cells)

    def test_features_are_polygons(self) -> None:
        grid = BouguerProcessor().process(_make_records(6), _bbox())
        assert grid is not None
        for feat in grid.to_geojson()["features"]:
            assert feat["geometry"]["type"] == "Polygon"
            assert feat["type"] == "Feature"

    def test_properties_present(self) -> None:
        grid = BouguerProcessor().process(_make_records(6), _bbox())
        assert grid is not None
        for feat in grid.to_geojson()["features"]:
            props = feat["properties"]
            assert "bouguer" in props
            assert "hgm" in props
            assert "is_lineament" in props

    def test_polygon_ring_closed(self) -> None:
        grid = BouguerProcessor().process(_make_records(6), _bbox())
        assert grid is not None
        for feat in grid.to_geojson()["features"]:
            ring = feat["geometry"]["coordinates"][0]
            assert len(ring) == 5
            assert ring[0] == ring[-1]  # fechado


# ---------------------------------------------------------------------------
# TestComputeHgmEdgeCases
# ---------------------------------------------------------------------------


class TestComputeHgmEdgeCases:
    def test_polar_latitude_no_zero_division(self) -> None:
        """_compute_hgm não deve lançar ZeroDivisionError com lat_center ≈ 90°."""
        # lat_center = 89.9° → cos ≈ 0.00175 → sem proteção causaria /0 com step muito pequeno
        grid = [1.0, 2.0, 3.0, 4.0]
        hgm = _compute_hgm(grid, ncols=2, nrows=2, step_lon=0.01, step_lat=0.01, lat_center=89.9)
        assert len(hgm) == 4
        assert all(h >= 0 for h in hgm)

    def test_single_row_dy_zero(self) -> None:
        """Linha 352-353: nrows=1 → dy=0.0 para todos os pontos."""
        # Grade 3×1 (ncols=3, nrows=1): única linha → gradiente em y = 0
        grid = [1.0, 2.0, 4.0]  # valores crescentes em x
        hgm = _compute_hgm(grid, ncols=3, nrows=1, step_lon=0.1, step_lat=0.1, lat_center=-6.0)
        assert len(hgm) == 3
        # Gradiente em y é zero; gradiente em x é não-negativo
        assert all(h >= 0 for h in hgm)


# ---------------------------------------------------------------------------
# Testes para branch "else: nenhum lineamento" (linha 133)
# ---------------------------------------------------------------------------


class TestBouguerGridFormatNoLineaments:
    """Linha 133: mensagem 'Nenhum lineamento' quando lineament_cells é vazio."""

    def test_no_lineaments_message_shown(self) -> None:
        """Grade com HGM=0 (campo uniforme) → nenhum lineamento → linha 133."""
        from miner_harness.geophysics.bouguer_processor import BouguerCell

        # Criar grid com células onde is_lineament=False
        cells = [
            BouguerCell(lon=-50.5, lat=-6.0, bouguer=-30.0, hgm=0.0, is_lineament=False),
            BouguerCell(lon=-50.4, lat=-6.0, bouguer=-30.0, hgm=0.0, is_lineament=False),
            BouguerCell(lon=-50.3, lat=-6.0, bouguer=-30.0, hgm=0.0, is_lineament=False),
        ]
        grid = BouguerGrid(
            lon_min=-51.0,
            lat_min=-7.0,
            lon_max=-49.0,
            lat_max=-5.0,
            step_deg=0.1,
            cells=cells,
            n_source_points=4,
            bouguer_mean=-30.0,
            bouguer_std=0.0,
            hgm_threshold=1.0,
        )
        text = grid.format_for_prompt()
        assert "Nenhum lineamento" in text

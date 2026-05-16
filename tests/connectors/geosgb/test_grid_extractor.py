"""Testes do GridExtractor — geração de grid e deduplicação."""

from __future__ import annotations

import pytest

from miner_harness.connectors.geosgb.grid_extractor import (
    GridDensity,
    build_identify_params,
    deduplicate_features,
    generate_grid,
)
from miner_harness.core.types import BoundingBox


class TestGridDensity:
    """Testes dos valores de densidade."""

    def test_low_density(self) -> None:
        assert GridDensity.LOW.points_per_degree == 2.0
        assert GridDensity.LOW.tolerance == 100

    def test_medium_density(self) -> None:
        assert GridDensity.MEDIUM.points_per_degree == 4.0
        assert GridDensity.MEDIUM.tolerance == 50

    def test_high_density(self) -> None:
        assert GridDensity.HIGH.points_per_degree == 8.0
        assert GridDensity.HIGH.tolerance == 25


class TestGenerateGrid:
    """Testes da geração de grid."""

    def test_minimum_2x2_grid(self) -> None:
        """Bbox muito pequeno ainda gera pelo menos 2x2 pontos."""
        bbox = BoundingBox(lon_min=-50.0, lat_min=-6.0, lon_max=-49.99, lat_max=-5.99)
        points = generate_grid(bbox, GridDensity.LOW)
        assert len(points) >= 4

    def test_grid_covers_corners(self) -> None:
        """Grid deve incluir pontos nos cantos do bbox."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        points = generate_grid(bbox, GridDensity.LOW)
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        assert min(lons) == pytest.approx(bbox.lon_min)
        assert max(lons) == pytest.approx(bbox.lon_max)
        assert min(lats) == pytest.approx(bbox.lat_min)
        assert max(lats) == pytest.approx(bbox.lat_max)

    def test_higher_density_more_points(self) -> None:
        """Densidade alta gera mais pontos que baixa."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        low = generate_grid(bbox, GridDensity.LOW)
        high = generate_grid(bbox, GridDensity.HIGH)
        assert len(high) > len(low)

    def test_medium_carajas_region(self) -> None:
        """Grid MEDIUM para Carajas gera quantidade esperada."""
        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        points = generate_grid(bbox, GridDensity.MEDIUM)
        # 2.5 graus * 4 ppd + 1 = 11 lon, 2.0 * 4 + 1 = 9 lat -> 99
        assert len(points) == 11 * 9

    def test_all_points_within_bbox(self) -> None:
        """Todos os pontos devem estar dentro do bbox."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        points = generate_grid(bbox, GridDensity.MEDIUM)
        for lon, lat in points:
            assert bbox.lon_min <= lon <= bbox.lon_max
            assert bbox.lat_min <= lat <= bbox.lat_max


class TestDeduplicateFeatures:
    """Testes da deduplicação."""

    def test_removes_duplicates(self) -> None:
        features = [
            {"objectid": 1, "name": "A"},
            {"objectid": 2, "name": "B"},
            {"objectid": 1, "name": "A"},  # duplicata
        ]
        unique = deduplicate_features(features)
        assert len(unique) == 2
        assert unique[0]["objectid"] == 1
        assert unique[1]["objectid"] == 2

    def test_preserves_first_occurrence(self) -> None:
        features = [
            {"objectid": 1, "extra": "first"},
            {"objectid": 1, "extra": "second"},
        ]
        unique = deduplicate_features(features)
        assert len(unique) == 1
        assert unique[0]["extra"] == "first"

    def test_keeps_features_without_key(self) -> None:
        features = [
            {"name": "no-id-1"},
            {"name": "no-id-2"},
        ]
        unique = deduplicate_features(features)
        assert len(unique) == 2

    def test_empty_list(self) -> None:
        assert deduplicate_features([]) == []

    def test_custom_key(self) -> None:
        features = [
            {"id": 1, "val": "a"},
            {"id": 1, "val": "b"},
            {"id": 2, "val": "c"},
        ]
        unique = deduplicate_features(features, key="id")
        assert len(unique) == 2


class TestBuildIdentifyParams:
    """Testes da construção de parâmetros identify."""

    def test_basic_params(self) -> None:
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        params = build_identify_params((-50.0, -6.0), bbox)
        assert params["f"] == "json"
        assert params["geometry"] == "-50.0,-6.0"
        assert params["geometryType"] == "esriGeometryPoint"
        assert params["sr"] == "4326"
        assert params["layers"] == "all"
        assert params["tolerance"] == "50"
        assert params["returnGeometry"] == "true"

    def test_specific_layers(self) -> None:
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        params = build_identify_params((-50.0, -6.0), bbox, layers=[0, 2, 5])
        assert params["layers"] == "visible:0,2,5"

    def test_custom_tolerance(self) -> None:
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        params = build_identify_params((-50.0, -6.0), bbox, tolerance=25)
        assert params["tolerance"] == "25"

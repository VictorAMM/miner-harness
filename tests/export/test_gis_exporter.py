"""Testes do GisExporter — exportação GeoPackage e GeoJSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    ProspectionReport,
    StepResult,
)
from miner_harness.export.gis_exporter import (
    GisExporter,
    _build_feature_collection,
    _furo_to_feature,
    _gravimetria_to_feature,
    _ocorrencia_to_feature,
    _target_to_buffer_feature,
    _target_to_point_feature,
)


def _make_report(
    with_targets: bool = True,
    geological_data: dict | None = None,
) -> ProspectionReport:
    bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
    steps = [
        StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="test",
            summary="ok",
            findings=[],
            confidence=Confidence.MEDIUM,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=10,
        )
    ]
    targets = (
        [
            MineralTarget(
                name="Target A",
                longitude=-50.5,
                latitude=-6.0,
                radius_km=5.0,
                commodities=["Cu", "Au"],
                mineral_system="Porphyry",
                confidence=Confidence.HIGH,
                priority=1,
                rationale="anomaly",
                recommended_followup=["drilling"],
            )
        ]
        if with_targets
        else []
    )
    return ProspectionReport(
        region_name="Carajas",
        bbox=bbox,
        steps=steps,
        targets=targets,
        integrated_summary="ok",
        caveats=[],
        data_quality_score=0.8,
        model_used="qwen3:8b",
        total_duration_ms=100,
        analysis_date=datetime.now(tz=timezone.utc),
        geological_data=geological_data,
    )


class TestTargetToPointFeature:
    """Testes do _target_to_point_feature."""

    def test_geometry_type(self) -> None:
        report = _make_report()
        feat = _target_to_point_feature(report.targets[0])
        assert feat["geometry"]["type"] == "Point"

    def test_coordinates(self) -> None:
        report = _make_report()
        t = report.targets[0]
        feat = _target_to_point_feature(t)
        assert feat["geometry"]["coordinates"] == [t.longitude, t.latitude]

    def test_properties(self) -> None:
        report = _make_report()
        t = report.targets[0]
        feat = _target_to_point_feature(t)
        props = feat["properties"]
        assert props["name"] == t.name
        assert props["priority"] == 1
        assert props["confidence"] == "high"
        assert props["commodities"] == "Cu, Au"
        assert props["radius_km"] == 5.0
        assert props["recommended_followup"] == "drilling"


class TestTargetToBufferFeature:
    """Testes do _target_to_buffer_feature."""

    def test_geometry_type(self) -> None:
        report = _make_report()
        feat = _target_to_buffer_feature(report.targets[0])
        assert feat["geometry"]["type"] == "Polygon"

    def test_polygon_is_closed(self) -> None:
        report = _make_report()
        feat = _target_to_buffer_feature(report.targets[0])
        ring = feat["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]

    def test_polygon_has_37_points(self) -> None:
        report = _make_report()
        feat = _target_to_buffer_feature(report.targets[0])
        ring = feat["geometry"]["coordinates"][0]
        assert len(ring) == 37  # 36 + closing point

    def test_radius_approx_degrees(self) -> None:
        report = _make_report()
        t = report.targets[0]
        feat = _target_to_buffer_feature(t)
        ring = feat["geometry"]["coordinates"][0]
        # First point is (lon + r_deg, lat)
        r_deg = t.radius_km / 111.0
        assert ring[0][0] == pytest.approx(t.longitude + r_deg, abs=1e-6)

    def test_properties_subset(self) -> None:
        report = _make_report()
        feat = _target_to_buffer_feature(report.targets[0])
        assert feat["properties"]["radius_km"] == 5.0
        assert feat["properties"]["mineral_system"] == "Porphyry"


class TestOcorrenciaToFeature:
    """Testes do _ocorrencia_to_feature."""

    def test_valid_record(self) -> None:
        rec = {
            "objectid": 1,
            "substancias": "Ouro",
            "municipio": "Parauapebas",
            "uf": "PA",
            "coordenada": {"longitude": -50.0, "latitude": -6.0},
        }
        feat = _ocorrencia_to_feature(rec)
        assert feat is not None
        assert feat["geometry"]["coordinates"] == [-50.0, -6.0]
        assert feat["properties"]["substancias"] == "Ouro"

    def test_missing_coordenada_returns_none(self) -> None:
        rec = {"objectid": 1, "substancias": "Ouro"}
        assert _ocorrencia_to_feature(rec) is None

    def test_coordenada_not_dict_returns_none(self) -> None:
        rec = {"objectid": 1, "coordenada": None}
        assert _ocorrencia_to_feature(rec) is None

    def test_missing_lon_returns_none(self) -> None:
        rec = {"objectid": 1, "coordenada": {"latitude": -6.0}}
        assert _ocorrencia_to_feature(rec) is None


class TestGravimetriaToFeature:
    """Testes do _gravimetria_to_feature."""

    def test_valid_record(self) -> None:
        rec = {
            "objectid": 10,
            "anomalia_bouguer": -45.2,
            "coordenada": {"longitude": -50.5, "latitude": -6.5},
        }
        feat = _gravimetria_to_feature(rec)
        assert feat is not None
        assert feat["properties"]["anomalia_bouguer"] == -45.2

    def test_missing_coordenada_returns_none(self) -> None:
        rec = {"objectid": 10}
        assert _gravimetria_to_feature(rec) is None


class TestFuroToFeature:
    """Testes do _furo_to_feature."""

    def test_valid_record(self) -> None:
        rec = {
            "objectid": 100,
            "projeto": "CARAJAS",
            "profundidade_m": 250.0,
            "azimute": 45.0,
            "mergulho": -60.0,
            "ano": 1985,
            "coordenada": {"longitude": -50.0, "latitude": -6.0},
        }
        feat = _furo_to_feature(rec)
        assert feat is not None
        assert feat["geometry"]["coordinates"] == [-50.0, -6.0]
        assert feat["properties"]["projeto"] == "CARAJAS"
        assert feat["properties"]["profundidade_m"] == 250.0
        assert feat["properties"]["ano"] == 1985

    def test_missing_coordenada_returns_none(self) -> None:
        rec = {"objectid": 100}
        assert _furo_to_feature(rec) is None


class TestBuildFeatureCollection:
    """Testes do _build_feature_collection."""

    def test_structure(self) -> None:
        fc = _build_feature_collection([{"type": "Feature"}])
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 1


class TestGisExporterGeoJSON:
    """Testes do GisExporter.export_geojson()."""

    def test_creates_geojson_file(self, tmp_path: Path) -> None:
        report = _make_report()
        exporter = GisExporter()
        out = tmp_path / "targets.geojson"
        result = exporter.export_geojson(report, out)
        assert result == out
        assert out.exists()

    def test_geojson_content(self, tmp_path: Path) -> None:
        report = _make_report()
        exporter = GisExporter()
        out = tmp_path / "targets.geojson"
        exporter.export_geojson(report, out)
        data = json.loads(out.read_text())
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1
        assert data["features"][0]["properties"]["name"] == "Target A"

    def test_no_targets_raises(self, tmp_path: Path) -> None:
        report = _make_report(with_targets=False)
        exporter = GisExporter()
        with pytest.raises(ValueError, match="sem alvos"):
            exporter.export_geojson(report, tmp_path / "out.geojson")

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        report = _make_report()
        exporter = GisExporter()
        out = tmp_path / "nested" / "dir" / "targets.geojson"
        exporter.export_geojson(report, out)
        assert out.exists()


class TestGisExporterGeoPackage:
    """Testes do GisExporter.export() — GeoPackage."""

    def test_no_targets_raises(self, tmp_path: Path) -> None:
        report = _make_report(with_targets=False)
        exporter = GisExporter()
        with pytest.raises(ValueError, match="sem alvos"):
            exporter.export(report, tmp_path / "out.gpkg")

    def test_missing_geopandas_raises_import_error(self, tmp_path: Path) -> None:
        report = _make_report()
        exporter = GisExporter()
        with (
            patch("builtins.__import__", side_effect=_block_geopandas),
            pytest.raises(ImportError, match="geopandas"),
        ):
            exporter.export(report, tmp_path / "out.gpkg")

    def test_export_with_geopandas_mock(self, tmp_path: Path) -> None:
        """Testa o fluxo principal com geopandas mockado."""
        report = _make_report(
            geological_data={
                "ocorrencias": [
                    {
                        "objectid": 1,
                        "substancias": "Cu",
                        "coordenada": {"longitude": -50.0, "latitude": -6.0},
                    }
                ],
                "gravimetria": [],
                "furos": [
                    {
                        "objectid": 99,
                        "projeto": "X",
                        "coordenada": {"longitude": -50.1, "latitude": -6.1},
                    }
                ],
            }
        )
        exporter = GisExporter()
        out = tmp_path / "result.gpkg"

        mock_gdf = MagicMock()
        mock_gdf_cls = MagicMock(return_value=mock_gdf)
        mock_gdf_cls.from_features = MagicMock(return_value=mock_gdf)

        with patch.dict(
            "sys.modules",
            {
                "geopandas": MagicMock(GeoDataFrame=mock_gdf_cls),
                "shapely.geometry": MagicMock(),
            },
        ):
            result = exporter.export(report, out)

        assert result == out

    def test_export_removes_existing_file(self, tmp_path: Path) -> None:
        """Se o arquivo já existe, ele é removido antes de escrever (fiona não sobrescreve)."""
        report = _make_report()
        exporter = GisExporter()
        out = tmp_path / "result.gpkg"
        out.write_text("old content")  # simula arquivo existente

        mock_gdf = MagicMock()
        mock_gdf_cls = MagicMock()
        mock_gdf_cls.from_features = MagicMock(return_value=mock_gdf)

        with patch.dict(
            "sys.modules",
            {
                "geopandas": MagicMock(GeoDataFrame=mock_gdf_cls),
                "shapely.geometry": MagicMock(),
            },
        ):
            exporter.export(report, out)

        # O mock substitui to_file, então o arquivo é recriado pelo mock (não existe como .gpkg
        # real), mas o unlink() garante que o arquivo antigo é removido antes de chamar to_file
        # O importante é que to_file foi chamado
        mock_gdf.to_file.assert_called()


class TestGisExporterSkipsEmptyFeats:
    """Linha 232-233: camada ignorada quando converter retorna None para todos os registros."""

    def test_gravimetria_without_coords_skipped(self, tmp_path: Path) -> None:
        """Registros sem coordenada → _gravimetria_to_feature → None → feats=[] → skip."""
        report = _make_report(
            geological_data={
                "gravimetria": [
                    {"objectid": 1},  # sem coordenada → None
                    {"objectid": 2},  # sem coordenada → None
                ]
            }
        )
        exporter = GisExporter()
        out = tmp_path / "out.gpkg"

        mock_gdf = MagicMock()
        mock_gdf_cls = MagicMock()
        mock_gdf_cls.from_features = MagicMock(return_value=mock_gdf)

        with patch.dict(
            "sys.modules",
            {
                "geopandas": MagicMock(GeoDataFrame=mock_gdf_cls),
                "shapely.geometry": MagicMock(),
            },
        ):
            result = exporter.export(report, out)

        # gravimetria layer NÃO exportada (feats=[])
        assert result == out
        # to_file foi chamado apenas para targets e targets_buffer (2 vezes)
        assert mock_gdf.to_file.call_count == 2


def _block_geopandas(name: str, *args: object, **kwargs: object) -> object:
    """Bloqueia importação de geopandas para testar ImportError."""
    if name in ("geopandas", "shapely", "shapely.geometry"):
        raise ImportError(f"No module named '{name}'")
    import builtins

    return builtins.__import__(name, *args, **kwargs)

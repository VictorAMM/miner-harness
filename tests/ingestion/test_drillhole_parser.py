"""Testes de DrillholeParser — leitura e normalização de CSV de furos."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from miner_harness.ingestion.drillhole_parser import DrillholeParser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_csv(tmp_path: Path, content: str, filename: str = "furos.csv") -> Path:
    """Escreve conteúdo CSV em arquivo temporário e retorna o path."""
    path = tmp_path / filename
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def _write_csv_bom(tmp_path: Path, content: str) -> Path:
    """Escreve CSV com BOM UTF-8."""
    path = tmp_path / "furos_bom.csv"
    path.write_bytes(b"\xef\xbb\xbf" + textwrap.dedent(content).encode("utf-8"))
    return path


# ---------------------------------------------------------------------------
# TestParse — leitura básica
# ---------------------------------------------------------------------------


class TestParse:
    def test_empty_csv_returns_empty_list(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "hole_id,x,y\n")
        records = DrillholeParser.parse(path)
        assert records == []

    def test_minimal_columns_hole_id_only(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "hole_id\nDH-001\nDH-001\n")
        records = DrillholeParser.parse(path)
        assert len(records) == 2
        assert records[0]["hole_id"] == "DH-001"

    def test_column_aliases_en(self, tmp_path: Path) -> None:
        path = _write_csv(
            tmp_path,
            """\
            hole_id,x,y,z,from,to,lithology,alteration
            DH-001,-51.0,-6.5,400.0,0.0,5.0,Granito,propilítica
            """,
        )
        records = DrillholeParser.parse(path)
        assert len(records) == 1
        r = records[0]
        assert r["hole_id"] == "DH-001"
        assert r["x"] == pytest.approx(-51.0)
        assert r["y"] == pytest.approx(-6.5)
        assert r["z"] == pytest.approx(400.0)
        assert r["from_m"] == pytest.approx(0.0)
        assert r["to_m"] == pytest.approx(5.0)
        assert r["lithology"] == "Granito"
        assert r["alteration"] == "propilítica"

    def test_column_aliases_pt(self, tmp_path: Path) -> None:
        path = _write_csv(
            tmp_path,
            """\
            sondagem,longitude,latitude,elevação,de,ate
            FU-01,-50.5,-7.1,350.0,10.0,15.5
            """,
        )
        records = DrillholeParser.parse(path)
        r = records[0]
        assert r["hole_id"] == "FU-01"
        assert r["x"] == pytest.approx(-50.5)
        assert r["y"] == pytest.approx(-7.1)
        assert r["from_m"] == pytest.approx(10.0)
        assert r["to_m"] == pytest.approx(15.5)

    def test_column_alias_bhid(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "bhid,x,y\nRC-99,-49.0,-5.5\n")
        records = DrillholeParser.parse(path)
        assert records[0]["hole_id"] == "RC-99"

    def test_numeric_conversion(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "hole_id,x,y,from_m,to_m\nA,-51.5,-6.0,0.0,10.0\n")
        r = DrillholeParser.parse(path)[0]
        assert isinstance(r["x"], float)
        assert isinstance(r["from_m"], float)

    def test_comma_decimal_separator(self, tmp_path: Path) -> None:
        # Values with comma as decimal separator must be quoted in CSV
        path = _write_csv(tmp_path, 'hole_id,x,y\nA,"-51,5","-6,1"\n')
        r = DrillholeParser.parse(path)[0]
        assert r["x"] == pytest.approx(-51.5)
        assert r["y"] == pytest.approx(-6.1)

    def test_invalid_numeric_returns_none(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "hole_id,x,y\nA,n/a,—\n")
        r = DrillholeParser.parse(path)[0]
        assert r["x"] is None
        assert r["y"] is None

    def test_blank_numeric_cells_return_none(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "hole_id,x,y,from_m,to_m\nA,,,, \n")
        r = DrillholeParser.parse(path)[0]
        assert r["x"] is None
        assert r["from_m"] is None

    def test_extra_analytic_columns(self, tmp_path: Path) -> None:
        path = _write_csv(
            tmp_path,
            "hole_id,x,y,Au,Cu_ppm\nDH-1,-50.0,-6.0,1.23,45.0\n",
        )
        r = DrillholeParser.parse(path)[0]
        assert r["au"] == pytest.approx(1.23)
        assert r["cu_ppm"] == pytest.approx(45.0)

    def test_extra_analytic_blank_returns_none(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "hole_id,x,y,Au\nA,-50,-6,\n")
        r = DrillholeParser.parse(path)[0]
        assert r["au"] is None

    def test_missing_hole_id_raises_value_error(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "coluna_estranha,x,y\nval,-50,-6\n")
        with pytest.raises(ValueError, match="identificação"):
            DrillholeParser.parse(path)

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            DrillholeParser.parse("/caminho/nao/existe.csv")

    def test_utf8_bom_handled(self, tmp_path: Path) -> None:
        path = _write_csv_bom(tmp_path, "hole_id,x,y\nBOM-01,-50.0,-6.0\n")
        records = DrillholeParser.parse(path)
        assert records[0]["hole_id"] == "BOM-01"

    def test_defaults_for_missing_optional_columns(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, "hole_id\nDH-X\n")
        r = DrillholeParser.parse(path)[0]
        assert r["lithology"] == ""
        assert r["alteration"] == ""
        assert r["x"] is None
        assert r["y"] is None
        assert r["z"] is None
        assert r["from_m"] is None
        assert r["to_m"] is None

    def test_multiple_rows(self, tmp_path: Path) -> None:
        path = _write_csv(
            tmp_path,
            """\
            hole_id,x,y,from_m,to_m
            A,-51.0,-6.0,0.0,5.0
            A,-51.0,-6.0,5.0,10.0
            B,-51.1,-6.1,0.0,3.0
            """,
        )
        records = DrillholeParser.parse(path)
        assert len(records) == 3
        assert records[0]["hole_id"] == "A"
        assert records[2]["hole_id"] == "B"


# ---------------------------------------------------------------------------
# TestFormatForPrompt
# ---------------------------------------------------------------------------


class TestFormatForPrompt:
    def test_empty_records_returns_message(self) -> None:
        text = DrillholeParser.format_for_prompt([])
        assert "Nenhum" in text

    def test_single_record_contains_hole_id(self) -> None:
        records = [
            {
                "hole_id": "DH-001",
                "x": -51.0,
                "y": -6.5,
                "z": None,
                "from_m": 0.0,
                "to_m": 5.0,
                "lithology": "Granito",
                "alteration": "propilítica",
            }
        ]
        text = DrillholeParser.format_for_prompt(records)
        assert "DH-001" in text
        assert "Granito" in text
        assert "propilítica" in text
        assert "0.0" in text
        assert "5.0m" in text

    def test_analytic_values_in_output(self) -> None:
        records = [
            {
                "hole_id": "A",
                "x": -50.0,
                "y": -6.0,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
                "au": 1.5,
                "cu_ppm": 300.0,
            }
        ]
        text = DrillholeParser.format_for_prompt(records)
        assert "AU=" in text or "au=" in text.lower()

    def test_max_records_limit(self) -> None:
        records = [
            {
                "hole_id": f"H{i}",
                "x": None,
                "y": None,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
            }
            for i in range(50)
        ]
        text = DrillholeParser.format_for_prompt(records, max_records=3)
        # Only 3 actual records, then truncation notice
        assert "H0" in text
        assert "H2" in text
        assert "omitidos" in text

    def test_max_chars_limit(self) -> None:
        records = [
            {
                "hole_id": f"H{i:05d}",
                "x": -50.0,
                "y": -6.0,
                "z": None,
                "from_m": float(i),
                "to_m": float(i + 5),
                "lithology": "X" * 80,
                "alteration": "Y" * 80,
            }
            for i in range(100)
        ]
        text = DrillholeParser.format_for_prompt(records, max_chars=500)
        assert len(text) <= 600  # within reasonable margin
        assert "omitidos" in text

    def test_header_shows_total_count(self) -> None:
        records = [
            {
                "hole_id": "A",
                "x": None,
                "y": None,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
            },
            {
                "hole_id": "B",
                "x": None,
                "y": None,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
            },
        ]
        text = DrillholeParser.format_for_prompt(records)
        assert "2 trechos" in text


# ---------------------------------------------------------------------------
# TestToGeoJSON
# ---------------------------------------------------------------------------


class TestToGeoJSON:
    def test_empty_records_returns_empty_collection(self) -> None:
        gj = DrillholeParser.to_geojson([])
        assert gj["type"] == "FeatureCollection"
        assert gj["features"] == []

    def test_records_without_coords_excluded(self) -> None:
        records = [
            {
                "hole_id": "A",
                "x": None,
                "y": None,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
            },
        ]
        gj = DrillholeParser.to_geojson(records)
        assert gj["features"] == []

    def test_valid_record_produces_point_feature(self) -> None:
        records = [
            {
                "hole_id": "DH-1",
                "x": -51.0,
                "y": -6.5,
                "z": 400.0,
                "from_m": 0.0,
                "to_m": 5.0,
                "lithology": "Granito",
                "alteration": "",
            },
        ]
        gj = DrillholeParser.to_geojson(records)
        assert len(gj["features"]) == 1
        feat = gj["features"][0]
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "Point"
        assert feat["geometry"]["coordinates"] == [-51.0, -6.5]
        assert feat["properties"]["hole_id"] == "DH-1"
        assert feat["properties"]["lithology"] == "Granito"

    def test_collar_deduplication_per_hole_id(self) -> None:
        # Three trechos for the same hole — only the first (collar) should appear
        records = [
            {
                "hole_id": "DH-1",
                "x": -51.0,
                "y": -6.0,
                "z": None,
                "from_m": 0.0,
                "to_m": 5.0,
                "lithology": "A",
                "alteration": "",
            },
            {
                "hole_id": "DH-1",
                "x": -51.0,
                "y": -6.0,
                "z": None,
                "from_m": 5.0,
                "to_m": 10.0,
                "lithology": "B",
                "alteration": "",
            },
            {
                "hole_id": "DH-1",
                "x": -51.0,
                "y": -6.0,
                "z": None,
                "from_m": 10.0,
                "to_m": 15.0,
                "lithology": "C",
                "alteration": "",
            },
        ]
        gj = DrillholeParser.to_geojson(records)
        assert len(gj["features"]) == 1
        assert gj["features"][0]["properties"]["lithology"] == "A"

    def test_distinct_holes_all_appear(self) -> None:
        records = [
            {
                "hole_id": f"DH-{i}",
                "x": -51.0 + i * 0.01,
                "y": -6.0,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
            }
            for i in range(5)
        ]
        gj = DrillholeParser.to_geojson(records)
        assert len(gj["features"]) == 5

    def test_assay_data_in_properties(self) -> None:
        records = [
            {
                "hole_id": "A",
                "x": -50.0,
                "y": -6.0,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
                "au": 2.5,
                "cu_ppm": 100.0,
            },
        ]
        gj = DrillholeParser.to_geojson(records)
        props = gj["features"][0]["properties"]
        assert props["au"] == pytest.approx(2.5)
        assert props["cu_ppm"] == pytest.approx(100.0)

    def test_nan_coords_excluded(self) -> None:
        import math

        records = [
            {
                "hole_id": "A",
                "x": math.nan,
                "y": -6.0,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
            },
        ]
        gj = DrillholeParser.to_geojson(records)
        assert gj["features"] == []

    def test_geojson_structure_valid(self) -> None:
        records = [
            {
                "hole_id": "X",
                "x": -50.0,
                "y": -5.0,
                "z": None,
                "from_m": None,
                "to_m": None,
                "lithology": "",
                "alteration": "",
            },
        ]
        gj = DrillholeParser.to_geojson(records)
        assert "type" in gj
        assert "features" in gj
        feat = gj["features"][0]
        assert "type" in feat
        assert "geometry" in feat
        assert "properties" in feat
        assert "coordinates" in feat["geometry"]

"""Testes do ANMConnector — concessões minerárias via SIGMINE WFS."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from miner_harness.connectors.anm.connector import ANMConnector, _centroid, _parse_feature
from miner_harness.core.config import ANMConfig
from miner_harness.core.types import BoundingBox

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BBOX = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)

POLYGON_FEATURE = {
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[-50.5, -6.5], [-50.0, -6.5], [-50.0, -6.0], [-50.5, -6.0], [-50.5, -6.5]]
        ],
    },
    "properties": {
        "PROCESSO": "860384/2007",
        "FASE": "Concessão de Lavra",
        "NOME": "Mineração Exemplo S.A.",
        "SUBSTANCIA": "FERRO",
        "UF": "PA",
        "AREA_HA": "1500.5",
        "ANO": "2007",
    },
}

POINT_FEATURE = {
    "geometry": {"type": "Point", "coordinates": [-50.2, -6.1]},
    "properties": {
        "PROCESSO": "123/2010",
        "FASE": "Autorização de Pesquisa",
        "NOME": "Empresa Mineral Ltda",
        "SUBSTANCIA": "OURO",
        "UF": "PA",
        "AREA_HA": "200.0",
        "ANO": "2010",
    },
}

GEOJSON_RESPONSE = {
    "type": "FeatureCollection",
    "features": [POLYGON_FEATURE, POINT_FEATURE],
}


def _make_config(**kwargs: object) -> ANMConfig:
    return ANMConfig(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests — _centroid
# ---------------------------------------------------------------------------


class TestCentroid:
    def test_point(self) -> None:
        lon, lat = _centroid("Point", [-50.0, -6.0])
        assert lon == -50.0
        assert lat == -6.0

    def test_multipoint(self) -> None:
        lon, lat = _centroid("MultiPoint", [[-50.0, -6.0], [-51.0, -7.0]])
        assert lon == pytest.approx(-50.5)
        assert lat == pytest.approx(-6.5)

    def test_linestring(self) -> None:
        lon, lat = _centroid("LineString", [[-50.0, -6.0], [-51.0, -7.0]])
        assert lon == pytest.approx(-50.5)
        assert lat == pytest.approx(-6.5)

    def test_multilinestring(self) -> None:
        lon, lat = _centroid("MultiLineString", [[[-50.0, -6.0], [-51.0, -7.0]]])
        assert lon == pytest.approx(-50.5)

    def test_polygon(self) -> None:
        ring = [[-50.5, -6.5], [-50.0, -6.5], [-50.0, -6.0], [-50.5, -6.0], [-50.5, -6.5]]
        lon, lat = _centroid("Polygon", [ring])
        assert -51.0 < lon < -49.0
        assert -7.0 < lat < -5.0

    def test_multipolygon(self) -> None:
        ring = [[-50.5, -6.5], [-50.0, -6.5], [-50.0, -6.0], [-50.5, -6.0], [-50.5, -6.5]]
        lon, lat = _centroid("MultiPolygon", [[[ring[0], ring[1], ring[2]]]])
        assert isinstance(lon, float)

    def test_unsupported_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported geometry type"):
            _centroid("GeometryCollection", [])


# ---------------------------------------------------------------------------
# Tests — _parse_feature
# ---------------------------------------------------------------------------


class TestParseFeature:
    def test_polygon_parsed(self) -> None:
        result = _parse_feature(0, POLYGON_FEATURE)
        assert result is not None
        assert result.processo == "860384/2007"
        assert result.fase == "Concessão de Lavra"
        assert result.nome_titular == "Mineração Exemplo S.A."
        assert result.substancias == "FERRO"
        assert result.uf == "PA"
        assert result.area_ha == pytest.approx(1500.5)
        assert result.ano == 2007

    def test_point_parsed(self) -> None:
        result = _parse_feature(1, POINT_FEATURE)
        assert result is not None
        assert result.coordenada.longitude == pytest.approx(-50.2)
        assert result.coordenada.latitude == pytest.approx(-6.1)

    def test_no_geometry_returns_none(self) -> None:
        feat = {"geometry": None, "properties": {}}
        assert _parse_feature(0, feat) is None

    def test_empty_coordinates_returns_none(self) -> None:
        feat = {"geometry": {"type": "Point", "coordinates": []}, "properties": {}}
        assert _parse_feature(0, feat) is None

    def test_out_of_brazil_bounds_returns_none(self) -> None:
        feat = {
            "geometry": {"type": "Point", "coordinates": [10.0, 50.0]},
            "properties": {},
        }
        assert _parse_feature(0, feat) is None

    def test_invalid_area_ha_becomes_none(self) -> None:
        feat = {**POINT_FEATURE, "properties": {**POINT_FEATURE["properties"], "AREA_HA": "bad"}}
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.area_ha is None

    def test_invalid_ano_becomes_none(self) -> None:
        feat = {**POINT_FEATURE, "properties": {**POINT_FEATURE["properties"], "ANO": "bad"}}
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.ano is None

    def test_uf_truncated_to_2_chars(self) -> None:
        feat = {**POINT_FEATURE, "properties": {**POINT_FEATURE["properties"], "UF": "PARA"}}
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.uf == "PA"

    def test_alternate_field_names(self) -> None:
        feat = {
            "geometry": {"type": "Point", "coordinates": [-50.0, -6.0]},
            "properties": {
                "NR_PROCESSO": "999/2020",
                "NOME_REQUERENTE": "Outra Empresa",
                "SUBSTANCIAS": "COBRE, OURO",
            },
        }
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.processo == "999/2020"
        assert result.nome_titular == "Outra Empresa"
        assert result.substancias == "COBRE, OURO"


# ---------------------------------------------------------------------------
# Tests — ANMConnector.concessoes
# ---------------------------------------------------------------------------


class TestANMConnector:
    @pytest.mark.asyncio
    async def test_returns_empty_when_disabled(self) -> None:
        cfg = _make_config(enabled=False)
        connector = ANMConnector(cfg)
        result = await connector.concessoes(BBOX)
        assert result == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_returns_parsed_features(self) -> None:
        cfg = _make_config(enabled=True)
        connector = ANMConnector(cfg)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=GEOJSON_RESPONSE)

        with patch.object(connector._client, "get", new=AsyncMock(return_value=mock_resp)):
            result = await connector.concessoes(BBOX)

        assert len(result) == 2
        assert result[0].processo == "860384/2007"
        assert result[1].processo == "123/2010"
        await connector.close()

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self) -> None:
        cfg = _make_config(enabled=True)
        connector = ANMConnector(cfg)

        err = AsyncMock(side_effect=Exception("timeout"))
        with patch.object(connector._client, "get", new=err):
            result = await connector.concessoes(BBOX)

        assert result == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_empty_features_list(self) -> None:
        cfg = _make_config(enabled=True)
        connector = ANMConnector(cfg)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"type": "FeatureCollection", "features": []})

        with patch.object(connector._client, "get", new=AsyncMock(return_value=mock_resp)):
            result = await connector.concessoes(BBOX)

        assert result == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        cfg = _make_config(enabled=False)
        async with ANMConnector(cfg) as connector:
            result = await connector.concessoes(BBOX)
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_invalid_features(self) -> None:
        cfg = _make_config(enabled=True)
        connector = ANMConnector(cfg)

        geojson = {
            "features": [
                {"geometry": None, "properties": {}},
                POINT_FEATURE,
            ]
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=geojson)

        with patch.object(connector._client, "get", new=AsyncMock(return_value=mock_resp)):
            result = await connector.concessoes(BBOX)

        assert len(result) == 1
        await connector.close()

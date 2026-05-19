"""Testes do USGSConnector — eventos sísmicos via USGS Earthquake API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from miner_harness.connectors.usgs.connector import USGSConnector, _parse_feature
from miner_harness.core.config import USGSConfig
from miner_harness.core.types import BoundingBox

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BBOX = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)

FEATURE_M3 = {
    "geometry": {"type": "Point", "coordinates": [-50.5, -6.5, 10.0]},
    "properties": {
        "mag": 3.2,
        "depth": 10.0,
        "place": "50 km S of Altamira, Brazil",
        "time": 1716105600000,
    },
}

FEATURE_M2 = {
    "geometry": {"type": "Point", "coordinates": [-49.8, -5.9, 5.0]},
    "properties": {
        "mag": 2.1,
        "depth": 5.0,
        "place": "30 km NE of some city",
        "time": 1716019200000,
    },
}

GEOJSON_RESPONSE = {
    "type": "FeatureCollection",
    "features": [FEATURE_M3, FEATURE_M2],
}


def _make_config(**kwargs: object) -> USGSConfig:
    return USGSConfig(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests — _parse_feature
# ---------------------------------------------------------------------------


class TestParseFeature:
    def test_valid_feature_parsed(self) -> None:
        result = _parse_feature(0, FEATURE_M3)
        assert result is not None
        assert result.magnitude == pytest.approx(3.2)
        assert result.profundidade_km == pytest.approx(10.0)
        assert result.lugar == "50 km S of Altamira, Brazil"
        assert result.timestamp_ms == 1716105600000
        assert result.coordenada.longitude == pytest.approx(-50.5)
        assert result.coordenada.latitude == pytest.approx(-6.5)

    def test_no_geometry_returns_none(self) -> None:
        feat = {"geometry": None, "properties": {}}
        assert _parse_feature(0, feat) is None

    def test_empty_coordinates_returns_none(self) -> None:
        feat = {"geometry": {"type": "Point", "coordinates": []}, "properties": {}}
        assert _parse_feature(0, feat) is None

    def test_single_coordinate_returns_none(self) -> None:
        feat = {"geometry": {"type": "Point", "coordinates": [-50.0]}, "properties": {}}
        assert _parse_feature(0, feat) is None

    def test_out_of_brazil_bounds_returns_none(self) -> None:
        feat = {
            "geometry": {"type": "Point", "coordinates": [10.0, 50.0, 5.0]},
            "properties": {"mag": 3.0, "time": 0},
        }
        assert _parse_feature(0, feat) is None

    def test_missing_depth_defaults_to_zero(self) -> None:
        feat = {
            "geometry": {"type": "Point", "coordinates": [-50.0, -6.0]},
            "properties": {"mag": 2.5, "time": 12345},
        }
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.profundidade_km == pytest.approx(0.0)

    def test_invalid_magnitude_defaults_to_zero(self) -> None:
        feat = {
            "geometry": {"type": "Point", "coordinates": [-50.0, -6.0, 5.0]},
            "properties": {"mag": None, "time": 0},
        }
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.magnitude == pytest.approx(0.0)

    def test_missing_place_is_none(self) -> None:
        feat = {
            "geometry": {"type": "Point", "coordinates": [-50.0, -6.0, 5.0]},
            "properties": {"mag": 2.0, "time": 0},
        }
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.lugar is None

    def test_objectid_set_from_idx(self) -> None:
        result = _parse_feature(7, FEATURE_M3)
        assert result is not None
        assert result.objectid == 7

    def test_non_numeric_coordinates_returns_none(self) -> None:
        """coords com valor não numérico dispara TypeError (linhas 92-93)."""
        feat = {
            "geometry": {"type": "Point", "coordinates": ["bad", "data", 5.0]},
            "properties": {"mag": 2.0, "time": 0},
        }
        assert _parse_feature(0, feat) is None

    def test_non_numeric_magnitude_defaults_to_zero(self) -> None:
        """mag não numérico dispara ValueError (linhas 104-105)."""
        feat = {
            "geometry": {"type": "Point", "coordinates": [-50.0, -6.0, 5.0]},
            "properties": {"mag": "not_a_number", "time": 0},
        }
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.magnitude == pytest.approx(0.0)

    def test_non_numeric_timestamp_defaults_to_zero(self) -> None:
        """time não numérico dispara ValueError (linhas 109-110)."""
        feat = {
            "geometry": {"type": "Point", "coordinates": [-50.0, -6.0, 5.0]},
            "properties": {"mag": 2.5, "time": "not_a_timestamp"},
        }
        result = _parse_feature(0, feat)
        assert result is not None
        assert result.timestamp_ms == 0


# ---------------------------------------------------------------------------
# Tests — USGSConnector.sismos
# ---------------------------------------------------------------------------


class TestUSGSConnector:
    @pytest.mark.asyncio
    async def test_returns_empty_when_disabled(self) -> None:
        cfg = _make_config(enabled=False)
        connector = USGSConnector(cfg)
        result = await connector.sismos(BBOX)
        assert result == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_returns_parsed_features(self) -> None:
        cfg = _make_config(enabled=True)
        connector = USGSConnector(cfg)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=GEOJSON_RESPONSE)

        with patch.object(connector._client, "get", new=AsyncMock(return_value=mock_resp)):
            result = await connector.sismos(BBOX)

        assert len(result) == 2
        assert result[0].magnitude == pytest.approx(3.2)
        assert result[1].magnitude == pytest.approx(2.1)
        await connector.close()

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self) -> None:
        cfg = _make_config(enabled=True)
        connector = USGSConnector(cfg)

        err = AsyncMock(side_effect=Exception("timeout"))
        with patch.object(connector._client, "get", new=err):
            result = await connector.sismos(BBOX)

        assert result == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_empty_features_list(self) -> None:
        cfg = _make_config(enabled=True)
        connector = USGSConnector(cfg)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"type": "FeatureCollection", "features": []})

        with patch.object(connector._client, "get", new=AsyncMock(return_value=mock_resp)):
            result = await connector.sismos(BBOX)

        assert result == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        cfg = _make_config(enabled=False)
        async with USGSConnector(cfg) as connector:
            result = await connector.sismos(BBOX)
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_invalid_features(self) -> None:
        cfg = _make_config(enabled=True)
        connector = USGSConnector(cfg)

        geojson = {
            "features": [
                {"geometry": None, "properties": {}},
                FEATURE_M3,
            ]
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=geojson)

        with patch.object(connector._client, "get", new=AsyncMock(return_value=mock_resp)):
            result = await connector.sismos(BBOX)

        assert len(result) == 1
        await connector.close()

    @pytest.mark.asyncio
    async def test_request_includes_bbox_params(self) -> None:
        cfg = _make_config(enabled=True, min_magnitude=2.5, max_events=50)
        connector = USGSConnector(cfg)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"features": []})

        mock_get = AsyncMock(return_value=mock_resp)
        with patch.object(connector._client, "get", new=mock_get):
            await connector.sismos(BBOX)

        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"] if call_kwargs[1] else call_kwargs[0][1]
        assert params["minmagnitude"] == 2.5
        assert params["limit"] == 50
        assert params["minlatitude"] == BBOX.lat_min
        assert params["maxlatitude"] == BBOX.lat_max
        await connector.close()

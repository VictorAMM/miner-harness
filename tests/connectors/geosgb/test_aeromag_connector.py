"""Testes para AeromagConnector — amostragem de TMA via MapServer/identify."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from miner_harness.connectors.geosgb.aeromag_connector import AeromagConnector
from miner_harness.core.types import BoundingBox

# Caminho do AsyncClient para uso em patches
_ASYNC_CLIENT_PATH = "miner_harness.connectors.geosgb.aeromag_connector.httpx.AsyncClient"

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


def _identify_response(pixel_value: str | None) -> dict[str, Any]:
    """Simula resposta MapServer/identify com valor de pixel."""
    if pixel_value is None:
        return {"results": []}
    return {
        "results": [
            {
                "layerId": 1,
                "layerName": "Anomalia Magnética",
                "layerType": "Raster Layer",
                "displayFieldName": "Pixel Value",
                "attributes": {"Pixel Value": pixel_value},
            }
        ]
    }


# ---------------------------------------------------------------------------
# _parse_identify
# ---------------------------------------------------------------------------


class TestParseIdentify:
    def test_valid_float_string(self) -> None:
        data = _identify_response("124.56")
        result = AeromagConnector._parse_identify(data, -50.2, -6.1)
        assert result == {"lon": -50.2, "lat": -6.1, "tma_nt": 124.56}

    def test_negative_value(self) -> None:
        data = _identify_response("-201.4")
        result = AeromagConnector._parse_identify(data, -50.5, -6.3)
        assert result is not None
        assert result["tma_nt"] == pytest.approx(-201.4)

    def test_nodata_string_returns_none(self) -> None:
        data = _identify_response("NoData")
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_nodata_lowercase_returns_none(self) -> None:
        data = _identify_response("nodata")
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_no_data_with_space_returns_none(self) -> None:
        data = _identify_response("no data")
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_empty_results_returns_none(self) -> None:
        data = {"results": []}
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_non_numeric_returns_none(self) -> None:
        data = _identify_response("not-a-number")
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        data = _identify_response("")
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_dash_returns_none(self) -> None:
        data = _identify_response("-")
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_n_d_returns_none(self) -> None:
        data = _identify_response("n/d")
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_pixel_value_lowercase_key(self) -> None:
        """Suporte a 'pixel value' (lowercase) além de 'Pixel Value'."""
        data = {"results": [{"attributes": {"pixel value": "55.0"}}]}
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is not None
        assert result["tma_nt"] == pytest.approx(55.0)

    def test_value_key_fallback(self) -> None:
        """Suporte a 'VALUE' como fallback."""
        data = {"results": [{"attributes": {"VALUE": "88.5"}}]}
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is not None
        assert result["tma_nt"] == pytest.approx(88.5)

    def test_result_without_pixel_value_key(self) -> None:
        """Resultado sem nenhuma chave de pixel → None."""
        data = {"results": [{"attributes": {"OBJECTID": "1", "Name": "Point"}}]}
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is None

    def test_zero_tma_is_valid(self) -> None:
        """TMA = 0.0 é valor numérico válido."""
        data = _identify_response("0.0")
        result = AeromagConnector._parse_identify(data, -50.0, -6.0)
        assert result is not None
        assert result["tma_nt"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _generate_grid
# ---------------------------------------------------------------------------


class TestGenerateGrid:
    def test_default_n6_produces_36_points(self) -> None:
        conn = AeromagConnector(grid_n=6)
        bbox = _make_bbox()
        grid = conn._generate_grid(bbox)
        assert len(grid) == 36

    def test_n2_produces_4_points(self) -> None:
        conn = AeromagConnector(grid_n=2)
        bbox = _make_bbox()
        grid = conn._generate_grid(bbox)
        assert len(grid) == 4

    def test_n1_clipped_to_2(self) -> None:
        """grid_n < 2 é forçado para 2."""
        conn = AeromagConnector(grid_n=1)
        bbox = _make_bbox()
        grid = conn._generate_grid(bbox)
        assert len(grid) == 4  # 2×2

    def test_points_within_bbox(self) -> None:
        conn = AeromagConnector(grid_n=4)
        bbox = _make_bbox()
        grid = conn._generate_grid(bbox)
        for lon, lat in grid:
            assert bbox.lon_min <= lon <= bbox.lon_max
            assert bbox.lat_min <= lat <= bbox.lat_max

    def test_n3_produces_9_points(self) -> None:
        conn = AeromagConnector(grid_n=3)
        bbox = _make_bbox()
        grid = conn._generate_grid(bbox)
        assert len(grid) == 9


# ---------------------------------------------------------------------------
# sample_tma — mocked HTTP
# ---------------------------------------------------------------------------


class TestSampleTma:
    @pytest.mark.asyncio
    async def test_returns_valid_points_from_grid(self) -> None:
        """sample_tma retorna lista de pontos com tma_nt quando API responde."""
        conn = AeromagConnector(grid_n=2, min_delay_ms=0)
        bbox = _make_bbox()

        # Simula resposta com pixel value 100.0 para todos os pontos
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=_identify_response("100.0"))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(_ASYNC_CLIENT_PATH) as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value.aclose = AsyncMock()
            mock_cls.return_value.get = AsyncMock(return_value=mock_response)

            # Usar conector sem context manager (ownership mode)
            result = await conn.sample_tma(bbox)

        assert len(result) == 4  # 2×2
        for pt in result:
            assert "lon" in pt
            assert "lat" in pt
            assert pt["tma_nt"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_empty_list_when_all_points_nodata(self) -> None:
        """Se todos os pontos retornam NoData, lista é vazia."""
        conn = AeromagConnector(grid_n=2, min_delay_ms=0)
        bbox = _make_bbox()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=_identify_response("NoData"))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(_ASYNC_CLIENT_PATH) as mock_cls:
            mock_cls.return_value.aclose = AsyncMock()
            mock_cls.return_value.get = AsyncMock(return_value=mock_response)

            result = await conn.sample_tma(bbox)

        assert result == []

    @pytest.mark.asyncio
    async def test_http_error_skips_point_gracefully(self) -> None:
        """Falha HTTP em um ponto não interrompe o grid."""
        import httpx

        conn = AeromagConnector(grid_n=2, min_delay_ms=0)
        bbox = _make_bbox()

        ok_response = MagicMock()
        ok_response.raise_for_status = MagicMock()
        ok_response.json = MagicMock(return_value=_identify_response("50.0"))

        err_response = MagicMock()
        err_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock())
        )

        call_count = 0

        async def _get(*args: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            return err_response if call_count == 1 else ok_response

        with patch(_ASYNC_CLIENT_PATH) as mock_cls:
            mock_cls.return_value.aclose = AsyncMock()
            mock_cls.return_value.get = _get

            result = await conn.sample_tma(bbox)

        # 3 pontos válidos (o 1º falhou)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self) -> None:
        """Context manager fecha o cliente HTTP ao sair."""
        conn = AeromagConnector(grid_n=2, min_delay_ms=0)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value={"results": []}),
            )
        )
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with conn:
                bbox = _make_bbox()
                await conn.sample_tma(bbox)
            mock_client.aclose.assert_called_once()

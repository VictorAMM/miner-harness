"""Testes do GeoSGBConnector — integração de componentes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from miner_harness.connectors.geosgb.connector import GeoSGBConnector
from miner_harness.core.config import GeoSGBConfig
from miner_harness.core.exceptions import GeoSGBQueryError
from miner_harness.core.types import BoundingBox


@pytest.fixture()
def fast_config() -> GeoSGBConfig:
    """Config com delays mínimos para testes rápidos."""
    return GeoSGBConfig(
        min_delay_ms=0,
        max_concurrent=10,
        max_retries=1,
        backoff_factor=1.0,
        timeout_s=5,
    )


@pytest.fixture()
def bbox_small() -> BoundingBox:
    """Bbox pequeno para minimizar pontos de grid."""
    return BoundingBox(lon_min=-50.1, lat_min=-6.1, lon_max=-50.0, lat_max=-6.0)


def _make_identify_response(features: list[dict[str, Any]]) -> dict[str, Any]:
    """Constrói resposta fake de MapServer/identify."""
    return {
        "results": [
            {
                "layerId": 0,
                "attributes": feat,
                "geometry": {
                    "x": feat.get("longitude", -50.0),
                    "y": feat.get("latitude", -6.0),
                },
            }
            for feat in features
        ]
    }


def _make_query_response(features: list[dict[str, Any]]) -> dict[str, Any]:
    """Constrói resposta fake de FeatureServer/query."""
    return {
        "features": [
            {
                "attributes": feat,
                "geometry": {
                    "x": feat.get("longitude", -50.0),
                    "y": feat.get("latitude", -6.0),
                },
            }
            for feat in features
        ]
    }


class TestParseIdentifyResponse:
    """Testes do parser de respostas identify."""

    def test_extracts_attributes(self) -> None:
        data = _make_identify_response(
            [
                {"OBJECTID": 1, "nome": "Test"},
            ]
        )
        features = GeoSGBConnector._parse_identify_response(data)
        assert len(features) == 1
        assert features[0]["OBJECTID"] == 1
        assert features[0]["longitude"] == -50.0

    def test_empty_results(self) -> None:
        data = {"results": []}
        features = GeoSGBConnector._parse_identify_response(data)
        assert features == []

    def test_missing_results_key(self) -> None:
        data: dict[str, Any] = {}
        features = GeoSGBConnector._parse_identify_response(data)
        assert features == []


class TestParseModels:
    """Testes dos construtores de modelos tipados."""

    def test_parse_ocorrencia(self) -> None:
        data = {
            "objectid": 42,
            "substancias": "Cobre, Ouro",
            "municipio": "Parauapebas",
            "uf": "PA",
            "provincia": "Carajas",
            "longitude": -49.9,
            "latitude": -6.07,
        }
        result = GeoSGBConnector._parse_ocorrencia(data)
        assert result.objectid == 42
        assert result.substancias == "Cobre, Ouro"
        assert result.coordenada.longitude == -49.9

    def test_parse_gravimetria(self) -> None:
        data = {
            "objectid": 100,
            "longitude": -50.5,
            "latitude": -6.5,
            "altitude_ortometrica": 250.0,
            "gravidade": 978050.0,
            "anomalia_ar_livre": -12.5,
            "anomalia_bouguer": -45.2,
        }
        result = GeoSGBConnector._parse_gravimetria(data)
        assert result.objectid == 100
        assert result.anomalia_bouguer == -45.2

    def test_parse_geoquimica_extras_in_analises(self) -> None:
        data = {
            "objectid": 200,
            "projeto": "RENCA",
            "classe": "Sedimento de Corrente",
            "longitude": -50.0,
            "latitude": -6.0,
            "cu_ppm": 125.3,
            "au_ppb": 15.0,
        }
        result = GeoSGBConnector._parse_geoquimica(data)
        assert result.objectid == 200
        assert result.analises["cu_ppm"] == 125.3
        assert result.analises["au_ppb"] == 15.0

    def test_parse_geocronologia_optional_fields(self) -> None:
        data = {
            "objectid": 300,
            "metodo": "U-Pb",
            "idade_ma": 2750.0,
            "longitude": -50.0,
            "latitude": -6.0,
        }
        result = GeoSGBConnector._parse_geocronologia(data)
        assert result.idade_ma == 2750.0
        assert result.erro_ma is None

    def test_parse_litoestratigrafia(self) -> None:
        data = {
            "objectid": 400,
            "sigla": "A4gs",
            "nome": "Grupo Serra dos Carajas",
            "hierarquia": "Grupo",
        }
        result = GeoSGBConnector._parse_litoestratigrafia(data)
        assert result.sigla == "A4gs"
        assert result.hierarquia == "Grupo"

    def test_parse_aerogeofisica(self) -> None:
        data = {
            "objectid": 500,
            "nome_projeto": "Projeto Carajas",
            "ano": 2015,
            "tipo_levantamento": "Magnetometria",
            "area_km2": 15000.0,
            "longitude": -50.0,
            "latitude": -6.0,
        }
        result = GeoSGBConnector._parse_aerogeofisica(data)
        assert result.ano == 2015
        assert result.area_km2 == 15000.0


class TestConnectorExtraction:
    """Testes de extração end-to-end com mocks."""

    async def test_ocorrencias_extraction(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """ocorrencias usa FeatureServer/query (não mais MapServer/identify)."""
        connector = GeoSGBConnector(fast_config)

        query_resp = _make_query_response(
            [
                {
                    "OBJECTID": 1,
                    "Substancias minerais": "Cobre",
                    "Municipio": "Parauapebas",
                    "UF": "PA",
                    "longitude": -50.05,
                    "latitude": -6.05,
                },
            ]
        )

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = query_resp
            results = await connector.ocorrencias(bbox_small)

        assert len(results) >= 1
        assert results[0].substancias == "Cobre"
        assert results[0].municipio == "Parauapebas"
        await connector.close()

    async def test_gravimetria_via_query(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        connector = GeoSGBConnector(fast_config)

        query_resp = _make_query_response(
            [
                {
                    "objectid": 1,
                    "altitude_ortometrica": 250.0,
                    "gravidade": 978050.0,
                    "anomalia_ar_livre": -12.5,
                    "anom_bougu": -45.2,
                },
            ]
        )

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = query_resp
            results = await connector.gravimetria(bbox_small)

        assert len(results) == 1
        assert results[0].anomalia_bouguer == -45.2
        await connector.close()

    async def test_http_500_raises_geosgb_query_error(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """HTTP 500 from FeatureServer/query é convertido em GeoSGBQueryError."""
        connector = GeoSGBConnector(fast_config)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        http_error = httpx.HTTPStatusError("500 error", request=MagicMock(), response=mock_response)

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = http_error
            with pytest.raises(GeoSGBQueryError):
                await connector.ocorrencias(bbox_small)

        await connector.close()

    async def test_query_all_layers_tolerates_layer_failure(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """_query_all_layers continua se uma layer falhar."""
        connector = GeoSGBConnector(fast_config)

        good_resp = _make_query_response([{"objectid": 1, "projeto": "X", "classe": "Rocha"}])
        bad_resp = {"error": {"code": 404, "message": "Layer not found", "details": []}}

        responses = [bad_resp, good_resp, good_resp]

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = responses
            results = await connector.geoquimica(bbox_small)

        assert len(results) >= 1
        await connector.close()

    async def test_query_400_falls_back_to_ids(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """Quando _query_features recebe error 400, faz fallback para _query_via_ids."""
        connector = GeoSGBConnector(fast_config)

        error_resp = {
            "error": {"code": 400, "message": "Unable to complete operation.", "details": []}
        }
        ids_resp = {"objectIdFieldName": "OBJECTID", "objectIds": [93362, 93363]}
        attrs_resp = _make_query_response(
            [
                {
                    "OBJECTID": 93362,
                    "Substancias minerais": "Ferro",
                    "Municipio": "Parauapebas",
                    "UF": "PA",
                    "longitude": -50.05,
                    "latitude": -6.05,
                },
                {
                    "OBJECTID": 93363,
                    "Substancias minerais": "Ouro",
                    "Municipio": "Parauapebas",
                    "UF": "PA",
                    "longitude": -50.06,
                    "latitude": -6.06,
                },
            ]
        )

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [error_resp, ids_resp, attrs_resp]
            results = await connector.ocorrencias(bbox_small)

        assert len(results) == 2
        assert results[0].substancias == "Ferro"
        assert results[1].substancias == "Ouro"
        await connector.close()


    async def test_context_manager(self, fast_config: GeoSGBConfig) -> None:
        async with GeoSGBConnector(fast_config) as connector:
            assert connector is not None


class TestServices:
    """Testes do registry de servicos."""

    def test_service_registry_has_all_services(self) -> None:
        from miner_harness.connectors.geosgb.services import SERVICE_REGISTRY

        expected = {
            "ocorrencias",
            "gravimetria",
            "geoquimica",
            "geocronologia",
            "litoestratigrafia",
            "aerogeofisica",
        }
        assert set(SERVICE_REGISTRY.keys()) == expected

    def test_all_services_support_query(self) -> None:
        from miner_harness.connectors.geosgb.services import SERVICE_REGISTRY

        for name, ep in SERVICE_REGISTRY.items():
            assert ep.supports_query is True, f"{name} should support FeatureServer/query"

    def test_service_urls(self) -> None:
        from miner_harness.connectors.geosgb.services import OCORRENCIAS

        assert "geoportal.sgb.gov.br" in OCORRENCIAS.url
        assert OCORRENCIAS.url.endswith("/FeatureServer")

    def test_geoquimica_multi_layer(self) -> None:
        from miner_harness.connectors.geosgb.services import GEOQUIMICA

        assert len(GEOQUIMICA.default_layers) > 1

    def test_aerogeofisica_multi_layer(self) -> None:
        from miner_harness.connectors.geosgb.services import AEROGEOFISICA

        assert len(AEROGEOFISICA.default_layers) == 4

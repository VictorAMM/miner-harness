"""Testes do GeoSGBConnector — integração de componentes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from miner_harness.connectors.geosgb.connector import GeoSGBConnector
from miner_harness.core.config import GeoSGBConfig
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
        connector = GeoSGBConnector(fast_config)

        identify_resp = _make_identify_response(
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
            mock_get.return_value = identify_resp
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

    def test_gravimetria_supports_query(self) -> None:
        from miner_harness.connectors.geosgb.services import GRAVIMETRIA

        assert GRAVIMETRIA.supports_query is True

    def test_ocorrencias_no_query(self) -> None:
        from miner_harness.connectors.geosgb.services import OCORRENCIAS

        assert OCORRENCIAS.supports_query is False

    def test_service_urls(self) -> None:
        from miner_harness.connectors.geosgb.services import OCORRENCIAS

        assert "geoportal.sgb.gov.br" in OCORRENCIAS.url
        assert OCORRENCIAS.url.endswith("/MapServer")

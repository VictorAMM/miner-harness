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
        assert result.coordenada is None  # sem geometria → sem coord

    def test_parse_litoestratigrafia_with_coord(self) -> None:
        """_parse_litoestratigrafia popula coordenada quando lon/lat estão presentes."""
        data = {
            "objectid": 401,
            "sigla": "A3f",
            "hierarquia": "Formação",
            "longitude": -50.0,
            "latitude": -6.0,
        }
        result = GeoSGBConnector._parse_litoestratigrafia(data)
        assert result.coordenada is not None
        assert result.coordenada.longitude == pytest.approx(-50.0)
        assert result.coordenada.latitude == pytest.approx(-6.0)

    def test_geom_to_xy_point(self) -> None:
        """_geom_to_xy extrai x/y de ponto GeoSGB."""
        xy = GeoSGBConnector._geom_to_xy({"x": -50.0, "y": -6.0})
        assert xy == pytest.approx((-50.0, -6.0))

    def test_geom_to_xy_polygon_centroid(self) -> None:
        """_geom_to_xy calcula centróide aritmético do anel exterior do polígono."""
        # Quadrado 2×2 graus centrado em (-50, -6) — 4 vértices sem ponto de fechamento
        ring = [[-51.0, -7.0], [-49.0, -7.0], [-49.0, -5.0], [-51.0, -5.0]]
        xy = GeoSGBConnector._geom_to_xy({"rings": [ring]})
        assert xy is not None
        assert xy[0] == pytest.approx(-50.0, abs=0.001)
        assert xy[1] == pytest.approx(-6.0, abs=0.001)

    def test_geom_to_xy_empty(self) -> None:
        """_geom_to_xy retorna None para geometria vazia."""
        assert GeoSGBConnector._geom_to_xy({}) is None
        assert GeoSGBConnector._geom_to_xy({"rings": []}) is None

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

    def test_parse_aerogeofisica_null_coordinates(self) -> None:
        """GeoSGB retorna longitude/latitude null em alguns registros — deve ser descartado."""
        data = {
            "objectid": 62784,
            "id_projeto": "1019",
            "longitude": None,
            "latitude": None,
        }
        result = GeoSGBConnector._parse_aerogeofisica(data)
        assert result is None

    # ------------------------------------------------------------------
    # _safe_int / _safe_int_or_none / _safe_float_or_none — exception paths
    # ------------------------------------------------------------------

    def test_safe_int_invalid_raises_default(self) -> None:
        assert GeoSGBConnector._safe_int("abc") == 0
        assert GeoSGBConnector._safe_int(None) == 0
        assert GeoSGBConnector._safe_int("abc", default=99) == 99

    def test_safe_int_or_none_none_input(self) -> None:
        assert GeoSGBConnector._safe_int_or_none(None) is None

    def test_safe_int_or_none_invalid(self) -> None:
        assert GeoSGBConnector._safe_int_or_none("bad") is None

    def test_safe_float_or_none_invalid(self) -> None:
        assert GeoSGBConnector._safe_float_or_none("bad") is None

    # ------------------------------------------------------------------
    # _parse_coordenada — exception branch
    # ------------------------------------------------------------------

    def test_parse_coordenada_invalid_values(self) -> None:
        """Valores não-numéricos disparam except e retornam None."""
        result = GeoSGBConnector._parse_coordenada({"longitude": "bad", "latitude": "bad"})
        assert result is None

    # ------------------------------------------------------------------
    # Parsers — None coord paths (sem coordenada → retorna None)
    # ------------------------------------------------------------------

    def test_parse_ocorrencia_no_coord_returns_none(self) -> None:
        data = {"objectid": 1, "substancias": "Cobre", "municipio": "X", "uf": "PA"}
        assert GeoSGBConnector._parse_ocorrencia(data) is None

    def test_parse_gravimetria_no_coord_returns_none(self) -> None:
        data = {"objectid": 2, "altitude_ortometrica": 100.0}
        assert GeoSGBConnector._parse_gravimetria(data) is None

    def test_parse_geoquimica_no_coord_returns_none(self) -> None:
        data = {"objectid": 3, "projeto": "P", "classe": "Rocha"}
        assert GeoSGBConnector._parse_geoquimica(data) is None

    def test_parse_geocronologia_no_coord_returns_none(self) -> None:
        data = {"objectid": 4, "metodo": "U-Pb"}
        assert GeoSGBConnector._parse_geocronologia(data) is None


class TestConnectorExtraction:
    """Testes de extração end-to-end com mocks."""

    async def test_ocorrencias_extraction(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """ocorrencias usa MapServer/identify — resposta identify retornada por mock."""
        connector = GeoSGBConnector(fast_config)

        identify_resp = _make_identify_response(
            [
                {
                    "objectid": 1,
                    "substancias_minerais": "Cobre",
                    "municipio": "Parauapebas",
                    "uf": "PA",
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

    async def test_http_500_raises_geosgb_query_error(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """HTTP 500 from FeatureServer/query é convertido em GeoSGBQueryError (gravimetria)."""
        connector = GeoSGBConnector(fast_config)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        http_error = httpx.HTTPStatusError("500 error", request=MagicMock(), response=mock_response)

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = http_error
            with pytest.raises(GeoSGBQueryError):
                await connector.gravimetria(bbox_small)

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
        ids_resp = {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2]}
        attrs_resp = _make_query_response(
            [
                {
                    "objectid": 1,
                    "altitude_ortometrica": 250.0,
                    "gravidade": 978050.0,
                    "anomalia_ar_livre": -12.5,
                    "anomalia_bouguer": -45.2,
                    "longitude": -50.05,
                    "latitude": -6.05,
                },
                {
                    "objectid": 2,
                    "altitude_ortometrica": 300.0,
                    "gravidade": 978060.0,
                    "anomalia_ar_livre": -11.5,
                    "anomalia_bouguer": -44.2,
                    "longitude": -50.06,
                    "latitude": -6.06,
                },
            ]
        )

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [error_resp, ids_resp, attrs_resp]
            results = await connector.gravimetria(bbox_small)

        assert len(results) == 2
        assert results[0].anomalia_bouguer == -45.2
        assert results[1].anomalia_bouguer == -44.2
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
            "furos",
        }
        assert set(SERVICE_REGISTRY.keys()) == expected

    def test_all_services_support_query(self) -> None:
        """FeatureServer endpoints têm supports_query=True; MapServer têm False."""
        from miner_harness.connectors.geosgb.services import SERVICE_REGISTRY

        for name, ep in SERVICE_REGISTRY.items():
            expected = ep.server_type == "FeatureServer"
            assert ep.supports_query is expected, (
                f"{name}: supports_query={ep.supports_query} mas server_type={ep.server_type}"
            )

    def test_service_urls(self) -> None:
        from miner_harness.connectors.geosgb.services import GRAVIMETRIA, OCORRENCIAS

        assert "geoportal.sgb.gov.br" in OCORRENCIAS.url
        assert OCORRENCIAS.url.endswith("/MapServer")  # migrado de FeatureServer
        assert GRAVIMETRIA.url.endswith("/FeatureServer")  # permanece FeatureServer

    def test_geoquimica_multi_layer(self) -> None:
        from miner_harness.connectors.geosgb.services import GEOQUIMICA

        assert len(GEOQUIMICA.default_layers) > 1

    def test_aerogeofisica_multi_layer(self) -> None:
        from miner_harness.connectors.geosgb.services import AEROGEOFISICA

        assert len(AEROGEOFISICA.default_layers) == 4


class TestConnectorServiceMethods:
    """Testes dos métodos de serviço do GeoSGBConnector."""

    @pytest.mark.asyncio
    async def test_geocronologia(self, fast_config: GeoSGBConfig, bbox_small: BoundingBox) -> None:
        """geocronologia usa MapServer/identify; dedup por objectid garante 1 resultado."""
        connector = GeoSGBConnector(fast_config)
        resp = _make_identify_response(
            [
                {
                    "objectid": 1,
                    "metodo": "U-Pb",
                    "idade_ma": 2750.0,
                    "longitude": -50.0,
                    "latitude": -6.0,
                }
            ]
        )
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp
            results = await connector.geocronologia(bbox_small)
        assert len(results) == 1
        assert results[0].metodo == "U-Pb"
        await connector.close()

    @pytest.mark.asyncio
    async def test_litoestratigrafia(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """litoestratigrafia usa MapServer/identify; dedup por objectid garante 1 resultado."""
        connector = GeoSGBConnector(fast_config)
        resp = _make_identify_response(
            [{"objectid": 1, "sigla": "Xbj", "nome": "Formação Carajás", "hierarquia": "Grupo"}]
        )
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp
            results = await connector.litoestratigrafia(bbox_small)
        assert len(results) == 1
        assert results[0].sigla == "Xbj"
        await connector.close()

    @pytest.mark.asyncio
    async def test_aerogeofisica(self, fast_config: GeoSGBConfig, bbox_small: BoundingBox) -> None:
        connector = GeoSGBConnector(fast_config)
        resp = _make_query_response(
            [{"objectid": 1, "projeto": "Carajás", "ano": 1997, "empresa": "CPRM"}]
        )
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp
            results = await connector.aerogeofisica(bbox_small)
        assert isinstance(results, list)
        await connector.close()

    @pytest.mark.asyncio
    async def test_count_ocorrencias_sem_bbox(self, fast_config: GeoSGBConfig) -> None:
        connector = GeoSGBConnector(fast_config)
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"count": 42000}
            total = await connector.count_ocorrencias()
        assert total == 42000
        await connector.close()

    @pytest.mark.asyncio
    async def test_count_ocorrencias_com_bbox(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        connector = GeoSGBConnector(fast_config)
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"count": 7}
            total = await connector.count_ocorrencias(bbox_small)
        assert total == 7
        await connector.close()


class TestConnectorQueryEdgeCases:
    """Testes de edge cases nos métodos de query interno."""

    @pytest.mark.asyncio
    async def test_query_features_service_not_supporting_query_raises(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """_query_features levanta GeoSGBQueryError se endpoint não suporta query."""
        from miner_harness.connectors.geosgb.services import ServiceEndpoint

        connector = GeoSGBConnector(fast_config)
        bad_endpoint = ServiceEndpoint(
            name="fake",
            path="Fake/Service",
            server_type="FeatureServer",
            default_layers=[0],
            supports_query=False,
        )
        with pytest.raises(GeoSGBQueryError):
            await connector._query_features(bad_endpoint, bbox=bbox_small)
        await connector.close()

    @pytest.mark.asyncio
    async def test_query_via_ids_empty_ids_returns_empty(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """_query_via_ids retorna [] quando servidor retorna objectIds vazio."""
        from miner_harness.connectors.geosgb.services import OCORRENCIAS

        connector = GeoSGBConnector(fast_config)
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"objectIdFieldName": "OBJECTID", "objectIds": []}
            results = await connector._query_via_ids(OCORRENCIAS, bbox=bbox_small)
        assert results == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_query_via_ids_error_in_response_raises(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """_query_via_ids levanta GeoSGBQueryError quando resposta contém 'error'."""
        from miner_harness.connectors.geosgb.services import OCORRENCIAS

        connector = GeoSGBConnector(fast_config)
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "error": {"code": 400, "message": "Invalid parameters", "details": []}
            }
            with pytest.raises(GeoSGBQueryError):
                await connector._query_via_ids(OCORRENCIAS, bbox=bbox_small)
        await connector.close()

    @pytest.mark.asyncio
    async def test_query_via_ids_batch_http_error_continues(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """Falha HTTP em um lote de IDs não aborta — continua com os demais."""
        from miner_harness.connectors.geosgb.services import OCORRENCIAS

        connector = GeoSGBConnector(fast_config)
        ids_resp = {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2]}
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        http_error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [ids_resp, http_error]
            results = await connector._query_via_ids(OCORRENCIAS, bbox=bbox_small)
        assert results == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_query_via_ids_batch_error_in_body_continues(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """Erro no body de um lote de IDs não aborta — continua com os demais."""
        from miner_harness.connectors.geosgb.services import OCORRENCIAS

        connector = GeoSGBConnector(fast_config)
        ids_resp = {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2]}
        error_batch = {"error": {"code": 500, "message": "Internal error", "details": []}}

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [ids_resp, error_batch]
            results = await connector._query_via_ids(OCORRENCIAS, bbox=bbox_small)
        assert results == []
        await connector.close()

    @pytest.mark.asyncio
    async def test_query_via_ids_http_error_on_ids_request(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """HTTPStatusError no fetch de IDs levanta GeoSGBQueryError (linhas 388-389)."""
        from miner_harness.connectors.geosgb.services import OCORRENCIAS

        connector = GeoSGBConnector(fast_config)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 503
        http_error = httpx.HTTPStatusError("503", request=MagicMock(), response=mock_response)

        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = http_error
            with pytest.raises(GeoSGBQueryError):
                await connector._query_via_ids(OCORRENCIAS, bbox=bbox_small)
        await connector.close()

    @pytest.mark.asyncio
    async def test_query_features_limit_breaks_pagination(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """Quando limit é atingido após página cheia, para de paginar (linhas 352-353)."""
        page_size = 1000
        features_1000 = [
            {"OBJECTID": i, "longitude": -50.0, "latitude": -6.0} for i in range(page_size)
        ]
        page1 = {
            "features": [
                {"attributes": f, "geometry": {"x": -50.0, "y": -6.0}} for f in features_1000
            ]
        }
        connector = GeoSGBConnector(fast_config)
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = page1
            from miner_harness.connectors.geosgb.services import GRAVIMETRIA

            result = await connector._query_features(GRAVIMETRIA, limit=500)
        assert len(result) >= 500  # noqa: PLR2004
        await connector.close()

    @pytest.mark.asyncio
    async def test_query_features_offset_increments_between_pages(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """Offset incrementa quando página cheia e sem limit (linha 354)."""
        page_size = 1000
        features_1000 = [
            {"OBJECTID": i, "longitude": -50.0, "latitude": -6.0} for i in range(page_size)
        ]
        page1 = {
            "features": [
                {"attributes": f, "geometry": {"x": -50.0, "y": -6.0}} for f in features_1000
            ]
        }
        page2 = {
            "features": [{"attributes": {"OBJECTID": 9999}, "geometry": {"x": -50.0, "y": -6.0}}]
        }
        connector = GeoSGBConnector(fast_config)
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [page1, page2]
            from miner_harness.connectors.geosgb.services import GRAVIMETRIA

            result = await connector._query_features(GRAVIMETRIA)
        assert len(result) == page_size + 1
        await connector.close()


class TestExtractViaIdentify:
    """Testes do método _extract_via_identify (linhas 215-258)."""

    @pytest.mark.asyncio
    async def test_extract_via_identify_success(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """_extract_via_identify percorre grid e agrega resultados."""
        from miner_harness.connectors.geosgb.services import ServiceEndpoint

        fake_endpoint = ServiceEndpoint(
            name="fake_map",
            path="geologia/fake_map",
            server_type="MapServer",
            default_layers=[0],
        )
        identify_resp = {
            "results": [
                {
                    "layerId": 0,
                    "attributes": {"OBJECTID": 1, "nome": "Carajas"},
                    "geometry": {"x": -50.05, "y": -6.05},
                }
            ]
        }
        connector = GeoSGBConnector(fast_config)
        with (
            patch.dict(
                "miner_harness.connectors.geosgb.connector.SERVICE_REGISTRY",
                {"fake_map": fake_endpoint},
            ),
            patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.return_value = identify_resp
            results = await connector._extract_via_identify("fake_map", bbox_small)
        assert isinstance(results, list)
        await connector.close()

    @pytest.mark.asyncio
    async def test_extract_via_identify_exception_is_swallowed(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """Erro no identify de um ponto é logado e ignorado (linhas 237-238)."""
        from miner_harness.connectors.geosgb.services import ServiceEndpoint
        from miner_harness.core.exceptions import GeoSGBConnectionError

        fake_endpoint = ServiceEndpoint(
            name="fake_map",
            path="geologia/fake_map",
            server_type="MapServer",
            default_layers=[0],
        )
        connector = GeoSGBConnector(fast_config)
        with (
            patch.dict(
                "miner_harness.connectors.geosgb.connector.SERVICE_REGISTRY",
                {"fake_map": fake_endpoint},
            ),
            patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.side_effect = GeoSGBConnectionError("identify failed")
            results = await connector._extract_via_identify("fake_map", bbox_small)
        assert results == []
        await connector.close()


class TestParseFuro:
    """Testes do _parse_furo estático."""

    def test_valid_furo(self) -> None:
        data = {
            "objectid": 1,
            "projeto": "CARAJAS",
            "tipo_furo": "Diamantada",
            "profundidade_m": 350.0,
            "azimute": 90.0,
            "mergulho": -60.0,
            "ano": 1985,
            "longitude": -50.0,
            "latitude": -6.0,
        }
        result = GeoSGBConnector._parse_furo(data)
        assert result is not None
        assert result.projeto == "CARAJAS"
        assert result.profundidade_m == 350.0
        assert result.coordenada.longitude == -50.0

    def test_no_coord_returns_none(self) -> None:
        data = {"objectid": 2, "projeto": "X"}
        assert GeoSGBConnector._parse_furo(data) is None

    def test_optional_fields_none(self) -> None:
        data = {"objectid": 3, "longitude": -50.0, "latitude": -6.0}
        result = GeoSGBConnector._parse_furo(data)
        assert result is not None
        assert result.projeto is None
        assert result.profundidade_m is None


class TestFurosSondagemMethod:
    """Testes do método furos_sondagem do GeoSGBConnector."""

    @pytest.mark.asyncio
    async def test_furos_sondagem_returns_list(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        connector = GeoSGBConnector(fast_config)
        resp = _make_query_response(
            [
                {
                    "objectid": 1,
                    "projeto": "CARAJAS",
                    "profundidade_m": 250.0,
                    "longitude": -50.05,
                    "latitude": -6.05,
                }
            ]
        )
        with patch.object(connector._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp
            results = await connector.furos_sondagem(bbox_small)
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].projeto == "CARAJAS"
        await connector.close()

    @pytest.mark.asyncio
    async def test_furos_sondagem_endpoint_unavailable_returns_empty(
        self, fast_config: GeoSGBConfig, bbox_small: BoundingBox
    ) -> None:
        """Quando endpoint falha com qualquer exceção, retorna [] (degradação segura)."""
        connector = GeoSGBConnector(fast_config)
        with patch.object(
            connector._client, "get", new_callable=AsyncMock, side_effect=Exception("timeout")
        ):
            results = await connector.furos_sondagem(bbox_small)
        assert results == []
        await connector.close()

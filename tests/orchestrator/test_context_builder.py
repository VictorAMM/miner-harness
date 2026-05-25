"""Testes do ContextBuilder.

Ref: RFC-002 §6
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from miner_harness.cache.manager import CacheManager
from miner_harness.core.config import StorageConfig
from miner_harness.core.types import BoundingBox, Coordenada, OcorrenciaMineral
from miner_harness.orchestrator.context_builder import ContextBuilder


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)


@pytest.fixture
def cache(tmp_path: Path) -> CacheManager:
    config = StorageConfig(miner_home=tmp_path / ".miner-harness")
    c = CacheManager(config)
    yield c
    c.close()


@pytest.fixture
def mock_connector() -> MagicMock:
    connector = MagicMock()
    for method in [
        "ocorrencias",
        "gravimetria",
        "geoquimica",
        "geocronologia",
        "litoestratigrafia",
        "aerogeofisica",
        "furos_sondagem",
    ]:
        setattr(connector, method, AsyncMock(return_value=[]))
    return connector


class TestContextBuilder:
    """Testes do ContextBuilder."""

    @pytest.mark.asyncio
    async def test_build_fetches_all_services(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox)
        assert len(context) == 7  # 6 GeoSGB + furos
        assert all(isinstance(v, list) for v in context.values())

    @pytest.mark.asyncio
    async def test_build_uses_cache(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Cache hit should not call connector."""
        cache.put("ocorrencias", bbox, [{"objectid": 1}])
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox)
        assert len(context["ocorrencias"]) == 1
        mock_connector.ocorrencias.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_fetches_on_cache_miss(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Cache miss should call connector and populate cache."""
        oc = OcorrenciaMineral(
            objectid=1,
            substancias="Cobre",
            municipio="Parauapebas",
            uf="PA",
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        mock_connector.ocorrencias = AsyncMock(return_value=[oc])
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox)
        assert len(context["ocorrencias"]) == 1
        assert cache.contains("ocorrencias", bbox)

    @pytest.mark.asyncio
    async def test_build_truncates(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Exceeding max_records should truncate."""
        features = [{"objectid": i} for i in range(100)]
        cache.put("ocorrencias", bbox, features)
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox, max_records_per_service=10)
        assert len(context["ocorrencias"]) == 10

    @pytest.mark.asyncio
    async def test_build_handles_fetch_error(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Fetch error should result in empty list, not crash."""
        mock_connector.ocorrencias = AsyncMock(side_effect=RuntimeError("API down"))
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox)
        assert context["ocorrencias"] == []

    @pytest.mark.asyncio
    async def test_fetch_error_does_not_cache_empty_result(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Falhas de fetch NÃO devem ser cacheadas.

        Erro transitório não deve bloquear próximas execuções.
        """
        mock_connector.ocorrencias = AsyncMock(side_effect=RuntimeError("API down"))
        builder = ContextBuilder(mock_connector, cache)
        await builder.build(bbox)
        # Cache deve estar vazio — próxima execução tentará de novo
        assert not cache.contains("ocorrencias", bbox)

    @pytest.mark.asyncio
    async def test_index_features_skips_when_no_documents(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """_index_features retorna cedo quando context está vazio (linha 130)."""
        mock_engine = MagicMock()
        mock_engine.index_batch = AsyncMock(return_value=0)
        builder = ContextBuilder(mock_connector, cache, search_engine=mock_engine)
        # All services return empty → context has no features → _index_features returns early
        context = await builder.build(bbox)
        assert all(len(v) == 0 for v in context.values())
        mock_engine.index_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_index_features_calls_index_batch(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """_index_features chama index_batch quando há features (linha 139)."""
        mock_engine = MagicMock()
        mock_engine.index_batch = AsyncMock(return_value=1)
        cache.put("ocorrencias", bbox, [{"objectid": 1, "substancias": "Cu"}])
        builder = ContextBuilder(mock_connector, cache, search_engine=mock_engine)
        await builder.build(bbox)
        mock_engine.index_batch.assert_called()

    @pytest.mark.asyncio
    async def test_extra_sources_fetched_and_included(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """extra_sources são consultados e incluídos no contexto."""
        extra_connector = MagicMock()
        mock_item = MagicMock()
        mock_item.model_dump = MagicMock(return_value={"objectid": 0, "magnitude": 3.0})
        extra_connector.sismos = AsyncMock(return_value=[mock_item])

        builder = ContextBuilder(
            mock_connector,
            cache,
            extra_sources={"usgs": (extra_connector, "sismos")},
        )
        context = await builder.build(bbox)
        assert "usgs" in context
        assert len(context["usgs"]) == 1
        extra_connector.sismos.assert_awaited_once_with(bbox)

    @pytest.mark.asyncio
    async def test_build_fetches_services_concurrently(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Todos os serviços devem ser buscados em paralelo.

        Verifica que build() usa asyncio.gather() medindo que serviços
        com delay artificial completam em tempo próximo ao maior delay,
        não à soma de todos os delays.
        """
        import asyncio as _asyncio
        import time

        call_times: list[float] = []

        async def delayed_fetch(bbox_arg: object) -> list:
            call_times.append(time.perf_counter())
            await _asyncio.sleep(0.05)  # 50 ms por serviço
            return []

        for method in [
            "ocorrencias",
            "gravimetria",
            "geoquimica",
            "geocronologia",
            "litoestratigrafia",
            "aerogeofisica",
        ]:
            setattr(mock_connector, method, delayed_fetch)

        builder = ContextBuilder(mock_connector, cache)
        t0 = time.perf_counter()
        await builder.build(bbox)
        elapsed = time.perf_counter() - t0

        # 6 serviços × 50ms sequencial = 300ms; paralelo ≈ 50ms
        assert elapsed < 0.2, f"build() levou {elapsed:.3f}s — esperado < 0.2s (paralelo)"
        assert len(call_times) == 6
        # Todos iniciaram quase ao mesmo tempo (< 20ms de diferença)
        spread = max(call_times) - min(call_times)
        assert spread < 0.02, f"Serviços não iniciaram em paralelo (spread={spread:.3f}s)"

    @pytest.mark.asyncio
    async def test_extra_sources_truncated(
        self, mock_connector: MagicMock, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """extra_sources com mais de max_records_per_service são truncados (linhas 102-103)."""
        extra_connector = MagicMock()
        items = [MagicMock() for _ in range(60)]
        for item in items:
            item.model_dump = MagicMock(return_value={"objectid": 0})
        extra_connector.sismos = AsyncMock(return_value=items)

        builder = ContextBuilder(
            mock_connector,
            cache,
            extra_sources={"usgs": (extra_connector, "sismos")},
        )
        context = await builder.build(bbox, max_records_per_service=10)
        assert len(context["usgs"]) == 10


class TestFilterByBbox:
    """Testes de _filter_by_bbox."""

    def test_keeps_records_inside_bbox(self) -> None:
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        features = [
            {"coordenada": {"longitude": -50.0, "latitude": -6.0}},  # dentro
        ]
        result = ContextBuilder._filter_by_bbox(features, bbox)
        assert len(result) == 1

    def test_removes_records_far_outside_bbox(self) -> None:
        bbox = BoundingBox(lon_min=-49.0, lat_min=-19.5, lon_max=-47.5, lat_max=-18.5)
        features = [
            {"coordenada": {"longitude": -48.3, "latitude": -19.0}},  # dentro
            {"coordenada": {"longitude": -55.8, "latitude": -5.4}},  # Pará — fora
        ]
        result = ContextBuilder._filter_by_bbox(features, bbox)
        assert len(result) == 1
        assert result[0]["coordenada"]["longitude"] == -48.3

    def test_keeps_records_without_coordenada(self) -> None:
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        features = [
            {},  # sem coordenada — preservar
            {"coordenada": None},  # coordenada nula — preservar
        ]
        result = ContextBuilder._filter_by_bbox(features, bbox)
        assert len(result) == 2

    def test_keeps_records_within_tolerance_buffer(self) -> None:
        """Registros levemente fora do bbox (dentro do buffer 20%) são mantidos."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        # bbox width=2°, 20% buffer = 0.4° → lon_min efetivo = -51.4
        features = [
            {"coordenada": {"longitude": -51.3, "latitude": -6.0}},  # dentro do buffer
            {"coordenada": {"longitude": -53.0, "latitude": -6.0}},  # fora do buffer
        ]
        result = ContextBuilder._filter_by_bbox(features, bbox)
        assert len(result) == 1
        assert result[0]["coordenada"]["longitude"] == -51.3

    def test_keeps_records_with_invalid_coord_values(self) -> None:
        """Coord com valores inválidos não deve ser filtrada (preservar por segurança)."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        features = [
            {"coordenada": {"longitude": "bad", "latitude": -6.0}},
        ]
        result = ContextBuilder._filter_by_bbox(features, bbox)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_build_filters_out_of_bbox_records(
        self, mock_connector: MagicMock, cache: CacheManager
    ) -> None:
        """build() deve remover registros com coordenadas fora do bbox."""
        bbox = BoundingBox(lon_min=-49.0, lat_min=-19.5, lon_max=-47.5, lat_max=-18.5)
        # Um registro dentro do bbox, um fora (Pará)
        cache.put(
            "aerogeofisica",
            bbox,
            [
                {"objectid": 1, "coordenada": {"longitude": -48.3, "latitude": -19.0}},
                {"objectid": 2, "coordenada": {"longitude": -55.8, "latitude": -5.4}},
            ],
        )
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox)
        assert len(context["aerogeofisica"]) == 1
        assert context["aerogeofisica"][0]["objectid"] == 1

    @pytest.mark.asyncio
    async def test_bbox_filtered_sources_tracked_when_all_records_removed(
        self, mock_connector: MagicMock, cache: CacheManager
    ) -> None:
        """Serviço com 100% dos registros filtrados aparece em bbox_filtered_sources."""
        bbox = BoundingBox(lon_min=-49.0, lat_min=-19.5, lon_max=-47.5, lat_max=-18.5)
        cache.put(
            "aerogeofisica",
            bbox,
            [
                {"objectid": 1, "coordenada": {"longitude": -55.8, "latitude": -5.4}},  # fora
                {"objectid": 2, "coordenada": {"longitude": -56.0, "latitude": -6.0}},  # fora
            ],
        )
        builder = ContextBuilder(mock_connector, cache)
        await builder.build(bbox)
        assert "aerogeofisica" in builder.bbox_filtered_sources

    @pytest.mark.asyncio
    async def test_bbox_filtered_sources_not_set_when_some_records_kept(
        self, mock_connector: MagicMock, cache: CacheManager
    ) -> None:
        """Se pelo menos um registro é mantido, o serviço NÃO aparece em bbox_filtered_sources."""
        bbox = BoundingBox(lon_min=-49.0, lat_min=-19.5, lon_max=-47.5, lat_max=-18.5)
        cache.put(
            "aerogeofisica",
            bbox,
            [
                {"objectid": 1, "coordenada": {"longitude": -48.3, "latitude": -19.0}},  # dentro
                {"objectid": 2, "coordenada": {"longitude": -55.8, "latitude": -5.4}},  # fora
            ],
        )
        builder = ContextBuilder(mock_connector, cache)
        await builder.build(bbox)
        assert "aerogeofisica" not in builder.bbox_filtered_sources


class TestSortByProximity:
    """Testes de _sort_by_proximity."""

    def test_sorts_closer_first(self) -> None:
        features = [
            {"coordenada": {"longitude": -40.0, "latitude": -6.0}},  # distante
            {"coordenada": {"longitude": -50.0, "latitude": -6.0}},  # centro
        ]
        result = ContextBuilder._sort_by_proximity(features, cx=-50.0, cy=-6.0)
        assert result[0]["coordenada"]["longitude"] == -50.0

    def test_missing_coord_goes_last(self) -> None:
        features = [
            {},  # sem coordenada
            {"coordenada": {"longitude": -50.0, "latitude": -6.0}},
        ]
        result = ContextBuilder._sort_by_proximity(features, cx=-50.0, cy=-6.0)
        assert result[0]["coordenada"]["longitude"] == -50.0
        assert result[-1] == {}

    def test_invalid_coord_values_go_last(self) -> None:
        """TypeError/ValueError ao converter coord: vai para o final."""
        features = [
            {"coordenada": {"longitude": "bad", "latitude": "bad"}},
            {"coordenada": {"longitude": -50.0, "latitude": -6.0}},
        ]
        result = ContextBuilder._sort_by_proximity(features, cx=-50.0, cy=-6.0)
        assert result[0]["coordenada"]["longitude"] == -50.0
        assert result[-1]["coordenada"]["longitude"] == "bad"

    def test_non_dict_coord_goes_last(self) -> None:
        """coord que nao e dict: vai para o final."""
        features = [
            {"coordenada": None},
            {"coordenada": {"longitude": -50.0, "latitude": -6.0}},
        ]
        result = ContextBuilder._sort_by_proximity(features, cx=-50.0, cy=-6.0)
        assert result[0]["coordenada"]["longitude"] == -50.0


# ---------------------------------------------------------------------------
# TestContextBuilderEnrichment — linhas 162-163, 190-193, 201-206, 214-219, 241-242
# ---------------------------------------------------------------------------


class TestContextBuilderEnrichment:
    """Cobre injeção de computed keys: geoquimica_normalizada, bouguer_gradient,
    user_drillholes, sentinel2_indices, ml_prospectivity exception.
    """

    @pytest.mark.asyncio
    async def test_geoquimica_normalizada_injected(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linha 162-163: geoquimica com dados → geoquimica_normalizada injetada."""
        cache.put(
            "geoquimica",
            bbox,
            [
                {
                    "objectid": 1,
                    "coordenada": {"longitude": -50.0, "latitude": -6.0},
                    "analises": {"cu_ppm": 1.0},
                },
                {
                    "objectid": 2,
                    "coordenada": {"longitude": -50.1, "latitude": -6.0},
                    "analises": {"cu_ppm": 50.0},
                },
            ],
        )
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox)
        assert "geoquimica_normalizada" in context
        assert len(context["geoquimica_normalizada"]) == 1
        assert "text" in context["geoquimica_normalizada"][0]

    @pytest.mark.asyncio
    async def test_bouguer_gradient_injected(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 190-193: gravimetria com dados → bouguer_gradient injetada."""
        # Provide enough gravimetry points spread across bbox for IDW to work
        grav_records = [
            {
                "objectid": i,
                "anomalia_bouguer": -30.0 + i,
                "coordenada": {"longitude": -51.0 + i * 0.4, "latitude": -7.0 + i * 0.4},
            }
            for i in range(6)
        ]
        cache.put("gravimetria", bbox, grav_records)
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox)
        assert "bouguer_gradient" in context
        assert len(context["bouguer_gradient"]) == 1

    @pytest.mark.asyncio
    async def test_user_drillholes_injected(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 201-206: user_drillholes passados → injetados no contexto."""
        drillholes = [
            {
                "hole_id": "FUR-001",
                "x": -50.0,
                "y": -6.0,
                "z": 100.0,
                "depth_from": 0.0,
                "depth_to": 200.0,
                "depth_m": 200.0,
            }
        ]
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox, user_drillholes=drillholes)
        assert "user_drillholes" in context
        assert len(context["user_drillholes"]) == 1

    @pytest.mark.asyncio
    async def test_sentinel2_indices_injected(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 214-219: copernicus com resultado → sentinel2_indices injetada."""
        from miner_harness.connectors.sentinel2.processor import (
            IndexStats,
            Sentinel2Indices,
            SentinelIndexProcessor,
        )

        mock_copernicus = AsyncMock()
        mock_copernicus.statistics = AsyncMock(
            return_value={
                "data": [
                    {
                        "interval": {
                            "from": "2024-01-01T00:00:00Z",
                            "to": "2024-04-01T00:00:00Z",
                        },
                        "outputs": {},
                    }
                ]
            }
        )
        mock_s2 = Sentinel2Indices(
            ndvi=IndexStats(
                name="ndvi",
                mean=0.4,
                std=0.1,
                max=0.8,
                p90=0.6,
                area_anomalous_pct=12.0,
                sample_count=1000,
            )
        )
        builder = ContextBuilder(mock_connector, cache, copernicus=mock_copernicus)
        with patch.object(SentinelIndexProcessor, "process", return_value=mock_s2):
            context = await builder.build(bbox)
        assert "sentinel2_indices" in context
        assert len(context["sentinel2_indices"]) == 1

    @pytest.mark.asyncio
    async def test_ml_prospectivity_exception_logged(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 241-242: exceção no ML scorer → except silencioso, sem crash."""
        cache.put(
            "ocorrencias",
            bbox,
            [{"objectid": 1, "coordenada": {"longitude": -50.0, "latitude": -6.0}}],
        )
        builder = ContextBuilder(mock_connector, cache)
        builder._ml_enabled = True  # forçar ML path

        with patch(
            "miner_harness.ml.scorer.ProspectivityMLScorer.score",
            side_effect=RuntimeError("model error"),
        ):
            # Não deve lançar exceção
            context = await builder.build(bbox)

        # ml_prospectivity não deve estar no contexto (exceção foi silenciada)
        assert "ml_prospectivity" not in context


# ---------------------------------------------------------------------------
# TestGetSentinel2Indices — linhas 355-396
# ---------------------------------------------------------------------------


class TestGetSentinel2Indices:
    """Testes de ContextBuilder._get_sentinel2_indices."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Cache hit → retorna sem chamar copernicus."""
        from miner_harness.connectors.sentinel2.processor import (
            IndexStats,
            Sentinel2Indices,
        )

        s2 = Sentinel2Indices(
            ndvi=IndexStats(
                name="ndvi",
                mean=0.4,
                std=0.1,
                max=0.8,
                p90=0.6,
                area_anomalous_pct=12.0,
                sample_count=1000,
            )
        )
        cache.put("sentinel2", bbox, [s2.to_dict()])
        mock_copernicus = AsyncMock()
        builder = ContextBuilder(mock_connector, cache, copernicus=mock_copernicus)
        result = await builder._get_sentinel2_indices(bbox)
        assert result is not None
        mock_copernicus.statistics.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_deserialize_exception_falls_through(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Cache com valor inválido → deserialize falha → vai para copernicus."""
        cache.put("sentinel2", bbox, [None])  # None → from_dict(None) → AttributeError
        mock_copernicus = AsyncMock()
        mock_copernicus.statistics = AsyncMock(return_value={})
        builder = ContextBuilder(mock_connector, cache, copernicus=mock_copernicus)
        result = await builder._get_sentinel2_indices(bbox)
        assert result is None  # raw vazio → return None

    @pytest.mark.asyncio
    async def test_empty_raw_returns_none(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Copernicus retorna {} vazio → return None."""
        mock_copernicus = AsyncMock()
        mock_copernicus.statistics = AsyncMock(return_value={})
        builder = ContextBuilder(mock_connector, cache, copernicus=mock_copernicus)
        result = await builder._get_sentinel2_indices(bbox)
        assert result is None

    @pytest.mark.asyncio
    async def test_processor_returns_none_gives_none(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 352-354: processor.process() retorna None → return None."""
        from miner_harness.connectors.sentinel2.processor import SentinelIndexProcessor

        mock_copernicus = AsyncMock()
        mock_copernicus.statistics = AsyncMock(
            return_value={"data": [{"interval": {}, "outputs": {}}]}
        )
        builder = ContextBuilder(mock_connector, cache, copernicus=mock_copernicus)
        with patch.object(SentinelIndexProcessor, "process", return_value=None):
            result = await builder._get_sentinel2_indices(bbox)
        assert result is None

    @pytest.mark.asyncio
    async def test_connector_exception_returns_none(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 365-368: exceção no connector → except → return None."""
        mock_copernicus = AsyncMock()
        mock_copernicus.statistics = AsyncMock(side_effect=RuntimeError("API down"))
        builder = ContextBuilder(mock_connector, cache, copernicus=mock_copernicus)
        result = await builder._get_sentinel2_indices(bbox)
        assert result is None

    @pytest.mark.asyncio
    async def test_success_path_caches_and_returns(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 356-363: caminho bem-sucedido — salva no cache e retorna resultado."""
        from miner_harness.connectors.sentinel2.processor import (
            IndexStats,
            Sentinel2Indices,
            SentinelIndexProcessor,
        )

        mock_copernicus = AsyncMock()
        mock_copernicus.statistics = AsyncMock(
            return_value={
                "data": [
                    {
                        "interval": {
                            "from": "2024-01-01T00:00:00Z",
                            "to": "2024-04-01T00:00:00Z",
                        },
                        "outputs": {"ndvi": {}},
                    }
                ]
            }
        )
        mock_s2 = Sentinel2Indices(
            ndvi=IndexStats(
                name="ndvi",
                mean=0.4,
                std=0.1,
                max=0.8,
                p90=0.6,
                area_anomalous_pct=12.0,
                sample_count=1000,
            )
        )
        builder = ContextBuilder(mock_connector, cache, copernicus=mock_copernicus)
        with patch.object(SentinelIndexProcessor, "process", return_value=mock_s2):
            result = await builder._get_sentinel2_indices(bbox)

        assert result is not None
        assert cache.contains("sentinel2", bbox)


# ---------------------------------------------------------------------------
# Aeromag integration paths (linhas 255-268 context_builder.py)
# ---------------------------------------------------------------------------


class TestContextBuilderAeromag:
    """Cobre o bloco aeromag do ContextBuilder.build() — linhas 255-268."""

    @pytest.mark.asyncio
    async def test_valid_points_inject_aeromag_grid(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 256-266: amostras válidas → AeromagProcessor → context['aeromag_grid']."""
        aeromag_pts = [
            {"lon": -51.5, "lat": -6.5, "tma_nt": 100.0},
            {"lon": -50.5, "lat": -6.5, "tma_nt": 120.0},
            {"lon": -51.5, "lat": -5.5, "tma_nt": 110.0},
            {"lon": -50.5, "lat": -5.5, "tma_nt": 130.0},
            {"lon": -50.0, "lat": -6.0, "tma_nt": 115.0},
        ]
        mock_aeromag = AsyncMock()
        mock_aeromag.sample_tma = AsyncMock(return_value=aeromag_pts)
        builder = ContextBuilder(mock_connector, cache, aeromag=mock_aeromag)
        context = await builder.build(bbox)
        assert "aeromag_grid" in context
        entry = context["aeromag_grid"][0]
        assert "text" in entry
        assert "═══" in entry["text"]

    @pytest.mark.asyncio
    async def test_insufficient_points_no_injection(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linha 257 (False): < 3 pontos válidos → AeromagProcessor retorna None → sem injeção."""
        aeromag_pts = [
            {"lon": -51.5, "lat": -6.5, "tma_nt": 100.0},
            {"lon": -50.5, "lat": -6.5, "tma_nt": 120.0},
        ]
        mock_aeromag = AsyncMock()
        mock_aeromag.sample_tma = AsyncMock(return_value=aeromag_pts)
        builder = ContextBuilder(mock_connector, cache, aeromag=mock_aeromag)
        context = await builder.build(bbox)
        assert "aeromag_grid" not in context

    @pytest.mark.asyncio
    async def test_exception_in_sample_tma_does_not_propagate(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Linhas 267-268: exceção em sample_tma capturada pelo except → sem crash."""
        mock_aeromag = AsyncMock()
        mock_aeromag.sample_tma = AsyncMock(side_effect=RuntimeError("Portal down"))
        builder = ContextBuilder(mock_connector, cache, aeromag=mock_aeromag)
        context = await builder.build(bbox)
        assert "aeromag_grid" not in context

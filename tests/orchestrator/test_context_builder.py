"""Testes do ContextBuilder.

Ref: RFC-002 §6
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

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
        assert len(context) == 6
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
        """Falhas de fetch NÃO devem ser cacheadas — erro transitório não bloqueia próximas execuções."""
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

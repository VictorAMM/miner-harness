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
        "ocorrencias", "gravimetria", "geoquimica",
        "geocronologia", "litoestratigrafia", "aerogeofisica",
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
            objectid=1, substancias="Cobre", municipio="Parauapebas", uf="PA",
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

"""Shared fixtures for benchmark tests."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from unittest.mock import AsyncMock, MagicMock

import pytest

from miner_harness.cache.manager import CacheManager
from miner_harness.core.config import (
    ANMConfig,
    MinerHarnessConfig,
    OrchestratorConfig,
    StorageConfig,
    USGSConfig,
)
from miner_harness.core.types import BoundingBox

_LLM_RESPONSE = (
    '{"summary": "Bench summary", '
    '"findings": ["Au anomaly", "NW structural control"], '
    '"confidence": "high", '
    '"data_sources_used": ["ocorrencias", "gravimetria"], '
    '"data_gaps": []}'
)

BBOX_SMALL = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.health = AsyncMock(return_value=True)
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content=_LLM_RESPONSE,
            prompt_eval_count=100,
            eval_count=200,
        )
    )
    return llm


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
        features = [MagicMock(model_dump=lambda i=i: {"objectid": i}) for i in range(5)]
        setattr(connector, method, AsyncMock(return_value=features))
    return connector


@pytest.fixture
def bench_cache(tmp_path: Path) -> CacheManager:
    config = StorageConfig(miner_home=tmp_path / ".miner-harness")
    c = CacheManager(config)
    yield c
    c.close()


@pytest.fixture
def bench_config() -> MinerHarnessConfig:
    return MinerHarnessConfig(
        orchestrator=OrchestratorConfig(use_rag=False),
        # Disable extra connectors to prevent real HTTP requests in benchmarks
        anm=ANMConfig(enabled=False),
        usgs=USGSConfig(enabled=False),
    )


@pytest.fixture
def populated_cache(bench_cache: CacheManager) -> CacheManager:
    """Cache pre-filled with all 6 GeoSGB services for BBOX_SMALL."""
    for svc in [
        "ocorrencias",
        "gravimetria",
        "geoquimica",
        "geocronologia",
        "litoestratigrafia",
        "aerogeofisica",
    ]:
        bench_cache.put(svc, BBOX_SMALL, [{"objectid": i, "data": f"{svc}_{i}"} for i in range(5)])
    return bench_cache

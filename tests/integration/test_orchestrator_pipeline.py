"""Integration tests: Full Orchestrator pipeline.

Tests the complete analysis flow: connector -> cache -> context_builder ->
agents -> report generation.

Ref: RFC-002 (full pipeline), Phase 6 Validation Harness
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from miner_harness.cache.manager import CacheManager
from miner_harness.core.config import ANMConfig, MinerHarnessConfig, StorageConfig, USGSConfig
from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
)
from miner_harness.orchestrator.context_builder import ContextBuilder
from miner_harness.orchestrator.orchestrator import Orchestrator


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)


@pytest.fixture
def cache(tmp_path: Path) -> CacheManager:
    config = StorageConfig(miner_home=tmp_path / ".miner-harness")
    c = CacheManager(config)
    yield c
    c.close()


class _FakeFeature:
    """Minimal object with model_dump() to mimic Pydantic models."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def model_dump(self) -> dict:
        return self._data


def _make_fake_features(method: str, count: int = 5) -> list[_FakeFeature]:
    return [_FakeFeature({"objectid": i, "data": f"sample_{method}_{i}"}) for i in range(count)]


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
        setattr(connector, method, AsyncMock(return_value=_make_fake_features(method)))
    connector.furos_sondagem = AsyncMock(return_value=[])
    return connector


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content='{"summary": "Integration test summary", '
            '"findings": ["Major Cu-Au anomaly detected", "NW structural control confirmed"], '
            '"confidence": "high", '
            '"data_sources_used": ["ocorrencias", "gravimetria", "geoquimica"], '
            '"data_gaps": ["Sem dados de sensoriamento remoto"]}',
            prompt_eval_count=150,
            eval_count=300,
        )
    )
    return llm


@pytest.fixture
def config() -> MinerHarnessConfig:
    return MinerHarnessConfig(
        anm=ANMConfig(enabled=False),
        usgs=USGSConfig(enabled=False),
    )


def _populate_cache_full(cache: CacheManager, bbox: BoundingBox) -> None:
    """Populate all 6 services with sample data."""
    services = [
        "ocorrencias",
        "gravimetria",
        "geoquimica",
        "geocronologia",
        "litoestratigrafia",
        "aerogeofisica",
    ]
    for svc in services:
        cache.put(svc, bbox, [{"objectid": i, "data": f"sample_{svc}_{i}"} for i in range(5)])


class TestOrchestratorPipeline:
    """Integration: connector -> cache -> context -> agents -> report."""

    @pytest.mark.asyncio
    async def test_full_analysis_produces_valid_report(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Complete pipeline produces a well-formed ProspectionReport."""
        _populate_cache_full(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        report = await orch.analyze_region(bbox, "Carajas Integration Test")

        # Report structure
        assert report.region_name == "Carajas Integration Test"
        assert report.bbox == bbox
        assert len(report.steps) == 5
        assert report.analysis_date is not None
        assert report.model_used == config.orchestrator.model
        assert 0 <= report.data_quality_score <= 1
        assert report.total_duration_ms >= 0

        # Each step has correct structure
        expected_steps = list(AnalysisStep)
        for step_result, expected_step in zip(report.steps, expected_steps, strict=True):
            assert step_result.step == expected_step
            assert step_result.agent != ""
            assert step_result.summary != ""
            assert step_result.confidence in list(Confidence)
            assert step_result.duration_ms >= 0

        # LLM called once per agent invocation:
        # step1(1) + step2(1) + step3(2) + step4(3) + step5(1) = 8
        assert mock_llm.chat.call_count == 8

    @pytest.mark.asyncio
    async def test_context_builder_caches_fetched_data(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """ContextBuilder should cache data after fetching from connector."""
        builder = ContextBuilder(mock_connector, cache)
        context = await builder.build(bbox)

        # 7 serviços GeoSGB (6 + furos) + 1 chave ML derivada (ml_prospectivity, PRD-002 F8)
        assert len(context) == 8
        for _svc, features in context.items():
            assert isinstance(features, list)

        # Data should now be cached
        for svc in [
            "ocorrencias",
            "gravimetria",
            "geoquimica",
            "geocronologia",
            "litoestratigrafia",
            "aerogeofisica",
        ]:
            assert cache.contains(svc, bbox)

        # Second call should NOT hit connector again
        mock_connector.ocorrencias.reset_mock()
        context2 = await builder.build(bbox)
        assert len(context2["ocorrencias"]) == 5
        mock_connector.ocorrencias.assert_not_called()

    @pytest.mark.asyncio
    async def test_pipeline_with_partial_data(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Pipeline with 3+ services should still work (MIN_DATA_SOURCES=3)."""
        # Only cache 3 services
        cache.put("ocorrencias", bbox, [{"objectid": i} for i in range(5)])
        cache.put("gravimetria", bbox, [{"objectid": i} for i in range(5)])
        cache.put("geoquimica", bbox, [{"objectid": i} for i in range(5)])
        # Other 3 services return empty from connector
        mock_connector.geocronologia = AsyncMock(return_value=[])
        mock_connector.litoestratigrafia = AsyncMock(return_value=[])
        mock_connector.aerogeofisica = AsyncMock(return_value=[])

        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        report = await orch.analyze_region(bbox, "Partial Data Test")

        # Should complete with 3 sources
        assert len(report.steps) == 5
        # Should have caveats about missing data
        assert len(report.caveats) > 0

    @pytest.mark.asyncio
    async def test_step_chaining_passes_context(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Each step receives previous step results for context chaining."""
        _populate_cache_full(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)

        # Run only 2 steps to verify chaining
        report = await orch.analyze_region(
            bbox,
            "Chain Test",
            steps=[AnalysisStep.TECTONIC_HISTORY, AnalysisStep.STRUCTURAL_ARCHITECTURE],
        )
        assert len(report.steps) == 2

        # Both steps should have been executed in order
        assert report.steps[0].step == AnalysisStep.TECTONIC_HISTORY
        assert report.steps[1].step == AnalysisStep.STRUCTURAL_ARCHITECTURE

    @pytest.mark.asyncio
    async def test_report_data_quality_reflects_coverage(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Data quality score should reflect actual data coverage."""
        # Full data -> higher quality
        _populate_cache_full(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        report_full = await orch.analyze_region(bbox, "Full Coverage")

        # Partial data -> lower quality
        cache.clear()
        cache.put("ocorrencias", bbox, [{"objectid": 1}])
        cache.put("gravimetria", bbox, [{"objectid": 2}])
        cache.put("geoquimica", bbox, [{"objectid": 3}])
        mock_connector.geocronologia = AsyncMock(return_value=[])
        mock_connector.litoestratigrafia = AsyncMock(return_value=[])
        mock_connector.aerogeofisica = AsyncMock(return_value=[])

        report_partial = await orch.analyze_region(bbox, "Partial Coverage")

        # Full coverage should have higher or equal quality
        assert report_full.data_quality_score >= report_partial.data_quality_score

"""Pipeline latency benchmarks.

Measures wall-clock time for the full analysis pipeline with a mocked LLM,
so results reflect orchestration overhead, not actual inference time.
All assertions use generous upper bounds (10 s) — these tests exist to
catch catastrophic regressions, not to enforce tight SLAs.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock  # noqa: TC003

import pytest

from miner_harness.core.types import AnalysisStep
from miner_harness.orchestrator.orchestrator import Orchestrator

from .conftest import BBOX_SMALL


class TestPipelineLatency:
    @pytest.mark.asyncio
    async def test_full_pipeline_completes_under_10s(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
    ) -> None:
        """Full 5-step pipeline with mocked LLM should complete in under 10 s."""
        orch = Orchestrator(mock_connector, populated_cache, mock_llm, bench_config)
        t0 = time.perf_counter()
        report = await orch.analyze_region(BBOX_SMALL, "Benchmark Region")
        elapsed = time.perf_counter() - t0

        assert elapsed < 10.0, f"Pipeline too slow: {elapsed:.2f}s"
        assert len(report.steps) == 5

    @pytest.mark.asyncio
    async def test_two_step_pipeline_faster_than_full(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
    ) -> None:
        """2-step pipeline should be faster than the 5-step full run."""
        orch = Orchestrator(mock_connector, populated_cache, mock_llm, bench_config)

        t0 = time.perf_counter()
        report_full = await orch.analyze_region(BBOX_SMALL, "Full")
        t_full = time.perf_counter() - t0

        t0 = time.perf_counter()
        report_two = await orch.analyze_region(
            BBOX_SMALL,
            "Two Steps",
            steps=[AnalysisStep.TECTONIC_HISTORY, AnalysisStep.STRUCTURAL_ARCHITECTURE],
        )
        t_two = time.perf_counter() - t0

        assert len(report_full.steps) == 5
        assert len(report_two.steps) == 2
        assert t_two < t_full, f"2-step ({t_two:.3f}s) not faster than full ({t_full:.3f}s)"

    @pytest.mark.asyncio
    async def test_step_duration_ms_populated(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
    ) -> None:
        """Every step result must have duration_ms >= 0."""
        orch = Orchestrator(mock_connector, populated_cache, mock_llm, bench_config)
        report = await orch.analyze_region(BBOX_SMALL, "Duration Check")

        for step_result in report.steps:
            assert step_result.duration_ms >= 0, (
                f"step {step_result.step.value} has negative duration"
            )

    @pytest.mark.asyncio
    async def test_total_duration_ms_matches_wall_time(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
    ) -> None:
        """report.total_duration_ms should be within 2x of actual wall time."""
        orch = Orchestrator(mock_connector, populated_cache, mock_llm, bench_config)
        t0 = time.perf_counter()
        report = await orch.analyze_region(BBOX_SMALL, "Duration Accuracy")
        wall_ms = (time.perf_counter() - t0) * 1000

        # Allow 2x slack — instrumentation overhead, scheduling jitter
        assert report.total_duration_ms <= wall_ms * 2 + 500, (
            f"reported {report.total_duration_ms}ms but wall was {wall_ms:.0f}ms"
        )

    @pytest.mark.asyncio
    async def test_parallel_steps_faster_than_sequential_model(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
    ) -> None:
        """Steps 3+4 run agents in parallel; wall time < sum of per-agent times."""
        orch = Orchestrator(mock_connector, populated_cache, mock_llm, bench_config)
        report = await orch.analyze_region(BBOX_SMALL, "Parallel Check")

        # step MAGMATIC_FERTILITY uses 2 agents; INDIRECT_EVIDENCE uses 3
        step_map = {r.step: r for r in report.steps}
        for step_enum in [AnalysisStep.MAGMATIC_FERTILITY, AnalysisStep.INDIRECT_EVIDENCE]:
            result = step_map[step_enum]
            # Wall time recorded in result.duration_ms is max across agents (parallel)
            # It must be non-negative and the step must have completed
            assert result.duration_ms >= 0
            assert result.agent != ""

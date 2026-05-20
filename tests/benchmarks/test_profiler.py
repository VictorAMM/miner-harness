"""Tests for PipelineProfiler / ProfilingRunner."""

from __future__ import annotations

from unittest.mock import MagicMock  # noqa: TC003

import pytest

from miner_harness.core.types import AnalysisStep
from miner_harness.observability.profiler import ProfileReport, ProfilingRunner, StepTiming

from .conftest import BBOX_SMALL


class TestProfileReport:
    def test_print_summary_outputs_region_name(self, capsys: pytest.CaptureFixture) -> None:
        pr = ProfileReport(
            region_name="Carajás",
            total_wall_ms=5000.0,
            data_fetch_ms=800.0,
            steps=[
                StepTiming(
                    step="tectonic_history",
                    agents=["structural_geologist"],
                    wall_ms=1200.0,
                    llm_ms=1100,
                )
            ],
        )
        pr.print_summary()
        out = capsys.readouterr().out
        assert "Carajás" in out
        assert "5000" in out
        assert "800" in out
        assert "tectonic_history" in out
        assert "structural_geologist" in out

    def test_print_summary_empty_steps(self, capsys: pytest.CaptureFixture) -> None:
        pr = ProfileReport(region_name="Empty", total_wall_ms=100.0, data_fetch_ms=50.0)
        pr.print_summary()
        out = capsys.readouterr().out
        assert "Empty" in out


class TestProfilingRunner:
    @pytest.mark.asyncio
    async def test_profile_populated_after_run(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
    ) -> None:
        """After analyze_region, _profile must contain timing for all 5 steps."""
        runner = ProfilingRunner(mock_connector, populated_cache, mock_llm, bench_config)
        await runner.analyze_region(BBOX_SMALL, "Profile Test")

        assert runner._profile is not None
        assert runner._profile.region_name == "Profile Test"
        assert runner._profile.total_wall_ms > 0
        assert runner._profile.data_fetch_ms >= 0
        assert len(runner._profile.steps) == 5

    @pytest.mark.asyncio
    async def test_step_timings_have_correct_step_names(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
    ) -> None:
        """StepTiming entries must match the AnalysisStep enum values in order."""
        runner = ProfilingRunner(mock_connector, populated_cache, mock_llm, bench_config)
        await runner.analyze_region(BBOX_SMALL, "Step Order")

        expected = [s.value for s in AnalysisStep]
        actual = [t.step for t in runner._profile.steps]
        assert actual == expected

    @pytest.mark.asyncio
    async def test_data_fetch_ms_less_than_total(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
    ) -> None:
        """Data fetch time must be a subset of total wall time."""
        runner = ProfilingRunner(mock_connector, populated_cache, mock_llm, bench_config)
        await runner.analyze_region(BBOX_SMALL, "Timing Subset")

        assert runner._profile.data_fetch_ms <= runner._profile.total_wall_ms + 10

    @pytest.mark.asyncio
    async def test_print_summary_called(
        self,
        mock_connector: MagicMock,
        populated_cache: object,
        mock_llm: MagicMock,
        bench_config: object,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """ProfilingRunner must print the profile summary after a successful run."""
        runner = ProfilingRunner(mock_connector, populated_cache, mock_llm, bench_config)
        await runner.analyze_region(BBOX_SMALL, "Print Test")
        out = capsys.readouterr().out
        assert "Pipeline Profile" in out
        assert "Print Test" in out

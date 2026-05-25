"""PipelineProfiler — lightweight latency profiler for the analysis pipeline.

Wraps AnalysisRunner to collect wall-clock timing per step and
print a structured summary to stdout when the pipeline completes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from miner_harness.core.types import AnalysisStep, StepResult  # noqa: TC001
from miner_harness.server.analysis_runner import AnalysisRunner

if TYPE_CHECKING:
    from collections.abc import Callable

    from miner_harness.core.types import BoundingBox, ProspectionReport


@dataclass
class StepTiming:
    step: str
    agents: list[str]
    wall_ms: float
    llm_ms: int  # from StepResult.duration_ms


@dataclass
class ProfileReport:
    region_name: str
    total_wall_ms: float
    data_fetch_ms: float
    steps: list[StepTiming] = field(default_factory=list)

    def print_summary(self) -> None:
        print("\n── Pipeline Profile ─────────────────────────────────────")
        print(f"  Region          : {self.region_name}")
        print(f"  Total wall time : {self.total_wall_ms:>8.0f} ms")
        print(f"  Data fetch      : {self.data_fetch_ms:>8.0f} ms")
        print()
        print(f"  {'Step':<30} {'Agents':<35} {'Wall':>8}  {'LLM':>8}")
        print(f"  {'-' * 30} {'-' * 35} {'-' * 8}  {'-' * 8}")
        for s in self.steps:
            agents_str = ", ".join(s.agents) if s.agents else "—"
            print(f"  {s.step:<30} {agents_str:<35} {s.wall_ms:>7.0f}ms  {s.llm_ms:>7}ms")
        print("─────────────────────────────────────────────────────────\n")


class ProfilingRunner(AnalysisRunner):
    """AnalysisRunner that records wall-clock timing for each step."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._profile: ProfileReport | None = None
        self._fetch_start: float = 0.0
        self._pipeline_start: float = 0.0

    async def analyze_region(
        self,
        bbox: BoundingBox,
        region_name: str,
        steps: list[AnalysisStep] | None = None,
        user_drillholes: list[dict[str, Any]] | None = None,
        on_step_complete: Callable[[AnalysisStep, int, int, str], None] | None = None,
    ) -> ProspectionReport:
        self._pipeline_start = time.perf_counter()
        self._profile = ProfileReport(
            region_name=region_name,
            total_wall_ms=0.0,
            data_fetch_ms=0.0,
        )
        self._fetch_start = time.perf_counter()
        report = await super().analyze_region(
            bbox,
            region_name,
            steps,
            user_drillholes=user_drillholes,
            on_step_complete=on_step_complete,
        )
        self._profile.total_wall_ms = (time.perf_counter() - self._pipeline_start) * 1000
        self._profile.print_summary()
        return report

    async def _on_data_fetched(self, geological_data: dict[str, list[dict[str, Any]]]) -> None:
        if self._profile is not None:
            self._profile.data_fetch_ms = (time.perf_counter() - self._fetch_start) * 1000
        await super()._on_data_fetched(geological_data)

    async def _execute_step(
        self,
        step: AnalysisStep,
        geological_data: dict[str, list[dict[str, Any]]],
        previous_results: list[StepResult],
        bbox: BoundingBox | None = None,
    ) -> StepResult:
        t0 = time.perf_counter()
        result = await super()._execute_step(step, geological_data, previous_results, bbox)
        wall_ms = (time.perf_counter() - t0) * 1000
        if self._profile is not None:
            from miner_harness.orchestrator.orchestrator import _STEP_AGENTS

            self._profile.steps.append(
                StepTiming(
                    step=step.value,
                    agents=_STEP_AGENTS.get(step, []),
                    wall_ms=wall_ms,
                    llm_ms=result.duration_ms,
                )
            )
        return result

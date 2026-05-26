"""AnalysisRunner — Orchestrator com callbacks SSE por step."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from miner_harness.core.types import AnalysisStep, ProspectionReport, StepResult
from miner_harness.orchestrator.orchestrator import (
    _STEP_AGENTS,
    Orchestrator,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from miner_harness.core.types import BoundingBox
    from miner_harness.server.sse import SseChannel

_STEP_ORDER = list(AnalysisStep)


class AnalysisRunner(Orchestrator):
    """Subclasse do Orchestrator que emite eventos SSE a cada step."""

    def set_channel(self, channel: SseChannel) -> None:
        self._sse_channel: SseChannel | None = channel
        # ETA tracking: reset per analysis run
        self._step_durations: list[float] = []
        self._step_start_t: float | None = None
        self._run_start_t: float = time.monotonic()

    async def analyze_region(
        self,
        bbox: BoundingBox,
        region_name: str,
        steps: list[AnalysisStep] | None = None,
        user_drillholes: list[dict[str, Any]] | None = None,
        on_step_complete: Callable[[AnalysisStep, int, int, str], None] | None = None,
    ) -> ProspectionReport:
        ch = getattr(self, "_sse_channel", None)
        if ch is not None:
            ch.send("data_fetch_start", {"msg": "Coletando dados GeoSGB..."})

        try:
            report = await super().analyze_region(
                bbox,
                region_name,
                steps,
                user_drillholes=user_drillholes,
                on_step_complete=on_step_complete,
            )
        except Exception as exc:
            if ch is not None:
                ch.send("error", {"msg": str(exc), "type": type(exc).__name__})
                ch.close()
            raise

        if ch is not None:
            ch.send("complete", {"report": report.model_dump(mode="json")})
            ch.close()

        return report

    async def _on_data_fetched(self, geological_data: dict[str, list[dict[str, Any]]]) -> None:
        ch = getattr(self, "_sse_channel", None)
        if ch is not None:
            sources_found = sum(1 for v in geological_data.values() if v)
            ch.send("data_fetch_done", {"sources_found": sources_found})

    async def _execute_step(
        self,
        step: AnalysisStep,
        geological_data: dict[str, list[dict[str, Any]]],
        previous_results: list[StepResult],
        bbox: BoundingBox | None = None,
    ) -> StepResult:
        ch = getattr(self, "_sse_channel", None)
        step_index = _STEP_ORDER.index(step) if step in _STEP_ORDER else -1
        agents = _STEP_AGENTS.get(step, [])

        if ch is not None:
            now = time.monotonic()
            elapsed_s = round(now - getattr(self, "_run_start_t", now), 1)
            durations = getattr(self, "_step_durations", [])
            remaining_steps = len(_STEP_ORDER) - step_index
            if durations and remaining_steps > 0:
                avg_dur = sum(durations) / len(durations)
                eta_s: float | None = round(avg_dur * remaining_steps, 0)
            else:
                eta_s = None
            self._step_start_t = now
            ch.send(
                "step_start",
                {
                    "step": step.value,
                    "step_index": step_index,
                    "total_steps": len(_STEP_ORDER),
                    "agents": agents,
                    "elapsed_s": elapsed_s,
                    "eta_s": eta_s,
                },
            )

        result = await super()._execute_step(step, geological_data, previous_results, bbox)

        if ch is not None:
            step_end = time.monotonic()
            step_start = getattr(self, "_step_start_t", step_end)
            duration = step_end - step_start
            if not hasattr(self, "_step_durations"):
                self._step_durations = []
            self._step_durations.append(duration)
            ch.send(
                "step_complete",
                {
                    "step": step.value,
                    "step_index": step_index,
                    "result": result.model_dump(mode="json"),
                },
            )

        return result

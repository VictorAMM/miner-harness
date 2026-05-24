"""AnalysisRunner — Orchestrator com callbacks SSE por step."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from miner_harness.core.types import AnalysisStep, ProspectionReport, StepResult
from miner_harness.orchestrator.orchestrator import (
    _STEP_AGENTS,
    Orchestrator,
)

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox
    from miner_harness.server.sse import SseChannel

_STEP_ORDER = list(AnalysisStep)


class AnalysisRunner(Orchestrator):
    """Subclasse do Orchestrator que emite eventos SSE a cada step."""

    def set_channel(self, channel: SseChannel) -> None:
        self._sse_channel: SseChannel | None = channel

    async def analyze_region(
        self,
        bbox: BoundingBox,
        region_name: str,
        steps: list[AnalysisStep] | None = None,
        user_drillholes: list[dict[str, Any]] | None = None,
    ) -> ProspectionReport:
        ch = getattr(self, "_sse_channel", None)
        if ch is not None:
            ch.send("data_fetch_start", {"msg": "Coletando dados GeoSGB..."})

        try:
            report = await super().analyze_region(
                bbox, region_name, steps, user_drillholes=user_drillholes
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
            ch.send(
                "step_start",
                {
                    "step": step.value,
                    "step_index": step_index,
                    "total_steps": len(_STEP_ORDER),
                    "agents": agents,
                },
            )

        result = await super()._execute_step(step, geological_data, previous_results, bbox)

        if ch is not None:
            ch.send(
                "step_complete",
                {
                    "step": step.value,
                    "step_index": step_index,
                    "result": result.model_dump(mode="json"),
                },
            )

        return result

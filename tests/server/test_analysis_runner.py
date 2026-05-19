"""Testes do AnalysisRunner — SSE callbacks durante análise."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    ProspectionReport,
    StepResult,
)
from miner_harness.orchestrator.orchestrator import Orchestrator
from miner_harness.server.analysis_runner import AnalysisRunner
from miner_harness.server.sse import SseChannel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report() -> ProspectionReport:
    step = StepResult(
        step=AnalysisStep.TECTONIC_HISTORY,
        agent="structural_geologist",
        summary="Sumário.",
        findings=["finding"],
        confidence=Confidence.HIGH,
        data_sources_used=["GeoSGB/litoestratigrafia"],
        data_gaps=[],
        raw_reasoning="reasoning",
        duration_ms=1000,
    )
    target = MineralTarget(
        name="Alvo 1",
        longitude=-50.0,
        latitude=-6.0,
        radius_km=5.0,
        commodities=["Au"],
        mineral_system="Ouro Orogênico",
        confidence=Confidence.HIGH,
        priority=1,
        rationale="Teste",
        recommended_followup=[],
    )
    return ProspectionReport(
        region_name="Teste",
        bbox=BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
        analysis_date=datetime(2026, 5, 19, 10, 0, 0, tzinfo=UTC),
        steps=[step],
        targets=[target],
        integrated_summary="Resumo integrado.",
        caveats=[],
        data_quality_score=0.8,
        total_duration_ms=30000,
        model_used="qwen3:8b",
    )


def _collect_chunks_sync(channel: SseChannel) -> list[str]:
    import asyncio

    chunks: list[str] = []

    async def collect() -> None:
        async for chunk in channel:
            chunks.append(chunk)

    asyncio.get_event_loop().run_until_complete(collect())
    return chunks


def _event_types(chunks: list[str]) -> list[str]:
    return [
        line[len("event: ") :]
        for chunk in chunks
        for line in chunk.split("\n")
        if line.startswith("event: ")
    ]


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestAnalysisRunner:
    def test_set_channel_stores_reference(self) -> None:
        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)
        assert runner._sse_channel is channel

    @pytest.mark.asyncio
    async def test_step_complete_events_emitted(self) -> None:
        """analyze_region emite data_fetch_start e complete via SSE."""
        report = _make_report()

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "analyze_region",
            new=AsyncMock(return_value=report),
        ):
            bb = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
            await runner.analyze_region(bb, "Teste")

        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        types = _event_types(chunks)
        assert "data_fetch_start" in types
        assert "complete" in types

    @pytest.mark.asyncio
    async def test_complete_event_contains_report_json(self) -> None:
        """O evento 'complete' deve conter o JSON do relatório."""
        report = _make_report()

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "analyze_region",
            new=AsyncMock(return_value=report),
        ):
            bb = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
            await runner.analyze_region(bb, "Teste")

        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        complete_chunk = next((c for c in chunks if "event: complete" in c), None)
        assert complete_chunk is not None
        data_line = next(line for line in complete_chunk.split("\n") if line.startswith("data: "))
        payload = json.loads(data_line[len("data: ") :])
        assert payload["report"]["region_name"] == "Teste"

    @pytest.mark.asyncio
    async def test_error_emits_error_event_and_closes_channel(self) -> None:
        """Quando super().analyze_region lança exceção, emite 'error' e fecha o canal."""
        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "analyze_region",
            new=AsyncMock(side_effect=RuntimeError("GeoSGB timeout")),
        ):
            bb = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
            with pytest.raises(RuntimeError):
                await runner.analyze_region(bb, "Teste")

        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        types = _event_types(chunks)
        assert "error" in types

        error_chunk = next((c for c in chunks if "event: error" in c), None)
        assert error_chunk is not None
        data_line = next(line for line in error_chunk.split("\n") if line.startswith("data: "))
        payload = json.loads(data_line[len("data: ") :])
        assert "GeoSGB timeout" in payload["msg"]

    @pytest.mark.asyncio
    async def test_no_channel_analyze_still_returns_report(self) -> None:
        """Sem channel SSE, analyze_region funciona normalmente."""
        report = _make_report()

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)
        # Sem set_channel

        with patch.object(
            Orchestrator,
            "analyze_region",
            new=AsyncMock(return_value=report),
        ):
            bb = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
            result = await runner.analyze_region(bb, "Teste")

        assert result.region_name == "Teste"

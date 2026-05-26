"""Testes do AnalysisRunner — SSE callbacks durante análise."""

from __future__ import annotations

import json
from datetime import datetime, timezone  # noqa: UP017
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
        analysis_date=datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc),  # noqa: UP017
        steps=[step],
        targets=[target],
        integrated_summary="Resumo integrado.",
        caveats=[],
        data_quality_score=0.8,
        total_duration_ms=30000,
        model_used="qwen3:8b",
    )


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

    @pytest.mark.asyncio
    async def test_execute_step_emits_step_start_and_step_complete(self) -> None:
        """_execute_step emite step_start e step_complete via SSE."""
        mock_result = StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="structural_geologist",
            summary="Sumário.",
            findings=["finding"],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="reasoning",
            duration_ms=100,
        )

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "_execute_step",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await runner._execute_step(AnalysisStep.TECTONIC_HISTORY, {}, [])

        assert result is mock_result

        channel.close()
        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        types = _event_types(chunks)
        assert "step_start" in types
        assert "step_complete" in types

    @pytest.mark.asyncio
    async def test_execute_step_step_complete_payload(self) -> None:
        """step_complete payload contém step, step_index e result."""
        mock_result = StepResult(
            step=AnalysisStep.MAGMATIC_FERTILITY,
            agent="geochemist",
            summary="Magmatismo intenso.",
            findings=["Granito Jamon"],
            confidence=Confidence.MEDIUM,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="dados geoquímicos",
            duration_ms=200,
        )

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "_execute_step",
            new=AsyncMock(return_value=mock_result),
        ):
            await runner._execute_step(AnalysisStep.MAGMATIC_FERTILITY, {}, [])

        channel.close()
        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        complete_chunk = next((c for c in chunks if "event: step_complete" in c), None)
        assert complete_chunk is not None
        data_line = next(line for line in complete_chunk.split("\n") if line.startswith("data: "))
        payload = json.loads(data_line[len("data: ") :])
        assert payload["step"] == AnalysisStep.MAGMATIC_FERTILITY.value
        assert payload["step_index"] >= 0
        assert payload["result"]["agent"] == "geochemist"

    @pytest.mark.asyncio
    async def test_execute_step_unknown_step_index_is_minus_one(self) -> None:
        """Step não pertencente a _STEP_ORDER recebe step_index -1."""
        from unittest.mock import MagicMock

        mock_result = StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="structural_geologist",
            summary=".",
            findings=[],
            confidence=Confidence.LOW,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        unknown_step = MagicMock(spec=AnalysisStep)
        unknown_step.value = "unknown_step"

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "_execute_step",
            new=AsyncMock(return_value=mock_result),
        ):
            await runner._execute_step(unknown_step, {}, [])

        channel.close()
        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        start_chunk = next((c for c in chunks if "event: step_start" in c), None)
        assert start_chunk is not None
        data_line = next(line for line in start_chunk.split("\n") if line.startswith("data: "))
        payload = json.loads(data_line[len("data: ") :])
        assert payload["step_index"] == -1

    @pytest.mark.asyncio
    async def test_on_data_fetched_emits_data_fetch_done(self) -> None:
        """_on_data_fetched emite data_fetch_done com sources_found."""
        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        geo_data: dict = {
            "ocorrencias": [{"objectid": 1}],
            "gravimetria": [],
            "geoquimica": [{"objectid": 2}, {"objectid": 3}],
            "geocronologia": [],
            "litoestratigrafia": [{"objectid": 4}],
            "aerogeofisica": [],
        }
        await runner._on_data_fetched(geo_data)

        channel.close()
        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        types = _event_types(chunks)
        assert "data_fetch_done" in types

        done_chunk = next((c for c in chunks if "event: data_fetch_done" in c), None)
        assert done_chunk is not None
        data_line = next(line for line in done_chunk.split("\n") if line.startswith("data: "))
        payload = json.loads(data_line[len("data: ") :])
        assert payload["sources_found"] == 3  # ocorrencias, geoquimica, litoestratigrafia

    @pytest.mark.asyncio
    async def test_on_data_fetched_no_channel_is_noop(self) -> None:
        """_on_data_fetched sem canal SSE nao levanta excecao."""
        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)
        await runner._on_data_fetched({"ocorrencias": [{"objectid": 1}]})

    @pytest.mark.asyncio
    async def test_step_start_includes_agents(self) -> None:
        """step_start payload inclui a lista de agentes para o passo."""
        mock_result = StepResult(
            step=AnalysisStep.MAGMATIC_FERTILITY,
            agent="geochemist + geophysicist",
            summary=".",
            findings=[],
            confidence=Confidence.MEDIUM,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=100,
        )

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "_execute_step",
            new=AsyncMock(return_value=mock_result),
        ):
            await runner._execute_step(AnalysisStep.MAGMATIC_FERTILITY, {}, [])

        channel.close()
        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        start_chunk = next((c for c in chunks if "event: step_start" in c), None)
        assert start_chunk is not None
        data_line = next(line for line in start_chunk.split("\n") if line.startswith("data: "))
        payload = json.loads(data_line[len("data: ") :])
        assert "agents" in payload
        assert "geochemist" in payload["agents"]
        assert "geophysicist" in payload["agents"]

    @pytest.mark.asyncio
    async def test_execute_step_no_channel_returns_result(self) -> None:
        """_execute_step sem channel SSE ainda retorna o resultado corretamente."""
        mock_result = StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="structural_geologist",
            summary=".",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=50,
        )

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)
        # Sem set_channel

        with patch.object(
            Orchestrator,
            "_execute_step",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await runner._execute_step(AnalysisStep.TECTONIC_HISTORY, {}, [])

        assert result is mock_result


class TestAnalysisRunnerEta:
    """Testes do campo ETA nos eventos step_start (PRD-005 T2)."""

    def _make_mock_result(self, step: AnalysisStep = AnalysisStep.TECTONIC_HISTORY) -> StepResult:
        return StepResult(
            step=step,
            agent="structural_geologist",
            summary=".",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=100,
        )

    @pytest.mark.asyncio
    async def test_step_start_includes_elapsed_s(self) -> None:
        """step_start payload deve incluir elapsed_s (segundos desde início da análise)."""
        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "_execute_step",
            new=AsyncMock(return_value=self._make_mock_result()),
        ):
            await runner._execute_step(AnalysisStep.TECTONIC_HISTORY, {}, [])

        channel.close()
        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        start_chunk = next((c for c in chunks if "event: step_start" in c), None)
        assert start_chunk is not None
        data_line = next(line for line in start_chunk.split("\n") if line.startswith("data: "))
        payload = json.loads(data_line[len("data: ") :])
        assert "elapsed_s" in payload
        assert isinstance(payload["elapsed_s"], (int, float))
        assert payload["elapsed_s"] >= 0

    @pytest.mark.asyncio
    async def test_step_start_eta_none_on_first_step(self) -> None:
        """No primeiro step, eta_s deve ser None (sem histórico de duração)."""
        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        with patch.object(
            Orchestrator,
            "_execute_step",
            new=AsyncMock(return_value=self._make_mock_result()),
        ):
            await runner._execute_step(AnalysisStep.TECTONIC_HISTORY, {}, [])

        channel.close()
        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        start_chunk = next((c for c in chunks if "event: step_start" in c), None)
        assert start_chunk is not None
        data_line = next(line for line in start_chunk.split("\n") if line.startswith("data: "))
        payload = json.loads(data_line[len("data: ") :])
        # Primeiro step: sem histórico → eta_s = None
        assert payload.get("eta_s") is None

    @pytest.mark.asyncio
    async def test_step_start_eta_populated_after_first_step(self) -> None:
        """Após completar o 1º step, o 2º deve ter eta_s calculado."""
        mock_result_1 = self._make_mock_result(AnalysisStep.TECTONIC_HISTORY)
        mock_result_2 = self._make_mock_result(AnalysisStep.MAGMATIC_FERTILITY)

        with patch.object(Orchestrator, "__init__", return_value=None):
            runner = AnalysisRunner(None, None, None, None)

        channel = SseChannel()
        runner.set_channel(channel)

        results = [mock_result_1, mock_result_2]
        call_count = 0

        async def fake_execute(_self, step, geo_data, prev, bbox=None):
            nonlocal call_count
            result = results[call_count]
            call_count += 1
            return result

        with patch.object(Orchestrator, "_execute_step", new=fake_execute):
            await runner._execute_step(AnalysisStep.TECTONIC_HISTORY, {}, [])
            await runner._execute_step(AnalysisStep.MAGMATIC_FERTILITY, {}, [])

        channel.close()
        chunks: list[str] = []
        async for chunk in channel:
            chunks.append(chunk)

        # O 2º step_start deve ter eta_s numérico (não None)
        start_chunks = [c for c in chunks if "event: step_start" in c]
        assert len(start_chunks) == 2

        data_line_2 = next(
            line for line in start_chunks[1].split("\n") if line.startswith("data: ")
        )
        payload_2 = json.loads(data_line_2[len("data: ") :])
        assert payload_2.get("eta_s") is not None
        assert isinstance(payload_2["eta_s"], (int, float))
        assert payload_2["eta_s"] >= 0

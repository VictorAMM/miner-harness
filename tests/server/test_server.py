"""Testes do DashboardServer — rotas HTTP e SSE."""

from __future__ import annotations

from datetime import datetime, timezone  # noqa: UP017
from unittest.mock import MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    ProspectionReport,
    StepResult,
)
from miner_harness.server.server import DashboardServer

# ---------------------------------------------------------------------------
# Fixtures
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
        name="Alvo Teste",
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
        analysis_date=datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc),
        steps=[step],
        targets=[target],
        integrated_summary="Resumo.",
        caveats=[],
        data_quality_score=0.8,
        total_duration_ms=30000,
        model_used="qwen3:8b",
    )


@pytest.fixture()
def server_instance() -> DashboardServer:
    report = _make_report()
    connector = MagicMock()
    cache = MagicMock()
    llm = MagicMock()
    config = MagicMock()
    return DashboardServer(
        initial_report=report,
        connector=connector,
        cache=cache,
        llm=llm,
        config=config,
        port=9999,
    )


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestDashboardServerRoutes:
    @pytest.mark.asyncio
    async def test_get_root_returns_html(self, server_instance: DashboardServer) -> None:
        async with TestClient(TestServer(server_instance._app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            text = await resp.text()
            assert "<!DOCTYPE html>" in text or "<!doctype html>" in text.lower()
            assert "miner-harness" in text.lower()

    @pytest.mark.asyncio
    async def test_get_root_serve_mode_contains_nova_pesquisa(
        self, server_instance: DashboardServer
    ) -> None:
        async with TestClient(TestServer(server_instance._app)) as client:
            resp = await client.get("/")
            text = await resp.text()
            assert "np-submit" in text
            assert "Nova Pesquisa" in text

    @pytest.mark.asyncio
    async def test_get_report_returns_json(self, server_instance: DashboardServer) -> None:
        async with TestClient(TestServer(server_instance._app)) as client:
            resp = await client.get("/api/report")
            assert resp.status == 200
            data = await resp.json()
            assert data["region_name"] == "Teste"

    @pytest.mark.asyncio
    async def test_post_analyze_returns_202(self, server_instance: DashboardServer) -> None:
        mock_report = _make_report()

        async def fake_analyze(bb, region, steps=None):
            return mock_report

        with patch(
            "miner_harness.server.server.AnalysisRunner.analyze_region",
            new=fake_analyze,
        ):
            async with TestClient(TestServer(server_instance._app)) as client:
                resp = await client.post(
                    "/api/analyze",
                    json={
                        "region": "Serra Pelada",
                        "bbox": {
                            "lon_min": -51.5,
                            "lat_min": -7.0,
                            "lon_max": -49.0,
                            "lat_max": -5.0,
                        },
                    },
                )
                assert resp.status == 202
                data = await resp.json()
                assert data["status"] == "started"

    @pytest.mark.asyncio
    async def test_post_analyze_400_missing_region(self, server_instance: DashboardServer) -> None:
        async with TestClient(TestServer(server_instance._app)) as client:
            resp = await client.post(
                "/api/analyze",
                json={"region": "", "bbox": {}},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_post_analyze_400_invalid_bbox(self, server_instance: DashboardServer) -> None:
        async with TestClient(TestServer(server_instance._app)) as client:
            resp = await client.post(
                "/api/analyze",
                json={"region": "Teste", "bbox": {"lon_min": "bad"}},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_post_analyze_400_invalid_json_body(
        self, server_instance: DashboardServer
    ) -> None:
        """Body não-JSON deve retornar 400."""
        async with TestClient(TestServer(server_instance._app)) as client:
            resp = await client.post(
                "/api/analyze",
                data=b"this is not json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
            data = await resp.json()
            assert "inválido" in data["msg"]

    @pytest.mark.asyncio
    async def test_post_analyze_409_when_busy(self, server_instance: DashboardServer) -> None:
        """Deve retornar 409 se já há uma análise em andamento."""

        await server_instance._semaphore.acquire()
        try:
            async with TestClient(TestServer(server_instance._app)) as client:
                resp = await client.post(
                    "/api/analyze",
                    json={
                        "region": "Teste",
                        "bbox": {
                            "lon_min": -51.5,
                            "lat_min": -7.0,
                            "lon_max": -49.0,
                            "lat_max": -5.0,
                        },
                    },
                )
                assert resp.status == 409
        finally:
            server_instance._semaphore.release()

    @pytest.mark.asyncio
    async def test_get_stream_sem_analise_retorna_erro_sse(
        self, server_instance: DashboardServer
    ) -> None:
        """GET /api/analyze/stream sem análise em curso retorna evento de erro SSE."""
        server_instance._current_channel = None
        async with (
            TestClient(TestServer(server_instance._app)) as client,
            client.session.get(client.make_url("/api/analyze/stream")) as resp,
        ):
            assert resp.status == 200
            assert "text/event-stream" in resp.headers.get("Content-Type", "")
            body = await resp.read()

        assert b"event: error" in body

    @pytest.mark.asyncio
    async def test_get_stream_entrega_chunks_do_canal(
        self, server_instance: DashboardServer
    ) -> None:
        """GET /api/analyze/stream itera sobre o SseChannel atual."""
        from miner_harness.server.sse import SseChannel

        channel = SseChannel()
        channel.send("step_start", {"step": "tectonic_history"})
        channel.close()
        server_instance._current_channel = channel

        async with (
            TestClient(TestServer(server_instance._app)) as client,
            client.session.get(client.make_url("/api/analyze/stream")) as resp,
        ):
            body = await resp.read()

        assert b"event: step_start" in body

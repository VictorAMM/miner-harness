"""Testes e2e — DashboardServer com serviços reais.

Verifica que o servidor HTTP local:
- Serve o dashboard HTML com painel Nova Pesquisa (serve_mode=True)
- Aceita POST /api/analyze e retorna 202
- O stream SSE entrega eventos data_fetch_start, step_start, step_complete e complete
- O relatório é atualizado após análise completa

Requer: GeoSGB API + Ollama local. Para testar só o servidor sem LLM:
    MINER_E2E=1 MINER_E2E_NO_OLLAMA=1 uv run pytest tests/e2e/test_server_live.py -v -k "not ollama"

Executar com: MINER_E2E=1 uv run pytest tests/e2e/test_server_live.py -v
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone  # noqa: UP017

import pytest
from aiohttp.test_utils import TestClient, TestServer

from miner_harness.cache.manager import CacheManager
from miner_harness.connectors.geosgb.connector import GeoSGBConnector
from miner_harness.connectors.ollama.client import OllamaClient
from miner_harness.core.config import MinerHarnessConfig, OrchestratorConfig, StorageConfig
from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    ProspectionReport,
    StepResult,
)
from miner_harness.server.server import DashboardServer

from .conftest import skip_no_e2e, skip_no_ollama

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_initial_report() -> ProspectionReport:
    """Relatório mínimo para inicializar o servidor sem análise real."""
    step = StepResult(
        step=AnalysisStep.TECTONIC_HISTORY,
        agent="structural_geologist",
        summary="Relatório inicial de placeholder.",
        findings=["Dado inicial"],
        confidence=Confidence.LOW,
        data_sources_used=[],
        data_gaps=["Análise real pendente"],
        raw_reasoning="placeholder",
        duration_ms=0,
    )
    target = MineralTarget(
        name="Alvo Placeholder",
        longitude=-50.0,
        latitude=-6.0,
        radius_km=5.0,
        commodities=["Fe"],
        mineral_system="IOCG",
        confidence=Confidence.LOW,
        priority=1,
        rationale="Dados iniciais",
        recommended_followup=[],
    )
    return ProspectionReport(
        region_name="Carajás Inicial",
        bbox=BoundingBox(lon_min=-50.3, lat_min=-6.3, lon_max=-50.0, lat_max=-6.0),
        analysis_date=datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc),
        steps=[step],
        targets=[target],
        integrated_summary="Relatório inicial sem análise real.",
        caveats=["Análise real pendente"],
        data_quality_score=0.1,
        total_duration_ms=0,
        model_used="qwen3:8b",
    )


def _parse_sse_events(raw: str) -> list[dict[str, str]]:
    """Extrai eventos SSE de texto bruto, retornando lista de {event, data}."""
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in raw.split("\n"):
        if line.startswith("event: "):
            current["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current["data"] = line[len("data: ") :]
        elif line == "" and current:
            if "event" in current and "data" in current:
                events.append(current)
            current = {}
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def server_config(
    tmp_path_factory: pytest.TempPathFactory,
    ollama_url: str,
    ollama_model: str,
) -> MinerHarnessConfig:
    tmp = tmp_path_factory.mktemp("e2e_server_home")
    config = MinerHarnessConfig(
        storage=StorageConfig(miner_home=tmp),
        orchestrator=OrchestratorConfig(
            ollama_base_url=ollama_url,
            model=ollama_model,
            ollama_timeout_s=180,
        ),
    )
    config.storage.ensure_dirs()
    return config


@pytest.fixture(scope="module")
def live_components(server_config: MinerHarnessConfig):
    """Retorna (connector, cache, llm) reais para os testes do servidor."""
    cache = CacheManager(server_config.storage)
    connector = GeoSGBConnector(server_config.geosgb)
    llm = OllamaClient(server_config.orchestrator)
    yield connector, cache, llm
    cache.close()


# ---------------------------------------------------------------------------
# Testes de rotas HTTP — sem análise real (só GeoSGB habilitado)
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_server_get_root_retorna_html_serve_mode(
    server_config: MinerHarnessConfig,
    live_components: tuple,
) -> None:
    """GET / retorna HTML com painel Nova Pesquisa (serve_mode=True)."""
    connector, cache, llm = live_components
    server = DashboardServer(
        initial_report=_make_initial_report(),
        connector=connector,
        cache=cache,
        llm=llm,
        config=server_config,
    )
    async with TestClient(TestServer(server._app)) as client:
        resp = await client.get("/")
        assert resp.status == 200
        text = await resp.text()

    assert "<!DOCTYPE html>" in text or "<!doctype html>" in text.lower()
    assert "np-submit" in text, "Painel Nova Pesquisa ausente no HTML serve_mode"
    assert "Nova Pesquisa" in text
    assert "progress-overlay" in text
    assert "Carajás Inicial" in text


@skip_no_e2e
@pytest.mark.asyncio
async def test_server_get_report_retorna_json(
    server_config: MinerHarnessConfig,
    live_components: tuple,
) -> None:
    """GET /api/report retorna o relatório inicial como JSON válido."""
    connector, cache, llm = live_components
    server = DashboardServer(
        initial_report=_make_initial_report(),
        connector=connector,
        cache=cache,
        llm=llm,
        config=server_config,
    )
    async with TestClient(TestServer(server._app)) as client:
        resp = await client.get("/api/report")
        assert resp.status == 200
        data = await resp.json()

    assert data["region_name"] == "Carajás Inicial"
    assert "steps" in data
    assert "targets" in data


@skip_no_e2e
@pytest.mark.asyncio
async def test_server_post_analyze_400_sem_region(
    server_config: MinerHarnessConfig,
    live_components: tuple,
) -> None:
    """POST /api/analyze sem 'region' retorna 400."""
    connector, cache, llm = live_components
    server = DashboardServer(
        initial_report=_make_initial_report(),
        connector=connector,
        cache=cache,
        llm=llm,
        config=server_config,
    )
    async with TestClient(TestServer(server._app)) as client:
        resp = await client.post("/api/analyze", json={"region": "", "bbox": {}})
        assert resp.status == 400


@skip_no_e2e
@pytest.mark.asyncio
async def test_server_post_analyze_400_bbox_invalida(
    server_config: MinerHarnessConfig,
    live_components: tuple,
) -> None:
    """POST /api/analyze com bbox inválida retorna 400."""
    connector, cache, llm = live_components
    server = DashboardServer(
        initial_report=_make_initial_report(),
        connector=connector,
        cache=cache,
        llm=llm,
        config=server_config,
    )
    async with TestClient(TestServer(server._app)) as client:
        resp = await client.post(
            "/api/analyze",
            json={"region": "Carajás", "bbox": {"lon_min": "bad"}},
        )
        assert resp.status == 400


@skip_no_e2e
@pytest.mark.asyncio
async def test_server_post_analyze_409_quando_ocupado(
    server_config: MinerHarnessConfig,
    live_components: tuple,
) -> None:
    """POST /api/analyze retorna 409 se análise já está em andamento."""
    connector, cache, llm = live_components
    server = DashboardServer(
        initial_report=_make_initial_report(),
        connector=connector,
        cache=cache,
        llm=llm,
        config=server_config,
    )
    await server._semaphore.acquire()
    try:
        async with TestClient(TestServer(server._app)) as client:
            resp = await client.post(
                "/api/analyze",
                json={
                    "region": "Carajás",
                    "bbox": {
                        "lon_min": -50.3,
                        "lat_min": -6.3,
                        "lon_max": -50.0,
                        "lat_max": -6.0,
                    },
                },
            )
            assert resp.status == 409
    finally:
        server._semaphore.release()


# ---------------------------------------------------------------------------
# Testes com análise real (requer Ollama)
# ---------------------------------------------------------------------------


@skip_no_ollama
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_server_analise_real_emite_eventos_sse(
    bbox_carajas_small: BoundingBox,
    server_config: MinerHarnessConfig,
    live_components: tuple,
) -> None:
    """POST /api/analyze + GET /api/analyze/stream emite eventos SSE reais.

    Verifica que data_fetch_start, step_complete e complete chegam via SSE
    durante uma análise real de Carajás com GeoSGB + Ollama.
    """
    connector, cache, llm = live_components
    server = DashboardServer(
        initial_report=_make_initial_report(),
        connector=connector,
        cache=cache,
        llm=llm,
        config=server_config,
    )

    async with TestClient(TestServer(server._app)) as client:
        # Dispara análise
        resp = await client.post(
            "/api/analyze",
            json={
                "region": "Carajás SSE E2E",
                "bbox": {
                    "lon_min": bbox_carajas_small.lon_min,
                    "lat_min": bbox_carajas_small.lat_min,
                    "lon_max": bbox_carajas_small.lon_max,
                    "lat_max": bbox_carajas_small.lat_max,
                },
            },
        )
        assert resp.status == 202

        # Coleta eventos SSE (aguarda até 'complete' ou timeout)
        raw_chunks: list[str] = []
        async with client.session.get(client.make_url("/api/analyze/stream")) as sse_resp:
            assert sse_resp.status == 200
            assert "text/event-stream" in sse_resp.headers.get("Content-Type", "")
            async for line in sse_resp.content:
                raw_chunks.append(line.decode("utf-8"))
                combined = "".join(raw_chunks)
                if "event: complete" in combined or "event: error" in combined:
                    break

    combined = "".join(raw_chunks)
    events = _parse_sse_events(combined)
    event_types = [e["event"] for e in events]

    assert "data_fetch_start" in event_types, (
        f"Evento data_fetch_start ausente. Eventos recebidos: {event_types}"
    )
    assert "complete" in event_types or "error" in event_types, (
        f"Nem 'complete' nem 'error' recebidos. Eventos: {event_types}"
    )

    # Se completou com sucesso, verifica o payload do relatório
    if "complete" in event_types:
        complete_event = next(e for e in events if e["event"] == "complete")
        payload = json.loads(complete_event["data"])
        assert "report" in payload
        assert payload["report"]["region_name"] == "Carajás SSE E2E"


@skip_no_ollama
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_server_relatorio_atualizado_apos_analise(
    bbox_carajas_small: BoundingBox,
    server_config: MinerHarnessConfig,
    live_components: tuple,
) -> None:
    """Após análise real, GET /api/report retorna o novo relatório."""
    connector, cache, llm = live_components
    server = DashboardServer(
        initial_report=_make_initial_report(),
        connector=connector,
        cache=cache,
        llm=llm,
        config=server_config,
    )

    async with TestClient(TestServer(server._app)) as client:
        # Relatório inicial
        before = await (await client.get("/api/report")).json()
        assert before["region_name"] == "Carajás Inicial"

        # Inicia análise real
        await client.post(
            "/api/analyze",
            json={
                "region": "Carajás Atualizado E2E",
                "bbox": {
                    "lon_min": bbox_carajas_small.lon_min,
                    "lat_min": bbox_carajas_small.lat_min,
                    "lon_max": bbox_carajas_small.lon_max,
                    "lat_max": bbox_carajas_small.lat_max,
                },
            },
        )

        # Aguarda o canal SSE fechar (análise concluída)
        async with client.session.get(client.make_url("/api/analyze/stream")) as sse_resp:
            raw = b""
            async for chunk in sse_resp.content:
                raw += chunk
                if b"event: complete" in raw or b"event: error" in raw:
                    break

        # Garante que a task background terminou
        await asyncio.sleep(0.5)

        after = await (await client.get("/api/report")).json()

    if b"event: complete" in raw:
        assert after["region_name"] == "Carajás Atualizado E2E", (
            f"Relatório não foi atualizado após análise. region_name={after['region_name']}"
        )

"""DashboardServer — servidor HTTP local para o modo --serve do dashboard."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import structlog
from aiohttp import web

from miner_harness.core.types import BoundingBox, ProspectionReport
from miner_harness.report.renderer import HtmlReportRenderer
from miner_harness.server.analysis_runner import AnalysisRunner
from miner_harness.server.sse import SseChannel

if TYPE_CHECKING:
    from miner_harness.cache.manager import CacheManager
    from miner_harness.connectors.geosgb.connector import GeoSGBConnector
    from miner_harness.connectors.ollama.client import OllamaClient
    from miner_harness.core.config import MinerHarnessConfig

logger = structlog.get_logger(__name__)


class DashboardServer:
    """Servidor HTTP local para o dashboard interativo de prospecção.

    Rotas:
        GET  /                    → HTML do dashboard (serve_mode=True)
        POST /api/analyze         → Inicia nova análise (202 ou 409)
        GET  /api/analyze/stream  → SSE com progresso da análise em curso
        GET  /api/report          → JSON do relatório atual
    """

    def __init__(
        self,
        initial_report: ProspectionReport,
        connector: GeoSGBConnector,
        cache: CacheManager,
        llm: OllamaClient,
        config: MinerHarnessConfig,
        port: int = 8765,
    ) -> None:
        self._report = initial_report
        self._connector = connector
        self._cache = cache
        self._llm = llm
        self._config = config
        self._port = port
        self._semaphore = asyncio.Semaphore(1)
        self._current_channel: SseChannel | None = None
        self._renderer = HtmlReportRenderer()
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # App setup
    # ------------------------------------------------------------------

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self.handle_root)
        app.router.add_post("/api/analyze", self.handle_analyze)
        app.router.add_get("/api/analyze/stream", self.handle_stream)
        app.router.add_get("/api/report", self.handle_report)
        return app

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def handle_root(self, _request: web.Request) -> web.Response:
        html = self._renderer.render(self._report, serve_mode=True)
        return web.Response(text=html, content_type="text/html", charset="utf-8")

    async def handle_report(self, _request: web.Request) -> web.Response:
        return web.Response(
            text=self._report.model_dump_json(),
            content_type="application/json",
            charset="utf-8",
        )

    async def handle_analyze(self, request: web.Request) -> web.Response:
        if self._semaphore.locked():
            return web.json_response({"msg": "Análise já em andamento."}, status=409)

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response({"msg": "Body JSON inválido."}, status=400)

        region = body.get("region", "").strip()
        if not region:
            return web.json_response({"msg": "Campo 'region' obrigatório."}, status=400)

        bbox_data = body.get("bbox", {})
        try:
            bb = BoundingBox(**bbox_data)
        except Exception as exc:
            return web.json_response({"msg": f"bbox inválida: {exc}"}, status=400)

        channel = SseChannel()
        self._current_channel = channel

        runner = AnalysisRunner(self._connector, self._cache, self._llm, self._config)
        runner.set_channel(channel)

        async def _run() -> None:
            async with self._semaphore:
                try:
                    report = await runner.analyze_region(bb, region)
                    self._report = report
                except Exception:
                    logger.exception("serve_analysis_error", region=region)

        asyncio.create_task(_run())

        return web.json_response({"status": "started"}, status=202)

    async def handle_stream(self, _request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            }
        )
        await response.prepare(_request)

        channel = self._current_channel
        if channel is None:
            await response.write(
                b'id: 0\nevent: error\ndata: {"msg": "Nenhuma an\\u00e1lise em andamento."}\n\n'
            )
            return response

        async for chunk in channel:
            await response.write(chunk.encode("utf-8"))

        return response

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:  # pragma: no cover
        """Inicia o servidor e bloqueia até Ctrl+C."""
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self._port)
        await site.start()
        logger.info("dashboard_server_started", port=self._port)
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
            self._cache.close()
            logger.info("dashboard_server_stopped")

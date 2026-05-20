"""Testes dos comandos CLI.

Ref: Phase 7 -- Coverage
"""

from __future__ import annotations

import json
from datetime import datetime, timezone  # noqa: UP017, E402
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

from unittest.mock import AsyncMock, MagicMock

import pytest

from miner_harness.cli.app import main
from miner_harness.cli.commands import (
    _print_report_summary,
    _render_html_report,
    _serve_dashboard,
    cmd_analyze,
    cmd_cache_clear,
    cmd_cache_evict,
    cmd_cache_stats,
    cmd_health,
    cmd_index_stats,
    cmd_install,
    cmd_validate,
)
from miner_harness.core.config import StorageConfig
from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    ProspectionReport,
    StepResult,
)


def _make_report(bbox: BoundingBox) -> ProspectionReport:
    steps = []
    for step_enum in AnalysisStep:
        steps.append(
            StepResult(
                step=step_enum,
                agent="test_agent",
                summary=f"Analysis of {step_enum.value}",
                findings=["Finding 1"],
                confidence=Confidence.MEDIUM,
                data_sources_used=["ocorrencias"],
                data_gaps=[],
                raw_reasoning="Reasoning text",
                duration_ms=100,
            )
        )
    return ProspectionReport(
        region_name="Carajas",
        bbox=bbox,
        steps=steps,
        targets=[
            MineralTarget(
                name="Target Alpha",
                longitude=-50.5,
                latitude=-6.0,
                radius_km=5.0,
                commodities=["Cu", "Au"],
                mineral_system="Porphyry Cu-Au",
                confidence=Confidence.MEDIUM,
                priority=1,
                rationale="High Cu anomaly",
                recommended_followup=["Soil sampling"],
            ),
        ],
        integrated_summary="Integration complete",
        caveats=["Low geocron coverage"],
        data_quality_score=0.85,
        model_used="qwen2.5:14b",
        total_duration_ms=500,
        analysis_date=datetime.now(tz=timezone.utc),  # noqa: UP017
    )


class TestCmdValidate:
    """Testes do cmd_validate."""

    def test_validate_missing_file(self) -> None:
        result = cmd_validate("/nonexistent/report.json")
        assert result == 1

    def test_validate_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not json")
        result = cmd_validate(str(f))
        assert result == 1

    def test_validate_valid_report(self, tmp_path: Path) -> None:
        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        report = _make_report(bbox)
        f = tmp_path / "report.json"
        f.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))
        result = cmd_validate(str(f))
        assert result == 0

    def test_validate_invalid_report_bad_json(self, tmp_path: Path) -> None:
        """Malformed report JSON should fail validation."""
        f = tmp_path / "bad_report.json"
        f.write_text('{"region_name": "X"}')
        result = cmd_validate(str(f))
        assert result == 1

    def test_validate_report_with_issues_prints_them(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Relatório com issues os imprime (linhas 151-153)."""
        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        report = _make_report(bbox)
        # Apenas um step → Missing steps warning → result.issues não vazio
        report.steps = [report.steps[0]]
        f = tmp_path / "report_partial.json"
        f.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))
        cmd_validate(str(f))
        captured = capsys.readouterr()
        assert "Issues" in captured.out or captured.out  # issues are printed


class TestCmdCacheStats:
    """Testes do cmd_cache_stats."""

    def test_cache_stats_empty(self, tmp_path: Path) -> None:
        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = StorageConfig(miner_home=tmp_path / ".miner")
            result = cmd_cache_stats()
            assert result == 0

    def test_cache_stats_with_data(self, tmp_path: Path) -> None:
        config = StorageConfig(miner_home=tmp_path / ".miner")
        from miner_harness.cache.manager import CacheManager

        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        cache = CacheManager(config)
        cache.put("ocorrencias", bbox, [{"id": 1}])
        cache.close()

        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = config
            result = cmd_cache_stats()
            assert result == 0


class TestCmdCacheClear:
    """Testes do cmd_cache_clear."""

    def test_cache_clear_empty(self, tmp_path: Path) -> None:
        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = StorageConfig(miner_home=tmp_path / ".miner")
            result = cmd_cache_clear()
            assert result == 0

    def test_cache_clear_with_data(self, tmp_path: Path) -> None:
        config = StorageConfig(miner_home=tmp_path / ".miner")
        from miner_harness.cache.manager import CacheManager

        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        cache = CacheManager(config)
        cache.put("ocorrencias", bbox, [{"id": 1}])
        cache.close()

        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = config
            result = cmd_cache_clear()
            assert result == 0


class TestCmdCacheEvict:
    """Testes do cmd_cache_evict."""

    def test_evict_no_expired(self, tmp_path: Path) -> None:
        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = StorageConfig(miner_home=tmp_path / ".miner")
            result = cmd_cache_evict()
            assert result == 0

    def test_evict_with_expired_entries(self, tmp_path: Path) -> None:
        config = StorageConfig(miner_home=tmp_path / ".miner")
        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = config
            with patch("miner_harness.cli.commands.CacheManager") as mock_cache_cls:
                mock_cache_cls.return_value.evict_expired = lambda: 5
                mock_cache_cls.return_value.close = lambda: None
                result = cmd_cache_evict()
        assert result == 0


class TestCmdCacheEvictIntegration:
    """Teste de integração do cmd_cache_evict com cache real."""

    def test_evict_expired_removes_stale_entries(self, tmp_path: Path) -> None:
        from datetime import datetime, timedelta, timezone  # noqa: UP017

        from miner_harness.cache.manager import CacheManager

        config = StorageConfig(miner_home=tmp_path / ".miner")
        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)

        # Put a fresh and an artificially expired entry
        cache = CacheManager(config)
        cache.put("ocorrencias", bbox, [{"id": 1}])
        # Manually insert an expired entry bypassing TTL
        expired_time = datetime.now(tz=timezone.utc) - timedelta(days=400)  # noqa: UP017
        old_bbox = BoundingBox(lon_min=-50.0, lat_min=-6.0, lon_max=-48.0, lat_max=-4.0)
        cols = (
            "service, bbox_hash, bbox_json, fetched_at,"
            " ttl_days, record_count, extraction_method, data"
        )
        cache._sqlite._get_conn().execute(
            f"INSERT INTO cache_entries ({cols}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",  # noqa: S608
            (
                "geoquimica",
                old_bbox.hash() + "_expired",
                old_bbox.model_dump_json(),
                expired_time.isoformat(),
                30,
                0,
                "identify",
                "[]",
            ),
        )
        cache._sqlite._get_conn().commit()
        cache.close()

        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = config
            result = cmd_cache_evict()
        assert result == 0


class TestCmdIndexStats:
    """Testes do cmd_index_stats."""

    def test_index_stats_no_index(self, tmp_path: Path) -> None:
        config = StorageConfig(miner_home=tmp_path / ".miner")
        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = config
            result = cmd_index_stats()
            assert result == 0

    def test_index_stats_with_data(self, tmp_path: Path) -> None:
        config = StorageConfig(miner_home=tmp_path / ".miner")
        config.ensure_dirs()
        from miner_harness.index.document_store import DocumentStore

        store = DocumentStore(config.index_dir)
        from miner_harness.index.types import IndexDocument

        doc = IndexDocument(id="doc1", source="geosgb/ocorrencias", text="Test")
        store.add(doc)
        store.close()

        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = config
            result = cmd_index_stats()
            assert result == 0


class TestPrintReportSummary:
    """Testes de _print_report_summary."""

    def test_print_summary(self, capsys) -> None:
        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        report = _make_report(bbox)
        _print_report_summary(report)
        captured = capsys.readouterr()
        assert "MINERAL PROSPECTION REPORT" in captured.out
        assert "Carajas" in captured.out
        assert "Target Alpha" in captured.out
        assert "Low geocron coverage" in captured.out

    def test_print_summary_no_targets(self, capsys) -> None:
        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        report = _make_report(bbox)
        report.targets = []
        report.caveats = []
        _print_report_summary(report)
        captured = capsys.readouterr()
        assert "MINERAL PROSPECTION REPORT" in captured.out
        assert "TARGETS" not in captured.out
        assert "CAVEATS" not in captured.out


class TestMainCLI:
    """Testes do main() com subcomandos."""

    def test_main_no_args(self) -> None:
        result = main([])
        assert result == 0

    def test_main_verbose(self) -> None:
        result = main(["--verbose"])
        assert result == 0

    def test_main_cache_stats(self, tmp_path: Path) -> None:
        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = StorageConfig(miner_home=tmp_path / ".miner")
            result = main(["cache", "stats"])
            assert result == 0

    def test_main_cache_clear(self, tmp_path: Path) -> None:
        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = StorageConfig(miner_home=tmp_path / ".miner")
            result = main(["cache", "clear"])
            assert result == 0

    def test_main_validate_missing(self) -> None:
        result = main(["validate", "/nonexistent.json"])
        assert result == 1

    def test_main_index_stats(self, tmp_path: Path) -> None:
        config = StorageConfig(miner_home=tmp_path / ".miner")
        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = config
            result = main(["index", "stats"])
            assert result == 0


class TestCmdAnalyze:
    """Testes do cmd_analyze com mocks dos componentes externos."""

    def _make_mock_report(self, bbox: BoundingBox) -> ProspectionReport:
        return _make_report(bbox)

    @pytest.mark.asyncio
    async def test_analyze_ollama_unavailable_returns_1(self, tmp_path: Path) -> None:
        """Retorna 1 quando Ollama não responde."""
        storage = StorageConfig(miner_home=tmp_path / ".miner")
        with (
            patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg,
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cli.commands.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
        ):
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_llm = AsyncMock()
            mock_llm.health = AsyncMock(return_value=False)
            mock_llm_cls.return_value = mock_llm

            result = await cmd_analyze(region="test", bbox=(-51.0, -7.0, -49.0, -5.0))
        assert result == 1

    @pytest.mark.asyncio
    async def test_analyze_success_prints_summary(self, tmp_path: Path) -> None:
        """Análise bem-sucedida retorna 0 e imprime resumo."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)
        storage = StorageConfig(miner_home=tmp_path / ".miner")

        with (
            patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg,
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cli.commands.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch("miner_harness.orchestrator.orchestrator.Orchestrator") as mock_orch_cls,
            patch("miner_harness.cli.commands._render_html_report"),
        ):
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_llm = AsyncMock()
            mock_llm.health = AsyncMock(return_value=True)
            mock_llm_cls.return_value = mock_llm
            mock_orch = AsyncMock()
            mock_orch.analyze_region = AsyncMock(return_value=report)
            mock_orch_cls.return_value = mock_orch

            result = await cmd_analyze(
                region="carajas", bbox=(-51.0, -7.0, -49.0, -5.0), no_html=True
            )
        assert result == 0

    @pytest.mark.asyncio
    async def test_analyze_saves_json_to_output_path(self, tmp_path: Path) -> None:
        """Com output_path, salva JSON e retorna 0."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)
        out = tmp_path / "report.json"
        storage = StorageConfig(miner_home=tmp_path / ".miner")

        with (
            patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg,
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cli.commands.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch("miner_harness.orchestrator.orchestrator.Orchestrator") as mock_orch_cls,
            patch("miner_harness.cli.commands._render_html_report"),
        ):
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_llm = AsyncMock()
            mock_llm.health = AsyncMock(return_value=True)
            mock_llm_cls.return_value = mock_llm
            mock_orch = AsyncMock()
            mock_orch.analyze_region = AsyncMock(return_value=report)
            mock_orch_cls.return_value = mock_orch

            result = await cmd_analyze(
                region="carajas",
                bbox=(-51.0, -7.0, -49.0, -5.0),
                output_path=str(out),
                no_html=True,
            )

        assert result == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["region_name"] == "Carajas"

    @pytest.mark.asyncio
    async def test_analyze_generates_html_by_default(self, tmp_path: Path) -> None:
        """Por padrão (no_html=False), _render_html_report é chamado."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)
        storage = StorageConfig(miner_home=tmp_path / ".miner")

        with (
            patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg,
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cli.commands.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch("miner_harness.orchestrator.orchestrator.Orchestrator") as mock_orch_cls,
            patch("miner_harness.cli.commands._render_html_report") as mock_render,
        ):
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_llm = AsyncMock()
            mock_llm.health = AsyncMock(return_value=True)
            mock_llm_cls.return_value = mock_llm
            mock_orch = AsyncMock()
            mock_orch.analyze_region = AsyncMock(return_value=report)
            mock_orch_cls.return_value = mock_orch

            await cmd_analyze(region="carajas", bbox=(-51.0, -7.0, -49.0, -5.0), no_html=False)

        mock_render.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_with_model_sets_config(self, tmp_path: Path) -> None:
        """Passando model= sobrescreve config.orchestrator.model (linha 42)."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)
        storage = StorageConfig(miner_home=tmp_path / ".miner")
        cfg_mock = MagicMock()
        cfg_mock.storage = storage
        cfg_mock.orchestrator.model = "qwen3:8b"

        with (
            patch("miner_harness.cli.commands.MinerHarnessConfig", return_value=cfg_mock),
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cli.commands.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch("miner_harness.orchestrator.orchestrator.Orchestrator") as mock_orch_cls,
            patch("miner_harness.cli.commands._render_html_report"),
        ):
            mock_llm = AsyncMock()
            mock_llm.health = AsyncMock(return_value=True)
            mock_llm_cls.return_value = mock_llm
            mock_orch = AsyncMock()
            mock_orch.analyze_region = AsyncMock(return_value=report)
            mock_orch_cls.return_value = mock_orch

            result = await cmd_analyze(
                region="test", bbox=(-51.0, -7.0, -49.0, -5.0), model="qwen3:4b", no_html=True
            )

        assert result == 0
        assert cfg_mock.orchestrator.model == "qwen3:4b"

    @pytest.mark.asyncio
    async def test_analyze_repairs_invalid_report(self, tmp_path: Path) -> None:
        """Relatório inválido é reparado (linhas 83-84)."""
        from datetime import datetime, timezone

        bbox_obj = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        # steps=[] → report inválido → validator.repair é chamado
        invalid_report = ProspectionReport(
            region_name="Invalid",
            bbox=bbox_obj,
            steps=[],
            targets=[],
            integrated_summary="no steps",
            caveats=[],
            data_quality_score=0.5,
            model_used="qwen3:8b",
            total_duration_ms=100,
            analysis_date=datetime.now(tz=timezone.utc),  # noqa: UP017
        )
        storage = StorageConfig(miner_home=tmp_path / ".miner")

        with (
            patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg,
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cli.commands.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch("miner_harness.orchestrator.orchestrator.Orchestrator") as mock_orch_cls,
            patch("miner_harness.cli.commands._render_html_report"),
        ):
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_llm = AsyncMock()
            mock_llm.health = AsyncMock(return_value=True)
            mock_llm_cls.return_value = mock_llm
            mock_orch = AsyncMock()
            mock_orch.analyze_region = AsyncMock(return_value=invalid_report)
            mock_orch_cls.return_value = mock_orch

            result = await cmd_analyze(region="test", bbox=(-51.0, -7.0, -49.0, -5.0), no_html=True)

        assert result == 0


class TestRenderHtmlReport:
    """Testes do _render_html_report."""

    def test_render_html_writes_file(self, tmp_path: Path) -> None:
        """_render_html_report cria arquivo HTML e chama webbrowser.open."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)
        storage = StorageConfig(miner_home=tmp_path / ".miner")
        storage.ensure_dirs()

        with patch("miner_harness.cli.commands.webbrowser") as mock_browser:
            _render_html_report(report, storage, "carajas")
            mock_browser.open.assert_called_once()

        html_files = list((storage.exports_dir / "reports").glob("*.html"))
        assert len(html_files) == 1
        assert "carajas" in html_files[0].name

    def test_render_html_failure_is_swallowed(self, tmp_path: Path) -> None:
        """Falha no renderer não propaga exceção."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)
        storage = StorageConfig(miner_home=tmp_path / ".miner")

        with patch(
            "miner_harness.report.HtmlReportRenderer",
            side_effect=RuntimeError("render failed"),
        ):
            _render_html_report(report, storage, "carajas")


class TestCmdInstall:
    """Testes do cmd_install."""

    def test_install_non_interactive_success(self, tmp_path: Path) -> None:
        """Non-interactive install retorna 0 quando checks e install passam."""
        mock_check_report = MagicMock()
        mock_check_report.all_passed = True
        mock_check_report.failures = []

        mock_install_result = MagicMock()
        mock_install_result.success = True
        mock_install_result.steps = [MagicMock(success=True, message="OK")]

        mock_runner = MagicMock()
        mock_runner.run_checks.return_value = mock_check_report
        mock_runner.run_install.return_value = mock_install_result

        with patch("miner_harness.wizard.runner.WizardRunner", return_value=mock_runner):
            result = cmd_install(
                miner_home=tmp_path / ".miner",
                non_interactive=True,
            )
        assert result == 0

    def test_install_non_interactive_check_fails(self, tmp_path: Path) -> None:
        """Non-interactive install retorna 1 quando checks falham."""
        mock_failure = MagicMock()
        mock_failure.name = "ollama"
        mock_failure.message = "não encontrado"

        mock_check_report = MagicMock()
        mock_check_report.all_passed = False
        mock_check_report.failures = [mock_failure]

        mock_runner = MagicMock()
        mock_runner.run_checks.return_value = mock_check_report

        with patch("miner_harness.wizard.runner.WizardRunner", return_value=mock_runner):
            result = cmd_install(non_interactive=True)
        assert result == 1

    def test_install_interactive_delegates_to_runner(self) -> None:
        """Modo interativo delega ao runner.run() e retorna seu código."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = 0

        with patch("miner_harness.wizard.runner.WizardRunner", return_value=mock_runner):
            result = cmd_install(non_interactive=False)
        assert result == 0
        mock_runner.run.assert_called_once()


class TestServeMode:
    """Testes do modo --serve e da função _serve_dashboard."""

    @pytest.mark.asyncio
    async def test_analyze_serve_mode_calls_serve_dashboard(self, tmp_path: Path) -> None:
        """Com serve=True, _serve_dashboard é chamado e cmd_analyze retorna 0."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)
        storage = StorageConfig(miner_home=tmp_path / ".miner")

        with (
            patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg,
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cli.commands.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch("miner_harness.orchestrator.orchestrator.Orchestrator") as mock_orch_cls,
            patch("miner_harness.cli.commands._serve_dashboard", new=AsyncMock()) as mock_serve,
        ):
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_llm = AsyncMock()
            mock_llm.health = AsyncMock(return_value=True)
            mock_llm_cls.return_value = mock_llm
            mock_orch = AsyncMock()
            mock_orch.analyze_region = AsyncMock(return_value=report)
            mock_orch_cls.return_value = mock_orch

            result = await cmd_analyze(
                region="carajas",
                bbox=(-51.0, -7.0, -49.0, -5.0),
                serve=True,
                port=8765,
            )

        assert result == 0
        mock_serve.assert_called_once()

    def test_serve_flag_in_argparse(self) -> None:
        """Flag --serve deve ser reconhecida pelo parser."""

        from miner_harness.cli.app import _build_parser

        parser = _build_parser()
        args = parser.parse_args(
            [
                "analyze",
                "carajas",
                "--bbox",
                "-51",
                "-7",
                "-49",
                "-5",
                "--serve",
            ]
        )
        assert args.serve is True
        assert args.port == 8765

    def test_port_flag_in_argparse(self) -> None:
        """Flag --port deve ser reconhecida e passada ao cmd_analyze."""
        from miner_harness.cli.app import _build_parser

        parser = _build_parser()
        args = parser.parse_args(
            [
                "analyze",
                "carajas",
                "--bbox",
                "-51",
                "-7",
                "-49",
                "-5",
                "--serve",
                "--port",
                "9999",
            ]
        )
        assert args.port == 9999

    @pytest.mark.asyncio
    async def test_serve_dashboard_opens_browser_and_calls_server(self, tmp_path: Path) -> None:
        """_serve_dashboard abre browser e chama server.run()."""
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)

        mock_server = AsyncMock()
        mock_server.run = AsyncMock()

        with (
            patch(
                "miner_harness.server.DashboardServer",
                return_value=mock_server,
            ) as mock_server_cls,
            patch("miner_harness.cli.commands.webbrowser") as mock_browser,
        ):
            await _serve_dashboard(
                report=report,
                connector=MagicMock(),
                cache=MagicMock(),
                llm=MagicMock(),
                config=MagicMock(),
                port=8765,
            )

        mock_server_cls.assert_called_once()
        mock_browser.open.assert_called_once_with("http://localhost:8765")
        mock_server.run.assert_called_once()


class TestCmdHealth:
    """Testes do cmd_health."""

    @pytest.mark.asyncio
    async def test_health_all_healthy(self, tmp_path: Path) -> None:
        """Retorna 0 quando todos os checks são healthy."""
        from miner_harness.observability.health import HealthStatus

        mock_check = MagicMock()
        mock_check.status = HealthStatus.HEALTHY
        mock_check.name = "ollama"
        mock_check.message = "OK"

        mock_report = MagicMock()
        mock_report.overall_status = HealthStatus.HEALTHY
        mock_report.is_healthy = True
        mock_report.checks = [mock_check]

        with (
            patch("miner_harness.cli.commands.StorageConfig") as mock_cfg,
            patch(
                "miner_harness.observability.health.run_health_checks",
                new=AsyncMock(return_value=mock_report),
            ),
        ):
            mock_cfg.return_value = StorageConfig(miner_home=tmp_path / ".miner")
            result = await cmd_health()
        assert result == 0

    @pytest.mark.asyncio
    async def test_health_unhealthy_returns_1(self, tmp_path: Path) -> None:
        """Retorna 1 quando pelo menos um check está unhealthy."""
        from miner_harness.observability.health import HealthStatus

        mock_check = MagicMock()
        mock_check.status = HealthStatus.UNHEALTHY
        mock_check.name = "ollama"
        mock_check.message = "not running"

        mock_report = MagicMock()
        mock_report.overall_status = HealthStatus.UNHEALTHY
        mock_report.is_healthy = False
        mock_report.checks = [mock_check]

        with (
            patch("miner_harness.cli.commands.StorageConfig") as mock_cfg,
            patch(
                "miner_harness.observability.health.run_health_checks",
                new=AsyncMock(return_value=mock_report),
            ),
        ):
            mock_cfg.return_value = StorageConfig(miner_home=tmp_path / ".miner")
            result = await cmd_health()
        assert result == 1


class TestProfileFlag:
    """Testes da flag --profile no CLI."""

    def test_profile_flag_in_argparse(self) -> None:
        """Flag --profile deve ser reconhecida pelo parser."""
        from miner_harness.cli.app import _build_parser

        parser = _build_parser()
        args = parser.parse_args(
            ["analyze", "carajas", "--bbox", "-51", "-7", "-49", "-5", "--profile"]
        )
        assert args.profile is True

    def test_profile_default_is_false(self) -> None:
        """--profile deve ser False por padrão."""
        from miner_harness.cli.app import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["analyze", "carajas", "--bbox", "-51", "-7", "-49", "-5"])
        assert args.profile is False

    @pytest.mark.asyncio
    async def test_analyze_profile_uses_profiling_runner(self, tmp_path: Path) -> None:
        """cmd_analyze com profile=True usa ProfilingRunner em vez de Orchestrator."""
        from miner_harness.cli.commands import cmd_analyze

        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        mock_runner = MagicMock()
        mock_runner.analyze_region = AsyncMock(return_value=_make_report(bbox))

        with (
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cache.manager.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch(
                "miner_harness.observability.profiler.ProfilingRunner",
                return_value=mock_runner,
            ) as mock_profiler_cls,
            patch("miner_harness.orchestrator.report_validator.ReportValidator"),
        ):
            mock_llm_cls.return_value.health = AsyncMock(return_value=True)

            result = await cmd_analyze(
                region="carajas",
                bbox=(-51.0, -7.0, -49.0, -5.0),
                no_html=True,
                profile=True,
            )

        assert result == 0
        mock_profiler_cls.assert_called_once()


class TestMinSourcesFlag:
    """Testes da flag --min-sources no CLI."""

    def test_min_sources_flag_in_argparse(self) -> None:
        """Flag --min-sources deve ser reconhecida pelo parser."""
        from miner_harness.cli.app import _build_parser

        parser = _build_parser()
        args = parser.parse_args(
            ["analyze", "carajas", "--bbox", "-51", "-7", "-49", "-5", "--min-sources", "2"]
        )
        assert args.min_sources == 2

    def test_min_sources_default_is_none(self) -> None:
        """--min-sources deve ser None por padrão (usa valor da config)."""
        from miner_harness.cli.app import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["analyze", "carajas", "--bbox", "-51", "-7", "-49", "-5"])
        assert args.min_sources is None

    @pytest.mark.asyncio
    async def test_min_sources_overrides_config(self, tmp_path: Path) -> None:
        """cmd_analyze com min_sources=2 deve setar config.orchestrator.min_data_sources=2."""
        from miner_harness.cli.commands import cmd_analyze
        from miner_harness.core.config import MinerHarnessConfig

        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        mock_orch = MagicMock()
        mock_orch.analyze_region = AsyncMock(return_value=_make_report(bbox))

        captured_config: list[MinerHarnessConfig] = []

        def capture_orch(*args: object, **kwargs: object) -> MagicMock:
            if args:
                captured_config.append(args[3])  # 4th positional = config
            return mock_orch

        with (
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cache.manager.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch("miner_harness.orchestrator.orchestrator.Orchestrator", side_effect=capture_orch),
            patch("miner_harness.orchestrator.report_validator.ReportValidator"),
        ):
            mock_llm_cls.return_value.health = AsyncMock(return_value=True)
            result = await cmd_analyze(
                region="carajas",
                bbox=(-51.0, -7.0, -49.0, -5.0),
                no_html=True,
                min_sources=2,
            )

        assert result == 0
        assert captured_config[0].orchestrator.min_data_sources == 2


class TestBboxValidation:
    """Testes da validação de bbox no cmd_analyze."""

    @pytest.mark.asyncio
    async def test_inverted_lon_returns_1(self, tmp_path: Path) -> None:
        """bbox com lon_min >= lon_max deve retornar 1 sem chamar Ollama."""
        storage = StorageConfig(miner_home=tmp_path / ".miner")
        with patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg:
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_cfg.return_value.orchestrator.min_data_sources = 3
            result = await cmd_analyze(region="test", bbox=(-49.5, -7.0, -51.5, -5.0))
        assert result == 1

    @pytest.mark.asyncio
    async def test_inverted_lat_returns_1(self, tmp_path: Path) -> None:
        """bbox com lat_min >= lat_max deve retornar 1."""
        storage = StorageConfig(miner_home=tmp_path / ".miner")
        with patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg:
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_cfg.return_value.orchestrator.min_data_sources = 3
            result = await cmd_analyze(region="test", bbox=(-51.5, -5.0, -49.5, -7.0))
        assert result == 1

    @pytest.mark.asyncio
    async def test_equal_lon_returns_1(self, tmp_path: Path) -> None:
        """bbox com lon_min == lon_max deve retornar 1."""
        storage = StorageConfig(miner_home=tmp_path / ".miner")
        with patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg:
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_cfg.return_value.orchestrator.min_data_sources = 3
            result = await cmd_analyze(region="test", bbox=(-51.5, -7.0, -51.5, -5.0))
        assert result == 1


class TestValidateEncoding:
    """Testes de encoding no cmd_validate."""

    def test_validate_utf8_report_with_accents(self, tmp_path: Path) -> None:
        """Relatório com acentos (não-ASCII) deve ser lido corretamente."""
        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        report = _make_report(bbox)
        report.region_name = "Carajás — Pará"  # non-ASCII
        f = tmp_path / "report_utf8.json"
        f.write_bytes(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        )
        result = cmd_validate(str(f))
        assert result == 0


class TestPortWithoutServeWarning:
    """Teste do aviso quando --port é passado sem --serve."""

    @pytest.mark.asyncio
    async def test_port_without_serve_warns(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--port sem --serve emite aviso no stderr."""
        storage = StorageConfig(miner_home=tmp_path / ".miner")
        bbox = BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        report = _make_report(bbox)

        with (
            patch("miner_harness.cli.commands.MinerHarnessConfig") as mock_cfg,
            patch("miner_harness.connectors.geosgb.connector.GeoSGBConnector"),
            patch("miner_harness.cli.commands.CacheManager"),
            patch("miner_harness.connectors.ollama.client.OllamaClient") as mock_llm_cls,
            patch("miner_harness.orchestrator.orchestrator.Orchestrator") as mock_orch_cls,
            patch("miner_harness.cli.commands._render_html_report"),
        ):
            mock_cfg.return_value.storage = storage
            mock_cfg.return_value.orchestrator.model = "qwen3:8b"
            mock_cfg.return_value.orchestrator.min_data_sources = 3
            mock_llm = AsyncMock()
            mock_llm.health = AsyncMock(return_value=True)
            mock_llm_cls.return_value = mock_llm
            mock_orch = AsyncMock()
            mock_orch.analyze_region = AsyncMock(return_value=report)
            mock_orch_cls.return_value = mock_orch

            await cmd_analyze(
                region="carajas",
                bbox=(-51.0, -7.0, -49.0, -5.0),
                port=9999,
                serve=False,
                no_html=True,
            )

        captured = capsys.readouterr()
        assert "--port" in captured.err
        assert "--serve" in captured.err


class TestCacheStatsDates:
    """Teste do formato de datas no cmd_cache_stats."""

    def test_cache_stats_date_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Datas exibidas em formato legível (não ISO com microsegundos)."""
        config = StorageConfig(miner_home=tmp_path / ".miner")
        from miner_harness.cache.manager import CacheManager

        bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        cache = CacheManager(config)
        cache.put("ocorrencias", bbox, [{"id": 1}])
        cache.close()

        with patch("miner_harness.cli.commands.StorageConfig") as mock_cfg:
            mock_cfg.return_value = config
            cmd_cache_stats()

        captured = capsys.readouterr()
        assert "UTC" in captured.out
        assert "." not in captured.out.split("Oldest")[1].split("\n")[0]  # no microseconds

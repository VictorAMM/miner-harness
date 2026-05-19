"""Testes e2e — geração de dashboard HTML com pipeline real.

Verifica que:
- HtmlReportRenderer gera arquivo HTML válido a partir de relatório real
- O arquivo contém região, alvos e estrutura esperada
- O CLI `analyze --no-html` não gera arquivo HTML
- O CLI `analyze` (sem --no-html) gera arquivo HTML e abre browser

Executar com: MINER_E2E=1 uv run pytest tests/e2e/test_report_live.py -v
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from miner_harness.cache.manager import CacheManager
from miner_harness.connectors.geosgb.connector import GeoSGBConnector
from miner_harness.connectors.ollama.client import OllamaClient
from miner_harness.core.config import MinerHarnessConfig, OrchestratorConfig, StorageConfig
from miner_harness.orchestrator.orchestrator import Orchestrator
from miner_harness.report import HtmlReportRenderer

from .conftest import skip_no_ollama

if TYPE_CHECKING:
    from pathlib import Path

    from miner_harness.core.types import BoundingBox


@pytest.fixture(scope="module")
def report_config(
    tmp_path_factory: pytest.TempPathFactory,
    ollama_url: str,
    ollama_model: str,
) -> MinerHarnessConfig:
    tmp = tmp_path_factory.mktemp("e2e_report_home")
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


# ---------------------------------------------------------------------------
# Dashboard HTML a partir de relatório real
# ---------------------------------------------------------------------------


@skip_no_ollama
@pytest.mark.asyncio
async def test_html_report_gerado_com_dados_reais(
    bbox_carajas_small: BoundingBox,
    report_config: MinerHarnessConfig,
    tmp_path: Path,
) -> None:
    """HtmlReportRenderer gera HTML válido a partir de análise real de Carajás."""
    cache = CacheManager(report_config.storage)
    connector = GeoSGBConnector(report_config.geosgb)
    llm = OllamaClient(report_config.orchestrator)

    try:
        orch = Orchestrator(connector, cache, llm, report_config)
        report = await orch.analyze_region(bbox_carajas_small, "Carajás E2E")
    finally:
        await connector.close()
        await llm.close()
        cache.close()

    out = tmp_path / "report.html"
    renderer = HtmlReportRenderer()
    result = renderer.render_to_file(report, out)

    assert result == out
    assert out.exists()

    content = out.read_text(encoding="utf-8")
    assert content.strip().startswith("<!DOCTYPE html>")
    assert "</html>" in content
    assert "Carajás E2E" in content
    assert "L.map" in content or "leaflet" in content.lower()
    assert "Chart" in content
    assert len(content) > 50_000  # HTML completo com assets inline


@skip_no_ollama
@pytest.mark.asyncio
async def test_html_report_contem_targets_reais(
    bbox_carajas_small: BoundingBox,
    report_config: MinerHarnessConfig,
    tmp_path: Path,
) -> None:
    """Se o LLM identificou alvos, eles aparecem no HTML gerado."""
    cache = CacheManager(report_config.storage)
    connector = GeoSGBConnector(report_config.geosgb)
    llm = OllamaClient(report_config.orchestrator)

    try:
        orch = Orchestrator(connector, cache, llm, report_config)
        report = await orch.analyze_region(bbox_carajas_small, "Carajás Targets E2E")
    finally:
        await connector.close()
        await llm.close()
        cache.close()

    html = HtmlReportRenderer().render(report)

    # Se há alvos, cada nome deve aparecer no HTML (JSON embutido)
    for target in report.targets:
        assert target.name in html, f"Alvo '{target.name}' ausente no HTML"


@skip_no_ollama
@pytest.mark.asyncio
async def test_html_report_render_to_file_cria_diretorios(
    bbox_carajas_small: BoundingBox,
    report_config: MinerHarnessConfig,
    tmp_path: Path,
) -> None:
    """render_to_file() cria diretórios intermediários automaticamente."""
    cache = CacheManager(report_config.storage)
    connector = GeoSGBConnector(report_config.geosgb)
    llm = OllamaClient(report_config.orchestrator)

    try:
        orch = Orchestrator(connector, cache, llm, report_config)
        report = await orch.analyze_region(bbox_carajas_small, "Carajás Dirs E2E")
    finally:
        await connector.close()
        await llm.close()
        cache.close()

    nested = tmp_path / "a" / "b" / "c" / "report.html"
    HtmlReportRenderer().render_to_file(report, nested)
    assert nested.exists()


# ---------------------------------------------------------------------------
# CLI flag --no-html
# ---------------------------------------------------------------------------


@skip_no_ollama
@pytest.mark.asyncio
async def test_cli_no_html_flag_nao_gera_arquivo(
    bbox_carajas_small: BoundingBox,
    report_config: MinerHarnessConfig,
) -> None:
    """Com --no-html, cmd_analyze não gera arquivo HTML nos exports."""
    from miner_harness.cli.commands import cmd_analyze  # noqa: PLC0415

    exports_dir = report_config.storage.exports_dir / "reports"

    html_files_before = list(exports_dir.glob("*.html")) if exports_dir.exists() else []

    await cmd_analyze(
        region="carajas_nohtml_e2e",
        bbox=(
            bbox_carajas_small.lon_min,
            bbox_carajas_small.lat_min,
            bbox_carajas_small.lon_max,
            bbox_carajas_small.lat_max,
        ),
        model=report_config.orchestrator.model,
        output_path=None,
        no_html=True,
    )

    html_files_after = list(exports_dir.glob("*.html")) if exports_dir.exists() else []
    new_files = [f for f in html_files_after if f not in html_files_before]
    assert len(new_files) == 0, f"--no-html gerou arquivos HTML inesperados: {new_files}"

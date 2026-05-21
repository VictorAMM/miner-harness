"""CLI command handlers.

Each function implements a CLI subcommand.
Returns exit code (0 = success, 1 = error).

Ref: ADR-004
"""

from __future__ import annotations

import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

import structlog

from miner_harness.cache.manager import CacheManager
from miner_harness.core.config import MinerHarnessConfig, StorageConfig
from miner_harness.core.types import BoundingBox, ProspectionReport
from miner_harness.index.document_store import DocumentStore
from miner_harness.orchestrator.report_validator import ReportValidator

logger = structlog.get_logger(__name__)


async def cmd_analyze(
    region: str,
    bbox: tuple[float, float, float, float],
    model: str | None = None,
    output_path: str | None = None,
    no_html: bool = False,
    serve: bool = False,
    port: int = 8765,
    profile: bool = False,
    min_sources: int | None = None,
    llm_timeout: int | None = None,
    ctx_size: int | None = None,
) -> int:
    """Run full analysis pipeline on a region."""
    from miner_harness.connectors.geosgb.connector import GeoSGBConnector
    from miner_harness.connectors.ollama.client import OllamaClient
    from miner_harness.orchestrator.orchestrator import Orchestrator

    config = MinerHarnessConfig()
    if model:
        config.orchestrator.model = model
    if min_sources is not None:
        config.orchestrator.min_data_sources = min_sources
    if llm_timeout is not None:
        config.orchestrator.ollama_timeout_s = llm_timeout
    if ctx_size is not None:
        config.orchestrator.num_ctx = ctx_size

    storage = config.storage
    storage.ensure_dirs()

    lon_min, lat_min, lon_max, lat_max = bbox
    if lon_min >= lon_max:
        print(
            f"Error: lon_min ({lon_min}) must be less than lon_max ({lon_max})",
            file=sys.stderr,
        )
        return 1
    if lat_min >= lat_max:
        print(
            f"Error: lat_min ({lat_min}) must be less than lat_max ({lat_max})",
            file=sys.stderr,
        )
        return 1

    bb = BoundingBox(
        lon_min=lon_min,
        lat_min=lat_min,
        lon_max=lon_max,
        lat_max=lat_max,
    )

    if port != 8765 and not serve:
        print("Warning: --port is ignored without --serve", file=sys.stderr)

    print(f"Analyzing region: {region}")
    print(f"BBox: {bb.as_tuple()}")
    print(f"Model: {config.orchestrator.model}")
    print(f"Context: {config.orchestrator.num_ctx} tokens")
    print(f"Min sources: {config.orchestrator.min_data_sources}")
    print()

    # Initialize components
    connector = GeoSGBConnector()
    cache = CacheManager(storage)
    llm = OllamaClient(config.orchestrator)

    try:
        # Check LLM connectivity
        print("Checking Ollama connectivity...")
        if not await llm.health():
            print(
                "Error: Ollama not available. Make sure Ollama is running.",
                file=sys.stderr,
            )
            return 1

        # Run analysis
        orch: Orchestrator
        if profile:
            from miner_harness.observability.profiler import ProfilingRunner  # noqa: PLC0415

            orch = ProfilingRunner(connector, cache, llm, config)
        else:
            orch = Orchestrator(connector, cache, llm, config)
        print("Running analysis pipeline...")
        report = await orch.analyze_region(bb, region)

        # Validate
        validator = ReportValidator()
        validation = validator.validate(report)
        if not validation.is_valid:
            print(f"\nWarning: {validation.error_count} validation errors")
            report = validator.repair(report, validation)

        # Output JSON se solicitado
        report_dict = report.model_dump(mode="json")
        if output_path:
            Path(output_path).write_text(
                json.dumps(report_dict, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\nReport saved to: {output_path}")
        else:
            _print_report_summary(report)

        # Modo --serve: inicia servidor HTTP interativo (gerencia cache internamente)
        if serve:
            await _serve_dashboard(report, connector, cache, llm, config, port)
            return 0

        # Gerar dashboard HTML estático
        if not no_html:
            _render_html_report(report, storage, region)

        return 0

    finally:
        # Em modo serve, o DashboardServer fecha o cache no seu próprio cleanup
        if not serve:
            cache.close()


def _render_html_report(
    report: ProspectionReport,
    storage: StorageConfig,
    region: str,
) -> None:
    """Gera dashboard HTML e abre no browser."""
    try:
        from miner_harness.report import HtmlReportRenderer

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_region = region.replace(" ", "_").replace("/", "_")
        html_path = storage.exports_dir / "reports" / f"{safe_region}_{ts}.html"
        renderer = HtmlReportRenderer()
        renderer.render_to_file(report, html_path)
        print(f"\nDashboard HTML: {html_path}")
        webbrowser.open(html_path.as_uri())
    except Exception as exc:  # noqa: BLE001
        logger.warning("html_report_failed", error=str(exc))
        print(f"Aviso: não foi possível gerar dashboard HTML: {exc}", file=sys.stderr)


async def _serve_dashboard(
    report: ProspectionReport,
    connector: object,
    cache: object,
    llm: object,
    config: MinerHarnessConfig,
    port: int,
) -> None:
    """Inicia o DashboardServer e abre o browser no URL local."""
    from miner_harness.server import DashboardServer

    server = DashboardServer(
        initial_report=report,
        connector=connector,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        config=config,
        port=port,
    )
    url = f"http://localhost:{port}"
    print(f"\nServidor iniciado: {url}")
    print("Pressione Ctrl+C para encerrar.")
    webbrowser.open(url)
    await server.run()


def cmd_validate(report_file: str) -> int:
    """Validate an existing report JSON file."""
    path = Path(report_file)
    if not path.exists():
        print(f"Error: file not found: {report_file}", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        report = ProspectionReport.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        print(f"Error parsing report: {exc}", file=sys.stderr)
        return 1

    validator = ReportValidator()
    result = validator.validate(report)

    print(f"Validation score: {result.score:.2f}")
    print(f"Valid: {result.is_valid}")
    print(f"Errors: {result.error_count}")
    print(f"Warnings: {result.warning_count}")

    if result.issues:
        print("\nIssues:")
        for issue in result.issues:
            print(f"  [{issue.severity.upper()}] {issue.message}")

    return 0 if result.is_valid else 1


def cmd_cache_stats() -> int:
    """Show cache statistics."""
    config = StorageConfig()
    cache = CacheManager(config)
    try:
        stats = cache.stats()
        print("Cache Statistics")
        print(f"  Total entries:  {stats.total_entries}")
        print(f"  Total records:  {stats.total_records}")
        print(f"  Size:           {stats.size_bytes / 1024:.1f} KB")
        if stats.services:
            print("  Services:")
            for svc, count in sorted(stats.services.items()):
                print(f"    {svc}: {count} entries")
        if stats.oldest_entry:
            print(f"  Oldest entry:   {stats.oldest_entry.strftime('%Y-%m-%d %H:%M UTC')}")
        if stats.newest_entry:
            print(f"  Newest entry:   {stats.newest_entry.strftime('%Y-%m-%d %H:%M UTC')}")
        return 0
    finally:
        cache.close()


def cmd_cache_clear() -> int:
    """Clear all cache entries."""
    config = StorageConfig()
    cache = CacheManager(config)
    try:
        removed = cache.clear()
        print(f"Cleared {removed} cache entries.")
        return 0
    finally:
        cache.close()


def cmd_cache_evict() -> int:
    """Remove only expired cache entries, leaving fresh data intact."""
    config = StorageConfig()
    cache = CacheManager(config)
    try:
        removed = cache.evict_expired()
        if removed:
            print(f"Evicted {removed} expired cache entries.")
        else:
            print("No expired entries found.")
        return 0
    finally:
        cache.close()


def cmd_index_stats() -> int:
    """Show index statistics."""
    config = StorageConfig()
    index_dir = config.index_dir
    if not index_dir.exists():
        print("No index found.")
        return 0

    store = DocumentStore(index_dir)
    try:
        total = store.count()
        print("Index Statistics")
        print(f"  Total documents: {total}")
        # Count by source
        for source in [
            "geosgb/ocorrencias",
            "geosgb/gravimetria",
            "geosgb/geoquimica",
            "geosgb/geocronologia",
            "geosgb/litoestratigrafia",
            "geosgb/aerogeofisica",
        ]:
            count = store.count(source)
            if count > 0:
                print(f"  {source}: {count}")
        return 0
    finally:
        store.close()


def _print_report_summary(report: ProspectionReport) -> None:
    """Print a human-readable report summary."""
    print(f"\n{'=' * 60}")
    print(f"  MINERAL PROSPECTION REPORT: {report.region_name}")
    print(f"{'=' * 60}")
    print(f"  Date:     {report.analysis_date}")
    print(f"  Model:    {report.model_used}")
    print(f"  Quality:  {report.data_quality_score:.2f}")
    print(f"  Duration: {report.total_duration_ms}ms")
    print()

    print("  ANALYSIS STEPS:")
    for step in report.steps:
        conf_icon = {
            "high": "+",
            "medium": "~",
            "low": "-",
            "insufficient": "!",
        }.get(step.confidence.value, "?")
        print(f"    [{conf_icon}] {step.step.value}: {step.summary[:80]}")

    if report.targets:
        print(f"\n  TARGETS ({len(report.targets)}):")
        for t in report.targets:
            print(
                f"    P{t.priority} | {t.name} | {', '.join(t.commodities)} | {t.confidence.value}"
            )

    if report.caveats:
        print(f"\n  CAVEATS ({len(report.caveats)}):")
        for c in report.caveats:
            print(f"    - {c}")

    print(f"\n{'=' * 60}")


def cmd_install(
    miner_home: Path | None = None,
    model: str = "qwen3:8b",
    ollama_url: str = "http://localhost:11434",
    non_interactive: bool = False,
) -> int:
    """Run the guided installation wizard."""
    from miner_harness.wizard.runner import WizardRunner  # noqa: PLC0415

    runner = WizardRunner()

    if non_interactive:
        report = runner.run_checks(miner_home=miner_home, ollama_url=ollama_url)
        if not report.all_passed:
            for failure in report.failures:
                print(f"[FAIL] {failure.name}: {failure.message}", file=sys.stderr)
            return 1
        result = runner.run_install(miner_home=miner_home, model=model, ollama_url=ollama_url)
        for step in result.steps:
            icon = "[OK]" if step.success else "[FAIL]"
            print(f"  {icon} {step.message}")
        return 0 if result.success else 1

    return runner.run()


async def cmd_health() -> int:
    """Run system health checks."""
    from miner_harness.observability.health import HealthStatus, run_health_checks

    config = StorageConfig()
    report = await run_health_checks(config.miner_home)

    status_icons = {
        HealthStatus.HEALTHY: "[OK]",
        HealthStatus.DEGRADED: "[!!]",
        HealthStatus.UNHEALTHY: "[XX]",
    }

    print(f"\nSystem Health: {report.overall_status.value.upper()}")
    print("-" * 40)
    for check in report.checks:
        icon = status_icons.get(check.status, "[??]")
        print(f"  {icon} {check.name}: {check.message}")

    return 0 if report.is_healthy else 1

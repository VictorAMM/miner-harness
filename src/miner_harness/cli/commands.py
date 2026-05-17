"""CLI command handlers.

Each function implements a CLI subcommand.
Returns exit code (0 = success, 1 = error).

Ref: ADR-004
"""

from __future__ import annotations

import json
import sys
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
) -> int:
    """Run full analysis pipeline on a region."""
    from miner_harness.connectors.geosgb.connector import GeoSGBConnector
    from miner_harness.connectors.ollama.client import OllamaClient
    from miner_harness.orchestrator.orchestrator import Orchestrator

    config = MinerHarnessConfig()
    if model:
        config.orchestrator.model = model

    storage = config.storage
    storage.ensure_dirs()

    bb = BoundingBox(
        lon_min=bbox[0],
        lat_min=bbox[1],
        lon_max=bbox[2],
        lat_max=bbox[3],
    )

    print(f"Analyzing region: {region}")
    print(f"BBox: {bb.as_tuple()}")
    print(f"Model: {config.orchestrator.model}")
    print()

    # Initialize components
    connector = GeoSGBConnector()
    cache = CacheManager(storage)
    llm = OllamaClient()

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
        orch = Orchestrator(connector, cache, llm, config)
        print("Running analysis pipeline...")
        report = await orch.analyze_region(bb, region)

        # Validate
        validator = ReportValidator()
        validation = validator.validate(report)
        if not validation.is_valid:
            print(f"\nWarning: {validation.error_count} validation errors")
            report = validator.repair(report, validation)

        # Output
        report_dict = report.model_dump(mode="json")
        if output_path:
            Path(output_path).write_text(
                json.dumps(report_dict, indent=2, ensure_ascii=False),
            )
            print(f"\nReport saved to: {output_path}")
        else:
            _print_report_summary(report)

        return 0

    finally:
        cache.close()


def cmd_validate(report_file: str) -> int:
    """Validate an existing report JSON file."""
    path = Path(report_file)
    if not path.exists():
        print(f"Error: file not found: {report_file}", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text())
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
            print(f"  Oldest entry:   {stats.oldest_entry}")
        if stats.newest_entry:
            print(f"  Newest entry:   {stats.newest_entry}")
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

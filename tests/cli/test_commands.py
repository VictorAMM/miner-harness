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

from miner_harness.cli.app import main
from miner_harness.cli.commands import (
    _print_report_summary,
    cmd_cache_clear,
    cmd_cache_stats,
    cmd_index_stats,
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

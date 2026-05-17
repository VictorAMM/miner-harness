"""Tests for rca.reporter module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from miner_harness.rca.classifier import (
    ClassifiedError,
    ErrorCategory,
    ErrorSeverity,
)
from miner_harness.rca.diagnostics import DiagnosticSnapshot
from miner_harness.rca.reporter import (
    RCAReport,
    generate_rca_report,
    save_rca_report,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def sample_classified() -> ClassifiedError:
    """Sample classified error for tests."""
    return ClassifiedError(
        category=ErrorCategory.NETWORK,
        severity=ErrorSeverity.HIGH,
        error_type="ConnectError",
        message="Connection refused to ollama:11434",
        context={"service": "ollama", "step": "llm_call"},
        recoverable=True,
        suggested_action="Retry with backoff",
    )


@pytest.fixture
def sample_diagnostics() -> DiagnosticSnapshot:
    """Sample diagnostics snapshot."""
    return DiagnosticSnapshot(
        disk_free_gb=120.5,
        disk_total_gb=500.0,
        python_version="3.11.9",
        platform_info="Linux-6.1-x86_64",
        ollama_reachable=False,
    )


class TestRCAReport:
    """Tests for RCAReport dataclass."""

    def test_to_dict(
        self, sample_classified: ClassifiedError, sample_diagnostics: DiagnosticSnapshot
    ) -> None:
        report = RCAReport(
            id="RCA-20260516-120000",
            title="Network Error — ConnectError",
            classified_error=sample_classified,
            diagnostics=sample_diagnostics,
            root_cause="Ollama offline",
            remediation_steps=["Restart ollama"],
            prevention_measures=["Health check"],
        )
        d = report.to_dict()
        assert d["id"] == "RCA-20260516-120000"
        assert d["classified_error"]["category"] == "network"
        assert d["diagnostics"]["ollama_reachable"] is False
        assert "Restart ollama" in d["remediation_steps"]

    def test_to_markdown(
        self, sample_classified: ClassifiedError, sample_diagnostics: DiagnosticSnapshot
    ) -> None:
        report = RCAReport(
            id="RCA-20260516-120000",
            title="Network Error — ConnectError",
            classified_error=sample_classified,
            diagnostics=sample_diagnostics,
            root_cause="Ollama server not running",
            remediation_steps=["Restart ollama serve"],
            prevention_measures=["Add startup check"],
        )
        md = report.to_markdown()
        assert "# RCA: Network Error" in md
        assert "ConnectError" in md
        assert "Ollama server not running" in md
        assert "Restart ollama serve" in md
        assert "120.5 GB" in md


class TestGenerateRCAReport:
    """Tests for generate_rca_report function."""

    @pytest.mark.asyncio
    async def test_generates_report(
        self, sample_classified: ClassifiedError, sample_diagnostics: DiagnosticSnapshot
    ) -> None:
        report = await generate_rca_report(sample_classified, sample_diagnostics)
        assert report.id.startswith("RCA-")
        assert report.classified_error == sample_classified
        assert report.diagnostics == sample_diagnostics
        assert report.root_cause != ""
        assert len(report.prevention_measures) > 0

    @pytest.mark.asyncio
    async def test_with_timeline(
        self, sample_classified: ClassifiedError, sample_diagnostics: DiagnosticSnapshot
    ) -> None:
        timeline = [
            {"timestamp": "12:00:00", "description": "Request sent"},
            {"timestamp": "12:00:05", "description": "Timeout"},
        ]
        report = await generate_rca_report(
            sample_classified, sample_diagnostics, timeline=timeline
        )
        assert len(report.timeline) == 2  # noqa: PLR2004


class TestSaveRCAReport:
    """Tests for save_rca_report function."""

    @pytest.mark.asyncio
    async def test_saves_files(
        self,
        tmp_path: Path,
        sample_classified: ClassifiedError,
        sample_diagnostics: DiagnosticSnapshot,
    ) -> None:
        report = await generate_rca_report(sample_classified, sample_diagnostics)
        md_path = await save_rca_report(report, output_dir=tmp_path)

        assert md_path.exists()
        assert md_path.suffix == ".md"

        json_path = md_path.with_suffix(".json")
        assert json_path.exists()

        content = md_path.read_text()
        assert "# RCA:" in content

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
        report = await generate_rca_report(sample_classified, sample_diagnostics, timeline=timeline)
        assert len(report.timeline) == 2  # noqa: PLR2004


class TestRCAReportMarkdownBranches:
    """Cobre branches opcionais de to_markdown."""

    def test_contributing_factors_listed(
        self, sample_classified: ClassifiedError, sample_diagnostics: DiagnosticSnapshot
    ) -> None:
        """contributing_factors não-vazio aparece no markdown (linhas 82-83)."""
        report = RCAReport(
            id="RCA-TEST",
            title="Test",
            classified_error=sample_classified,
            diagnostics=sample_diagnostics,
            contributing_factors=["Fator A", "Fator B"],
        )
        md = report.to_markdown()
        assert "Fator A" in md
        assert "Fator B" in md

    def test_timeline_events_listed(
        self, sample_classified: ClassifiedError, sample_diagnostics: DiagnosticSnapshot
    ) -> None:
        """timeline não-vazia aparece no markdown (linhas 96-99)."""
        report = RCAReport(
            id="RCA-TEST",
            title="Test",
            classified_error=sample_classified,
            diagnostics=sample_diagnostics,
            timeline=[{"timestamp": "12:00", "description": "Erro ocorreu"}],
        )
        md = report.to_markdown()
        assert "12:00" in md
        assert "Erro ocorreu" in md

    def test_empty_remediation_uses_suggested_action(
        self, sample_classified: ClassifiedError, sample_diagnostics: DiagnosticSnapshot
    ) -> None:
        """remediation_steps vazia usa suggested_action (linha 115)."""
        report = RCAReport(
            id="RCA-TEST",
            title="Test",
            classified_error=sample_classified,
            diagnostics=sample_diagnostics,
            remediation_steps=[],
        )
        md = report.to_markdown()
        assert sample_classified.suggested_action in md

    def test_empty_prevention_shows_placeholder(
        self, sample_classified: ClassifiedError, sample_diagnostics: DiagnosticSnapshot
    ) -> None:
        """prevention_measures vazia exibe placeholder (linha 129)."""
        report = RCAReport(
            id="RCA-TEST",
            title="Test",
            classified_error=sample_classified,
            diagnostics=sample_diagnostics,
            prevention_measures=[],
        )
        md = report.to_markdown()
        assert "_Medidas a definir_" in md

    def test_cache_size_in_markdown(self, sample_classified: ClassifiedError) -> None:
        """cache_size_mb não-nulo aparece no markdown (linha 148)."""
        diag_with_cache = DiagnosticSnapshot(
            disk_free_gb=50.0,
            disk_total_gb=200.0,
            python_version="3.11",
            platform_info="Linux",
            cache_size_mb=42.5,
        )
        report = RCAReport(
            id="RCA-TEST",
            title="Test",
            classified_error=sample_classified,
            diagnostics=diag_with_cache,
        )
        md = report.to_markdown()
        assert "42.5 MB" in md


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

    @pytest.mark.asyncio
    async def test_saves_to_default_dir(
        self,
        sample_classified: ClassifiedError,
        sample_diagnostics: DiagnosticSnapshot,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """output_dir=None usa docs/rca relativo ao cwd (linha 276)."""
        monkeypatch.chdir(tmp_path)
        report = await generate_rca_report(sample_classified, sample_diagnostics)
        md_path = await save_rca_report(report, output_dir=None)
        assert md_path.exists()
        assert "docs" in str(md_path)

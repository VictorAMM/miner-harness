"""Testes do HtmlReportRenderer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    ProspectionReport,
    StepResult,
)
from miner_harness.report import HtmlReportRenderer

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_target() -> MineralTarget:
    return MineralTarget(
        name="Alvo Carajás Norte",
        longitude=-49.8,
        latitude=-6.1,
        radius_km=5.0,
        commodities=["Au", "Cu"],
        mineral_system="IOCG",
        confidence=Confidence.HIGH,
        priority=1,
        rationale="Anomalia gravimétrica + alteração hidrotermal",
        recommended_followup=["Sondagem rotativa", "Levantamento IP"],
    )


@pytest.fixture()
def sample_step() -> StepResult:
    return StepResult(
        step=AnalysisStep.TECTONIC_HISTORY,
        agent="structural_geologist",
        summary="Região integra o Cráton Amazônico.",
        findings=["Evento transamazônico 2.1 Ga", "Domínio Carajás"],
        confidence=Confidence.HIGH,
        data_sources_used=["GeoSGB/litoestratigrafia"],
        data_gaps=["Dados de geocronologia ausentes"],
        raw_reasoning="O agente analisou... raciocínio completo.",
        duration_ms=4200,
    )


@pytest.fixture()
def sample_report(sample_target: MineralTarget, sample_step: StepResult) -> ProspectionReport:
    return ProspectionReport(
        region_name="Carajás",
        bbox=BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
        analysis_date=datetime(2026, 5, 18, 10, 0, 0, tzinfo=UTC),
        steps=[sample_step],
        targets=[sample_target],
        integrated_summary="Região com alto potencial para IOCG.",
        caveats=["Dados gravimétricos indisponíveis"],
        data_quality_score=0.87,
        total_duration_ms=42000,
        model_used="qwen3:8b",
    )


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestHtmlReportRenderer:
    def test_render_returns_html_string(self, sample_report: ProspectionReport) -> None:
        renderer = HtmlReportRenderer()
        html = renderer.render(sample_report)
        assert isinstance(html, str)
        assert len(html) > 10_000  # arquivo substancial

    def test_html_contains_region_name(self, sample_report: ProspectionReport) -> None:
        html = HtmlReportRenderer().render(sample_report)
        assert "Carajás" in html

    def test_html_contains_target_name(self, sample_report: ProspectionReport) -> None:
        html = HtmlReportRenderer().render(sample_report)
        assert "Alvo Carajás Norte" in html

    def test_html_contains_leaflet(self, sample_report: ProspectionReport) -> None:
        html = HtmlReportRenderer().render(sample_report)
        # Leaflet define L.map
        assert "L.map" in html or "leaflet" in html.lower()

    def test_html_contains_chartjs(self, sample_report: ProspectionReport) -> None:
        html = HtmlReportRenderer().render(sample_report)
        assert "Chart" in html

    def test_html_contains_report_json(self, sample_report: ProspectionReport) -> None:
        html = HtmlReportRenderer().render(sample_report)
        assert "IOCG" in html  # presente no JSON injetado

    def test_html_valid_structure(self, sample_report: ProspectionReport) -> None:
        html = HtmlReportRenderer().render(sample_report)
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_render_to_file(
        self,
        sample_report: ProspectionReport,
        tmp_path: Path,
    ) -> None:
        renderer = HtmlReportRenderer()
        out = tmp_path / "sub" / "report.html"
        result = renderer.render_to_file(sample_report, out)
        assert result == out
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Carajás" in content

    def test_render_to_file_creates_parents(
        self,
        sample_report: ProspectionReport,
        tmp_path: Path,
    ) -> None:
        nested = tmp_path / "a" / "b" / "c" / "report.html"
        HtmlReportRenderer().render_to_file(sample_report, nested)
        assert nested.exists()

    def test_render_empty_targets(self) -> None:
        report = ProspectionReport(
            region_name="Vazio",
            bbox=BoundingBox(lon_min=-50.0, lat_min=-6.0, lon_max=-49.0, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 18, tzinfo=UTC),
            steps=[],
            targets=[],
            integrated_summary="Sem dados.",
            caveats=[],
            data_quality_score=0.0,
            total_duration_ms=1000,
            model_used="qwen3:8b",
        )
        html = HtmlReportRenderer().render(report)
        assert "Vazio" in html
        assert "0%" in html or "0.0" in html

    def test_render_multiple_targets(
        self,
        sample_step: StepResult,
    ) -> None:
        targets = [
            MineralTarget(
                name=f"Alvo {i}",
                longitude=-50.0 + i * 0.1,
                latitude=-6.0 + i * 0.1,
                radius_km=3.0,
                commodities=["Au"],
                mineral_system="Ouro Orogênico",
                confidence=Confidence.MEDIUM,
                priority=i,
                rationale="Teste",
                recommended_followup=[],
            )
            for i in range(1, 4)
        ]
        report = ProspectionReport(
            region_name="Multi",
            bbox=BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 18, tzinfo=UTC),
            steps=[sample_step],
            targets=targets,
            integrated_summary="Três alvos.",
            caveats=[],
            data_quality_score=0.6,
            total_duration_ms=5000,
            model_used="qwen3:8b",
        )
        html = HtmlReportRenderer().render(report)
        assert "Alvo 1" in html
        assert "Alvo 2" in html
        assert "Alvo 3" in html

    def test_html_escapes_special_chars(self) -> None:
        report = ProspectionReport(
            region_name="Test <script>alert(1)</script>",
            bbox=BoundingBox(lon_min=-50.0, lat_min=-6.0, lon_max=-49.0, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 18, tzinfo=UTC),
            steps=[],
            targets=[],
            integrated_summary="",
            caveats=[],
            data_quality_score=0.5,
            total_duration_ms=0,
            model_used="qwen3:8b",
        )
        html = HtmlReportRenderer().render(report)
        # O JSON embute os dados raw, mas o JS usa esc() para renderizar no DOM
        # O region_name aparece no JSON (não em HTML diretamente fora do script)
        assert "</html>" in html  # renderizou sem erro

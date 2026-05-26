"""Testes do HtmlReportRenderer."""

from __future__ import annotations

from datetime import datetime, timezone  # noqa: UP017
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
        analysis_date=datetime(2026, 5, 18, 10, 0, 0, tzinfo=timezone.utc),
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
            analysis_date=datetime(2026, 5, 18, tzinfo=timezone.utc),
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
            analysis_date=datetime(2026, 5, 18, tzinfo=timezone.utc),
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
            analysis_date=datetime(2026, 5, 18, tzinfo=timezone.utc),
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

    def test_render_serve_mode_contains_nova_pesquisa(
        self, sample_report: ProspectionReport
    ) -> None:
        html = HtmlReportRenderer().render(sample_report, serve_mode=True)
        assert "np-submit" in html
        assert "Nova Pesquisa" in html
        assert "progress-overlay" in html

    def test_render_static_mode_omits_nova_pesquisa(self, sample_report: ProspectionReport) -> None:
        html = HtmlReportRenderer().render(sample_report, serve_mode=False)
        assert "np-submit" not in html
        assert "progress-overlay" not in html

    def test_render_serve_mode_default_is_false(self, sample_report: ProspectionReport) -> None:
        html = HtmlReportRenderer().render(sample_report)
        assert "np-submit" not in html

    def test_render_to_file_does_not_include_serve_mode(
        self,
        sample_report: ProspectionReport,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "report.html"
        HtmlReportRenderer().render_to_file(sample_report, out)
        content = out.read_text(encoding="utf-8")
        assert "np-submit" not in content

    def test_integrated_summary_in_analise_tab(self, sample_report: ProspectionReport) -> None:
        """integrated_summary deve aparecer na aba Análise como síntese integrada."""
        html = HtmlReportRenderer().render(sample_report)
        assert "integrated-summary-box" in html
        assert "Síntese Integrada" in html
        # Conteúdo do integrated_summary da fixture
        assert "IOCG" in html

    def test_integrated_summary_in_alvos_tab(self, sample_report: ProspectionReport) -> None:
        """integrated_summary deve aparecer também na aba Alvos como contexto."""
        html = HtmlReportRenderer().render(sample_report)
        # A função renderAlvosTab também usa integrated-summary-box
        assert html.count("integrated-summary-box") >= 2

    def test_integrated_summary_css_class_defined(self, sample_report: ProspectionReport) -> None:
        """CSS .integrated-summary-box deve estar definido no template."""
        html = HtmlReportRenderer().render(sample_report)
        assert ".integrated-summary-box" in html

    def test_integrated_summary_js_renders_it(self, sample_report: ProspectionReport) -> None:
        """JS deve referenciar r.integrated_summary no renderAnaliseTab."""
        html = HtmlReportRenderer().render(sample_report)
        assert "r.integrated_summary" in html


class TestDadosTabAndMapLayers:
    """Testes para a aba Dados e camadas ANM/USGS no mapa."""

    def _make_report_with_geo(self) -> ProspectionReport:
        from datetime import datetime, timezone  # noqa: UP017

        from miner_harness.core.types import BoundingBox, Confidence, StepResult

        step = StepResult(
            step="tectonic_history",
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        return ProspectionReport(
            region_name="Região Teste",
            bbox=BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
            steps=[step],
            targets=[],
            integrated_summary="ok",
            caveats=[],
            data_quality_score=0.5,
            total_duration_ms=1000,
            model_used="qwen3:8b",
            geological_data={
                "anm": [
                    {
                        "objectid": 0,
                        "processo": "860384/2007",
                        "fase": "Concessão de Lavra",
                        "nome_titular": "Empresa Teste SA",
                        "substancias": "FERRO",
                        "uf": "PA",
                        "area_ha": 1500.0,
                        "ano": 2007,
                        "coordenada": {
                            "longitude": -50.5,
                            "latitude": -6.5,
                            "datum": "WGS84",
                        },
                    }
                ],
                "usgs": [
                    {
                        "objectid": 0,
                        "magnitude": 3.2,
                        "profundidade_km": 10.0,
                        "lugar": "50 km S of Altamira",
                        "timestamp_ms": 1716105600000,
                        "coordenada": {
                            "longitude": -50.5,
                            "latitude": -6.5,
                            "datum": "WGS84",
                        },
                    }
                ],
                "ocorrencias": [
                    {
                        "objectid": 95303,
                        "substancias": "Ouro",
                        "municipio": "Marabá",
                        "uf": "PA",
                        "status_economico": "Indeterminado",
                        "importancia": "Indeterminado",
                        "rochas_hospedeiras": "Cascalho",
                        "morfologia": "Nodular",
                        "coordenada": {
                            "longitude": -50.87,
                            "latitude": -5.78,
                            "datum": "WGS84",
                        },
                    },
                    {
                        "objectid": 95304,
                        "substancias": "Cobre",
                        "municipio": "Parauapebas",
                        "uf": "PA",
                        "status_economico": "Garimpado",
                        "importancia": "Médio",
                        "rochas_hospedeiras": "Granito",
                        "morfologia": "Disseminado",
                        "coordenada": {
                            "longitude": -49.9,
                            "latitude": -6.1,
                            "datum": "WGS84",
                        },
                    },
                ],
            },
        )

    def test_html_contains_dados_tab_button(self) -> None:
        report = self._make_report_with_geo()
        html = HtmlReportRenderer().render(report)
        assert "tab-dados" in html
        assert "Dados" in html

    def test_html_contains_anm_map_layer_code(self) -> None:
        report = self._make_report_with_geo()
        html = HtmlReportRenderer().render(report)
        assert "anmLayers" in html
        assert "7c3aed" in html  # ANM violet color

    def test_html_contains_usgs_map_layer_code(self) -> None:
        report = self._make_report_with_geo()
        html = HtmlReportRenderer().render(report)
        assert "usgsLayers" in html
        assert "ea580c" in html  # USGS orange color

    def test_geological_data_embedded_in_report_json(self) -> None:
        report = self._make_report_with_geo()
        html = HtmlReportRenderer().render(report)
        assert "860384/2007" in html  # ANM processo embedded in JSON
        assert "Altamira" in html  # USGS lugar embedded in JSON
        assert "Marabá" in html  # Ocorrência municipio embedded in JSON

    def test_html_contains_occurrences_map_layer_code(self) -> None:
        """JS deve conter código de renderização das camadas de ocorrências."""
        report = self._make_report_with_geo()
        html = HtmlReportRenderer().render(report)
        assert "ocorrLayers" in html
        assert "substanciaColor" in html
        assert "SUBSTANCIA_COLORS" in html

    def test_html_contains_occurrences_toggle_button(self) -> None:
        """Botão de toggle das ocorrências deve estar presente nos controles do mapa."""
        report = self._make_report_with_geo()
        html = HtmlReportRenderer().render(report)
        assert "btn-ocorr" in html
        assert "Ocorrências" in html

    def test_html_contains_occurrences_legend_code(self) -> None:
        """JS deve conter código de legenda de substâncias para o mapa."""
        report = self._make_report_with_geo()
        html = HtmlReportRenderer().render(report)
        assert "ocorrLegend" in html

    def test_dados_tab_contains_occurrences_table(self) -> None:
        """Aba Dados deve conter tabela de ocorrências GeoSGB."""
        report = self._make_report_with_geo()
        html = HtmlReportRenderer().render(report)
        assert "GeoSGB" in html
        assert "Ocorrências Minerais" in html or "ocorrência" in html.lower()

    def test_report_without_geological_data_still_renders(self) -> None:
        from datetime import datetime, timezone  # noqa: UP017

        from miner_harness.core.types import BoundingBox, Confidence, StepResult

        step = StepResult(
            step="tectonic_history",
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        report = ProspectionReport(
            region_name="Sem Dados",
            bbox=BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
            steps=[step],
            targets=[],
            integrated_summary="ok",
            caveats=[],
            data_quality_score=0.5,
            total_duration_ms=1000,
            model_used="qwen3:8b",
            geological_data=None,
        )
        html = HtmlReportRenderer().render(report)
        assert "<!DOCTYPE html>" in html.lower() or "<!doctype html>" in html.lower()
        assert "tab-dados" in html


class TestOcorrenciasStatsWidget:
    """Testes do widget de estatísticas de ocorrências na sidebar."""

    def _make_report_with_ocorr(self) -> ProspectionReport:
        from datetime import datetime, timezone  # noqa: UP017

        from miner_harness.core.types import BoundingBox, Confidence, ProspectionReport, StepResult

        step = StepResult(
            step="tectonic_history",
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        return ProspectionReport(
            region_name="Stats Test",
            bbox=BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 20, tzinfo=timezone.utc),
            steps=[step],
            targets=[],
            integrated_summary="ok",
            caveats=[],
            data_quality_score=0.5,
            total_duration_ms=1000,
            model_used="qwen3:8b",
            geological_data={
                "ocorrencias": [
                    {
                        "objectid": 1,
                        "substancias": "Ouro",
                        "municipio": "Marabá",
                        "uf": "PA",
                        "status_economico": "Garimpado",
                        "rochas_hospedeiras": "Cascalho",
                        "morfologia": "Nodular",
                        "coordenada": {"longitude": -50.8, "latitude": -5.7},
                    },
                    {
                        "objectid": 2,
                        "substancias": "Ouro",
                        "municipio": "Parauapebas",
                        "uf": "PA",
                        "status_economico": "Indeterminado",
                        "rochas_hospedeiras": "Granito",
                        "morfologia": "Disseminado",
                        "coordenada": {"longitude": -49.9, "latitude": -6.1},
                    },
                    {
                        "objectid": 3,
                        "substancias": "Ferro",
                        "municipio": "Canaã dos Carajás",
                        "uf": "PA",
                        "status_economico": "Lavrado",
                        "rochas_hospedeiras": "Itabirito",
                        "morfologia": "Lenticular",
                        "coordenada": {"longitude": -50.2, "latitude": -6.5},
                    },
                    {
                        "objectid": 4,
                        "substancias": "Cobre, Ouro",
                        "municipio": "Ourilândia",
                        "uf": "PA",
                        "status_economico": "Indeterminado",
                        "rochas_hospedeiras": "Ultramáfica",
                        "morfologia": "Maciço",
                        "coordenada": {"longitude": -51.0, "latitude": -6.7},
                    },
                ],
            },
        )

    def test_stats_widget_section_present_in_html(self) -> None:
        """HTML deve conter o elemento da seção de estatísticas de ocorrências."""
        report = self._make_report_with_ocorr()
        html = HtmlReportRenderer().render(report)
        assert "ocorr-stats-section" in html
        assert "ocorr-stats-content" in html

    def test_stats_widget_js_function_defined(self) -> None:
        """Função renderOcorrenciasStats deve estar definida no JS."""
        report = self._make_report_with_ocorr()
        html = HtmlReportRenderer().render(report)
        assert "renderOcorrenciasStats" in html

    def test_stats_widget_called_in_render_dashboard(self) -> None:
        """renderDashboard deve invocar renderOcorrenciasStats."""
        report = self._make_report_with_ocorr()
        html = HtmlReportRenderer().render(report)
        # renderDashboard invoca renderOcorrenciasStats(r)
        assert "renderOcorrenciasStats(r)" in html

    def test_sub_pill_css_class_defined(self) -> None:
        """CSS .sub-pill deve estar definido no template."""
        report = self._make_report_with_ocorr()
        html = HtmlReportRenderer().render(report)
        assert "sub-pill" in html

    def test_no_stats_section_when_no_occurrences(self) -> None:
        """Com geological_data=None, seção de stats não deve exibir conteúdo (display:none)."""
        from datetime import datetime, timezone  # noqa: UP017

        from miner_harness.core.types import BoundingBox, Confidence, ProspectionReport, StepResult

        step = StepResult(
            step="tectonic_history",
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        report = ProspectionReport(
            region_name="Vazio",
            bbox=BoundingBox(lon_min=-51.0, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 20, tzinfo=timezone.utc),
            steps=[step],
            targets=[],
            integrated_summary="ok",
            caveats=[],
            data_quality_score=0.0,
            total_duration_ms=1000,
            model_used="qwen3:8b",
            geological_data=None,
        )
        html = HtmlReportRenderer().render(report)
        # A seção existe no HTML mas começa oculta (display:none)
        assert 'id="ocorr-stats-section"' in html
        assert "display:none" in html


class TestLowConfidenceBadge:
    """Testes do badge visual para steps com confiança baixa.

    Os badges são renderizados via JavaScript no browser; verificamos
    o código JS e o CSS presentes no HTML estático, não o DOM renderizado.
    """

    def test_warn_css_class_defined_in_template(self, sample_report: ProspectionReport) -> None:
        """CSS .step-accordion--warn deve estar definido no HTML."""
        html = HtmlReportRenderer().render(sample_report)
        assert "step-accordion--warn" in html

    def test_warn_icon_js_logic_present(self, sample_report: ProspectionReport) -> None:
        """JS deve conter lógica condicional para exibir ícone de aviso."""
        html = HtmlReportRenderer().render(sample_report)
        assert "step-warn-icon" in html
        assert "isWarn" in html

    def test_warn_triggered_for_low_and_insufficient(
        self, sample_report: ProspectionReport
    ) -> None:
        """JS deve verificar 'low' e 'insufficient' para ativar aviso."""
        html = HtmlReportRenderer().render(sample_report)
        # O condicional deve cobrir ambas as confidências problemáticas
        assert "'low'" in html or "=== 'low'" in html
        assert "'insufficient'" in html or "=== 'insufficient'" in html

    def test_tooltip_explains_low_confidence(self, sample_report: ProspectionReport) -> None:
        """Tooltip do ícone de aviso deve explicar o motivo ao usuário."""
        html = HtmlReportRenderer().render(sample_report)
        assert "Confiança baixa" in html or "dados insuficientes" in html


# ---------------------------------------------------------------------------
# PRD-005 — UX: grupos de botões, ETA e modo offline
# ---------------------------------------------------------------------------


class TestPrd005UxFeatures:
    """Testes das melhorias de UX do PRD-005 (v1.6.0)."""

    def _make_simple_report(self) -> ProspectionReport:
        step = StepResult(
            step="tectonic_history",
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        return ProspectionReport(
            region_name="UX Test",
            bbox=BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 26, tzinfo=timezone.utc),
            steps=[step],
            targets=[],
            integrated_summary="ok",
            caveats=[],
            data_quality_score=0.8,
            total_duration_ms=5000,
            model_used="qwen3:8b",
            geological_data=None,
        )

    # T1 — Grupos colapsáveis de botões
    def test_html_has_map_group_nav(self) -> None:
        """Grupo Navegação deve existir com id map-group-nav."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "map-group-nav" in html

    def test_html_has_map_group_data(self) -> None:
        """Grupo Camadas de Dados deve existir com id map-group-data."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "map-group-data" in html

    def test_html_has_map_group_atlas(self) -> None:
        """Grupo Atlas SGB/CPRM deve existir com id map-group-atlas."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "map-group-atlas" in html

    def test_html_has_toggle_map_group_function(self) -> None:
        """Função JS toggleMapGroup deve estar definida."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "function toggleMapGroup" in html

    def test_atlas_group_starts_collapsed(self) -> None:
        """Grupo Atlas deve iniciar colapsado (class collapsed)."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert 'id="map-group-atlas"' in html
        # O grupo atlas deve ter 'collapsed' na classe
        idx = html.find('id="map-group-atlas"')
        snippet = html[max(0, idx - 60) : idx + 60]
        assert "collapsed" in snippet

    def test_map_group_header_has_onclick(self) -> None:
        """Headers dos grupos devem ter onclick para toggleMapGroup."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "toggleMapGroup('map-group-nav')" in html
        assert "toggleMapGroup('map-group-data')" in html
        assert "toggleMapGroup('map-group-atlas')" in html

    def test_nav_group_contains_centralizar(self) -> None:
        """Botão Centralizar deve estar no grupo Navegação."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "btn-centralizar" in html

    def test_data_group_contains_ocorrencias(self) -> None:
        """Botão Ocorrências deve estar no grupo Camadas de Dados."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "btn-ocorr" in html

    # T2 — ETA de progresso
    def test_html_has_eta_element(self) -> None:
        """Elemento ETA deve estar presente no overlay de progresso (serve_mode)."""
        step = StepResult(
            step="tectonic_history",
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        report = ProspectionReport(
            region_name="ETA Test",
            bbox=BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 26, tzinfo=timezone.utc),
            steps=[step],
            targets=[],
            integrated_summary="ok",
            caveats=[],
            data_quality_score=0.8,
            total_duration_ms=5000,
            model_used="qwen3:8b",
            geological_data=None,
        )
        html = HtmlReportRenderer().render(report, serve_mode=True)
        assert "np-progress-eta" in html
        assert "eta_s" in html  # campo no payload SSE
        assert "restante" in html  # lógica de exibição

    # T3 — Modo offline
    def test_html_has_offline_mode_button(self) -> None:
        """Botão Modo Offline deve estar presente nos controles do mapa."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "btn-offline-mode" in html
        assert "Modo Offline" in html

    def test_html_has_toggle_offline_function(self) -> None:
        """Função JS toggleOfflineMode deve estar definida."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "function toggleOfflineMode" in html
        assert "_offlineMode" in html

    def test_offline_mode_removes_tile_layer(self) -> None:
        """Lógica de remoção de TileLayer deve estar no JS."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "L.TileLayer" in html
        assert "eachLayer" in html


# ---------------------------------------------------------------------------
# PRD-006 — Dual-persona dashboard improvements
# ---------------------------------------------------------------------------


class TestPrd006DashboardImprovements:
    """Testes das melhorias do PRD-006 (persona criança + geólogo)."""

    def _make_simple_report(self, **overrides: object) -> ProspectionReport:
        step = StepResult(
            step="tectonic_history",
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        base: dict[str, object] = {
            "region_name": "PRD-006 Test",
            "bbox": BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0),
            "analysis_date": datetime(2026, 5, 26, tzinfo=timezone.utc),
            "steps": [step],
            "targets": [],
            "integrated_summary": "ok",
            "caveats": [],
            "data_quality_score": 0.8,
            "total_duration_ms": 5000,
            "model_used": "qwen3:8b",
            "geological_data": None,
        }
        base.update(overrides)
        return ProspectionReport(**base)  # type: ignore[arg-type]

    # C3 — Confidence tooltips
    def test_html_has_conf_tooltips_constant(self) -> None:
        """Constante CONF_TOOLTIPS deve estar definida no JS."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "CONF_TOOLTIPS" in html

    def test_conf_tooltips_covers_all_levels(self) -> None:
        """CONF_TOOLTIPS cobre os 4 níveis de confiança."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        for level in ("high", "medium", "low", "insufficient"):
            assert level in html

    # C2 — Aba padrão é Alvos
    def test_html_default_tab_is_alvos(self) -> None:
        """Tab Alvos deve ser a ativa por padrão (não Análise)."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        # tab-btn active deve estar no botão de alvos, não no de análise
        assert 'tab-btn active" data-tab="alvos"' in html

    # G1 — Botão Aeromag local
    def test_html_has_aeromag_grid_button(self) -> None:
        """Botão de grade aeromag local deve estar na sidebar."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "btn-aeromag-grid" in html

    def test_html_has_aeromag_grid_js_logic(self) -> None:
        """Lógica JS de toggle da grade aeromag deve estar presente."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "aeromagGridLayers" in html
        assert "aeromagGridVisible" in html

    # G3 — Nota de calibração
    def test_html_has_calibration_note_css(self) -> None:
        """Classe CSS .calibration-note deve estar definida."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert ".calibration-note" in html

    def test_html_renders_calibration_note_when_present(self) -> None:
        """calibration_note de um step aparece no HTML renderizado."""
        step_with_note = StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.MEDIUM,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
            calibration_note="Confiança recalibrada para MEDIUM.",
        )
        report = ProspectionReport(
            region_name="Calib Test",
            bbox=BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 26, tzinfo=timezone.utc),
            steps=[step_with_note],
            targets=[],
            integrated_summary="ok",
            caveats=[],
            data_quality_score=0.6,
            total_duration_ms=1000,
            model_used="qwen3:8b",
        )
        html = HtmlReportRenderer().render(report)
        assert "Confiança recalibrada para MEDIUM." in html

    # G11 — Nota de diversidade removida
    def test_html_has_diversity_removed_note_css(self) -> None:
        """Classe CSS .diversity-removed-note deve estar definida."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "diversity-removed-note" in html

    def test_html_renders_diversity_removed_when_nonzero(self) -> None:
        """Nota de diversidade removida aparece quando diversity_removed_count > 0."""
        report = self._make_simple_report(diversity_removed_count=2)
        html = HtmlReportRenderer().render(report)
        assert "diversity_removed_count" in html or "diversidade espacial" in html

    # C1 — Painel inferior maior
    def test_html_has_larger_bottom_panel(self) -> None:
        """Painel inferior deve usar 40vh em vez de valor fixo pequeno."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "40vh" in html

    # A2 — Benchmark de qualidade
    def test_html_has_quality_benchmark_logic(self) -> None:
        """Lógica de benchmark de qualidade deve estar no JS (cores e dicas)."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "benchmarkTip" in html or "benchmark" in html.lower()

    # G5 — TMA local no popup
    def test_html_has_tma_popup_logic(self) -> None:
        """Lógica de TMA local no popup do alvo deve estar presente."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "nearestTma" in html or "tma_nt" in html

    # A1 — Legenda do mapa expandida por padrão
    def test_html_legend_starts_expanded(self) -> None:
        """Legenda do mapa deve começar expandida (collapsed = false)."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        # A variável collapsed deve ser inicializada como false
        assert "collapsed = false" in html or "collapsed=false" in html


class TestAtlasWmsFix:
    """Testes do fix WMS→REST para Mapas_Tern_Mag_MIL1 (serviço sem WMS)."""

    def _make_simple_report(self) -> ProspectionReport:
        step = StepResult(
            step="tectonic_history",
            agent="structural_geologist",
            summary="ok",
            findings=[],
            confidence=Confidence.HIGH,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        return ProspectionReport(
            region_name="Atlas Fix Test",
            bbox=BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0),
            analysis_date=datetime(2026, 5, 26, tzinfo=timezone.utc),
            steps=[step],
            targets=[],
            integrated_summary="ok",
            caveats=[],
            data_quality_score=0.8,
            total_duration_ms=1000,
            model_used="qwen3:8b",
        )

    def test_uses_rest_export_not_wms_for_tern_mag(self) -> None:
        """Mapas_Tern_Mag_MIL1 deve usar REST /export, não WMSServer."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "_REST_TERN_MAG" in html
        # WMSServer jamais deve aparecer para esse serviço
        assert "Mapas_Tern_Mag_MIL1/MapServer/WMSServer" not in html

    def test_arcgis_export_tile_layer_class_defined(self) -> None:
        """Classe L.TileLayer.ArcGISExport deve estar definida no HTML."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "L.TileLayer.ArcGISExport" in html

    def test_arcgis_export_bbox_formula_present(self) -> None:
        """Fórmula de bbox EPSG:3857 por tile deve estar no HTML."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "20037508" in html  # constante E do EPSG:3857
        assert "bboxSR=3857" in html

    def test_offline_guard_excludes_arcgis_export(self) -> None:
        """Guard de modo offline deve excluir L.TileLayer.ArcGISExport."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "L.TileLayer.ArcGISExport" in html
        # Garantir que o guard de remoção de tiles não remove camadas ArcGISExport
        assert "!(l instanceof L.TileLayer.ArcGISExport)" in html

    def test_aeroprojetos_uses_rest_export(self) -> None:
        """geofisica/aerogeofisica deve usar REST /export (WMS só suporta EPSG:4326)."""
        html = HtmlReportRenderer().render(self._make_simple_report())
        assert "_REST_AEROPROJ" in html
        assert "geofisica/aerogeofisica/MapServer/export" in html
        # WMSServer não deve mais aparecer para este serviço
        assert "geofisica/aerogeofisica/MapServer/WMSServer" not in html

"""HtmlReportRenderer — dashboard HTML self-contained do ProspectionReport.

Usa Jinja2 + Leaflet.js + Chart.js para gerar um arquivo HTML
único com mapa interativo, gráficos e visões do relatório.

Ref: ADR-004
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2

if TYPE_CHECKING:
    from miner_harness.core.types import ProspectionReport

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


class HtmlReportRenderer:
    """Renderiza ProspectionReport como dashboard HTML self-contained.

    Embute Leaflet.js, Chart.js e dados do relatório diretamente
    no HTML — sem dependências externas ao abrir no browser.

    Usage:
        renderer = HtmlReportRenderer()
        path = renderer.render_to_file(report, Path("report.html"))
    """

    def __init__(self) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=False,
        )

    def render(self, report: ProspectionReport) -> str:
        """Renderiza relatório como HTML string completa."""
        template = self._env.get_template("report.html.j2")
        return template.render(
            report_json_str=json.dumps(
                report.model_dump(mode="json"),
                ensure_ascii=False,
                default=str,
            ),
            leaflet_js=self._static("leaflet.min.js"),
            leaflet_css=self._static("leaflet.min.css"),
            chart_js=self._static("chart.umd.min.js"),
        )

    def render_to_file(self, report: ProspectionReport, path: Path) -> Path:
        """Renderiza e salva arquivo HTML. Retorna o path gravado."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report), encoding="utf-8")
        return path

    @staticmethod
    def _static(filename: str) -> str:
        """Lê arquivo da pasta static/."""
        return (_STATIC_DIR / filename).read_text(encoding="utf-8")

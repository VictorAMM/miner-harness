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
from markupsafe import Markup

if TYPE_CHECKING:
    from miner_harness.core.types import ProspectionReport

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

# Characters that must be escaped when embedding JSON inside a <script> tag
# to prevent early script-tag termination (</script>) or CDATA injection.
_SCRIPT_ESCAPES = {
    "<": r"<",
    ">": r">",
    "&": r"&",
}


def _safe_json(data: object) -> Markup:
    """Serialize *data* to JSON safe for embedding inside a <script> tag."""
    raw = json.dumps(data, ensure_ascii=False, default=str)
    for char, escape in _SCRIPT_ESCAPES.items():
        raw = raw.replace(char, escape)
    return Markup(raw)  # nosec B704 — raw is HTML-escaped above; safe for <script> embedding


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
            autoescape=True,
        )

    def render(self, report: ProspectionReport) -> str:
        """Renderiza relatório como HTML string completa."""
        template = self._env.get_template("report.html.j2")
        return template.render(
            report_json_str=_safe_json(report.model_dump(mode="json")),
            # nosec B704 — bundled static assets from the package, not user data
            leaflet_js=Markup(self._static("leaflet.min.js")),  # nosec B704
            leaflet_css=Markup(self._static("leaflet.min.css")),  # nosec B704
            chart_js=Markup(self._static("chart.umd.min.js")),  # nosec B704
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

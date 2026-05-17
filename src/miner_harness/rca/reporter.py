"""RCA Reporter — generates Root Cause Analysis documents.

Produces structured RCA reports from classified errors and diagnostics,
following the ASO v3 RCA template format.

Ref: ASO v3 Phase 10 — RCA Autonomo
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone  # noqa: UP017
from pathlib import Path
from typing import Any

import structlog

from miner_harness.rca.classifier import ClassifiedError  # noqa: TCH001
from miner_harness.rca.diagnostics import DiagnosticSnapshot  # noqa: TCH001

logger = structlog.get_logger(__name__)


@dataclass
class RCAReport:
    """Structured RCA report."""

    id: str
    title: str
    classified_error: ClassifiedError
    diagnostics: DiagnosticSnapshot
    timeline: list[dict[str, Any]] = field(default_factory=list)
    root_cause: str = ""
    contributing_factors: list[str] = field(default_factory=list)
    remediation_steps: list[str] = field(default_factory=list)
    prevention_measures: list[str] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc),  # noqa: UP017
    )

    def to_dict(self) -> dict[str, Any]:
        """Export as dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "classified_error": self.classified_error.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
            "timeline": self.timeline,
            "root_cause": self.root_cause,
            "contributing_factors": self.contributing_factors,
            "remediation_steps": self.remediation_steps,
            "prevention_measures": self.prevention_measures,
            "created_at": self.created_at.isoformat(),
        }

    def to_markdown(self) -> str:
        """Generate markdown RCA document."""
        lines = [
            f"# RCA: {self.title}",
            "",
            f"**ID**: {self.id}",
            f"**Data**: {self.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Categoria**: {self.classified_error.category.value}",
            f"**Severidade**: {self.classified_error.severity.value}",
            "",
            "## Erro",
            "",
            f"- **Tipo**: `{self.classified_error.error_type}`",
            f"- **Mensagem**: {self.classified_error.message}",
            f"- **Recuperavel**: {'Sim' if self.classified_error.recoverable else 'Nao'}",
            "",
            "## Causa Raiz",
            "",
            self.root_cause or "_Analise pendente_",
            "",
            "## Fatores Contribuintes",
            "",
        ]

        if self.contributing_factors:
            for factor in self.contributing_factors:
                lines.append(f"- {factor}")
        else:
            lines.append("_Nenhum identificado_")

        lines.extend([
            "",
            "## Timeline",
            "",
        ])

        if self.timeline:
            for event in self.timeline:
                ts = event.get("timestamp", "")
                desc = event.get("description", "")
                lines.append(f"- **{ts}**: {desc}")
        else:
            lines.append("_Sem eventos registrados_")

        lines.extend([
            "",
            "## Remediacao",
            "",
        ])

        if self.remediation_steps:
            for i, step in enumerate(self.remediation_steps, 1):
                lines.append(f"{i}. {step}")
        else:
            lines.append(f"- {self.classified_error.suggested_action}")

        lines.extend([
            "",
            "## Prevencao",
            "",
        ])

        if self.prevention_measures:
            for measure in self.prevention_measures:
                lines.append(f"- {measure}")
        else:
            lines.append("_Medidas a definir_")

        lines.extend([
            "",
            "## Diagnostico do Sistema",
            "",
            f"- **Disco livre**: {self.diagnostics.disk_free_gb:.1f} GB"
            f" / {self.diagnostics.disk_total_gb:.1f} GB",
            f"- **Python**: {self.diagnostics.python_version}",
            f"- **Plataforma**: {self.diagnostics.platform_info}",
        ])

        if self.diagnostics.ollama_reachable is not None:
            status = "Sim" if self.diagnostics.ollama_reachable else "Nao"
            lines.append(f"- **Ollama acessivel**: {status}")

        if self.diagnostics.cache_size_mb is not None:
            lines.append(f"- **Cache**: {self.diagnostics.cache_size_mb:.1f} MB")

        lines.append("")
        return "\n".join(lines)


def _generate_rca_id() -> str:
    """Generate a unique RCA ID."""
    now = datetime.now(tz=timezone.utc)  # noqa: UP017
    return f"RCA-{now.strftime('%Y%m%d-%H%M%S')}"


def _infer_root_cause(classified: ClassifiedError) -> str:
    """Infer root cause based on classification."""
    causes = {
        "NETWORK": (
            f"Falha de conectividade com servico externo "
            f"({classified.context.get('service', 'desconhecido')}). "
            f"Erro: {classified.error_type}"
        ),
        "LLM": (
            f"Falha no modelo LLM — {classified.error_type}. "
            f"Possivel timeout, modelo indisponivel, ou resposta malformada."
        ),
        "STORAGE": (
            f"Erro de armazenamento — {classified.error_type}. "
            f"Verificar integridade do banco e espaco em disco."
        ),
        "DATA": (
            f"Dados invalidos ou insuficientes — {classified.error_type}. "
            f"Fonte de dados pode estar indisponivel ou formato mudou."
        ),
        "CONFIG": (
            f"Erro de configuracao — {classified.error_type}. "
            f"Verificar paths e permissoes."
        ),
    }
    return causes.get(
        classified.category.name,
        f"Erro nao classificado: {classified.error_type} — {classified.message}",
    )


def _infer_prevention(classified: ClassifiedError) -> list[str]:
    """Infer prevention measures based on classification."""
    measures: dict[str, list[str]] = {
        "NETWORK": [
            "Implementar circuit breaker para servicos externos",
            "Adicionar health check pre-execucao",
            "Configurar alertas de conectividade",
        ],
        "LLM": [
            "Configurar fallback para modelo alternativo",
            "Implementar validacao de resposta LLM",
            "Monitorar latencia e timeouts do modelo",
        ],
        "STORAGE": [
            "Implementar verificacao de integridade periodica",
            "Configurar alertas de espaco em disco",
            "Manter backups do cache",
        ],
        "DATA": [
            "Adicionar validacao de schema na entrada",
            "Implementar fallback para dados ausentes",
            "Monitorar mudancas na API fonte",
        ],
        "CONFIG": [
            "Validar configuracao no startup",
            "Documentar dependencias de arquivos",
            "Implementar config check no health command",
        ],
    }
    return measures.get(classified.category.name, ["Investigar causa manualmente"])


async def generate_rca_report(
    classified: ClassifiedError,
    diagnostics: DiagnosticSnapshot,
    timeline: list[dict[str, Any]] | None = None,
) -> RCAReport:
    """Generate an RCA report from a classified error and diagnostics.

    Args:
        classified: The classified error.
        diagnostics: System diagnostic snapshot.
        timeline: Optional event timeline.

    Returns:
        Complete RCAReport ready for export.
    """
    rca_id = _generate_rca_id()
    title = (
        f"{classified.category.value.title()} Error — "
        f"{classified.error_type}"
    )

    report = RCAReport(
        id=rca_id,
        title=title,
        classified_error=classified,
        diagnostics=diagnostics,
        timeline=timeline or [],
        root_cause=_infer_root_cause(classified),
        contributing_factors=[],
        remediation_steps=[classified.suggested_action],
        prevention_measures=_infer_prevention(classified),
    )

    logger.info(
        "rca_report_generated",
        rca_id=rca_id,
        category=classified.category.value,
        severity=classified.severity.value,
    )

    return report


async def save_rca_report(
    report: RCAReport,
    output_dir: Path | None = None,
) -> Path:
    """Save RCA report as markdown and JSON.

    Args:
        report: The RCA report to save.
        output_dir: Directory to save reports. Defaults to docs/rca/.

    Returns:
        Path to the saved markdown file.
    """
    if output_dir is None:
        output_dir = Path("docs/rca")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save markdown
    md_path = output_dir / f"{report.id.lower()}.md"
    md_path.write_text(report.to_markdown(), encoding="utf-8")

    # Save JSON
    json_path = output_dir / f"{report.id.lower()}.json"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("rca_report_saved", path=str(md_path), rca_id=report.id)
    return md_path

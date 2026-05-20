"""Wizard system checks — verifies prerequisites before installation.

Each check returns a CheckResult with status, message, and optional detail.
All checks are pure functions with no side effects, making them testable
without a running Textual app.

Ref: ADR-004, ASO v3 Wizard
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TCH003
from typing import Any

if sys.version_info >= (3, 11):  # noqa: UP036
    from enum import StrEnum  # noqa: F811
else:  # pragma: no cover
    from enum import Enum

    class StrEnum(str, Enum):  # noqa: UP042
        """Compatibility shim — project requires 3.11+ but dev env may differ."""


import structlog

logger = structlog.get_logger(__name__)

# Requirements
_MIN_PYTHON = (3, 11)
_MIN_DISK_GB = 2.0
_OLLAMA_DEFAULT_URL = "http://localhost:11434"
_OLLAMA_TIMEOUT_S = 5


class CheckStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class CheckResult:
    """Result of a single prerequisite check."""

    name: str
    status: CheckStatus
    message: str
    detail: str = ""
    fix_hint: str = ""

    @property
    def passed(self) -> bool:
        return self.status in (CheckStatus.OK, CheckStatus.WARNING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "detail": self.detail,
            "fix_hint": self.fix_hint,
        }


@dataclass
class SystemReport:
    """Aggregated result of all system checks."""

    results: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == CheckStatus.FAIL]

    @property
    def warnings(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == CheckStatus.WARNING]

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "results": [r.to_dict() for r in self.results],
        }


def check_python_version() -> CheckResult:
    """Verify Python version meets minimum requirement."""
    current = sys.version_info[:2]
    version_str = f"{current[0]}.{current[1]}"
    min_str = f"{_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}"

    if current >= _MIN_PYTHON:
        return CheckResult(
            name="python_version",
            status=CheckStatus.OK,
            message=f"Python {version_str} — OK",
        )
    return CheckResult(
        name="python_version",
        status=CheckStatus.FAIL,
        message=f"Python {version_str} encontrado, minimo {min_str}",
        fix_hint=f"Instale Python {min_str}+ em python.org",
    )


def check_disk_space(path: Path | None = None) -> CheckResult:
    """Verify sufficient free disk space for models and cache."""
    check_path = path or Path.home()
    try:
        usage = shutil.disk_usage(check_path)
        free_gb = usage.free / (1024**3)
    except OSError as e:
        return CheckResult(
            name="disk_space",
            status=CheckStatus.FAIL,
            message=f"Nao foi possivel verificar espaco em disco: {e}",
        )

    if free_gb >= _MIN_DISK_GB:
        return CheckResult(
            name="disk_space",
            status=CheckStatus.OK,
            message=f"{free_gb:.1f} GB livres — OK",
            detail=f"Minimo requerido: {_MIN_DISK_GB} GB",
        )
    if free_gb >= _MIN_DISK_GB * 0.5:
        return CheckResult(
            name="disk_space",
            status=CheckStatus.WARNING,
            message=f"Apenas {free_gb:.1f} GB livres (recomendado: {_MIN_DISK_GB} GB)",
            fix_hint="Libere espaco antes de baixar modelos LLM grandes",
        )
    return CheckResult(
        name="disk_space",
        status=CheckStatus.FAIL,
        message=f"Espaco insuficiente: {free_gb:.1f} GB (minimo: {_MIN_DISK_GB} GB)",
        fix_hint="Libere pelo menos 2 GB antes de continuar",
    )


def check_ollama(base_url: str = _OLLAMA_DEFAULT_URL) -> CheckResult:
    """Verify Ollama is running and reachable."""
    try:
        import httpx  # noqa: PLC0415

        with httpx.Client(timeout=_OLLAMA_TIMEOUT_S) as client:
            resp = client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                model_list = ", ".join(models[:3]) or "nenhum"
                return CheckResult(
                    name="ollama",
                    status=CheckStatus.OK,
                    message=f"Ollama em execucao — {len(models)} modelo(s)",
                    detail=f"Modelos: {model_list}",
                )
            return CheckResult(
                name="ollama",
                status=CheckStatus.WARNING,
                message=f"Ollama respondeu com status {resp.status_code}",
                fix_hint="Verifique se o Ollama esta configurado corretamente",
            )
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            name="ollama",
            status=CheckStatus.WARNING,
            message=f"Ollama nao acessivel em {base_url}",
            detail=str(e),
            fix_hint=(
                "Instale e inicie o Ollama: https://ollama.com"
                " — o sistema funciona sem ele, mas os agentes precisam do LLM"
            ),
        )


def check_miner_home(miner_home: Path | None = None) -> CheckResult:
    """Verify or prepare the MINER_HOME directory."""
    home = miner_home or (Path.home() / ".miner-harness")

    if home.exists():
        if not home.is_dir():
            return CheckResult(
                name="miner_home",
                status=CheckStatus.FAIL,
                message=f"{home} existe mas nao e um diretorio",
                fix_hint=f"Remova o arquivo {home} manualmente",
            )
        return CheckResult(
            name="miner_home",
            status=CheckStatus.OK,
            message=f"MINER_HOME ja existe: {home}",
        )

    # Check if parent is writable
    try:
        home.parent.stat()
        return CheckResult(
            name="miner_home",
            status=CheckStatus.OK,
            message=f"MINER_HOME sera criado em: {home}",
        )
    except OSError as e:
        return CheckResult(
            name="miner_home",
            status=CheckStatus.FAIL,
            message=f"Nao foi possivel acessar {home.parent}: {e}",
            fix_hint="Verifique permissoes do diretorio home",
        )


def run_all_checks(
    miner_home: Path | None = None,
    ollama_url: str = _OLLAMA_DEFAULT_URL,
    disk_path: Path | None = None,
) -> SystemReport:
    """Run all prerequisite checks and return a SystemReport.

    Args:
        miner_home: Override MINER_HOME path for testing.
        ollama_url: Override Ollama URL for testing.
        disk_path: Override disk check path for testing.

    Returns:
        SystemReport with results of all checks.
    """
    report = SystemReport()

    checks = [
        check_python_version(),
        check_disk_space(disk_path),
        check_ollama(ollama_url),
        check_miner_home(miner_home),
    ]

    for result in checks:
        report.results.append(result)
        logger.info(
            "check_complete",
            check=result.name,
            status=result.status.value,
        )

    logger.info(
        "system_checks_done",
        passed=report.all_passed,
        failures=len(report.failures),
        warnings=len(report.warnings),
    )
    return report

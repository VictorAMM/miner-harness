"""Wizard — instalação guiada e setup inicial.

TUI via Rich para verificação de dependências, configuração
e setup inicial do sistema.

Ref: ADR-004, ASO v3
"""

from miner_harness.wizard.checks import (
    CheckResult,
    CheckStatus,
    SystemReport,
    check_disk_space,
    check_miner_home,
    check_ollama,
    check_python_version,
    run_all_checks,
)
from miner_harness.wizard.installer import (
    InstallResult,
    InstallStep,
    run_installation,
)
from miner_harness.wizard.runner import WizardRunner

__all__ = [
    "CheckResult",
    "CheckStatus",
    "InstallResult",
    "InstallStep",
    "SystemReport",
    "WizardRunner",
    "check_disk_space",
    "check_miner_home",
    "check_ollama",
    "check_python_version",
    "run_all_checks",
    "run_installation",
]

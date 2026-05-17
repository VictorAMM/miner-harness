"""Wizard runner — orchestrates checks and installation with rich output.

Provides a rich terminal UI for the guided installation flow.
Business logic lives in checks.py and installer.py; this module
handles only presentation and user interaction.

Ref: ADR-004
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from miner_harness.wizard.checks import CheckStatus, SystemReport, run_all_checks
from miner_harness.wizard.installer import InstallResult, run_installation

logger = structlog.get_logger(__name__)

_BANNER = """
[bold cyan]miner-harness[/bold cyan] — Sistema de Prospecção Mineral Inteligente
[dim]Wizard de Instalação[/dim]
"""

_OLLAMA_DEFAULT = "http://localhost:11434"
_DEFAULT_MODEL = "qwen3:8b-q4_K_M"


class WizardRunner:
    """Orchestrates the guided installation wizard.

    Separates I/O (console, prompts) from business logic so that
    run_checks() and run_install() can be called independently in tests.

    Usage::

        runner = WizardRunner()
        exit_code = runner.run()
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Execute the full wizard flow interactively.

        Returns:
            0 on success, 1 on failure.
        """
        self._print_banner()

        # 1. Collect configuration from user
        params = self._prompt_config()

        # 2. Run system checks
        self._console.print("\n[bold]Verificando prerequisitos...[/bold]")
        report = run_all_checks(
            miner_home=params["miner_home"],
            ollama_url=params["ollama_url"],
        )
        self._print_check_report(report)

        if not report.all_passed:
            self._console.print(
                "[red]Uma ou mais verificacoes falharam. "
                "Corrija os problemas acima e execute novamente.[/red]"
            )
            return 1

        # 3. Confirm before installing
        if not self._confirm_install(params):
            self._console.print("[yellow]Instalacao cancelada.[/yellow]")
            return 0

        # 4. Run installation
        self._console.print("\n[bold]Instalando...[/bold]")
        result = run_installation(
            miner_home=params["miner_home"],
            model=params["model"],
            ollama_url=params["ollama_url"],
        )
        self._print_install_result(result)

        if result.success:
            self._print_success(result.miner_home)
            return 0

        self._console.print("[red]Instalacao falhou. Verifique os erros acima.[/red]")
        return 1

    def run_checks(
        self,
        miner_home: Path | None = None,
        ollama_url: str = _OLLAMA_DEFAULT,
    ) -> SystemReport:
        """Run checks only (no prompts). Useful for CI and testing."""
        return run_all_checks(miner_home=miner_home, ollama_url=ollama_url)

    def run_install(
        self,
        miner_home: Path | None = None,
        model: str = _DEFAULT_MODEL,
        ollama_url: str = _OLLAMA_DEFAULT,
    ) -> InstallResult:
        """Run installation only (no prompts). Useful for CI and testing."""
        return run_installation(
            miner_home=miner_home,
            model=model,
            ollama_url=ollama_url,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        self._console.print(Panel(_BANNER, border_style="cyan"))

    def _prompt_config(self) -> dict[str, Any]:
        """Collect installation parameters from user."""
        default_home = str(Path.home() / ".miner-harness")

        miner_home_str = Prompt.ask(
            "Diretorio de instalacao (MINER_HOME)",
            default=default_home,
            console=self._console,
        )
        model = Prompt.ask(
            "Modelo LLM padrao",
            default=_DEFAULT_MODEL,
            console=self._console,
        )
        ollama_url = Prompt.ask(
            "URL do Ollama",
            default=_OLLAMA_DEFAULT,
            console=self._console,
        )

        return {
            "miner_home": Path(miner_home_str),
            "model": model,
            "ollama_url": ollama_url,
        }

    def _print_check_report(self, report: SystemReport) -> None:
        """Print system check results as a rich table."""
        table = Table(show_header=True, header_style="bold")
        table.add_column("Verificacao", style="cyan", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Mensagem")
        table.add_column("Dica", style="dim")

        icons = {
            CheckStatus.OK: "[green]✓[/green]",
            CheckStatus.WARNING: "[yellow]⚠[/yellow]",
            CheckStatus.FAIL: "[red]✗[/red]",
        }

        for r in report.results:
            table.add_row(
                r.name,
                icons[r.status],
                r.message,
                r.fix_hint,
            )

        self._console.print(table)

    def _confirm_install(self, params: dict[str, Any]) -> bool:
        """Ask user to confirm installation parameters."""
        self._console.print(
            f"\nInstalar em [cyan]{params['miner_home']}[/cyan] "
            f"com modelo [cyan]{params['model']}[/cyan]?"
        )
        return Confirm.ask("Continuar?", default=True, console=self._console)

    def _print_install_result(self, result: InstallResult) -> None:
        """Print installation step results."""
        for step in result.steps:
            icon = "[green]✓[/green]" if step.success else "[red]✗[/red]"
            self._console.print(f"  {icon} {step.message}")
            if step.detail and not step.success:
                self._console.print(f"    [dim]{step.detail}[/dim]")

    def _print_success(self, miner_home: Path) -> None:
        """Print success summary."""
        self._console.print(
            Panel(
                f"[green bold]Instalacao concluida![/green bold]\n\n"
                f"MINER_HOME: [cyan]{miner_home}[/cyan]\n\n"
                f"Execute [cyan]miner-harness health[/cyan] para verificar o sistema.\n"
                f"Execute [cyan]miner-harness analyze --help[/cyan] para comecar.",
                title="[green]Pronto[/green]",
                border_style="green",
            )
        )

"""Tests for wizard.runner module."""

from __future__ import annotations

from pathlib import Path  # noqa: TCH003
from unittest.mock import patch

from rich.console import Console

from miner_harness.wizard.runner import WizardRunner


def _silent_console() -> Console:
    """Return a no-output console for tests."""
    return Console(quiet=True)


class TestWizardRunnerChecks:
    def test_run_checks_returns_report(self, tmp_path: Path) -> None:
        runner = WizardRunner(console=_silent_console())
        report = runner.run_checks(
            miner_home=tmp_path / ".miner-harness",
            ollama_url="http://localhost:99999",
        )
        assert report is not None
        assert len(report.results) == 4  # noqa: PLR2004

    def test_run_checks_all_named(self, tmp_path: Path) -> None:
        runner = WizardRunner(console=_silent_console())
        report = runner.run_checks(miner_home=tmp_path / ".miner-harness")
        names = {r.name for r in report.results}
        assert "python_version" in names
        assert "ollama" in names


class TestWizardRunnerInstall:
    def test_run_install_creates_home(self, tmp_path: Path) -> None:
        runner = WizardRunner(console=_silent_console())
        home = tmp_path / ".miner-harness"
        result = runner.run_install(miner_home=home)
        assert result.success is True
        assert home.exists()

    def test_run_install_returns_result(self, tmp_path: Path) -> None:
        runner = WizardRunner(console=_silent_console())
        result = runner.run_install(miner_home=tmp_path / ".miner-harness")
        assert result is not None
        assert len(result.steps) > 0


class TestWizardRunnerInteractive:
    def test_run_returns_zero_on_success(self, tmp_path: Path) -> None:
        runner = WizardRunner(console=_silent_console())

        with (
            patch.object(runner, "_prompt_config") as mock_prompt,
            patch.object(runner, "_confirm_install", return_value=True),
        ):
            mock_prompt.return_value = {
                "miner_home": tmp_path / ".miner-harness",
                "model": "qwen3:8b-q4_K_M",
                "ollama_url": "http://localhost:99999",
            }
            exit_code = runner.run()

        assert exit_code == 0

    def test_run_returns_zero_on_cancel(self, tmp_path: Path) -> None:
        runner = WizardRunner(console=_silent_console())

        with (
            patch.object(runner, "_prompt_config") as mock_prompt,
            patch.object(runner, "_confirm_install", return_value=False),
        ):
            mock_prompt.return_value = {
                "miner_home": tmp_path / ".miner-harness",
                "model": "qwen3:8b-q4_K_M",
                "ollama_url": "http://localhost:99999",
            }
            exit_code = runner.run()

        assert exit_code == 0

    def test_run_returns_one_on_check_failure(self, tmp_path: Path) -> None:
        runner = WizardRunner(console=_silent_console())

        # Make a path that causes miner_home check to fail (file conflict)
        conflict = tmp_path / "blocker"
        conflict.write_text("file")

        with patch.object(runner, "_prompt_config") as mock_prompt:
            mock_prompt.return_value = {
                "miner_home": conflict,  # file, not dir → FAIL
                "model": "qwen3:8b-q4_K_M",
                "ollama_url": "http://localhost:99999",
            }
            exit_code = runner.run()

        assert exit_code == 1

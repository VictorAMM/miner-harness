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
                "model": "qwen3:8b",
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
                "model": "qwen3:8b",
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
                "model": "qwen3:8b",
                "ollama_url": "http://localhost:99999",
            }
            exit_code = runner.run()

        assert exit_code == 1

    def test_run_returns_one_on_install_failure(self, tmp_path: Path) -> None:
        """run() retorna 1 quando instalação falha (linhas 98-99)."""
        from unittest.mock import MagicMock

        runner = WizardRunner(console=_silent_console())

        mock_step = MagicMock()
        mock_step.success = False
        mock_step.message = "Falhou"
        mock_step.detail = None

        mock_fail_result = MagicMock()
        mock_fail_result.success = False
        mock_fail_result.miner_home = tmp_path / ".miner"
        mock_fail_result.steps = [mock_step]

        mock_ok_report = MagicMock()
        mock_ok_report.all_passed = True

        with (
            patch.object(
                runner,
                "_prompt_config",
                return_value={
                    "miner_home": tmp_path / ".miner",
                    "model": "qwen3:8b",
                    "ollama_url": "http://localhost:99999",
                },
            ),
            patch.object(runner, "_confirm_install", return_value=True),
            patch("miner_harness.wizard.runner.run_all_checks", return_value=mock_ok_report),
            patch(
                "miner_harness.wizard.runner.run_installation",
                return_value=mock_fail_result,
            ),
        ):
            exit_code = runner.run()

        assert exit_code == 1


class TestWizardRunnerPrivateHelpers:
    """Testa helpers privados — _prompt_config, _confirm_install, _print_install_result."""

    def test_prompt_config_returns_dict(self, tmp_path: Path) -> None:
        """_prompt_config usa Prompt.ask e retorna dict (linhas 131-149)."""
        runner = WizardRunner(console=_silent_console())

        with patch("miner_harness.wizard.runner.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = [
                str(tmp_path / ".miner"),
                "qwen3:8b",
                "http://localhost:11434",
            ]
            params = runner._prompt_config()

        assert params["model"] == "qwen3:8b"
        assert params["ollama_url"] == "http://localhost:11434"
        assert params["miner_home"] == tmp_path / ".miner"

    def test_confirm_install_delegates_to_confirm(self, tmp_path: Path) -> None:
        """_confirm_install usa Confirm.ask (linhas 181-185)."""
        runner = WizardRunner(console=_silent_console())
        params = {
            "miner_home": tmp_path / ".miner",
            "model": "qwen3:8b",
            "ollama_url": "http://localhost:11434",
        }

        with patch("miner_harness.wizard.runner.Confirm") as mock_confirm:
            mock_confirm.ask.return_value = True
            result = runner._confirm_install(params)

        assert result is True

    def test_print_install_result_with_detail_on_failure(self, tmp_path: Path) -> None:
        """Passo com detail e success=False exibe detalhe (linha 193)."""
        from unittest.mock import MagicMock

        runner = WizardRunner(console=_silent_console())

        mock_step = MagicMock()
        mock_step.success = False
        mock_step.message = "Passo falhou"
        mock_step.detail = "Motivo detalhado aqui"

        mock_result = MagicMock()
        mock_result.steps = [mock_step]

        runner._print_install_result(mock_result)  # não deve lançar

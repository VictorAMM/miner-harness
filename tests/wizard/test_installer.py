"""Tests for wizard.installer module."""

from __future__ import annotations

import json
from pathlib import Path

from miner_harness.wizard.installer import (
    InstallResult,
    InstallStep,
    create_miner_home,
    run_installation,
    write_env_hint,
    write_initial_config,
)


class TestInstallStep:
    def test_success(self) -> None:
        step = InstallStep("create_dirs", True, "Done")
        assert step.success is True

    def test_failure(self) -> None:
        step = InstallStep("create_dirs", False, "Error")
        assert step.success is False


class TestInstallResult:
    def test_success_all_pass(self) -> None:
        result = InstallResult(miner_home=Path("/tmp/test"))
        result.steps.append(InstallStep("a", True, "ok"))
        result.steps.append(InstallStep("b", True, "ok"))
        assert result.success is True

    def test_failure_one_fails(self) -> None:
        result = InstallResult(miner_home=Path("/tmp/test"))
        result.steps.append(InstallStep("a", True, "ok"))
        result.steps.append(InstallStep("b", False, "fail"))
        assert result.success is False
        assert len(result.failed_steps) == 1

    def test_to_dict(self) -> None:
        result = InstallResult(miner_home=Path("/tmp/test"))
        d = result.to_dict()
        assert "miner_home" in d
        assert "success" in d
        assert "steps" in d


class TestCreateMinerHome:
    def test_creates_dirs(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        step = create_miner_home(home)
        assert step.success is True
        assert home.exists()
        assert (home / "cache").exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        create_miner_home(home)
        step = create_miner_home(home)  # run twice
        assert step.success is True


class TestWriteInitialConfig:
    def test_creates_config_file(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        home.mkdir()
        step = write_initial_config(home, model="llama3", ollama_url="http://x:11434")
        assert step.success is True
        config_path = home / "config.json"
        assert config_path.exists()

    def test_config_contains_model(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        home.mkdir()
        write_initial_config(home, model="custom-model")
        config_path = home / "config.json"
        data = json.loads(config_path.read_text())
        assert data["orchestrator"]["model"] == "custom-model"

    def test_config_contains_ollama_url(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        home.mkdir()
        write_initial_config(home, ollama_url="http://custom:9999")
        data = json.loads((home / "config.json").read_text())
        assert data["orchestrator"]["ollama_base_url"] == "http://custom:9999"


class TestWriteEnvHint:
    def test_creates_hint_file(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        home.mkdir()
        step = write_env_hint(home)
        assert step.success is True
        hint = home / "env_hint.sh"
        assert hint.exists()
        content = hint.read_text()
        assert "MINER_HOME" in content


class TestWriteInitialConfigOSError:
    """Cobre OSError em write_initial_config (linhas 112-113)."""

    def test_oserror_returns_failed_step(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        home = tmp_path / ".miner"
        home.mkdir()
        with patch("pathlib.Path.write_text", side_effect=OSError("permission denied")):
            step = write_initial_config(home)
        assert step.success is False
        assert "permission denied" in step.message


class TestWriteEnvHintOSError:
    """Cobre OSError em write_env_hint (linhas 132-133)."""

    def test_oserror_returns_failed_step(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        home = tmp_path / ".miner"
        home.mkdir()
        with patch("pathlib.Path.write_text", side_effect=OSError("read-only")):
            step = write_env_hint(home)
        assert step.success is False
        assert "read-only" in step.message


class TestRunInstallation:
    def test_full_install(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        result = run_installation(miner_home=home)
        assert result.success is True
        assert len(result.steps) == 3  # noqa: PLR2004
        assert all(s.success for s in result.steps)

    def test_creates_expected_files(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        run_installation(miner_home=home)
        assert home.exists()
        assert (home / "config.json").exists()
        assert (home / "env_hint.sh").exists()

    def test_aborts_on_dir_failure(self, tmp_path: Path) -> None:
        # Point to a path that can't be created (parent is a file)
        bad_parent = tmp_path / "blocker"
        bad_parent.write_text("I am a file")
        home = bad_parent / ".miner-harness"
        result = run_installation(miner_home=home)
        # Should have only 1 step (create_dirs failed, rest skipped)
        assert len(result.steps) == 1
        assert not result.steps[0].success

    def test_custom_model_and_url(self, tmp_path: Path) -> None:
        home = tmp_path / ".miner-harness"
        result = run_installation(
            miner_home=home,
            model="llama3",
            ollama_url="http://remote:11434",
        )
        assert result.success is True
        data = json.loads((home / "config.json").read_text())
        assert data["orchestrator"]["model"] == "llama3"

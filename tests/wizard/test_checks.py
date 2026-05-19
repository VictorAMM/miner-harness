"""Tests for wizard.checks module."""

from __future__ import annotations

import sys
from pathlib import Path  # noqa: TCH003
from unittest.mock import MagicMock, patch

from miner_harness.wizard.checks import (
    CheckStatus,
    SystemReport,
    check_disk_space,
    check_miner_home,
    check_ollama,
    check_python_version,
    run_all_checks,
)


class TestCheckStatus:
    def test_values(self) -> None:
        assert CheckStatus.OK.value == "ok"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.FAIL.value == "fail"


class TestCheckResult:
    def test_passed_ok(self) -> None:
        r = check_python_version()
        # Current Python is 3.11+ so should pass
        assert r.passed is True

    def test_to_dict_keys(self) -> None:
        r = check_python_version()
        d = r.to_dict()
        assert "name" in d
        assert "status" in d
        assert "message" in d
        assert "fix_hint" in d


class TestSystemReport:
    def test_all_passed_empty(self) -> None:
        report = SystemReport()
        assert report.all_passed is True

    def test_failures_filter(self) -> None:
        from miner_harness.wizard.checks import CheckResult  # noqa: PLC0415

        report = SystemReport()
        report.results.append(CheckResult("a", CheckStatus.OK, "ok"))
        report.results.append(CheckResult("b", CheckStatus.FAIL, "fail"))
        assert len(report.failures) == 1
        assert len(report.warnings) == 0

    def test_to_dict(self) -> None:
        report = SystemReport()
        d = report.to_dict()
        assert "all_passed" in d
        assert "results" in d


class TestCheckPythonVersion:
    def test_current_version_passes(self) -> None:
        result = check_python_version()
        assert result.name == "python_version"
        # Running on 3.11+ so should be OK
        assert result.status == CheckStatus.OK
        assert result.passed is True

    def test_old_version_fails(self) -> None:
        with patch.object(sys, "version_info", (3, 9, 0)):
            result = check_python_version()
        assert result.status == CheckStatus.FAIL
        assert not result.passed
        assert result.fix_hint != ""


class TestCheckDiskSpace:
    def test_ample_space_passes(self, tmp_path: Path) -> None:
        with patch("shutil.disk_usage") as mock_du:
            mock_du.return_value = MagicMock(free=10 * 1024**3, total=100 * 1024**3)
            result = check_disk_space(tmp_path)
        assert result.status == CheckStatus.OK
        assert result.passed is True

    def test_tight_space_warns(self, tmp_path: Path) -> None:
        with patch("shutil.disk_usage") as mock_du:
            # 1.5 GB — below 2GB but above 1GB (50% of minimum)
            mock_du.return_value = MagicMock(free=1.5 * 1024**3, total=100 * 1024**3)
            result = check_disk_space(tmp_path)
        assert result.status == CheckStatus.WARNING
        assert result.passed is True  # warning still passes

    def test_no_space_fails(self, tmp_path: Path) -> None:
        with patch("shutil.disk_usage") as mock_du:
            mock_du.return_value = MagicMock(free=0.5 * 1024**3, total=100 * 1024**3)
            result = check_disk_space(tmp_path)
        assert result.status == CheckStatus.FAIL
        assert not result.passed

    def test_oserror_fails(self, tmp_path: Path) -> None:
        with patch("shutil.disk_usage", side_effect=OSError("permission denied")):
            result = check_disk_space(tmp_path)
        assert result.status == CheckStatus.FAIL


class TestCheckOllama:
    def test_ollama_running(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen3:8b"}, {"name": "llama3"}]}
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client
            result = check_ollama("http://localhost:11434")
        assert result.status == CheckStatus.OK
        assert result.passed is True

    def test_ollama_not_running(self) -> None:
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client_cls.return_value = mock_client
            result = check_ollama("http://localhost:11434")
        assert result.status == CheckStatus.WARNING
        assert result.passed is True  # warning — system works without ollama
        assert result.fix_hint != ""

    def test_ollama_bad_status(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client
            result = check_ollama("http://localhost:11434")
        assert result.status == CheckStatus.WARNING


class TestCheckMinerHome:
    def test_new_path_ok(self, tmp_path: Path) -> None:
        new_home = tmp_path / ".miner-harness"
        result = check_miner_home(new_home)
        assert result.status == CheckStatus.OK
        assert result.passed is True

    def test_existing_dir_ok(self, tmp_path: Path) -> None:
        existing = tmp_path / "miner"
        existing.mkdir()
        result = check_miner_home(existing)
        assert result.status == CheckStatus.OK

    def test_file_instead_of_dir_fails(self, tmp_path: Path) -> None:
        conflict = tmp_path / "miner"
        conflict.write_text("not a dir")
        result = check_miner_home(conflict)
        assert result.status == CheckStatus.FAIL
        assert not result.passed

    def test_inaccessible_parent_fails(self) -> None:
        """OSError ao acessar parent retorna FAIL (linhas 202-203)."""
        home = Path("/nonexistent_root/very/deep/.miner-harness")
        result = check_miner_home(home)
        assert result.status == CheckStatus.FAIL
        assert not result.passed


class TestRunAllChecks:
    def test_returns_system_report(self, tmp_path: Path) -> None:
        report = run_all_checks(
            miner_home=tmp_path / ".miner-harness",
            ollama_url="http://localhost:99999",
        )
        assert isinstance(report, SystemReport)
        assert len(report.results) == 4  # noqa: PLR2004

    def test_has_all_check_names(self, tmp_path: Path) -> None:
        report = run_all_checks(
            miner_home=tmp_path / ".miner-harness",
            ollama_url="http://localhost:99999",
        )
        names = {r.name for r in report.results}
        assert "python_version" in names
        assert "disk_space" in names
        assert "ollama" in names
        assert "miner_home" in names

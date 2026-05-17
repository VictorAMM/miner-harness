"""Tests for health checks.

Ref: Phase 9 — Observabilidade
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from miner_harness.observability.health import (
    CheckResult,
    HealthReport,
    HealthStatus,
    check_cache,
    check_disk_space,
    check_index,
    check_ollama,
    run_health_checks,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestCheckResult:
    """Test CheckResult and HealthReport dataclasses."""

    def test_healthy_report(self) -> None:
        report = HealthReport(
            checks=[
                CheckResult(name="a", status=HealthStatus.HEALTHY),
                CheckResult(name="b", status=HealthStatus.HEALTHY),
            ]
        )
        assert report.overall_status == HealthStatus.HEALTHY
        assert report.is_healthy

    def test_degraded_report(self) -> None:
        report = HealthReport(
            checks=[
                CheckResult(name="a", status=HealthStatus.HEALTHY),
                CheckResult(name="b", status=HealthStatus.DEGRADED),
            ]
        )
        assert report.overall_status == HealthStatus.DEGRADED
        assert not report.is_healthy

    def test_unhealthy_trumps_degraded(self) -> None:
        report = HealthReport(
            checks=[
                CheckResult(name="a", status=HealthStatus.DEGRADED),
                CheckResult(name="b", status=HealthStatus.UNHEALTHY),
            ]
        )
        assert report.overall_status == HealthStatus.UNHEALTHY

    def test_empty_report_is_unhealthy(self) -> None:
        report = HealthReport()
        assert report.overall_status == HealthStatus.UNHEALTHY

    def test_to_dict(self) -> None:
        report = HealthReport(
            checks=[
                CheckResult(name="test", status=HealthStatus.HEALTHY, message="OK"),
            ]
        )
        d = report.to_dict()
        assert d["overall"] == "healthy"
        assert len(d["checks"]) == 1
        assert d["checks"][0]["name"] == "test"


class TestCheckCache:
    """Test cache health check."""

    def test_no_db(self, tmp_path: Path) -> None:
        result = check_cache(tmp_path / "nonexistent")
        assert result.status == HealthStatus.DEGRADED

    def test_valid_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()
        result = check_cache(tmp_path)
        assert result.status == HealthStatus.HEALTHY
        assert "1 table" in result.message

    def test_corrupt_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        db_path.write_text("not a database")
        result = check_cache(tmp_path)
        assert result.status == HealthStatus.UNHEALTHY


class TestCheckIndex:
    """Test index health check."""

    def test_no_index(self, tmp_path: Path) -> None:
        result = check_index(tmp_path / "nonexistent")
        assert result.status == HealthStatus.DEGRADED

    def test_valid_index(self, tmp_path: Path) -> None:
        db_path = tmp_path / "documents.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE documents (id TEXT, source TEXT, text TEXT)")
        conn.execute("INSERT INTO documents VALUES ('1', 'test', 'hello')")
        conn.commit()
        conn.close()
        result = check_index(tmp_path)
        assert result.status == HealthStatus.HEALTHY
        assert "1 document" in result.message


class TestCheckDiskSpace:
    """Test disk space check."""

    def test_disk_space_check(self, tmp_path: Path) -> None:
        with patch("shutil.disk_usage") as mock_du:
            mock_du.return_value = MagicMock(free=50 * 1024**3, total=100 * 1024**3)
            result = check_disk_space(tmp_path)
        assert result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
        assert "free" in result.message or "Cannot" in result.message


class TestCheckOllama:
    """Test Ollama health check."""

    @pytest.mark.asyncio
    async def test_ollama_healthy(self) -> None:
        """Ollama reachable returns HEALTHY."""
        # Use a non-routable address to avoid real network calls,
        # but patch at a lower level
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen2.5:14b"}]}

        async def mock_get(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
            return mock_resp

        with patch("httpx.AsyncClient.get", new=mock_get):
            result = await check_ollama()
            assert result.status == HealthStatus.HEALTHY
            assert "1 model" in result.message

    @pytest.mark.asyncio
    async def test_ollama_unreachable(self) -> None:
        """Ollama unreachable returns UNHEALTHY."""
        import httpx

        async def mock_get(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
            raise httpx.ConnectError("refused")

        with patch("httpx.AsyncClient.get", new=mock_get):
            result = await check_ollama()
            assert result.status == HealthStatus.UNHEALTHY


class TestRunHealthChecks:
    """Test aggregated health checks."""

    @pytest.mark.asyncio
    async def test_run_all_checks(self, tmp_path: Path) -> None:
        with patch(
            "miner_harness.observability.health.check_ollama",
            return_value=CheckResult(name="ollama", status=HealthStatus.HEALTHY, message="OK"),
        ):
            report = await run_health_checks(tmp_path)
            assert len(report.checks) == 4
            names = [c.name for c in report.checks]
            assert "ollama" in names
            assert "cache" in names
            assert "index" in names
            assert "disk_space" in names

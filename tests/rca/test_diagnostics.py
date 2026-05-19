"""Tests for rca.diagnostics module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from miner_harness.rca.classifier import (
    ClassifiedError,
    ErrorCategory,
    ErrorSeverity,
)
from miner_harness.rca.diagnostics import (
    DiagnosticSnapshot,
    check_ollama_reachable,
    collect_cache_size,
    collect_diagnostics,
    collect_disk_info,
    collect_system_info,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestDiagnosticSnapshot:
    """Tests for DiagnosticSnapshot dataclass."""

    def test_to_dict(self) -> None:
        snap = DiagnosticSnapshot(
            disk_free_gb=50.5,
            disk_total_gb=500.0,
            python_version="3.11.9",
            platform_info="Linux-6.1",
        )
        d = snap.to_dict()
        assert d["disk_free_gb"] == 50.5
        assert d["disk_total_gb"] == 500.0
        assert d["python_version"] == "3.11.9"
        assert "timestamp" in d

    def test_recent_log_lines_truncated(self) -> None:
        snap = DiagnosticSnapshot(recent_log_lines=["line"] * 50)
        d = snap.to_dict()
        assert len(d["recent_log_lines"]) == 20  # noqa: PLR2004


class TestCollectDiskInfo:
    """Tests for collect_disk_info."""

    def test_returns_tuple(self) -> None:
        free, total = collect_disk_info()
        assert isinstance(free, float)
        assert isinstance(total, float)
        assert total > 0

    def test_oserror_returns_zeros(self) -> None:
        """OSError em disk_usage retorna (0.0, 0.0) (linhas 63-64)."""
        import shutil

        with patch.object(shutil, "disk_usage", side_effect=OSError("no disk")):
            free, total = collect_disk_info()
        assert free == 0.0
        assert total == 0.0


class TestCollectSystemInfo:
    """Tests for collect_system_info."""

    def test_returns_expected_keys(self) -> None:
        info = collect_system_info()
        assert "python_version" in info
        assert "platform" in info
        assert "machine" in info


class TestCheckOllamaReachable:
    """Tests for check_ollama_reachable."""

    @pytest.mark.asyncio
    async def test_reachable(self) -> None:
        mock_resp = type("Resp", (), {"status_code": 200})()

        async def mock_get(*args: object, **kwargs: object) -> object:
            return mock_resp

        with patch("httpx.AsyncClient.get", new=mock_get):
            result = await check_ollama_reachable()
        assert result is True

    @pytest.mark.asyncio
    async def test_unreachable(self) -> None:
        async def mock_get(*args: object, **kwargs: object) -> object:
            raise ConnectionError("refused")

        with patch("httpx.AsyncClient.get", new=mock_get):
            result = await check_ollama_reachable()
        assert result is False


class TestCollectCacheSize:
    """Tests for collect_cache_size."""

    def test_no_cache_returns_none(self, tmp_path: Path) -> None:
        result = collect_cache_size(tmp_path)
        assert result is None

    def test_default_dir_uses_miner_harness_home(self) -> None:
        """collect_cache_size() sem argumento usa ~/.miner-harness (linha 91)."""
        result = collect_cache_size()
        # Pode ser None (não existe) ou float (existe) — o importante é não levantar
        assert result is None or isinstance(result, float)

    def test_with_cache_file(self, tmp_path: Path) -> None:
        cache_db = tmp_path / "cache.db"
        cache_db.write_bytes(b"x" * 1024)
        result = collect_cache_size(tmp_path)
        assert result is not None
        assert result == pytest.approx(1024 / (1024 * 1024), rel=0.01)


class TestCollectDiagnostics:
    """Tests for collect_diagnostics."""

    @pytest.mark.asyncio
    async def test_network_error_checks_ollama(self) -> None:
        classified = ClassifiedError(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            error_type="ConnectError",
            message="refused",
        )

        async def mock_get(*args: object, **kwargs: object) -> object:
            raise ConnectionError("nope")

        with patch("httpx.AsyncClient.get", new=mock_get):
            snap = await collect_diagnostics(classified)

        assert snap.ollama_reachable is False
        assert snap.python_version != ""

    @pytest.mark.asyncio
    async def test_storage_error_checks_cache(self, tmp_path: Path) -> None:
        cache_db = tmp_path / "cache.db"
        cache_db.write_bytes(b"y" * 2048)

        classified = ClassifiedError(
            category=ErrorCategory.STORAGE,
            severity=ErrorSeverity.HIGH,
            error_type="OperationalError",
            message="disk full",
        )
        snap = await collect_diagnostics(classified, data_dir=tmp_path)
        assert snap.cache_size_mb is not None
        assert snap.ollama_reachable is None  # Not checked for storage errors

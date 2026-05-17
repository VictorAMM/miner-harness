"""Diagnostics module — automatic context collection on errors.

Collects system state and environmental context when errors occur
to support root cause analysis.

Ref: ASO v3 Phase 10 — RCA Autonomo
"""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone  # noqa: UP017
from pathlib import Path
from typing import Any

import structlog

from miner_harness.rca.classifier import ClassifiedError, ErrorCategory

logger = structlog.get_logger(__name__)


@dataclass
class DiagnosticSnapshot:
    """Snapshot of system state at time of error."""

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc),  # noqa: UP017
    )
    disk_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    python_version: str = ""
    platform_info: str = ""
    ollama_reachable: bool | None = None
    cache_size_mb: float | None = None
    recent_log_lines: list[str] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Export as dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "disk_free_gb": round(self.disk_free_gb, 2),
            "disk_total_gb": round(self.disk_total_gb, 2),
            "python_version": self.python_version,
            "platform_info": self.platform_info,
            "ollama_reachable": self.ollama_reachable,
            "cache_size_mb": self.cache_size_mb,
            "recent_log_lines": self.recent_log_lines[-20:],
            "environment": self.environment,
        }


def collect_disk_info() -> tuple[float, float]:
    """Collect disk usage information."""
    try:
        usage = shutil.disk_usage(Path.home())
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        return free_gb, total_gb
    except OSError:
        return 0.0, 0.0


def collect_system_info() -> dict[str, str]:
    """Collect basic system information."""
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


async def check_ollama_reachable() -> bool:
    """Check if Ollama server is reachable."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://127.0.0.1:11434/api/tags")
            return resp.status_code == 200  # noqa: PLR2004
    except Exception:  # noqa: BLE001
        return False


def collect_cache_size(data_dir: Path | None = None) -> float | None:
    """Get cache database size in MB."""
    if data_dir is None:
        data_dir = Path.home() / ".miner-harness"
    cache_db = data_dir / "cache.db"
    if cache_db.exists():
        return cache_db.stat().st_size / (1024 * 1024)
    return None


async def collect_diagnostics(
    classified: ClassifiedError,
    data_dir: Path | None = None,
) -> DiagnosticSnapshot:
    """Collect diagnostic snapshot relevant to the error category.

    Gathers system state proportional to error severity and category.

    Args:
        classified: The classified error to diagnose.
        data_dir: Optional data directory path.

    Returns:
        DiagnosticSnapshot with relevant context.
    """
    logger.info(
        "collecting_diagnostics",
        category=classified.category.value,
        severity=classified.severity.value,
    )

    free_gb, total_gb = collect_disk_info()
    sys_info = collect_system_info()

    snapshot = DiagnosticSnapshot(
        disk_free_gb=free_gb,
        disk_total_gb=total_gb,
        python_version=sys_info["python_version"],
        platform_info=sys_info["platform"],
        environment=classified.context,
    )

    # Category-specific diagnostics
    if classified.category == ErrorCategory.NETWORK:
        snapshot.ollama_reachable = await check_ollama_reachable()

    if classified.category in (ErrorCategory.STORAGE, ErrorCategory.CONFIG):
        snapshot.cache_size_mb = collect_cache_size(data_dir)

    return snapshot

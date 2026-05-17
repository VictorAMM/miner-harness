"""Health check infrastructure.

Verifies system dependencies are operational:
- Ollama server reachable and model available
- Cache database accessible
- Vector index intact

Ref: ASO v3 Phase 9 — Observabilidade
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path  # noqa: TCH003
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """Health check result status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class CheckResult:
    """Result of a single health check."""

    name: str
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthReport:
    """Aggregated health report."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def overall_status(self) -> HealthStatus:
        """Worst status across all checks."""
        if not self.checks:
            return HealthStatus.UNHEALTHY
        statuses = [c.status for c in self.checks]
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    @property
    def is_healthy(self) -> bool:
        return self.overall_status == HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        """Export as dictionary."""
        return {
            "overall": self.overall_status.value,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    **c.details,
                }
                for c in self.checks
            ],
        }


async def check_ollama(base_url: str = "http://localhost:11434") -> CheckResult:
    """Check if Ollama server is reachable."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                return CheckResult(
                    name="ollama",
                    status=HealthStatus.HEALTHY,
                    message=f"{len(models)} model(s) available",
                    details={"models": models},
                )
            return CheckResult(
                name="ollama",
                status=HealthStatus.DEGRADED,
                message=f"Unexpected status: {resp.status_code}",
            )
    except httpx.ConnectError:
        return CheckResult(
            name="ollama",
            status=HealthStatus.UNHEALTHY,
            message="Cannot connect to Ollama server",
            details={"url": base_url},
        )
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            name="ollama",
            status=HealthStatus.UNHEALTHY,
            message=f"Error: {e!s}",
        )


def check_cache(cache_dir: Path) -> CheckResult:
    """Check cache database accessibility."""
    db_path = cache_dir / "cache.db"
    if not db_path.exists():
        return CheckResult(
            name="cache",
            status=HealthStatus.DEGRADED,
            message="Cache database not found (will be created on first use)",
            details={"path": str(db_path)},
        )

    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        conn.close()
        return CheckResult(
            name="cache",
            status=HealthStatus.HEALTHY,
            message=f"Database accessible, {table_count} table(s)",
            details={"path": str(db_path), "tables": table_count},
        )
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            name="cache",
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {e!s}",
            details={"path": str(db_path)},
        )


def check_index(index_dir: Path) -> CheckResult:
    """Check vector index integrity."""
    db_path = index_dir / "documents.db"
    if not db_path.exists():
        return CheckResult(
            name="index",
            status=HealthStatus.DEGRADED,
            message="Index not found (will be created on first use)",
            details={"path": str(db_path)},
        )

    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM documents")
        doc_count = cursor.fetchone()[0]
        conn.close()
        return CheckResult(
            name="index",
            status=HealthStatus.HEALTHY,
            message=f"Index accessible, {doc_count} document(s)",
            details={"path": str(db_path), "documents": doc_count},
        )
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            name="index",
            status=HealthStatus.UNHEALTHY,
            message=f"Index error: {e!s}",
            details={"path": str(db_path)},
        )


def check_disk_space(miner_home: Path) -> CheckResult:
    """Check available disk space."""
    import shutil

    try:
        usage = shutil.disk_usage(str(miner_home.parent))
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        pct_free = (usage.free / usage.total) * 100

        if pct_free < 5:
            status = HealthStatus.UNHEALTHY
            msg = f"Critical: {free_gb:.1f}GB free ({pct_free:.0f}%)"
        elif pct_free < 15:
            status = HealthStatus.DEGRADED
            msg = f"Low: {free_gb:.1f}GB free ({pct_free:.0f}%)"
        else:
            status = HealthStatus.HEALTHY
            msg = f"{free_gb:.1f}GB free of {total_gb:.1f}GB ({pct_free:.0f}%)"

        return CheckResult(
            name="disk_space",
            status=status,
            message=msg,
            details={"free_gb": round(free_gb, 2), "total_gb": round(total_gb, 2)},
        )
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            name="disk_space",
            status=HealthStatus.DEGRADED,
            message=f"Cannot check: {e!s}",
        )


async def run_health_checks(
    miner_home: Path,
    ollama_url: str = "http://localhost:11434",
) -> HealthReport:
    """Run all health checks and return aggregated report."""
    report = HealthReport()

    ollama_result = await check_ollama(ollama_url)
    report.checks.append(ollama_result)

    cache_result = check_cache(miner_home / "cache")
    report.checks.append(cache_result)

    index_result = check_index(miner_home / "index")
    report.checks.append(index_result)

    disk_result = check_disk_space(miner_home)
    report.checks.append(disk_result)

    logger.info(
        "health_check_complete",
        overall=report.overall_status.value,
        checks={c.name: c.status.value for c in report.checks},
    )

    return report

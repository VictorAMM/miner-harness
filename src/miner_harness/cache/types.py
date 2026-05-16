"""Tipos do subsistema de cache.

Define CacheEntry, CacheStats e CoverageReport.

Ref: RFC-003 §3.1
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from miner_harness.core.types import BoundingBox  # noqa: TCH001


class CacheEntry(BaseModel):
    """Registro no cache SQLite."""

    service: str
    bbox_hash: str
    bbox: BoundingBox
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),  # noqa: UP017
    )
    ttl_days: int
    record_count: int
    extraction_method: str
    data: str  # JSON serializado das features


class CacheStats(BaseModel):
    """Estatísticas do cache."""

    total_entries: int = 0
    total_records: int = 0
    size_bytes: int = 0
    services: dict[str, int] = Field(default_factory=dict)
    oldest_entry: datetime | None = None
    newest_entry: datetime | None = None


class CoverageReport(BaseModel):
    """Relatório de cobertura de cache para uma região."""

    region: BoundingBox
    services_cached: dict[str, bool] = Field(default_factory=dict)
    services_fresh: dict[str, bool] = Field(default_factory=dict)
    total_features: int = 0
    indexed_features: int = 0
    can_run_offline: bool = False
    missing_services: list[str] = Field(default_factory=list)

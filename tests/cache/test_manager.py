"""Testes do CacheManager.

Ref: RFC-003 §3.4
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from miner_harness.cache.manager import CacheManager
from miner_harness.core.config import StorageConfig
from miner_harness.core.types import BoundingBox


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)


@pytest.fixture
def config(tmp_path: Path) -> StorageConfig:
    return StorageConfig(miner_home=tmp_path / ".miner-harness")


@pytest.fixture
def cache(config: StorageConfig) -> CacheManager:
    c = CacheManager(config)
    yield c
    c.close()


class TestCacheManager:
    """Testes do CacheManager facade."""

    def test_get_miss(self, cache: CacheManager, bbox: BoundingBox) -> None:
        assert cache.get("ocorrencias", bbox) is None

    def test_put_get_roundtrip(self, cache: CacheManager, bbox: BoundingBox) -> None:
        features = [{"objectid": 1, "substancias": "Cobre"}]
        cache.put("ocorrencias", bbox, features)
        result = cache.get("ocorrencias", bbox)
        assert result is not None
        assert len(result) == 1
        assert result[0]["substancias"] == "Cobre"

    def test_contains(self, cache: CacheManager, bbox: BoundingBox) -> None:
        assert not cache.contains("ocorrencias", bbox)
        cache.put("ocorrencias", bbox, [{"id": 1}])
        assert cache.contains("ocorrencias", bbox)

    def test_stats(self, cache: CacheManager, bbox: BoundingBox) -> None:
        cache.put("ocorrencias", bbox, [{"id": 1}, {"id": 2}])
        stats = cache.stats()
        assert stats.total_entries == 1
        assert stats.total_records == 2

    def test_clear(self, cache: CacheManager, bbox: BoundingBox) -> None:
        cache.put("ocorrencias", bbox, [{"id": 1}])
        removed = cache.clear()
        assert removed == 1
        assert cache.get("ocorrencias", bbox) is None


class TestCoverageReport:
    """Testes do CoverageReport."""

    def test_coverage_all_missing(self, cache: CacheManager, bbox: BoundingBox) -> None:
        report = cache.coverage_report(bbox)
        assert not report.can_run_offline
        assert len(report.missing_services) == 6
        assert report.total_features == 0

    def test_coverage_partial(self, cache: CacheManager, bbox: BoundingBox) -> None:
        cache.put("ocorrencias", bbox, [{"id": 1}])
        cache.put("gravimetria", bbox, [{"id": 2}])
        report = cache.coverage_report(bbox)
        assert not report.can_run_offline
        assert report.services_cached["ocorrencias"] is True
        assert report.services_cached["gravimetria"] is True
        assert "geoquimica" in report.missing_services
        assert report.total_features == 2

    def test_coverage_complete(self, cache: CacheManager, bbox: BoundingBox) -> None:
        """All 6 essential services cached -> can run offline."""
        services = [
            "ocorrencias", "gravimetria", "geoquimica",
            "geocronologia", "litoestratigrafia", "aerogeofisica",
        ]
        for svc in services:
            cache.put(svc, bbox, [{"id": 1}])
        report = cache.coverage_report(bbox)
        assert report.can_run_offline
        assert report.missing_services == []
        assert report.total_features == 6


class TestCacheManagerDirs:
    """Testes de criacao de diretorios."""

    def test_ensure_dirs_creates_structure(self, config: StorageConfig) -> None:
        """ensure_dirs() cria toda a arvore de diretorios."""
        config.ensure_dirs()
        assert config.cache_dir.exists()
        assert config.regions_dir.exists()
        assert config.index_dir.exists()
        assert config.exports_dir.exists()
        assert config.logs_dir.exists()

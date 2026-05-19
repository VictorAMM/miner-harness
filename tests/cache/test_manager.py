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
            "ocorrencias",
            "gravimetria",
            "geoquimica",
            "geocronologia",
            "litoestratigrafia",
            "aerogeofisica",
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


class TestCacheManagerExtraAPIs:
    """Cobre linhas não testadas: sqlite_store, evict_expired, context manager, auto-evict."""

    def test_sqlite_store_property(self, config: StorageConfig) -> None:
        """sqlite_store property retorna o SQLiteStore interno (linha 61)."""
        cache = CacheManager(config)
        try:
            assert cache.sqlite_store is not None
        finally:
            cache.close()

    def test_evict_expired_returns_int(self, cache: CacheManager) -> None:
        """evict_expired() retorna contagem de entradas removidas (linha 115)."""
        removed = cache.evict_expired()
        assert isinstance(removed, int)
        assert removed >= 0

    def test_context_manager(self, config: StorageConfig) -> None:
        """__enter__ e __exit__ funcionam corretamente (linhas 178, 181)."""
        with CacheManager(config) as cache:
            assert cache is not None

    def test_auto_evict_triggered_when_over_limit(
        self, config: StorageConfig, bbox: BoundingBox
    ) -> None:
        """Auto-evict é chamado quando size_bytes excede max (linhas 101-102)."""
        from unittest.mock import patch

        from miner_harness.cache.types import CacheStats

        cache = CacheManager(config)
        try:
            # Adiciona dado para que put() seja chamado
            oversized_stats = CacheStats(
                total_entries=1,
                total_records=1,
                size_bytes=int(10 * 1024**3),  # 10 GB > 5 GB default
            )
            with (
                patch.object(cache._sqlite, "stats", return_value=oversized_stats),
                patch.object(cache._sqlite, "evict_expired", return_value=1) as mock_evict,
            ):
                cache.put("ocorrencias", bbox, [{"id": 1}])
            mock_evict.assert_called_once()
        finally:
            cache.close()

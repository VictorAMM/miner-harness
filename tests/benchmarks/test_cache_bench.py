"""Cache read/write latency benchmarks."""

from __future__ import annotations

import time

from miner_harness.cache.manager import CacheManager  # noqa: TC001

from .conftest import BBOX_SMALL

_RECORDS = [{"objectid": i, "data": f"sample_{i}"} for i in range(100)]


class TestCacheLatency:
    def test_put_100_records_under_500ms(self, bench_cache: CacheManager) -> None:
        """Writing 100 records to cache should complete in under 500 ms."""
        t0 = time.perf_counter()
        bench_cache.put("ocorrencias", BBOX_SMALL, _RECORDS)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 500, f"Cache put too slow: {elapsed_ms:.1f}ms"

    def test_get_hits_under_50ms(self, bench_cache: CacheManager) -> None:
        """Cache hit should resolve in under 50 ms."""
        bench_cache.put("ocorrencias", BBOX_SMALL, _RECORDS)

        t0 = time.perf_counter()
        result = bench_cache.get("ocorrencias", BBOX_SMALL)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert result is not None
        assert elapsed_ms < 50, f"Cache get too slow: {elapsed_ms:.1f}ms"

    def test_cache_miss_under_50ms(self, bench_cache: CacheManager) -> None:
        """Cache miss check (no data) should also be fast."""
        from miner_harness.core.types import BoundingBox

        other_bbox = BoundingBox(lon_min=-60.0, lat_min=-10.0, lon_max=-58.0, lat_max=-8.0)
        t0 = time.perf_counter()
        result = bench_cache.get("ocorrencias", other_bbox)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert result is None
        assert elapsed_ms < 50, f"Cache miss too slow: {elapsed_ms:.1f}ms"

    def test_repeated_reads_consistent_latency(self, bench_cache: CacheManager) -> None:
        """Ten consecutive reads should each complete in under 50 ms."""
        bench_cache.put("geoquimica", BBOX_SMALL, _RECORDS)

        for _ in range(10):
            t0 = time.perf_counter()
            bench_cache.get("geoquimica", BBOX_SMALL)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert elapsed_ms < 50, f"Read iteration too slow: {elapsed_ms:.1f}ms"

    def test_stats_under_100ms(self, populated_cache: CacheManager) -> None:
        """cache.stats() with 6 populated services should complete in under 100 ms."""
        t0 = time.perf_counter()
        stats = populated_cache.stats()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert stats.total_entries >= 6
        assert elapsed_ms < 100, f"cache.stats() too slow: {elapsed_ms:.1f}ms"

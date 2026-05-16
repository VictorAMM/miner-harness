"""Cache — persistência local de dados GeoSGB em SQLite e GeoPackage.

Ref: RFC-003.
"""

from miner_harness.cache.manager import CacheManager
from miner_harness.cache.sqlite_store import SQLiteStore
from miner_harness.cache.ttl_policy import TTLPolicy
from miner_harness.cache.types import CacheEntry, CacheStats, CoverageReport

__all__ = [
    "CacheEntry",
    "CacheManager",
    "CacheStats",
    "CoverageReport",
    "SQLiteStore",
    "TTLPolicy",
]

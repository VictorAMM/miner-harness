"""Sentinel-2 connector via Copernicus Data Space Ecosystem (CDSE)."""

from miner_harness.connectors.sentinel2.connector import CopernicusConnector
from miner_harness.connectors.sentinel2.processor import (
    IndexStats,
    Sentinel2Indices,
    SentinelIndexProcessor,
)

__all__ = [
    "CopernicusConnector",
    "IndexStats",
    "Sentinel2Indices",
    "SentinelIndexProcessor",
]

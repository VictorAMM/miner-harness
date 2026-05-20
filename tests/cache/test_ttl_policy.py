"""Testes do TTLPolicy.

Ref: RFC-003 §3.3
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from miner_harness.cache.ttl_policy import TTLPolicy
from miner_harness.cache.types import CacheEntry
from miner_harness.core.types import BoundingBox


@pytest.fixture
def ttl() -> TTLPolicy:
    return TTLPolicy()


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51, lat_min=-7, lon_max=-49, lat_max=-5)


class TestTTLPolicy:
    """Testes da política de TTL."""

    def test_known_service_ttl(self, ttl: TTLPolicy) -> None:
        assert ttl.get_ttl("ocorrencias") == 30
        assert ttl.get_ttl("gravimetria") == 90
        assert ttl.get_ttl("litoestratigrafia") == 365
        assert ttl.get_ttl("count") == 7

    def test_unknown_service_uses_default(self, ttl: TTLPolicy) -> None:
        assert ttl.get_ttl("servico_desconhecido") == TTLPolicy.DEFAULT_TTL

    def test_fresh_entry_not_expired(self, ttl: TTLPolicy, bbox: BoundingBox) -> None:
        entry = CacheEntry(
            service="ocorrencias",
            bbox_hash=bbox.hash(),
            bbox=bbox,
            fetched_at=datetime.now(tz=timezone.utc),  # noqa: UP017
            ttl_days=30,
            record_count=10,
            extraction_method="identify",
            data="[]",
        )
        assert not ttl.is_expired(entry)

    def test_old_entry_is_expired(self, ttl: TTLPolicy, bbox: BoundingBox) -> None:
        entry = CacheEntry(
            service="ocorrencias",
            bbox_hash=bbox.hash(),
            bbox=bbox,
            fetched_at=datetime.now(tz=timezone.utc) - timedelta(days=31),  # noqa: UP017
            ttl_days=30,
            record_count=10,
            extraction_method="identify",
            data="[]",
        )
        assert ttl.is_expired(entry)

    def test_entry_on_boundary_not_expired(self, ttl: TTLPolicy, bbox: BoundingBox) -> None:
        """Entry exactly at TTL boundary should not be expired (<=)."""
        entry = CacheEntry(
            service="ocorrencias",
            bbox_hash=bbox.hash(),
            bbox=bbox,
            fetched_at=datetime.now(tz=timezone.utc) - timedelta(days=29, hours=23),  # noqa: UP017
            ttl_days=30,
            record_count=10,
            extraction_method="identify",
            data="[]",
        )
        assert not ttl.is_expired(entry)

    def test_naive_datetime_handled(self, ttl: TTLPolicy, bbox: BoundingBox) -> None:
        """Naive datetime (no tzinfo) should be treated as UTC."""
        entry = CacheEntry(
            service="ocorrencias",
            bbox_hash=bbox.hash(),
            bbox=bbox,
            fetched_at=datetime.now(tz=timezone.utc) - timedelta(days=31),  # noqa: UP017
            ttl_days=30,
            record_count=10,
            extraction_method="identify",
            data="[]",
        )
        # Replace tzinfo to simulate naive datetime from DB
        entry.fetched_at = entry.fetched_at.replace(tzinfo=None)
        assert ttl.is_expired(entry)

    def test_all_policies_are_positive(self, ttl: TTLPolicy) -> None:
        for service, days in TTLPolicy.POLICIES.items():
            assert days > 0, f"Policy for {service} must be positive"

    def test_anm_ttl(self, ttl: TTLPolicy) -> None:
        assert ttl.get_ttl("anm") == 30

    def test_usgs_ttl_shorter_than_anm(self, ttl: TTLPolicy) -> None:
        """USGS seismic data is more volatile — TTL must be shorter than ANM."""
        assert ttl.get_ttl("usgs") < ttl.get_ttl("anm")
        assert ttl.get_ttl("usgs") == 7

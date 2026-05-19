"""Testes do SQLiteStore.

Ref: RFC-003 §3.1, §9
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest

from miner_harness.cache.sqlite_store import SQLiteStore
from miner_harness.core.types import BoundingBox

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)


@pytest.fixture
def bbox2() -> BoundingBox:
    return BoundingBox(lon_min=-45.0, lat_min=-10.0, lon_max=-43.0, lat_max=-8.0)


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    s = SQLiteStore(tmp_path / "test_cache.db")
    yield s
    s.close()


@pytest.fixture
def sample_features() -> list[dict[str, object]]:
    return [
        {"objectid": 1, "substancias": "Cobre", "uf": "PA"},
        {"objectid": 2, "substancias": "Ouro", "uf": "PA"},
        {"objectid": 3, "substancias": "Ferro", "uf": "MG"},
    ]


class TestSQLiteStorePutGet:
    """Testes de put/get roundtrip."""

    def test_put_get_roundtrip(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
        sample_features: list[dict[str, object]],
    ) -> None:
        """Salva e recupera features sem perda de dados."""
        store.put("ocorrencias", bbox, sample_features)
        result = store.get("ocorrencias", bbox)
        assert result is not None
        assert len(result) == 3
        assert result[0]["substancias"] == "Cobre"
        assert result[2]["uf"] == "MG"

    def test_cache_miss_returns_none(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
    ) -> None:
        assert store.get("ocorrencias", bbox) is None

    def test_different_bbox_is_separate(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
        bbox2: BoundingBox,
        sample_features: list[dict[str, object]],
    ) -> None:
        store.put("ocorrencias", bbox, sample_features)
        assert store.get("ocorrencias", bbox) is not None
        assert store.get("ocorrencias", bbox2) is None

    def test_different_service_is_separate(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
        sample_features: list[dict[str, object]],
    ) -> None:
        store.put("ocorrencias", bbox, sample_features)
        assert store.get("ocorrencias", bbox) is not None
        assert store.get("gravimetria", bbox) is None

    def test_put_overwrites_existing(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
    ) -> None:
        store.put("ocorrencias", bbox, [{"id": 1}])
        store.put("ocorrencias", bbox, [{"id": 2}, {"id": 3}])
        result = store.get("ocorrencias", bbox)
        assert result is not None
        assert len(result) == 2

    def test_empty_features(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
    ) -> None:
        store.put("ocorrencias", bbox, [])
        result = store.get("ocorrencias", bbox)
        assert result is not None
        assert result == []


class TestSQLiteStoreTTL:
    """Testes de expiração TTL."""

    def test_ttl_expiration(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
        sample_features: list[dict[str, object]],
    ) -> None:
        """Entradas expiradas retornam None."""
        store.put("ocorrencias", bbox, sample_features)
        conn = store._get_conn()
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=31)).isoformat()  # noqa: UP017
        conn.execute(
            "UPDATE cache_entries SET fetched_at = ? WHERE service = ?",
            (old_date, "ocorrencias"),
        )
        conn.commit()
        assert store.get("ocorrencias", bbox) is None

    def test_fresh_entry_returned(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
        sample_features: list[dict[str, object]],
    ) -> None:
        store.put("ocorrencias", bbox, sample_features)
        result = store.get("ocorrencias", bbox)
        assert result is not None


class TestSQLiteStoreEviction:
    """Testes de evict_expired."""

    def test_evict_removes_expired(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
        bbox2: BoundingBox,
    ) -> None:
        """evict_expired() remove apenas entradas TTL expirado."""
        store.put("ocorrencias", bbox, [{"id": 1}])
        store.put("gravimetria", bbox2, [{"id": 2}])

        conn = store._get_conn()
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=31)).isoformat()  # noqa: UP017
        conn.execute(
            "UPDATE cache_entries SET fetched_at = ? WHERE service = ?",
            (old_date, "ocorrencias"),
        )
        conn.commit()

        evicted = store.evict_expired()
        assert evicted == 1
        assert store.get("gravimetria", bbox2) is not None

    def test_evict_returns_zero_when_nothing_expired(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
    ) -> None:
        store.put("ocorrencias", bbox, [{"id": 1}])
        assert store.evict_expired() == 0


class TestSQLiteStoreStats:
    """Testes de stats."""

    def test_stats_empty(self, store: SQLiteStore) -> None:
        stats = store.stats()
        assert stats.total_entries == 0
        assert stats.total_records == 0
        assert stats.services == {}

    def test_stats_with_data(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
        bbox2: BoundingBox,
    ) -> None:
        store.put("ocorrencias", bbox, [{"id": 1}, {"id": 2}])
        store.put("gravimetria", bbox2, [{"id": 3}])
        stats = store.stats()
        assert stats.total_entries == 2
        assert stats.total_records == 3
        assert stats.services["ocorrencias"] == 1
        assert stats.services["gravimetria"] == 1
        assert stats.size_bytes > 0
        assert stats.oldest_entry is not None
        assert stats.newest_entry is not None


class TestSQLiteStoreContains:
    """Testes de contains."""

    def test_contains_fresh(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
    ) -> None:
        store.put("ocorrencias", bbox, [{"id": 1}])
        assert store.contains("ocorrencias", bbox)

    def test_contains_expired(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
    ) -> None:
        store.put("ocorrencias", bbox, [{"id": 1}])
        conn = store._get_conn()
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=31)).isoformat()  # noqa: UP017
        conn.execute(
            "UPDATE cache_entries SET fetched_at = ? WHERE service = ?",
            (old_date, "ocorrencias"),
        )
        conn.commit()
        assert not store.contains("ocorrencias", bbox)

    def test_not_contains_missing(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
    ) -> None:
        assert not store.contains("ocorrencias", bbox)


class TestSQLiteStoreClear:
    """Testes de clear."""

    def test_clear(
        self,
        store: SQLiteStore,
        bbox: BoundingBox,
    ) -> None:
        store.put("ocorrencias", bbox, [{"id": 1}])
        store.put("gravimetria", bbox, [{"id": 2}])
        removed = store.clear()
        assert removed == 2
        assert store.stats().total_entries == 0


class TestBBoxHash:
    """Testes de hash determinístico do BoundingBox."""

    def test_bbox_hash_deterministic(self) -> None:
        bbox1 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        bbox2 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        assert bbox1.hash() == bbox2.hash()

    def test_bbox_hash_invariant_to_precision(self) -> None:
        bbox1 = BoundingBox(lon_min=-51.500, lat_min=-7.000, lon_max=-49.500, lat_max=-5.000)
        bbox2 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        assert bbox1.hash() == bbox2.hash()

    def test_different_bbox_different_hash(self) -> None:
        bbox1 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        bbox2 = BoundingBox(lon_min=-45.0, lat_min=-10.0, lon_max=-43.0, lat_max=-8.0)
        assert bbox1.hash() != bbox2.hash()


class TestSQLiteStoreDbPath:
    """Cobre a property db_path (linha 84)."""

    def test_db_path_property(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        assert store.db_path == db_path
        store.close()


class TestSQLiteStoreSchemaVersion:
    """Cobre CacheCorruptedError quando versão do schema diverge (linha 120)."""

    def test_schema_mismatch_raises(self, tmp_path: Path) -> None:
        import sqlite3

        from miner_harness.core.exceptions import CacheCorruptedError

        db_path = tmp_path / "old.db"
        # Criar DB com schema_version errada
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_meta (key, value) VALUES ('schema_version', '999')")
        conn.commit()
        conn.close()

        with pytest.raises(CacheCorruptedError):
            SQLiteStore(db_path)


class TestSQLiteStoreOversized:
    """Cobre log de aviso para features oversized (linha 197)."""

    def test_oversized_feature_does_not_raise(self, store: SQLiteStore, bbox: BoundingBox) -> None:
        """Feature acima de MAX_SINGLE_FEATURE_KB loga aviso mas não levanta exceção."""
        # MAX_SINGLE_FEATURE_KB=100, len(features)=1 → need size_kb > 100
        big_value = "x" * (105 * 1024)  # 105 KB de string
        store.put("ocorrencias", bbox, [{"big": big_value}])
        result = store.get("ocorrencias", bbox)
        assert result is not None


class TestSQLiteStoreNaiveDatetime:
    """Cobre branches de fallback para datetime sem tzinfo (linhas 338, 387)."""

    def test_is_fresh_with_naive_datetime(self, store: SQLiteStore, bbox: BoundingBox) -> None:
        """Entrada com datetime sem tzinfo ainda é tratada como fresca."""
        store.put("ocorrencias", bbox, [{"id": 1}])
        conn = store._get_conn()
        # Substituir fetched_at por datetime naive (sem timezone)
        from datetime import datetime

        naive_now = datetime.utcnow().isoformat()  # noqa: DTZ003
        conn.execute(
            "UPDATE cache_entries SET fetched_at = ? WHERE service = ?",
            (naive_now, "ocorrencias"),
        )
        conn.commit()
        # is_fresh deve tratar tzinfo=None adicionando UTC
        assert store.contains("ocorrencias", bbox)

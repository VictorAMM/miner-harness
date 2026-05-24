"""Testes de DrillholeStore — persistência SQLite de furos do usuário."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from miner_harness.ingestion.drillhole_store import DrillholeStore

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> DrillholeStore:
    miner_home = tmp_path / ".miner-harness"
    return DrillholeStore(miner_home)


def _make_record(
    hole_id: str = "DH-001",
    x: float | None = -51.0,
    y: float | None = -6.5,
    **kwargs: object,
) -> dict:
    return {
        "hole_id": hole_id,
        "x": x,
        "y": y,
        "z": 400.0,
        "from_m": 0.0,
        "to_m": 5.0,
        "lithology": "Granito",
        "alteration": "propilítica",
        **kwargs,
    }


# ---------------------------------------------------------------------------
# TestDbPath
# ---------------------------------------------------------------------------


class TestDbPath:
    def test_db_path_inside_miner_home(self, tmp_path: Path) -> None:
        miner_home = tmp_path / ".miner-harness"
        store = DrillholeStore(miner_home)
        try:
            assert store.db_path == miner_home / "drillholes.db"
            assert store.db_path.exists()
        finally:
            store.close()

    def test_creates_miner_home_if_missing(self, tmp_path: Path) -> None:
        miner_home = tmp_path / "deep" / "nested" / ".miner"
        assert not miner_home.exists()
        store = DrillholeStore(miner_home)
        try:
            assert miner_home.exists()
        finally:
            store.close()


# ---------------------------------------------------------------------------
# TestInsertAndQuery
# ---------------------------------------------------------------------------


class TestInsertAndQuery:
    def test_insert_batch_returns_count(self, store: DrillholeStore) -> None:
        records = [_make_record("A"), _make_record("B")]
        n = store.insert_batch(records)
        assert n == 2
        store.close()

    def test_query_all_returns_inserted_records(self, store: DrillholeStore) -> None:
        store.insert_batch([_make_record("DH-001")])
        rows = store.query_all()
        assert len(rows) == 1
        assert rows[0]["hole_id"] == "DH-001"
        store.close()

    def test_canonical_fields_preserved(self, store: DrillholeStore) -> None:
        rec = _make_record("DH-X", x=-50.5, y=-7.0)
        store.insert_batch([rec])
        row = store.query_all()[0]
        assert row["x"] == pytest.approx(-50.5)
        assert row["y"] == pytest.approx(-7.0)
        assert row["z"] == pytest.approx(400.0)
        assert row["from_m"] == pytest.approx(0.0)
        assert row["to_m"] == pytest.approx(5.0)
        assert row["lithology"] == "Granito"
        assert row["alteration"] == "propilítica"
        store.close()

    def test_extra_fields_preserved_via_json(self, store: DrillholeStore) -> None:
        rec = _make_record("DH-AU", au=1.23, cu_ppm=45.0)
        store.insert_batch([rec])
        row = store.query_all()[0]
        assert row["au"] == pytest.approx(1.23)
        assert row["cu_ppm"] == pytest.approx(45.0)
        store.close()

    def test_insert_empty_batch(self, store: DrillholeStore) -> None:
        n = store.insert_batch([])
        assert n == 0
        assert store.count() == 0
        store.close()

    def test_null_coords_preserved(self, store: DrillholeStore) -> None:
        rec = _make_record("DH-NULL", x=None, y=None, z=None)
        store.insert_batch([rec])
        row = store.query_all()[0]
        assert row["x"] is None
        assert row["y"] is None
        store.close()

    def test_multiple_batches_accumulate(self, store: DrillholeStore) -> None:
        store.insert_batch([_make_record("A")])
        store.insert_batch([_make_record("B"), _make_record("C")])
        assert store.count() == 3
        store.close()

    def test_order_preserved(self, store: DrillholeStore) -> None:
        ids = ["DH-03", "DH-01", "DH-02"]
        store.insert_batch([_make_record(i) for i in ids])
        rows = store.query_all()
        assert [r["hole_id"] for r in rows] == ids
        store.close()


# ---------------------------------------------------------------------------
# TestCount
# ---------------------------------------------------------------------------


class TestCount:
    def test_count_empty_store(self, store: DrillholeStore) -> None:
        assert store.count() == 0
        store.close()

    def test_count_after_insert(self, store: DrillholeStore) -> None:
        store.insert_batch([_make_record() for _ in range(7)])
        assert store.count() == 7
        store.close()


# ---------------------------------------------------------------------------
# TestClear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_all_records(self, store: DrillholeStore) -> None:
        store.insert_batch([_make_record("A"), _make_record("B")])
        store.clear()
        assert store.count() == 0
        store.close()

    def test_clear_returns_previous_count(self, store: DrillholeStore) -> None:
        store.insert_batch([_make_record() for _ in range(5)])
        removed = store.clear()
        assert removed == 5
        store.close()

    def test_clear_empty_store_returns_zero(self, store: DrillholeStore) -> None:
        assert store.clear() == 0
        store.close()

    def test_insert_after_clear(self, store: DrillholeStore) -> None:
        store.insert_batch([_make_record("A")])
        store.clear()
        store.insert_batch([_make_record("B")])
        rows = store.query_all()
        assert len(rows) == 1
        assert rows[0]["hole_id"] == "B"
        store.close()


# ---------------------------------------------------------------------------
# TestContextManager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_context_manager_closes_connection(self, tmp_path: Path) -> None:
        miner_home = tmp_path / ".miner-harness"
        with DrillholeStore(miner_home) as store:
            store.insert_batch([_make_record()])
            rows = store.query_all()
        assert len(rows) == 1

    def test_data_persists_after_reopen(self, tmp_path: Path) -> None:
        miner_home = tmp_path / ".miner-harness"
        with DrillholeStore(miner_home) as s:
            s.insert_batch([_make_record("PERSIST")])
        with DrillholeStore(miner_home) as s:
            rows = s.query_all()
        assert rows[0]["hole_id"] == "PERSIST"

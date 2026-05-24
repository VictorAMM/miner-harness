"""DrillholeStore — armazenamento persistente de furos de sondagem do usuário.

Persiste furos em SQLite local (miner_home/drillholes.db) para uso
em múltiplas análises sem reimportar o CSV toda vez.

Schema: campos canônicos como colunas nomeadas + JSON para extras analíticos.
Queries 100% parametrizadas (RFC-003 §8.2).

Ref: PRD-002 F7
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drillholes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    hole_id    TEXT    NOT NULL DEFAULT '',
    x          REAL,
    y          REAL,
    z          REAL,
    from_m     REAL,
    to_m       REAL,
    lithology  TEXT    NOT NULL DEFAULT '',
    alteration TEXT    NOT NULL DEFAULT '',
    extra_json TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_dh_hole_id ON drillholes(hole_id);
"""

_CANONICAL_FIELDS: frozenset[str] = frozenset(
    {"hole_id", "x", "y", "z", "from_m", "to_m", "lithology", "alteration"}
)


class DrillholeStore:
    """SQLite store para furos de sondagem do usuário.

    Persiste em ~/.miner-harness/drillholes.db.

    Usage:
        store = DrillholeStore(storage.miner_home)
        n = store.insert_batch(records)
        all_records = store.query_all()
        store.close()

    Context manager:
        with DrillholeStore(miner_home) as store:
            store.insert_batch(records)
    """

    def __init__(self, miner_home: Path) -> None:
        miner_home.mkdir(parents=True, exist_ok=True)
        self._db_path: Path = miner_home / "drillholes.db"
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def db_path(self) -> Path:
        """Caminho do arquivo SQLite."""
        return self._db_path

    def insert_batch(self, records: list[dict[str, Any]]) -> int:
        """Insere múltiplos registros.

        Args:
            records: Lista de dicts com chaves padronizadas (saída do DrillholeParser).

        Returns:
            Número de linhas inseridas.
        """
        if not records:
            return 0

        rows: list[tuple[Any, ...]] = []
        for r in records:
            extras = {k: v for k, v in r.items() if k not in _CANONICAL_FIELDS}
            rows.append(
                (
                    r.get("hole_id") or "",
                    r.get("x"),
                    r.get("y"),
                    r.get("z"),
                    r.get("from_m"),
                    r.get("to_m"),
                    r.get("lithology") or "",
                    r.get("alteration") or "",
                    json.dumps(extras, ensure_ascii=False),
                )
            )

        self._conn.executemany(
            """
            INSERT INTO drillholes
                (hole_id, x, y, z, from_m, to_m, lithology, alteration, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()
        logger.info("drillhole_store_insert", n_records=len(rows), db=str(self._db_path))
        return len(rows)

    def query_all(self) -> list[dict[str, Any]]:
        """Retorna todos os furos como lista de dicts."""
        cursor = self._conn.execute(
            "SELECT hole_id, x, y, z, from_m, to_m, lithology, alteration, extra_json "
            "FROM drillholes ORDER BY id"
        )
        result: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            rec: dict[str, Any] = {
                "hole_id": row["hole_id"],
                "x": row["x"],
                "y": row["y"],
                "z": row["z"],
                "from_m": row["from_m"],
                "to_m": row["to_m"],
                "lithology": row["lithology"],
                "alteration": row["alteration"],
            }
            extras: dict[str, Any] = json.loads(row["extra_json"])
            rec.update(extras)
            result.append(rec)
        return result

    def count(self) -> int:
        """Retorna o número total de registros armazenados."""
        row = self._conn.execute("SELECT COUNT(*) FROM drillholes").fetchone()
        return int(row[0])

    def clear(self) -> int:
        """Remove todos os registros.

        Returns:
            Número de linhas removidas.
        """
        n = self.count()
        self._conn.execute("DELETE FROM drillholes")
        self._conn.commit()
        logger.info("drillhole_store_cleared", removed=n, db=str(self._db_path))
        return n

    def close(self) -> None:
        """Fecha a conexão SQLite."""
        self._conn.close()

    def __enter__(self) -> DrillholeStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

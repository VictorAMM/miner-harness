"""SQLiteStore — cache de features GeoSGB em SQLite.

Armazena features pontuais como JSON serializado, junto com
metadados de quando e como os dados foram coletados.
Queries 100% parametrizadas (RFC-003 §8.2).

Ref: RFC-003 §3.1
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timezone
from typing import TYPE_CHECKING, Any

import structlog

from miner_harness.cache.ttl_policy import TTLPolicy
from miner_harness.cache.types import CacheEntry, CacheStats
from miner_harness.core.exceptions import CacheCorruptedError
from miner_harness.core.types import BoundingBox

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# Limites de segurança (RFC-003 §8.4)
MAX_SINGLE_FEATURE_KB = 100
MAX_CACHE_ENTRIES_PER_SERVICE = 50

_SCHEMA_VERSION = 1

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cache_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    bbox_hash TEXT NOT NULL,
    bbox_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    ttl_days INTEGER NOT NULL,
    record_count INTEGER NOT NULL,
    extraction_method TEXT NOT NULL,
    data TEXT NOT NULL,
    UNIQUE(service, bbox_hash)
);
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cache_service_bbox
ON cache_entries(service, bbox_hash);
"""


class SQLiteStore:
    """Cache de features GeoSGB em SQLite.

    Thread-safe via sqlite3 check_same_thread=False.
    Todas as queries são parametrizadas.

    Usage:
        store = SQLiteStore(Path("~/.miner-harness/cache/geosgb.db"))
        store.put("ocorrencias", bbox, features, "identify")
        cached = store.get("ocorrencias", bbox)
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ttl = TTLPolicy()
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        """Caminho do banco SQLite."""
        return self._db_path

    def _get_conn(self) -> sqlite3.Connection:
        """Retorna conexão SQLite (lazy init)."""
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            # WAL mode para melhor concorrência
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_schema(self) -> None:
        """Cria tabelas se não existirem. Verifica versão do schema."""
        conn = self._get_conn()
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_META)
        conn.execute(_CREATE_INDEX)

        # Verificar/setar versão do schema
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = ?",
            ("schema_version",),
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES (?, ?)",
                ("schema_version", str(_SCHEMA_VERSION)),
            )
            conn.commit()
        elif int(row["value"]) != _SCHEMA_VERSION:
            raise CacheCorruptedError(
                f"Schema version mismatch: expected {_SCHEMA_VERSION}, "
                f"got {row['value']}. Delete the cache DB and retry."
            )

    def get(
        self,
        service: str,
        bbox: BoundingBox,
    ) -> list[dict[str, Any]] | None:
        """Retorna features cacheadas se existirem e estiverem frescas.

        Args:
            service: Nome do serviço (ex: "ocorrencias").
            bbox: Bounding box da consulta.

        Returns:
            Lista de features ou None se cache miss/TTL expirado.
        """
        bbox_hash = bbox.hash()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM cache_entries WHERE service = ? AND bbox_hash = ?",
            (service, bbox_hash),
        ).fetchone()

        if row is None:
            logger.info(
                "cache_miss",
                service=service,
                bbox_hash=bbox_hash,
                reason="not_found",
            )
            return None

        entry = self._row_to_entry(row)

        if self._ttl.is_expired(entry):
            logger.info(
                "cache_miss",
                service=service,
                bbox_hash=bbox_hash,
                reason="ttl_expired",
                age_days=self._age_days(entry),
            )
            return None

        features: list[dict[str, Any]] = json.loads(entry.data)
        logger.info(
            "cache_hit",
            service=service,
            bbox_hash=bbox_hash,
            records=entry.record_count,
            age_days=self._age_days(entry),
        )
        return features

    def put(
        self,
        service: str,
        bbox: BoundingBox,
        features: list[dict[str, Any]],
        method: str = "identify",
    ) -> None:
        """Salva features no cache com timestamp.

        Args:
            service: Nome do serviço.
            bbox: Bounding box da consulta.
            features: Features a cachear.
            method: Método de extração ("identify", "query", "shapefile").
        """
        data_json = json.dumps(features, ensure_ascii=False, default=str)

        # Verificar limite de tamanho (RFC-003 §8.4)
        size_kb = len(data_json.encode()) / 1024
        if size_kb > MAX_SINGLE_FEATURE_KB * len(features) and len(features) > 0:
            logger.warning(
                "cache_put_oversized",
                service=service,
                size_kb=round(size_kb, 1),
                records=len(features),
            )

        bbox_hash = bbox.hash()
        ttl_days = self._ttl.get_ttl(service)
        bbox_json = bbox.model_dump_json()

        from datetime import datetime

        now = datetime.now(tz=timezone.utc).isoformat()  # noqa: UP017

        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO cache_entries
            (service, bbox_hash, bbox_json, fetched_at, ttl_days,
             record_count, extraction_method, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service,
                bbox_hash,
                bbox_json,
                now,
                ttl_days,
                len(features),
                method,
                data_json,
            ),
        )
        conn.commit()

        logger.info(
            "cache_put",
            service=service,
            bbox_hash=bbox_hash,
            records=len(features),
            ttl_days=ttl_days,
            method=method,
        )

    def evict_expired(self) -> int:
        """Remove entradas com TTL expirado.

        Returns:
            Número de entradas removidas.
        """
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM cache_entries").fetchall()

        expired_ids: list[int] = []
        for row in rows:
            entry = self._row_to_entry(row)
            if self._ttl.is_expired(entry):
                expired_ids.append(row["id"])

        if expired_ids:
            placeholders = ",".join("?" for _ in expired_ids)
            conn.execute(
                f"DELETE FROM cache_entries WHERE id IN ({placeholders})",  # noqa: S608  # nosec B608
                expired_ids,
            )
            conn.commit()

        if expired_ids:
            logger.info(
                "cache_eviction",
                evicted=len(expired_ids),
            )
        return len(expired_ids)

    def stats(self) -> CacheStats:
        """Estatísticas do cache."""
        conn = self._get_conn()

        total = conn.execute("SELECT COUNT(*) as cnt FROM cache_entries").fetchone()
        total_entries = total["cnt"] if total else 0

        records_sum = conn.execute(
            "SELECT COALESCE(SUM(record_count), 0) as s FROM cache_entries"
        ).fetchone()
        total_records = records_sum["s"] if records_sum else 0

        # Tamanho dos dados
        size_row = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(data)), 0) as s FROM cache_entries"
        ).fetchone()
        size_bytes = size_row["s"] if size_row else 0

        # Contagem por serviço
        services: dict[str, int] = {}
        for row in conn.execute(
            "SELECT service, COUNT(*) as cnt FROM cache_entries GROUP BY service"
        ):
            services[row["service"]] = row["cnt"]

        # Datas extremas
        oldest_row = conn.execute("SELECT MIN(fetched_at) as d FROM cache_entries").fetchone()
        newest_row = conn.execute("SELECT MAX(fetched_at) as d FROM cache_entries").fetchone()

        from datetime import datetime

        oldest = None
        newest = None
        if oldest_row and oldest_row["d"]:
            oldest = datetime.fromisoformat(oldest_row["d"])
        if newest_row and newest_row["d"]:
            newest = datetime.fromisoformat(newest_row["d"])

        return CacheStats(
            total_entries=total_entries,
            total_records=total_records,
            size_bytes=size_bytes,
            services=services,
            oldest_entry=oldest,
            newest_entry=newest,
        )

    def contains(self, service: str, bbox: BoundingBox) -> bool:
        """Verifica se bbox está coberto no cache (sem carregar dados).

        Retorna True apenas se existe E está fresco.
        """
        bbox_hash = bbox.hash()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT fetched_at, ttl_days FROM cache_entries WHERE service = ? AND bbox_hash = ?",
            (service, bbox_hash),
        ).fetchone()

        if row is None:
            return False

        from datetime import datetime, timedelta

        fetched = datetime.fromisoformat(row["fetched_at"])
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)  # noqa: UP017
        expiry = fetched + timedelta(days=row["ttl_days"])
        return datetime.now(tz=timezone.utc) <= expiry  # noqa: UP017

    def clear(self) -> int:
        """Remove todas as entradas. Retorna contagem removida."""
        conn = self._get_conn()
        count = conn.execute("SELECT COUNT(*) as cnt FROM cache_entries").fetchone()
        removed = count["cnt"] if count else 0
        conn.execute("DELETE FROM cache_entries")
        conn.commit()
        return removed

    def close(self) -> None:
        """Fecha a conexão SQLite."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> CacheEntry:
        """Converte row do SQLite para CacheEntry."""
        from datetime import datetime

        bbox = BoundingBox.model_validate_json(row["bbox_json"])
        fetched = datetime.fromisoformat(row["fetched_at"])
        return CacheEntry(
            service=row["service"],
            bbox_hash=row["bbox_hash"],
            bbox=bbox,
            fetched_at=fetched,
            ttl_days=row["ttl_days"],
            record_count=row["record_count"],
            extraction_method=row["extraction_method"],
            data=row["data"],
        )

    @staticmethod
    def _age_days(entry: CacheEntry) -> float:
        """Calcula idade da entrada em dias."""
        from datetime import datetime

        now = datetime.now(tz=timezone.utc)  # noqa: UP017
        fetched = entry.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)  # noqa: UP017
        return round((now - fetched).total_seconds() / 86400, 2)

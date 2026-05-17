"""DocumentStore — armazena e indexa documentos com embeddings.

Gerencia o ciclo de vida de documentos indexados:
inserção, busca por ID, e integração com o SearchEngine.

O storage usa SQLite puro para metadados e sqlite-vec para vetores.
Quando sqlite-vec não está disponível, opera em modo degradado
(busca por força bruta com cosine similarity em Python).

Ref: RFC-003 §4.4
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

import structlog

from miner_harness.index.types import IndexDocument

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# Limites de segurança (RFC-003 §8.4)
MAX_INDEX_BATCH = 1000

_METADATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    bbox_json TEXT,
    embedding_json TEXT
);
"""

_METADATA_INDEX = """
CREATE INDEX IF NOT EXISTS idx_docs_source ON documents(source);
"""


class DocumentStore:
    """Armazena documentos indexados com embeddings.

    Usa SQLite para metadados e embeddings serializados como JSON.
    A busca vetorial é delegada ao SearchEngine.

    Usage:
        store = DocumentStore(Path("~/.miner-harness/index"))
        store.add(document)
        doc = store.get("geosgb/ocorrencias:12345")
        docs = store.get_by_source("geosgb/ocorrencias")
    """

    def __init__(self, index_dir: Path) -> None:
        self._index_dir = index_dir
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = index_dir / "metadata.db"
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Retorna conexão SQLite (lazy init)."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_schema(self) -> None:
        """Cria tabelas se não existirem."""
        conn = self._get_conn()
        conn.execute(_METADATA_SCHEMA)
        conn.execute(_METADATA_INDEX)
        conn.commit()

    def add(self, document: IndexDocument) -> None:
        """Adiciona ou atualiza documento no store.

        Args:
            document: Documento com embedding preenchido.
        """
        conn = self._get_conn()
        metadata_json = json.dumps(document.metadata, ensure_ascii=False, default=str)
        bbox_json = document.bbox.model_dump_json() if document.bbox else None
        embedding_json = json.dumps(document.embedding) if document.embedding else None

        conn.execute(
            """
            INSERT OR REPLACE INTO documents
            (id, source, text, metadata_json, bbox_json, embedding_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document.id,
                document.source,
                document.text,
                metadata_json,
                bbox_json,
                embedding_json,
            ),
        )
        conn.commit()

    def add_batch(self, documents: list[IndexDocument]) -> int:
        """Adiciona múltiplos documentos em batch.

        Args:
            documents: Lista de documentos.

        Returns:
            Número de documentos adicionados.

        Raises:
            ValueError: Se batch exceder MAX_INDEX_BATCH.
        """
        if len(documents) > MAX_INDEX_BATCH:
            msg = f"Batch size {len(documents)} exceeds limit {MAX_INDEX_BATCH}"
            raise ValueError(msg)

        conn = self._get_conn()
        rows = []
        for doc in documents:
            metadata_json = json.dumps(doc.metadata, ensure_ascii=False, default=str)
            bbox_json = doc.bbox.model_dump_json() if doc.bbox else None
            embedding_json = json.dumps(doc.embedding) if doc.embedding else None
            rows.append(
                (
                    doc.id,
                    doc.source,
                    doc.text,
                    metadata_json,
                    bbox_json,
                    embedding_json,
                )
            )

        conn.executemany(
            """
            INSERT OR REPLACE INTO documents
            (id, source, text, metadata_json, bbox_json, embedding_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

        logger.info("index_batch_add", documents=len(documents))
        return len(documents)

    def get(self, doc_id: str) -> IndexDocument | None:
        """Busca documento por ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()

        if row is None:
            return None
        return self._row_to_document(row)

    def get_by_source(
        self,
        source: str,
        limit: int = 100,
    ) -> list[IndexDocument]:
        """Busca documentos por fonte.

        Args:
            source: Filtro de fonte (ex: "geosgb/ocorrencias").
            limit: Máximo de resultados.

        Returns:
            Lista de documentos.
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM documents WHERE source = ? LIMIT ?",
            (source, limit),
        ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def count(self, source: str | None = None) -> int:
        """Conta documentos, opcionalmente filtrado por fonte."""
        conn = self._get_conn()
        if source:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM documents WHERE source = ?",
                (source,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()
        return row["cnt"] if row else 0

    def get_all_with_embeddings(self) -> list[IndexDocument]:
        """Retorna todos os documentos que têm embedding.

        Usado pelo SearchEngine para busca por força bruta.
        """
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM documents WHERE embedding_json IS NOT NULL").fetchall()
        return [self._row_to_document(row) for row in rows]

    def delete(self, doc_id: str) -> bool:
        """Remove documento por ID. Retorna True se existia."""
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM documents WHERE id = ?",
            (doc_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def clear(self) -> int:
        """Remove todos os documentos. Retorna contagem."""
        conn = self._get_conn()
        count = self.count()
        conn.execute("DELETE FROM documents")
        conn.commit()
        return count

    def close(self) -> None:
        """Fecha a conexão SQLite."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> IndexDocument:
        """Converte row SQLite para IndexDocument."""
        from miner_harness.core.types import BoundingBox

        metadata: dict[str, Any] = json.loads(row["metadata_json"])
        bbox = BoundingBox.model_validate_json(row["bbox_json"]) if row["bbox_json"] else None
        embedding: list[float] | None = (
            json.loads(row["embedding_json"]) if row["embedding_json"] else None
        )

        return IndexDocument(
            id=row["id"],
            source=row["source"],
            text=row["text"],
            metadata=metadata,
            bbox=bbox,
            embedding=embedding,
        )

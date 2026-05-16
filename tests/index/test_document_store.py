"""Testes do DocumentStore.

Ref: RFC-003 §4.4
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from miner_harness.core.types import BoundingBox
from miner_harness.index.document_store import DocumentStore
from miner_harness.index.types import IndexDocument


@pytest.fixture
def store(tmp_path: Path) -> DocumentStore:
    s = DocumentStore(tmp_path / "index")
    yield s
    s.close()


@pytest.fixture
def sample_doc() -> IndexDocument:
    return IndexDocument(
        id="geosgb/ocorrencias:1",
        source="geosgb/ocorrencias",
        text="Ocorrencia mineral em Parauapebas, PA. Substancias: Cobre, Ouro.",
        metadata={"substancias": "Cobre, Ouro", "uf": "PA"},
        bbox=BoundingBox(lon_min=-51, lat_min=-7, lon_max=-49, lat_max=-5),
        embedding=[0.1] * 768,
    )


class TestDocumentStoreAddGet:
    """Testes de add/get."""

    def test_add_get_roundtrip(
        self, store: DocumentStore, sample_doc: IndexDocument
    ) -> None:
        store.add(sample_doc)
        retrieved = store.get(sample_doc.id)
        assert retrieved is not None
        assert retrieved.id == sample_doc.id
        assert retrieved.text == sample_doc.text
        assert retrieved.source == sample_doc.source
        assert retrieved.embedding is not None
        assert len(retrieved.embedding) == 768

    def test_get_nonexistent_returns_none(self, store: DocumentStore) -> None:
        assert store.get("nonexistent:99") is None

    def test_add_overwrites(
        self, store: DocumentStore, sample_doc: IndexDocument
    ) -> None:
        store.add(sample_doc)
        updated = sample_doc.model_copy(update={"text": "Updated text"})
        store.add(updated)
        retrieved = store.get(sample_doc.id)
        assert retrieved is not None
        assert retrieved.text == "Updated text"
        assert store.count() == 1


class TestDocumentStoreBatch:
    """Testes de batch operations."""

    def test_add_batch(self, store: DocumentStore) -> None:
        docs = [
            IndexDocument(
                id=f"test:{i}",
                source="test",
                text=f"doc {i}",
                metadata={},
                embedding=[float(i)] * 768,
            )
            for i in range(10)
        ]
        added = store.add_batch(docs)
        assert added == 10
        assert store.count() == 10

    def test_batch_exceeds_limit_raises(self, store: DocumentStore) -> None:
        docs = [
            IndexDocument(id=f"test:{i}", source="test", text=f"doc {i}", metadata={})
            for i in range(1001)
        ]
        with pytest.raises(ValueError, match="exceeds limit"):
            store.add_batch(docs)


class TestDocumentStoreQuery:
    """Testes de queries."""

    def test_get_by_source(self, store: DocumentStore) -> None:
        for i in range(5):
            store.add(IndexDocument(
                id=f"oc:{i}", source="geosgb/ocorrencias",
                text=f"oc {i}", metadata={},
            ))
        for i in range(3):
            store.add(IndexDocument(
                id=f"grav:{i}", source="geosgb/gravimetria",
                text=f"grav {i}", metadata={},
            ))
        ocs = store.get_by_source("geosgb/ocorrencias")
        assert len(ocs) == 5
        gravs = store.get_by_source("geosgb/gravimetria")
        assert len(gravs) == 3

    def test_count_by_source(self, store: DocumentStore) -> None:
        store.add(IndexDocument(
            id="a:1", source="source_a", text="a", metadata={}
        ))
        store.add(IndexDocument(
            id="b:1", source="source_b", text="b", metadata={}
        ))
        assert store.count() == 2
        assert store.count("source_a") == 1
        assert store.count("source_c") == 0

    def test_get_all_with_embeddings(self, store: DocumentStore) -> None:
        store.add(IndexDocument(
            id="with:1", source="test", text="has embedding",
            metadata={}, embedding=[0.5] * 768,
        ))
        store.add(IndexDocument(
            id="without:1", source="test", text="no embedding",
            metadata={},
        ))
        with_emb = store.get_all_with_embeddings()
        assert len(with_emb) == 1
        assert with_emb[0].id == "with:1"


class TestDocumentStoreDelete:
    """Testes de delete/clear."""

    def test_delete_existing(self, store: DocumentStore, sample_doc: IndexDocument) -> None:
        store.add(sample_doc)
        assert store.delete(sample_doc.id)
        assert store.get(sample_doc.id) is None

    def test_delete_nonexistent(self, store: DocumentStore) -> None:
        assert not store.delete("nonexistent:99")

    def test_clear(self, store: DocumentStore) -> None:
        for i in range(5):
            store.add(IndexDocument(
                id=f"test:{i}", source="test", text=f"doc {i}", metadata={}
            ))
        removed = store.clear()
        assert removed == 5
        assert store.count() == 0

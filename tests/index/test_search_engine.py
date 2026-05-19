"""Testes do SearchEngine e Embedder.

Usa mock do Ollama client para nao depender de LLM rodando.

Ref: RFC-003 §4.2, §9
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from miner_harness.core.types import BoundingBox
from miner_harness.index.document_store import DocumentStore
from miner_harness.index.embedder import Embedder
from miner_harness.index.search_engine import SearchEngine, _cosine_similarity
from miner_harness.index.types import EmbeddingConfig, IndexDocument


@pytest.fixture
def mock_ollama() -> MagicMock:
    client = MagicMock()
    client.embeddings = AsyncMock(return_value=[0.5] * 768)
    return client


@pytest.fixture
def embedder(mock_ollama: MagicMock) -> Embedder:
    return Embedder(mock_ollama, EmbeddingConfig())


@pytest.fixture
def store(tmp_path: Path) -> DocumentStore:
    s = DocumentStore(tmp_path / "index")
    yield s
    s.close()


@pytest.fixture
def engine(embedder: Embedder, store: DocumentStore) -> SearchEngine:
    return SearchEngine(embedder, store)


@pytest.fixture
def bbox_carajas() -> BoundingBox:
    return BoundingBox(lon_min=-51, lat_min=-7, lon_max=-49, lat_max=-5)


@pytest.fixture
def bbox_other() -> BoundingBox:
    return BoundingBox(lon_min=-45, lat_min=-20, lon_max=-43, lat_max=-18)


class TestCosineSimilarity:
    """Testes da funcao auxiliar cosine similarity."""

    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self) -> None:
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0


class TestEmbedder:
    """Testes do Embedder."""

    @pytest.mark.asyncio
    async def test_embed_text(self, embedder: Embedder, mock_ollama: MagicMock) -> None:
        result = await embedder.embed_text("Cobre em Carajas")
        assert len(result) == 768
        mock_ollama.embeddings.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_batch(self, embedder: Embedder, mock_ollama: MagicMock) -> None:
        texts = ["texto 1", "texto 2", "texto 3"]
        results = await embedder.embed_batch(texts)
        assert len(results) == 3
        assert all(len(v) == 768 for v in results)

    @pytest.mark.asyncio
    async def test_embed_truncates_long_text(
        self, embedder: Embedder, mock_ollama: MagicMock
    ) -> None:
        long_text = "x" * 1000
        await embedder.embed_text(long_text)
        call_args = mock_ollama.embeddings.call_args
        assert len(call_args.args[1]) == 512


class TestSearchEngine:
    """Testes do SearchEngine."""

    @pytest.mark.asyncio
    async def test_search_returns_ranked(
        self,
        engine: SearchEngine,
        store: DocumentStore,
        mock_ollama: MagicMock,
    ) -> None:
        """Resultados ordenados por similaridade descendente."""
        store.add(
            IndexDocument(
                id="close:1",
                source="test",
                text="very similar",
                metadata={},
                embedding=[0.5] * 768,
            )
        )
        store.add(
            IndexDocument(
                id="far:1",
                source="test",
                text="different",
                metadata={},
                embedding=[0.1] * 768,
            )
        )
        store.add(
            IndexDocument(
                id="medium:1",
                source="test",
                text="somewhat similar",
                metadata={},
                embedding=[0.3] * 768,
            )
        )

        results = await engine.search("test query", k=10)
        assert len(results) == 3
        assert results[0].rank == 1
        assert results[0].similarity >= results[1].similarity
        assert results[1].similarity >= results[2].similarity

    @pytest.mark.asyncio
    async def test_search_respects_k(
        self,
        engine: SearchEngine,
        store: DocumentStore,
    ) -> None:
        for i in range(10):
            store.add(
                IndexDocument(
                    id=f"doc:{i}",
                    source="test",
                    text=f"doc {i}",
                    metadata={},
                    embedding=[float(i) / 10] * 768,
                )
            )
        results = await engine.search("query", k=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_bbox_filter(
        self,
        engine: SearchEngine,
        store: DocumentStore,
        bbox_carajas: BoundingBox,
        bbox_other: BoundingBox,
    ) -> None:
        """Filtro espacial exclui features fora do bbox."""
        store.add(
            IndexDocument(
                id="in:1",
                source="test",
                text="inside",
                metadata={},
                embedding=[0.5] * 768,
                bbox=bbox_carajas,
            )
        )
        store.add(
            IndexDocument(
                id="out:1",
                source="test",
                text="outside",
                metadata={},
                embedding=[0.5] * 768,
                bbox=bbox_other,
            )
        )
        results = await engine.search_by_bbox("query", bbox_carajas, k=10)
        assert len(results) == 1
        assert results[0].document.id == "in:1"

    @pytest.mark.asyncio
    async def test_search_source_filter(
        self,
        engine: SearchEngine,
        store: DocumentStore,
    ) -> None:
        store.add(
            IndexDocument(
                id="oc:1",
                source="geosgb/ocorrencias",
                text="oc",
                metadata={},
                embedding=[0.5] * 768,
            )
        )
        store.add(
            IndexDocument(
                id="grav:1",
                source="geosgb/gravimetria",
                text="grav",
                metadata={},
                embedding=[0.5] * 768,
            )
        )
        results = await engine.search_by_type("query", "geosgb/ocorrencias", k=10)
        assert len(results) == 1
        assert results[0].document.source == "geosgb/ocorrencias"

    @pytest.mark.asyncio
    async def test_search_empty_store(self, engine: SearchEngine) -> None:
        results = await engine.search("query", k=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_get_context_returns_xml(
        self,
        engine: SearchEngine,
        store: DocumentStore,
    ) -> None:
        store.add(
            IndexDocument(
                id="doc:1",
                source="geosgb/ocorrencias",
                text="Cobre em Carajas",
                metadata={},
                embedding=[0.5] * 768,
            )
        )
        context = await engine.get_context("cobre", max_tokens=4000)
        assert "<rag_context>" in context
        assert "</rag_context>" in context
        assert "Cobre em Carajas" in context

    @pytest.mark.asyncio
    async def test_get_context_empty(self, engine: SearchEngine) -> None:
        context = await engine.get_context("query")
        assert "Sem dados relevantes" in context

    @pytest.mark.asyncio
    async def test_get_context_truncates_at_budget(
        self,
        engine: SearchEngine,
        store: DocumentStore,
    ) -> None:
        """Docs que excedem char_budget são descartados (linha 177)."""
        for i in range(5):
            store.add(
                IndexDocument(
                    id=f"doc:{i}",
                    source="test",
                    text="A" * 100,
                    metadata={},
                    embedding=[0.5] * 768,
                )
            )
        # max_tokens=1 → char_budget=4, impossível caber os docs
        context = await engine.get_context("query", max_tokens=1)
        assert "<rag_context>" in context
        assert "</rag_context>" in context
        # Nenhum <doc> deve ter sido incluído
        assert "<doc" not in context

    @pytest.mark.asyncio
    async def test_index_batch_empty_returns_zero(self, engine: SearchEngine) -> None:
        """index_batch([]) retorna 0 imediatamente (linha 194)."""
        result = await engine.index_batch([])
        assert result == 0

    @pytest.mark.asyncio
    async def test_index_batch_indexes_documents(
        self,
        engine: SearchEngine,
        store: DocumentStore,
    ) -> None:
        """index_batch() gera embeddings e indexa documentos (linhas 197-199)."""
        docs = [
            IndexDocument(id=f"new:{i}", source="test", text=f"text {i}", metadata={})
            for i in range(3)
        ]
        count = await engine.index_batch(docs)
        assert count == 3
        assert store.count() == 3

    @pytest.mark.asyncio
    async def test_search_bbox_includes_doc_without_bbox(
        self,
        engine: SearchEngine,
        store: DocumentStore,
        bbox_carajas: BoundingBox,
    ) -> None:
        """Doc sem bbox passa pelo filtro espacial (linhas 221-222)."""
        store.add(
            IndexDocument(
                id="no-bbox:1",
                source="test",
                text="no spatial info",
                metadata={},
                embedding=[0.5] * 768,
                bbox=None,
            )
        )
        results = await engine.search_by_bbox("query", bbox_carajas, k=10)
        assert len(results) == 1
        assert results[0].document.id == "no-bbox:1"

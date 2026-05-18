"""SearchEngine — busca semântica por similaridade vetorial.

Implementa busca por cosine similarity nos embeddings.
Versão atual usa busca por força bruta em Python (adequada
para dezenas de milhares de documentos). Quando sqlite-vec
estiver disponível, será usado como backend otimizado.

Ref: RFC-003 §4.2, §4.4
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import structlog

from miner_harness.index.types import SearchResult

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox
    from miner_harness.index.document_store import DocumentStore
    from miner_harness.index.embedder import Embedder
    from miner_harness.index.types import IndexDocument

logger = structlog.get_logger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calcula cosine similarity entre dois vetores."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SearchEngine:
    """Busca semântica em documentos indexados.

    Gera embedding da query via Embedder e busca os k documentos
    mais similares no DocumentStore.

    Usage:
        engine = SearchEngine(embedder, document_store)
        results = await engine.search("alteração hidrotermal", k=10)
        results = await engine.search_by_bbox("cobre", bbox, k=5)
    """

    def __init__(
        self,
        embedder: Embedder,
        store: DocumentStore,
    ) -> None:
        self._embedder = embedder
        self._store = store

    async def search(
        self,
        query: str,
        k: int = 10,
        bbox: BoundingBox | None = None,
        source_filter: str | None = None,
    ) -> list[SearchResult]:
        """Busca semântica nos documentos indexados.

        Args:
            query: Texto da busca.
            k: Número máximo de resultados.
            bbox: Filtro espacial opcional.
            source_filter: Filtro por fonte (ex: "geosgb/ocorrencias").

        Returns:
            Lista de SearchResult ordenada por similaridade descendente.
        """
        import time

        start = time.monotonic()

        # 1. Gerar embedding da query
        query_embedding = await self._embedder.embed_text(query)

        # 2. Buscar todos os documentos com embedding
        all_docs = self._store.get_all_with_embeddings()

        # 3. Aplicar filtros
        candidates = self._apply_filters(all_docs, bbox, source_filter)

        # 4. Calcular similaridades
        scored: list[tuple[float, IndexDocument]] = []
        for doc in candidates:
            if doc.embedding is not None:
                sim = _cosine_similarity(query_embedding, doc.embedding)
                scored.append((sim, doc))

        # 5. Ordenar por similaridade descendente
        scored.sort(key=lambda x: x[0], reverse=True)

        # 6. Montar resultados
        results = [
            SearchResult(
                document=doc,
                similarity=round(sim, 4),
                rank=i + 1,
            )
            for i, (sim, doc) in enumerate(scored[:k])
        ]

        latency_ms = int((time.monotonic() - start) * 1000)
        top_sim = results[0].similarity if results else 0.0
        logger.info(
            "index_search",
            query=query[:50],
            results=len(results),
            candidates=len(candidates),
            top_similarity=top_sim,
            latency_ms=latency_ms,
        )

        return results

    async def search_by_bbox(
        self,
        query: str,
        bbox: BoundingBox,
        k: int = 10,
    ) -> list[SearchResult]:
        """Atalho para busca com filtro espacial."""
        return await self.search(query, k=k, bbox=bbox)

    async def search_by_type(
        self,
        query: str,
        source: str,
        k: int = 10,
    ) -> list[SearchResult]:
        """Atalho para busca com filtro por tipo de fonte."""
        return await self.search(query, k=k, source_filter=source)

    async def get_context(
        self,
        query: str,
        max_tokens: int = 4000,
        k: int = 10,
    ) -> str:
        """Monta contexto RAG formatado para injeção em prompt.

        Busca os k documentos mais relevantes e formata como
        texto XML-tagged para uso pelo PromptManager (RFC-002).

        Args:
            query: Texto da busca.
            max_tokens: Limite aproximado de tokens (~4 chars/token).
            k: Número máximo de documentos a incluir.

        Returns:
            Texto formatado com contexto RAG.
        """
        results = await self.search(query, k=k)

        if not results:
            return "<rag_context>Sem dados relevantes no índice.</rag_context>"

        parts: list[str] = ["<rag_context>"]
        char_budget = max_tokens * 4  # ~4 chars per token
        used = len(parts[0])

        for result in results:
            entry = (
                f"<doc source='{result.document.source}' "
                f"similarity='{result.similarity}'>"
                f"{result.document.text}"
                f"</doc>"
            )
            if used + len(entry) > char_budget:
                break
            parts.append(entry)
            used += len(entry)

        parts.append("</rag_context>")
        return "\n".join(parts)

    async def index_batch(self, documents: list[IndexDocument]) -> int:
        """Gera embeddings e indexa múltiplos documentos.

        Args:
            documents: Documentos sem embedding preenchido.

        Returns:
            Número de documentos indexados.
        """
        if not documents:
            return 0
        texts = [doc.text for doc in documents]
        embeddings = await self._embedder.embed_batch(texts)
        for doc, embedding in zip(documents, embeddings, strict=False):
            doc.embedding = embedding
        return self._store.add_batch(documents)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_filters(
        docs: list[IndexDocument],
        bbox: BoundingBox | None,
        source_filter: str | None,
    ) -> list[IndexDocument]:
        """Aplica filtros espacial e de fonte."""
        filtered = docs

        if source_filter:
            filtered = [d for d in filtered if d.source == source_filter]

        if bbox:
            spatial: list[IndexDocument] = []
            for d in filtered:
                if d.bbox is None:
                    spatial.append(d)  # Sem bbox → incluir
                    continue
                # Verifica intersecção de bboxes
                if (
                    d.bbox.lon_max >= bbox.lon_min
                    and d.bbox.lon_min <= bbox.lon_max
                    and d.bbox.lat_max >= bbox.lat_min
                    and d.bbox.lat_min <= bbox.lat_max
                ):
                    spatial.append(d)
            filtered = spatial

        return filtered

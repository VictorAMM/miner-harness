"""Embedder — gera embeddings via Ollama.

Usa o modelo nomic-embed-text (768 dimensões) rodando
localmente via Ollama para gerar vetores de embedding.

Ref: RFC-003 §4.3
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from miner_harness.core.exceptions import EmbeddingError
from miner_harness.index.types import EmbeddingConfig

if TYPE_CHECKING:
    from miner_harness.connectors.ollama.client import OllamaClient

logger = structlog.get_logger(__name__)


class Embedder:
    """Gera embeddings via Ollama.

    Usage:
        embedder = Embedder(ollama_client)
        vector = await embedder.embed_text("Cobre em Carajás")
        vectors = await embedder.embed_batch(["texto1", "texto2"])
    """

    def __init__(
        self,
        client: OllamaClient,
        config: EmbeddingConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config or EmbeddingConfig()

    @property
    def model(self) -> str:
        """Nome do modelo de embeddings."""
        return self._config.model

    @property
    def dimensions(self) -> int:
        """Dimensões do vetor de embedding."""
        return self._config.dimensions

    async def embed_text(self, text: str) -> list[float]:
        """Gera embedding para um texto.

        Args:
            text: Texto para gerar embedding. Truncado a max_text_length.

        Returns:
            Vetor de embedding (768 floats por default).

        Raises:
            EmbeddingError: Falha na geração do embedding.
        """
        truncated = text[: self._config.max_text_length]
        try:
            embedding = await self._client.embeddings(self._config.model, truncated)
            if len(embedding) != self._config.dimensions:
                logger.warning(
                    "embedding_dimension_mismatch",
                    expected=self._config.dimensions,
                    got=len(embedding),
                )
            return embedding
        except Exception as exc:
            raise EmbeddingError(f"Failed to embed text: {exc}") from exc

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings em batch.

        Processa em chunks de max_batch_size para evitar
        sobrecarregar o Ollama.

        Args:
            texts: Lista de textos.

        Returns:
            Lista de vetores de embedding, um por texto.

        Raises:
            EmbeddingError: Falha na geração de embeddings.
        """
        results: list[list[float]] = []
        batch_size = self._config.max_batch_size

        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            for text in chunk:
                embedding = await self.embed_text(text)
                results.append(embedding)

            logger.debug(
                "embed_batch_progress",
                processed=len(results),
                total=len(texts),
            )

        logger.info(
            "index_batch_embed",
            documents=len(texts),
            model=self._config.model,
        )
        return results

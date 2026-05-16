"""Tipos do subsistema de índice vetorial.

Define IndexDocument, SearchResult e EmbeddingConfig.

Ref: RFC-003 §4
"""

from pydantic import BaseModel, Field

from miner_harness.core.types import BoundingBox  # noqa: TCH001


class EmbeddingConfig(BaseModel):
    """Configuração do modelo de embeddings."""

    model: str = "nomic-embed-text"
    dimensions: int = 768
    max_batch_size: int = 100
    max_text_length: int = 512


class IndexDocument(BaseModel):
    """Documento indexado no vetor store."""

    id: str = Field(description="service:objectid")
    source: str = Field(description='Ex: "geosgb/ocorrencias"')
    text: str = Field(description="Texto para embedding")
    metadata: dict[str, object] = Field(default_factory=dict)
    bbox: BoundingBox | None = None
    embedding: list[float] | None = None


class SearchResult(BaseModel):
    """Resultado de busca no índice vetorial."""

    document: IndexDocument
    similarity: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)

"""Index — índice vetorial para busca semântica (RAG).

Embeddings via Ollama + busca por similaridade cosine
em dados geocientíficos.
Ref: RFC-003.
"""

from miner_harness.index.document_store import DocumentStore
from miner_harness.index.embedder import Embedder
from miner_harness.index.search_engine import SearchEngine
from miner_harness.index.text_builder import dict_to_text, feature_to_text
from miner_harness.index.types import EmbeddingConfig, IndexDocument, SearchResult

__all__ = [
    "DocumentStore",
    "Embedder",
    "EmbeddingConfig",
    "IndexDocument",
    "SearchEngine",
    "SearchResult",
    "dict_to_text",
    "feature_to_text",
]

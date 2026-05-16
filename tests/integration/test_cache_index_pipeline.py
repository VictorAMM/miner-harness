"""Integration tests: Cache -> Index pipeline.

Tests the full flow: cache GeoSGB data -> convert to text ->
generate embeddings -> store in index -> search.

Ref: RFC-003 (full pipeline), Phase 6 Validation Harness
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from miner_harness.cache.manager import CacheManager
from miner_harness.core.config import StorageConfig
from miner_harness.core.types import BoundingBox
from miner_harness.index.document_store import DocumentStore
from miner_harness.index.embedder import Embedder
from miner_harness.index.search_engine import SearchEngine
from miner_harness.index.text_builder import dict_to_text
from miner_harness.index.types import EmbeddingConfig, IndexDocument


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)


@pytest.fixture
def storage_config(tmp_path: Path) -> StorageConfig:
    return StorageConfig(miner_home=tmp_path / ".miner-harness")


@pytest.fixture
def cache(storage_config: StorageConfig) -> CacheManager:
    c = CacheManager(storage_config)
    yield c
    c.close()


@pytest.fixture
def doc_store(tmp_path: Path) -> DocumentStore:
    s = DocumentStore(tmp_path / "index")
    yield s
    s.close()


@pytest.fixture
def mock_ollama() -> MagicMock:
    client = MagicMock()
    # Deterministic embeddings: hash of text length for reproducibility
    def _make_embedding(model: str, text: str) -> list[float]:
        seed = len(text) % 100
        return [float(seed + i) / 1000 for i in range(768)]

    client.embeddings = AsyncMock(side_effect=_make_embedding)
    return client


@pytest.fixture
def embedder(mock_ollama: MagicMock) -> Embedder:
    return Embedder(mock_ollama, EmbeddingConfig())


@pytest.fixture
def engine(embedder: Embedder, doc_store: DocumentStore) -> SearchEngine:
    return SearchEngine(embedder, doc_store)


# Sample geological data matching GeoSGB response format
SAMPLE_OCORRENCIAS = [
    {
        "objectid": 1,
        "substancias": "Cobre, Ouro",
        "municipio": "Parauapebas",
        "uf": "PA",
        "provincia": "Carajas",
        "status_economico": "Deposito",
        "longitude": -50.3,
        "latitude": -6.1,
    },
    {
        "objectid": 2,
        "substancias": "Ferro, Manganes",
        "municipio": "Maraba",
        "uf": "PA",
        "provincia": "Carajas",
        "status_economico": "Ocorrencia",
        "longitude": -49.8,
        "latitude": -5.5,
    },
    {
        "objectid": 3,
        "substancias": "Niquel",
        "municipio": "Ourilandia do Norte",
        "uf": "PA",
        "provincia": None,
        "status_economico": None,
        "longitude": -51.0,
        "latitude": -6.8,
    },
]

SAMPLE_GRAVIMETRIA = [
    {
        "objectid": 10,
        "longitude": -50.5,
        "latitude": -6.0,
        "altitude_ortometrica": 250.0,
        "gravidade": 978.1,
        "anomalia_ar_livre": -15.3,
        "anomalia_bouguer": -80.5,
    },
]

SAMPLE_GEOQUIMICA = [
    {
        "objectid": 20,
        "projeto": "Carajas 2020",
        "classe": "Sedimento de Corrente",
        "material_coletado": "Sedimento",
        "longitude": -50.1,
        "latitude": -6.3,
        "Cu_ppm": 120.5,
        "Au_ppb": 45.0,
        "Fe_pct": 35.2,
    },
]


class TestCacheToIndexPipeline:
    """Integration: cache -> text_builder -> embedder -> index -> search."""

    @pytest.mark.asyncio
    async def test_full_pipeline(
        self,
        cache: CacheManager,
        doc_store: DocumentStore,
        embedder: Embedder,
        engine: SearchEngine,
        bbox: BoundingBox,
    ) -> None:
        """End-to-end: cache data, index it, search it."""
        # Step 1: Populate cache
        cache.put("ocorrencias", bbox, SAMPLE_OCORRENCIAS)
        cache.put("gravimetria", bbox, SAMPLE_GRAVIMETRIA)
        cache.put("geoquimica", bbox, SAMPLE_GEOQUIMICA)

        # Step 2: Retrieve from cache
        cached_oc = cache.get("ocorrencias", bbox)
        cached_grav = cache.get("gravimetria", bbox)
        cached_geo = cache.get("geoquimica", bbox)
        assert cached_oc is not None
        assert cached_grav is not None
        assert cached_geo is not None

        # Step 3: Convert to text and create documents
        docs: list[IndexDocument] = []
        for feature in cached_oc:
            text = dict_to_text(feature, "geosgb/ocorrencias")
            embedding = await embedder.embed_text(text)
            docs.append(IndexDocument(
                id=f"ocorrencias:{feature['objectid']}",
                source="geosgb/ocorrencias",
                text=text,
                metadata=feature,
                bbox=bbox,
                embedding=embedding,
            ))

        for feature in cached_grav:
            text = dict_to_text(feature, "geosgb/gravimetria")
            embedding = await embedder.embed_text(text)
            docs.append(IndexDocument(
                id=f"gravimetria:{feature['objectid']}",
                source="geosgb/gravimetria",
                text=text,
                metadata=feature,
                bbox=bbox,
                embedding=embedding,
            ))

        for feature in cached_geo:
            text = dict_to_text(feature, "geosgb/geoquimica")
            embedding = await embedder.embed_text(text)
            docs.append(IndexDocument(
                id=f"geoquimica:{feature['objectid']}",
                source="geosgb/geoquimica",
                text=text,
                metadata=feature,
                bbox=bbox,
                embedding=embedding,
            ))

        # Step 4: Index documents
        added = doc_store.add_batch(docs)
        assert added == 5  # 3 oc + 1 grav + 1 geo

        # Step 5: Search
        results = await engine.search("cobre ouro carajas", k=5)
        assert len(results) == 5
        assert results[0].rank == 1
        assert results[0].similarity > 0

        # Step 6: Search by bbox
        results_bbox = await engine.search_by_bbox("cobre", bbox, k=10)
        assert len(results_bbox) == 5

        # Step 7: Search by source type
        results_oc = await engine.search_by_type(
            "cobre", "geosgb/ocorrencias", k=10
        )
        assert len(results_oc) == 3
        assert all(r.document.source == "geosgb/ocorrencias" for r in results_oc)

    @pytest.mark.asyncio
    async def test_cache_coverage_drives_offline(
        self,
        cache: CacheManager,
        bbox: BoundingBox,
    ) -> None:
        """Coverage report reflects what's cached for offline mode."""
        # Initially nothing cached
        report = cache.coverage_report(bbox)
        assert not report.can_run_offline
        assert len(report.missing_services) == 6

        # Cache 3 services
        cache.put("ocorrencias", bbox, SAMPLE_OCORRENCIAS)
        cache.put("gravimetria", bbox, SAMPLE_GRAVIMETRIA)
        cache.put("geoquimica", bbox, SAMPLE_GEOQUIMICA)

        report = cache.coverage_report(bbox)
        assert not report.can_run_offline  # Need all 6
        assert report.total_features == 5
        assert len(report.missing_services) == 3

        # Cache remaining 3 services
        cache.put("geocronologia", bbox, [{"objectid": 30}])
        cache.put("litoestratigrafia", bbox, [{"objectid": 40}])
        cache.put("aerogeofisica", bbox, [{"objectid": 50}])

        report = cache.coverage_report(bbox)
        assert report.can_run_offline
        assert report.missing_services == []
        assert report.total_features == 8

    @pytest.mark.asyncio
    async def test_rag_context_generation(
        self,
        doc_store: DocumentStore,
        engine: SearchEngine,
        bbox: BoundingBox,
    ) -> None:
        """RAG context XML is well-formed with indexed data."""
        doc_store.add(IndexDocument(
            id="oc:1",
            source="geosgb/ocorrencias",
            text="Cobre e Ouro em Parauapebas PA, Provincia Carajas",
            metadata={"substancias": "Cobre, Ouro"},
            bbox=bbox,
            embedding=[0.5] * 768,
        ))
        doc_store.add(IndexDocument(
            id="grav:1",
            source="geosgb/gravimetria",
            text="Anomalia Bouguer -80 mGal em Carajas",
            metadata={"anomalia_bouguer": -80.5},
            bbox=bbox,
            embedding=[0.3] * 768,
        ))

        context = await engine.get_context("cobre anomalia carajas", max_tokens=4000)
        assert "<rag_context>" in context
        assert "</rag_context>" in context
        # Both documents should appear
        assert "Cobre" in context or "Anomalia" in context

    @pytest.mark.asyncio
    async def test_index_survives_cache_clear(
        self,
        cache: CacheManager,
        doc_store: DocumentStore,
        embedder: Embedder,
        bbox: BoundingBox,
    ) -> None:
        """Index persists even after cache is cleared."""
        # Cache and index
        cache.put("ocorrencias", bbox, SAMPLE_OCORRENCIAS)
        for feature in SAMPLE_OCORRENCIAS:
            text = dict_to_text(feature, "geosgb/ocorrencias")
            embedding = await embedder.embed_text(text)
            doc_store.add(IndexDocument(
                id=f"oc:{feature['objectid']}",
                source="geosgb/ocorrencias",
                text=text,
                metadata=feature,
                embedding=embedding,
            ))

        assert doc_store.count() == 3

        # Clear cache
        cache.clear()
        assert cache.get("ocorrencias", bbox) is None

        # Index still has data
        assert doc_store.count() == 3
        doc = doc_store.get("oc:1")
        assert doc is not None

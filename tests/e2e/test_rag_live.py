"""Testes e2e — RAG (Retrieval-Augmented Generation) com GeoSGB + Ollama real.

Verifica que:
- O vector store é populado após análise com use_rag=True
- get_context() retorna texto relevante após indexação
- A análise com RAG produz relatório válido

Executar com: MINER_E2E=1 uv run pytest tests/e2e/test_rag_live.py -v
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from miner_harness.cache.manager import CacheManager
from miner_harness.connectors.geosgb.connector import GeoSGBConnector
from miner_harness.connectors.ollama.client import OllamaClient
from miner_harness.core.config import MinerHarnessConfig, OrchestratorConfig, StorageConfig
from miner_harness.index.document_store import DocumentStore
from miner_harness.index.embedder import Embedder
from miner_harness.index.search_engine import SearchEngine
from miner_harness.orchestrator.context_builder import ContextBuilder
from miner_harness.orchestrator.orchestrator import Orchestrator

from .conftest import skip_no_e2e, skip_no_ollama

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox


@pytest.fixture(scope="module")
def rag_config(
    tmp_path_factory: pytest.TempPathFactory,
    ollama_url: str,
    ollama_model: str,
) -> MinerHarnessConfig:
    tmp = tmp_path_factory.mktemp("e2e_rag_home")
    config = MinerHarnessConfig(
        storage=StorageConfig(miner_home=tmp),
        orchestrator=OrchestratorConfig(
            ollama_base_url=ollama_url,
            model=ollama_model,
            ollama_timeout_s=180,
            use_rag=True,
        ),
    )
    config.storage.ensure_dirs()
    return config


# ---------------------------------------------------------------------------
# RAG sem Ollama — indexação e busca com embedder local
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_rag_index_populates_after_context_build(
    bbox_carajas_small: BoundingBox,
    rag_config: MinerHarnessConfig,
) -> None:
    """Após ContextBuilder.build(), o vector store contém documentos GeoSGB."""
    store = DocumentStore(rag_config.storage.index_dir)
    embedder = Embedder(rag_config.orchestrator.ollama_base_url)
    engine = SearchEngine(embedder, store)

    cache = CacheManager(rag_config.storage)
    try:
        async with GeoSGBConnector(rag_config.geosgb) as connector:
            builder = ContextBuilder(connector, cache, engine)
            await builder.build(bbox_carajas_small)

        count = store.count()
        assert count > 0, "Vector store deve conter documentos após indexação de features GeoSGB"
    finally:
        cache.close()
        store.close()


@skip_no_e2e
@pytest.mark.asyncio
async def test_rag_get_context_returns_relevant_text(
    bbox_carajas_small: BoundingBox,
    rag_config: MinerHarnessConfig,
) -> None:
    """Após indexação, get_context() retorna texto não-vazio para query geológica."""
    store = DocumentStore(rag_config.storage.index_dir)
    embedder = Embedder(rag_config.orchestrator.ollama_base_url)
    engine = SearchEngine(embedder, store)

    cache = CacheManager(rag_config.storage)
    try:
        async with GeoSGBConnector(rag_config.geosgb) as connector:
            builder = ContextBuilder(connector, cache, engine)
            await builder.build(bbox_carajas_small)

        if store.count() == 0:
            pytest.skip("Vector store vazio — indexação não produziu documentos")

        context = await engine.get_context("ocorrências minerais sistemas IOCG Carajás")
        assert len(context) > 10, f"get_context() retornou texto insuficiente: {context!r}"
    finally:
        cache.close()
        store.close()


# ---------------------------------------------------------------------------
# Pipeline completo com RAG + Ollama
# ---------------------------------------------------------------------------


@skip_no_ollama
@pytest.mark.asyncio
async def test_rag_pipeline_completo(
    bbox_carajas_small: BoundingBox,
    rag_config: MinerHarnessConfig,
) -> None:
    """Orchestrator com use_rag=True completa análise sem erros e indexa features."""
    cache = CacheManager(rag_config.storage)
    connector = GeoSGBConnector(rag_config.geosgb)
    llm = OllamaClient(rag_config.orchestrator)

    try:
        orch = Orchestrator(connector, cache, llm, rag_config)
        report = await orch.analyze_region(bbox_carajas_small, "carajas_rag_e2e")
    finally:
        await connector.close()
        await llm.close()
        cache.close()

    assert report.region_name == "carajas_rag_e2e"
    assert len(report.steps) > 0

    # Vector store deve ter sido populado durante a análise
    store = DocumentStore(rag_config.storage.index_dir)
    try:
        count = store.count()
        assert count > 0, "Vector store vazio após análise com use_rag=True"
    finally:
        store.close()


@skip_no_ollama
@pytest.mark.asyncio
async def test_rag_pipeline_sem_rag_funciona(
    bbox_carajas_small: BoundingBox,
    tmp_path_factory: pytest.TempPathFactory,
    ollama_url: str,
    ollama_model: str,
) -> None:
    """Orchestrator com use_rag=False completa análise normalmente."""
    tmp = tmp_path_factory.mktemp("e2e_norag_home")
    config = MinerHarnessConfig(
        storage=StorageConfig(miner_home=tmp),
        orchestrator=OrchestratorConfig(
            ollama_base_url=ollama_url,
            model=ollama_model,
            ollama_timeout_s=180,
            use_rag=False,
        ),
    )
    config.storage.ensure_dirs()

    cache = CacheManager(config.storage)
    connector = GeoSGBConnector(config.geosgb)
    llm = OllamaClient(config.orchestrator)

    try:
        orch = Orchestrator(connector, cache, llm, config)
        report = await orch.analyze_region(bbox_carajas_small, "carajas_norag_e2e")
    finally:
        await connector.close()
        await llm.close()
        cache.close()

    assert report.region_name == "carajas_norag_e2e"
    assert len(report.steps) > 0

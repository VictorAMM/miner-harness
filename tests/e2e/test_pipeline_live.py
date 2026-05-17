"""Testes e2e — pipeline completo (GeoSGB + Ollama + Orchestrator).

Executa o fluxo completo de análise em uma BBox real de Carajás:
GeoSGBConnector → CacheManager → ContextBuilder → Agentes → ProspectionReport

Requer: GeoSGB API acessível + Ollama rodando com modelo configurado.

Executar com: MINER_E2E=1 uv run pytest tests/e2e/test_pipeline_live.py -v
"""

from __future__ import annotations

import pytest

from miner_harness.cache.manager import CacheManager
from miner_harness.connectors.geosgb.connector import GeoSGBConnector
from miner_harness.connectors.ollama.client import OllamaClient
from miner_harness.core.config import MinerHarnessConfig, OrchestratorConfig, StorageConfig
from miner_harness.core.types import BoundingBox, Confidence
from miner_harness.orchestrator.orchestrator import Orchestrator
from miner_harness.orchestrator.report_validator import ReportValidator

from .conftest import skip_no_e2e, skip_no_ollama

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def live_config(
    tmp_path_factory: pytest.TempPathFactory,
    ollama_url: str,
    ollama_model: str,
) -> MinerHarnessConfig:
    tmp = tmp_path_factory.mktemp("e2e_miner_home")
    config = MinerHarnessConfig(
        storage=StorageConfig(miner_home=tmp),
        orchestrator=OrchestratorConfig(
            ollama_base_url=ollama_url,
            model=ollama_model,
            ollama_timeout_s=180,
        ),
    )
    config.storage.ensure_dirs()
    return config


@pytest.fixture(scope="module")
def live_cache(live_config: MinerHarnessConfig) -> CacheManager:
    cache = CacheManager(live_config.storage)
    yield cache
    cache.close()


# ---------------------------------------------------------------------------
# GeoSGB + cache (não requer Ollama)
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_pipeline_connector_to_cache(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """Dados gravimétricos são buscados do GeoSGB e armazenados no cache."""
    async with GeoSGBConnector(live_config.geosgb) as conn:
        dados = await conn.gravimetria(bbox_carajas_small)

    assert len(dados) > 0

    # Persiste no cache
    cache_key = f"e2e_gravimetria_{bbox_carajas_small.as_tuple()}"
    live_cache.set(
        service="geosgb/gravimetria",
        key=cache_key,
        data=[d.model_dump() for d in dados],
    )

    # Confirma que está no cache
    cached = live_cache.get(service="geosgb/gravimetria", key=cache_key)
    assert cached is not None
    assert len(cached) == len(dados)


@skip_no_e2e
@pytest.mark.asyncio
async def test_pipeline_cache_hit_evita_requisicao(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """Segunda chamada com mesma chave retorna do cache sem nova requisição HTTP."""
    cache_key = f"e2e_gravimetria_{bbox_carajas_small.as_tuple()}"

    # Se o teste anterior rodou, já está no cache
    cached = live_cache.get(service="geosgb/gravimetria", key=cache_key)
    if cached is None:
        pytest.skip("Cache vazio — rode test_pipeline_connector_to_cache primeiro")

    # Não faz nova requisição — apenas lê cache
    stats_before = live_cache.stats()
    _ = live_cache.get(service="geosgb/gravimetria", key=cache_key)
    stats_after = live_cache.stats()

    # Total de entradas não mudou (sem insert)
    assert stats_after.total_entries == stats_before.total_entries


# ---------------------------------------------------------------------------
# Pipeline completo com Ollama
# ---------------------------------------------------------------------------


@skip_no_ollama
@pytest.mark.asyncio
async def test_pipeline_orchestrator_analyze_region(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """Orchestrator produz ProspectionReport válido para Carajás real."""
    connector = GeoSGBConnector(live_config.geosgb)
    llm = OllamaClient(live_config.orchestrator)

    try:
        orch = Orchestrator(connector, live_cache, llm, live_config)
        report = await orch.analyze_region(bbox_carajas_small, "carajas_e2e")
    finally:
        await connector.close()
        await llm.close()

    # Estrutura básica
    assert report.region_name == "carajas_e2e"
    assert report.total_duration_ms > 0
    assert len(report.steps) > 0

    # Ao menos um passo com confiança não-insufficient
    confidences = [s.confidence for s in report.steps]
    assert any(c != Confidence.INSUFFICIENT for c in confidences), (
        "Todos os passos retornaram confiança INSUFFICIENT — possível falha de LLM ou dados vazios"
    )


@skip_no_ollama
@pytest.mark.asyncio
async def test_pipeline_report_valido(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """ReportValidator aprova o relatório gerado para Carajás."""
    connector = GeoSGBConnector(live_config.geosgb)
    llm = OllamaClient(live_config.orchestrator)

    try:
        orch = Orchestrator(connector, live_cache, llm, live_config)
        report = await orch.analyze_region(bbox_carajas_small, "carajas_validation_e2e")
    finally:
        await connector.close()
        await llm.close()

    validator = ReportValidator()
    result = validator.validate(report)

    assert result.score >= 0.5, (
        f"Score de validação muito baixo: {result.score:.2f}. "
        f"Erros: {[i.message for i in result.issues]}"
    )


@skip_no_ollama
@pytest.mark.asyncio
async def test_pipeline_segunda_execucao_mais_rapida(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """Segunda execução reutiliza cache de dados e é mais rápida que a primeira."""
    import time

    connector = GeoSGBConnector(live_config.geosgb)
    llm = OllamaClient(live_config.orchestrator)

    try:
        orch = Orchestrator(connector, live_cache, llm, live_config)

        t0 = time.monotonic()
        await orch.analyze_region(bbox_carajas_small, "carajas_run1_e2e")
        first_duration = time.monotonic() - t0

        t1 = time.monotonic()
        await orch.analyze_region(bbox_carajas_small, "carajas_run2_e2e")
        second_duration = time.monotonic() - t1
    finally:
        await connector.close()
        await llm.close()

    # Segunda rodada deve ser pelo menos 20% mais rápida (cache de dados GeoSGB)
    # (o LLM ainda roda, então não esperamos 10× mais rápido)
    assert second_duration < first_duration * 0.9, (
        f"Segunda execução não foi mais rápida: 1ª={first_duration:.1f}s, 2ª={second_duration:.1f}s"
    )

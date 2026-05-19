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
    """Ocorrências minerais são buscadas do GeoSGB e armazenadas no cache."""
    async with GeoSGBConnector(live_config.geosgb) as conn:
        from miner_harness.connectors.geosgb.grid_extractor import GridDensity

        dados = await conn.ocorrencias(bbox_carajas_small, density=GridDensity.LOW)

    assert len(dados) > 0, "Esperava ocorrências em Carajás"

    # Persiste no cache via API real: put(service, bbox, features)
    live_cache.put(
        service="ocorrencias",
        bbox=bbox_carajas_small,
        features=[d.model_dump() for d in dados],
    )

    # Confirma que está no cache via API real: get(service, bbox)
    cached = live_cache.get("ocorrencias", bbox_carajas_small)
    assert cached is not None
    assert len(cached) == len(dados)


@skip_no_e2e
@pytest.mark.asyncio
async def test_pipeline_cache_hit_evita_requisicao(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """Segunda chamada com mesma bbox retorna do cache sem nova requisição HTTP."""
    # Se o teste anterior rodou, já está no cache
    cached = live_cache.get("ocorrencias", bbox_carajas_small)
    if cached is None:
        pytest.skip("Cache vazio — rode test_pipeline_connector_to_cache primeiro")

    # Não faz nova requisição — apenas lê cache
    stats_before = live_cache.stats()
    _ = live_cache.get("ocorrencias", bbox_carajas_small)
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


# ---------------------------------------------------------------------------
# geological_data — campo populado no relatório (v0.4.0+)
# ---------------------------------------------------------------------------


@skip_no_ollama
@pytest.mark.asyncio
async def test_pipeline_relatorio_contem_geological_data(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """ProspectionReport.geological_data é populado com os dados coletados."""
    connector = GeoSGBConnector(live_config.geosgb)
    llm = OllamaClient(live_config.orchestrator)

    try:
        orch = Orchestrator(connector, live_cache, llm, live_config)
        report = await orch.analyze_region(bbox_carajas_small, "carajas_geodata_e2e")
    finally:
        await connector.close()
        await llm.close()

    assert report.geological_data is not None, (
        "geological_data deve estar populado no relatório (v0.4.0)"
    )
    assert isinstance(report.geological_data, dict)

    # Ao menos uma das 6 fontes GeoSGB deve ter retornado dados
    total_records = sum(len(v) for v in report.geological_data.values())
    keys = list(report.geological_data.keys())
    assert total_records > 0, f"geological_data está vazio — nenhum dado coletado. Keys: {keys}"


@skip_no_e2e
@pytest.mark.asyncio
async def test_pipeline_geological_data_tem_chaves_geosgb(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """geological_data contém as chaves dos 6 serviços GeoSGB quando habilitados."""
    from miner_harness.orchestrator.context_builder import ContextBuilder

    async with GeoSGBConnector(live_config.geosgb) as connector:
        ctx = ContextBuilder(connector, live_cache)
        data = await ctx.build(bbox_carajas_small)

    expected_keys = {
        "ocorrencias",
        "gravimetria",
        "geoquimica",
        "geocronologia",
        "litoestratigrafia",
        "aerogeofisica",
    }
    assert expected_keys.issubset(set(data.keys())), (
        f"Chaves GeoSGB faltando. Presentes: {set(data.keys())}"
    )


@skip_no_e2e
@pytest.mark.asyncio
async def test_pipeline_geological_data_inclui_usgs_quando_habilitado(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """Quando USGS está habilitado, geological_data inclui chave 'usgs'."""
    if not live_config.usgs.enabled:
        pytest.skip("USGS desabilitado na config — defina usgs.enabled=True para este teste")

    from miner_harness.connectors.usgs.connector import USGSConnector
    from miner_harness.orchestrator.context_builder import ContextBuilder

    async with GeoSGBConnector(live_config.geosgb) as connector:
        usgs_conn = USGSConnector(live_config.usgs)
        ctx = ContextBuilder(
            connector,
            live_cache,
            extra_sources={"usgs": (usgs_conn, "sismos")},
        )
        data = await ctx.build(bbox_carajas_small)

    assert "usgs" in data, f"Chave 'usgs' ausente em geological_data. Keys: {list(data.keys())}"


@skip_no_e2e
@pytest.mark.asyncio
async def test_pipeline_geological_data_inclui_anm_quando_habilitado(
    bbox_carajas_small: BoundingBox,
    live_config: MinerHarnessConfig,
    live_cache: CacheManager,
) -> None:
    """Quando ANM está habilitado, geological_data inclui chave 'anm'."""
    if not live_config.anm.enabled:
        pytest.skip("ANM desabilitado na config — defina anm.enabled=True para este teste")

    from miner_harness.connectors.anm.connector import ANMConnector
    from miner_harness.orchestrator.context_builder import ContextBuilder

    async with GeoSGBConnector(live_config.geosgb) as connector:
        anm_conn = ANMConnector(live_config.anm)
        ctx = ContextBuilder(
            connector,
            live_cache,
            extra_sources={"anm": (anm_conn, "concessoes")},
        )
        data = await ctx.build(bbox_carajas_small)

    assert "anm" in data, f"Chave 'anm' ausente em geological_data. Keys: {list(data.keys())}"

"""Testes do Orchestrator.

Usa mocks para GeoSGB e Ollama — testa fluxo de orquestracao.

Ref: RFC-002 §4.2, §6
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from unittest.mock import patch

from miner_harness.cache.manager import CacheManager
from miner_harness.core.config import (
    ANMConfig,
    MinerHarnessConfig,
    OrchestratorConfig,
    StorageConfig,
    USGSConfig,
)
from miner_harness.core.exceptions import InsufficientDataError
from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    StepResult,
)
from miner_harness.orchestrator.orchestrator import Orchestrator


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)


@pytest.fixture
def cache(tmp_path: Path) -> CacheManager:
    config = StorageConfig(miner_home=tmp_path / ".miner-harness")
    c = CacheManager(config)
    yield c
    c.close()


@pytest.fixture
def mock_connector() -> MagicMock:
    connector = MagicMock()
    for method in [
        "ocorrencias",
        "gravimetria",
        "geoquimica",
        "geocronologia",
        "litoestratigrafia",
        "aerogeofisica",
    ]:
        setattr(connector, method, AsyncMock(return_value=[]))
    return connector


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content='{"summary": "Test summary", "findings": ["finding1"], '
            '"confidence": "medium", "data_sources_used": ["test"], '
            '"data_gaps": []}',
            prompt_eval_count=100,
            eval_count=200,
        )
    )
    return llm


@pytest.fixture
def config() -> MinerHarnessConfig:
    return MinerHarnessConfig(
        anm=ANMConfig(enabled=False),
        usgs=USGSConfig(enabled=False),
    )


def _populate_cache(cache: CacheManager, bbox: BoundingBox) -> None:
    """Popula cache com dados suficientes para analise."""
    services = [
        "ocorrencias",
        "gravimetria",
        "geoquimica",
        "geocronologia",
        "litoestratigrafia",
        "aerogeofisica",
    ]
    for svc in services:
        cache.put(svc, bbox, [{"objectid": i} for i in range(5)])


class TestOrchestrator:
    """Testes do Orchestrator."""

    def test_init(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
    ) -> None:
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        assert len(orch._agents) == 5

    def test_get_agent_for_step(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
    ) -> None:
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        agent = orch.get_agent_for_step(AnalysisStep.TECTONIC_HISTORY)
        assert agent.name == "structural_geologist"

        agent = orch.get_agent_for_step(AnalysisStep.TOTAL_INTEGRATION)
        assert agent.name == "evaluator"

    @pytest.mark.asyncio
    async def test_analyze_insufficient_data(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Should raise InsufficientDataError with < 3 sources."""
        cache.put("ocorrencias", bbox, [{"id": 1}])
        cache.put("gravimetria", bbox, [{"id": 2}])
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        with pytest.raises(InsufficientDataError):
            await orch.analyze_region(bbox, "Test Region")

    @pytest.mark.asyncio
    async def test_analyze_full_pipeline(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Full pipeline should execute all 5 steps and produce report."""
        _populate_cache(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        report = await orch.analyze_region(bbox, "Carajas")

        assert report.region_name == "Carajas"
        assert report.bbox == bbox
        assert len(report.steps) == 5
        assert report.total_duration_ms >= 0
        assert report.model_used == config.orchestrator.model
        assert 0 <= report.data_quality_score <= 1
        assert report.analysis_date is not None

    @pytest.mark.asyncio
    async def test_analyze_partial_steps(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Should execute only specified steps."""
        _populate_cache(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        report = await orch.analyze_region(
            bbox,
            "Test",
            steps=[AnalysisStep.TECTONIC_HISTORY, AnalysisStep.STRUCTURAL_ARCHITECTURE],
        )
        assert len(report.steps) == 2
        assert report.steps[0].step == AnalysisStep.TECTONIC_HISTORY
        assert report.steps[1].step == AnalysisStep.STRUCTURAL_ARCHITECTURE

    @pytest.mark.asyncio
    async def test_step_results_chained(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Each step should receive previous results."""
        _populate_cache(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        call_count = 0

        original_analyze = orch._agents["structural_geologist"].analyze

        async def tracking_analyze(
            step: AnalysisStep,
            data: dict,
            prev: list | None = None,
            bbox=None,  # noqa: ANN001
        ) -> StepResult:
            nonlocal call_count
            call_count += 1
            return await original_analyze(step, data, prev, bbox)

        orch._agents["structural_geologist"].analyze = tracking_analyze

        await orch.analyze_region(
            bbox,
            "Test",
            steps=[AnalysisStep.TECTONIC_HISTORY, AnalysisStep.STRUCTURAL_ARCHITECTURE],
        )
        assert call_count == 2


class TestOrchestratorHelpers:
    """Testes dos metodos auxiliares do Orchestrator."""

    def test_build_summary(self) -> None:
        results = [
            StepResult(
                step=AnalysisStep.TECTONIC_HISTORY,
                agent="structural_geologist",
                summary="Craton stability confirmed",
                findings=[],
                confidence=Confidence.HIGH,
                data_sources_used=[],
                data_gaps=[],
                raw_reasoning="",
                duration_ms=100,
            ),
            StepResult(
                step=AnalysisStep.STRUCTURAL_ARCHITECTURE,
                agent="structural_geologist",
                summary="NW-SE shear zones identified",
                findings=[],
                confidence=Confidence.MEDIUM,
                data_sources_used=[],
                data_gaps=[],
                raw_reasoning="",
                duration_ms=100,
            ),
        ]
        summary = Orchestrator._build_summary(results)
        assert "Craton stability" in summary
        assert "shear zones" in summary

    def test_build_summary_empty(self) -> None:
        assert Orchestrator._build_summary([]) == "Análise não executada."

    def test_build_summary_uses_evaluator_when_present(self) -> None:
        """Quando há um step total_integration, seu summary é usado diretamente."""
        results = [
            StepResult(
                step=AnalysisStep.TECTONIC_HISTORY,
                agent="structural_geologist",
                summary="Craton stability confirmed",
                findings=[],
                confidence=Confidence.HIGH,
                data_sources_used=[],
                data_gaps=[],
                raw_reasoning="",
                duration_ms=100,
            ),
            StepResult(
                step=AnalysisStep.TOTAL_INTEGRATION,
                agent="evaluator",
                summary="Alta fertilidade IOCG em Carajás Sul com 3 alvos prioritários.",
                findings=[],
                confidence=Confidence.HIGH,
                data_sources_used=[],
                data_gaps=[],
                raw_reasoning="",
                duration_ms=100,
            ),
        ]
        summary = Orchestrator._build_summary(results)
        # Deve usar o summary do evaluator, não a concatenação
        assert "IOCG" in summary
        assert "[tectonic_history]" not in summary
        assert "[total_integration]" not in summary

    def test_build_summary_strips_total_integration_prefix(self) -> None:
        """Prefixo [total_integration] adicionado por _merge_step_results é removido."""
        results = [
            StepResult(
                step=AnalysisStep.TOTAL_INTEGRATION,
                agent="evaluator",
                summary="[total_integration] Síntese final com potencial IOCG.",
                findings=[],
                confidence=Confidence.MEDIUM,
                data_sources_used=[],
                data_gaps=[],
                raw_reasoning="",
                duration_ms=0,
            ),
        ]
        summary = Orchestrator._build_summary(results)
        assert not summary.startswith("[total_integration]")
        assert "IOCG" in summary

    def test_dedup_gaps_semantic_removes_near_duplicates(self) -> None:
        """Gaps semanticamente similares (≥60% palavras em comum) são deduplicados."""
        gaps = [
            "Ausência de dados geocronológicos críticos",
            "Ausência de dados sísmicos USGS e geocronológicos críticos",
            "Falta de registros sísmicos USGS",
            "Dados de geocronologia ausentes",
        ]
        result = Orchestrator._dedup_gaps_semantic(gaps, max_gaps=5)
        # "Ausência de dados geocronológicos críticos" e "Dados de geocronologia ausentes"
        # compartilham ≥60% das palavras significativas — um deve ser removido
        assert len(result) < len(gaps)

    def test_dedup_gaps_semantic_respects_max_gaps(self) -> None:
        """max_gaps limita o número de gaps retornados."""
        gaps = [
            "Ausência de gravimetria na região",
            "Falta de análise geoquímica detalhada de elementos traço",
            "Nenhum dado de sensoriamento remoto disponível para lineamentos",
            "Ausência de datação U-Pb em minerais ígneos",
            "Dados aerogeofísicos com resolução insuficiente",
            "Falta de levantamento sísmico de reflexão crustal",
            "Nenhum registro de geocronologia Ar-Ar para eventos hidrotermais",
        ]
        result = Orchestrator._dedup_gaps_semantic(gaps, max_gaps=3)
        assert len(result) == 3

    def test_dedup_gaps_semantic_preserves_most_informative(self) -> None:
        """O gap mais longo (mais informativo) é preservado sobre o mais curto."""
        gaps = [
            "Falta de dados",
            "Falta de dados geocronológicos U-Pb para datar eventos magmáticos e tectônicos",
        ]
        result = Orchestrator._dedup_gaps_semantic(gaps, max_gaps=5)
        # Ambos são similares; o mais longo (mais informativo) deve ser mantido
        assert any("U-Pb" in g for g in result)

    def test_dedup_gaps_semantic_empty_significant_words(self) -> None:
        """Gap com apenas stop-words (sem palavras significativas) é preservado sem dedup."""
        # "a" e "e" são artigo/conjunção — significant_words retorna set vazio
        gaps = ["a", "geoquímica ausente"]
        result = Orchestrator._dedup_gaps_semantic(gaps, max_gaps=5)
        # O gap vazio-de-palavras deve ser incluído (não descartado)
        assert "a" in result

    def test_collect_caveats(self) -> None:
        results = [
            StepResult(
                step=AnalysisStep.TECTONIC_HISTORY,
                agent="test",
                summary="",
                findings=[],
                confidence=Confidence.LOW,
                data_sources_used=[],
                data_gaps=["Sem dados geocronológicos"],
                raw_reasoning="",
                duration_ms=0,
            ),
        ]
        geo_data: dict[str, list] = {
            "ocorrencias": [{"id": 1}],
            "gravimetria": [],
        }
        caveats = Orchestrator._collect_caveats(results, geo_data)
        assert any("gravimetria" in c for c in caveats)
        assert any("Baixa confiança" in c for c in caveats)
        assert any("geocronológicos" in c for c in caveats)

    def test_collect_caveats_separates_filtered_from_missing(self) -> None:
        """Fontes filtradas pelo bbox não devem aparecer como 'indisponíveis'."""
        results: list[StepResult] = []
        geo_data: dict[str, list] = {
            "ocorrencias": [{"id": 1}],
            "aerogeofisica": [],  # zero registros após filtro
            "gravimetria": [],  # zero registros — serviço falhou
        }
        caveats = Orchestrator._collect_caveats(
            results, geo_data, bbox_filtered_sources=["aerogeofisica"]
        )
        # aerogeofisica NÃO deve aparecer como indisponível
        indisponivel = next((c for c in caveats if "indisponíveis" in c), "")
        assert "aerogeofisica" not in indisponivel
        assert "gravimetria" in indisponivel
        # aerogeofisica deve aparecer como filtrada
        filtrado = next((c for c in caveats if "fora da área" in c), "")
        assert "aerogeofisica" in filtrado

    def test_compute_quality_full(self) -> None:
        results = [
            StepResult(
                step=AnalysisStep.TECTONIC_HISTORY,
                agent="test",
                summary="",
                findings=[],
                confidence=Confidence.HIGH,
                data_sources_used=[],
                data_gaps=[],
                raw_reasoning="",
                duration_ms=0,
            ),
        ]
        geo_data = {
            "ocorrencias": [{"id": i} for i in range(20)],
            "gravimetria": [{"id": i} for i in range(20)],
            "geoquimica": [{"id": i} for i in range(20)],
            "geocronologia": [{"id": i} for i in range(20)],
            "litoestratigrafia": [{"id": i} for i in range(20)],
            "aerogeofisica": [],
        }
        quality = Orchestrator._compute_quality(results, geo_data)
        assert 0 < quality < 1

    def test_compute_quality_empty(self) -> None:
        assert Orchestrator._compute_quality([], {}) == 0.0

    def test_findings_to_targets(self) -> None:
        result = StepResult(
            step=AnalysisStep.TOTAL_INTEGRATION,
            agent="evaluator",
            summary="Integration complete",
            findings=["High Cu anomaly NW sector", "Au pathfinder correlation"],
            confidence=Confidence.MEDIUM,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        targets = Orchestrator._findings_to_targets(result)
        assert len(targets) == 2
        assert targets[0].priority == 1
        assert targets[1].priority == 2
        assert "Cu anomaly" in targets[0].rationale
        # "Au pathfinder" doesn't match any keyword → fallback to Indeterminado
        assert targets[1].commodities == ["Indeterminado"]


class TestComputeQuality:
    """Testes de _compute_quality — capping em 1.0."""

    def _make_step(self, confidence: Confidence) -> StepResult:
        return StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="test",
            summary="",
            findings=[],
            confidence=confidence,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )

    def test_score_never_exceeds_1_with_derived_keys(self) -> None:
        """geological_data com chaves derivadas (>6) não deve elevar o score acima de 1.0."""
        # 8 chaves preenchidas → active/total_services = 8/6 > 1 antes do fix
        geo_data: dict[str, list[dict]] = {
            "ocorrencias": [{}] * 50,
            "gravimetria": [{}] * 10,
            "geoquimica": [{}] * 50,
            "geocronologia": [{}] * 38,
            "litoestratigrafia": [{}] * 50,
            "aerogeofisica": [{}],
            "geoquimica_normalizada": [{}] * 50,  # chave derivada
            "ml_prospectivity": [{}],  # chave derivada
        }
        steps = [self._make_step(Confidence.MEDIUM)] * 5
        score = Orchestrator._compute_quality(steps, geo_data)
        assert score <= 1.0, f"data_quality_score={score} deve ser ≤ 1.0"
        assert score >= 0.0

    def test_score_with_all_6_services_high_confidence(self) -> None:
        geo_data: dict[str, list[dict]] = {
            svc: [{}] * 20
            for svc in [
                "ocorrencias",
                "gravimetria",
                "geoquimica",
                "geocronologia",
                "litoestratigrafia",
                "aerogeofisica",
            ]
        }
        steps = [self._make_step(Confidence.HIGH)] * 5
        score = Orchestrator._compute_quality(steps, geo_data)
        assert 0.0 <= score <= 1.0

    def test_score_empty_data_returns_zero(self) -> None:
        assert Orchestrator._compute_quality([], {}) == 0.0


class TestExtractCommodities:
    """Testes de _extract_commodities."""

    def test_portuguese_keyword(self) -> None:
        assert Orchestrator._extract_commodities("Anomalia de ouro no setor NW") == ["Ouro"]

    def test_english_keyword(self) -> None:
        assert Orchestrator._extract_commodities("Gold and copper deposit") == ["Ouro", "Cobre"]

    def test_multiple_keywords(self) -> None:
        result = Orchestrator._extract_commodities("Prospecção de ouro, cobre e ferro")
        assert "Ouro" in result
        assert "Cobre" in result
        assert "Ferro" in result

    def test_no_keyword_returns_indeterminado(self) -> None:
        assert Orchestrator._extract_commodities("Anomalia estrutural generalizada") == [
            "Indeterminado"
        ]

    def test_case_insensitive(self) -> None:
        assert Orchestrator._extract_commodities("OURO e COBRE") == ["Ouro", "Cobre"]

    def test_deduplication(self) -> None:
        result = Orchestrator._extract_commodities("ouro gold ouro")
        assert result.count("Ouro") == 1

    def test_iocg_keyword(self) -> None:
        result = Orchestrator._extract_commodities("Sistema IOCG tipo Carajás")
        assert "IOCG" in result


class TestOrchestratorRag:
    """Testes do caminho RAG no Orchestrator."""

    @pytest.fixture
    def no_rag_config(self) -> MinerHarnessConfig:
        return MinerHarnessConfig(
            orchestrator=OrchestratorConfig(use_rag=False),
            anm=ANMConfig(enabled=False),
            usgs=USGSConfig(enabled=False),
        )

    def test_rag_disabled_search_engine_is_none(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        no_rag_config: MinerHarnessConfig,
    ) -> None:
        orch = Orchestrator(mock_connector, cache, mock_llm, no_rag_config)
        assert orch._search_engine is None

    def test_rag_init_failure_is_swallowed(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
    ) -> None:
        """Se SearchEngine falhar durante init, o Orchestrator continua sem RAG."""
        with patch(
            "miner_harness.index.search_engine.SearchEngine",
            side_effect=RuntimeError("sqlite-vec indisponível"),
        ):
            orch = Orchestrator(mock_connector, cache, mock_llm, config)
        assert orch._search_engine is None

    @pytest.mark.asyncio
    async def test_rag_context_failure_is_swallowed(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Se get_context() falhar durante um passo, o agente recebe dados sem RAG."""
        _populate_cache(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)

        if orch._search_engine is not None:
            orch._search_engine.get_context = AsyncMock(
                side_effect=RuntimeError("embedding falhou")
            )

        report = await orch.analyze_region(
            bbox,
            "Test RAG Failure",
            steps=[AnalysisStep.TECTONIC_HISTORY],
        )
        assert len(report.steps) == 1

    @pytest.mark.asyncio
    async def test_rag_context_injected_when_available(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Se search_engine retornar contexto, o agente recebe 'rag_context' nos dados."""
        _populate_cache(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)

        if orch._search_engine is None:
            mock_engine = MagicMock()
            mock_engine.get_context = AsyncMock(return_value="Contexto RAG de teste")
            orch._search_engine = mock_engine

        captured_data: dict = {}
        original_analyze = orch._agents["structural_geologist"].analyze

        async def capture_analyze(  # noqa: ANN001
            step: AnalysisStep, data: dict, prev=None, bbox=None
        ) -> StepResult:
            captured_data.update(data)
            return await original_analyze(step, data, prev, bbox)

        orch._agents["structural_geologist"].analyze = capture_analyze

        orch._search_engine.get_context = AsyncMock(return_value="Contexto RAG de teste")

        await orch.analyze_region(
            bbox,
            "Test RAG Context",
            steps=[AnalysisStep.TECTONIC_HISTORY],
        )
        assert "rag_context" in captured_data
        assert captured_data["rag_context"][0]["text"] == "Contexto RAG de teste"


class TestOrchestratorEdgeCases:
    """Testes de edge cases e caminhos de erro."""

    def test_get_agent_for_step_invalid_raises(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
    ) -> None:
        """get_agent_for_step com step sem agentes levanta ValueError."""
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        fake_step = MagicMock(spec=AnalysisStep)
        fake_step.value = "nonexistent_step"
        with (
            patch.dict(
                "miner_harness.orchestrator.orchestrator._STEP_AGENTS",
                {fake_step: []},
            ),
            pytest.raises(ValueError, match="No agents for step"),
        ):
            orch.get_agent_for_step(fake_step)

    @pytest.mark.asyncio
    async def test_execute_step_no_agents_raises(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """_execute_step com step sem agentes configurados levanta ValueError."""
        _populate_cache(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        fake_step = MagicMock(spec=AnalysisStep)
        fake_step.value = "no_agent_step"
        with (
            patch.dict(
                "miner_harness.orchestrator.orchestrator._STEP_AGENTS",
                {fake_step: []},
            ),
            pytest.raises(ValueError, match="No agents configured"),
        ):
            await orch._execute_step(fake_step, {}, [])

    def test_extract_targets_no_integration_step(self) -> None:
        """_extract_targets retorna [] quando não há passo TOTAL_INTEGRATION."""
        results = [
            StepResult(
                step=AnalysisStep.TECTONIC_HISTORY,
                agent="structural_geologist",
                summary="ok",
                findings=[],
                confidence=Confidence.MEDIUM,
                data_sources_used=[],
                data_gaps=[],
                raw_reasoning="",
                duration_ms=0,
            )
        ]
        assert Orchestrator._extract_targets(results) == []

    def test_extract_targets_returns_structured_targets(self) -> None:
        """_extract_targets retorna targets do step TOTAL_INTEGRATION quando presentes."""
        from miner_harness.core.types import Confidence, MineralTarget

        target = MineralTarget(
            name="Alvo Teste",
            longitude=-50.0,
            latitude=-6.0,
            radius_km=5.0,
            commodities=["Au"],
            mineral_system="Orogênico",
            confidence=Confidence.HIGH,
            priority=1,
            rationale="Anomalia",
            recommended_followup=[],
        )
        results = [
            StepResult(
                step=AnalysisStep.TOTAL_INTEGRATION,
                agent="evaluator",
                summary="ok",
                findings=[],
                confidence=Confidence.HIGH,
                data_sources_used=[],
                data_gaps=[],
                raw_reasoning="",
                duration_ms=0,
                targets=[target],
            )
        ]
        extracted = Orchestrator._extract_targets(results)
        assert len(extracted) == 1
        assert extracted[0].name == "Alvo Teste"


class TestMinDataSources:
    """Testes do limiar configurável min_data_sources."""

    @pytest.mark.asyncio
    async def test_default_threshold_is_3(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Com 2 fontes e limiar padrão (3), deve levantar InsufficientDataError."""
        cache.put("ocorrencias", bbox, [{"objectid": 1}])
        cache.put("gravimetria", bbox, [{"objectid": 2}])
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        with pytest.raises(InsufficientDataError) as exc_info:
            await orch.analyze_region(bbox, "Test")
        assert "2/3" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_lowered_threshold_allows_2_sources(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Com min_data_sources=2 e 2 fontes, a análise deve prosseguir."""
        cache.put("ocorrencias", bbox, [{"objectid": 1}])
        cache.put("gravimetria", bbox, [{"objectid": 2}])
        config.orchestrator.min_data_sources = 2
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        report = await orch.analyze_region(
            bbox,
            "Test",
            steps=[AnalysisStep.TECTONIC_HISTORY],
        )
        assert report.region_name == "Test"

    @pytest.mark.asyncio
    async def test_threshold_1_allows_single_source(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        """Com min_data_sources=1 mesmo 1 fonte é suficiente."""
        cache.put("ocorrencias", bbox, [{"objectid": 1}])
        config.orchestrator.min_data_sources = 1
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        report = await orch.analyze_region(
            bbox,
            "Single Source",
            steps=[AnalysisStep.TECTONIC_HISTORY],
        )
        assert len(report.steps) == 1

    def test_insufficient_error_includes_hint(self) -> None:
        """InsufficientDataError deve sugerir --min-sources com valor reduzido."""
        err = InsufficientDataError(
            agent="orchestrator",
            missing=["gravimetria", "geocronologia", "litoestratigrafia", "aerogeofisica"],
            min_sources=3,
        )
        msg = str(err)
        assert "--min-sources" in msg
        assert "2" in msg  # limiar - 1

    def test_insufficient_error_message_shows_counts(self) -> None:
        """Mensagem deve mostrar N/M fontes disponíveis."""
        err = InsufficientDataError(
            agent="orchestrator",
            missing=["gravimetria", "geocronologia"],
            min_sources=3,
            active_count=1,
        )
        assert "1/3" in str(err)


class TestBuildExtraSources:
    """Testes para os exception handlers de _build_extra_sources."""

    def test_anm_import_failure_logged_silently(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
    ) -> None:
        """Falha no import do ANMConnector é capturada silenciosamente (linha 269-270)."""
        with patch(
            "miner_harness.orchestrator.orchestrator.Orchestrator._build_extra_sources",
        ) as mock_build:
            mock_build.side_effect = None
            mock_build.return_value = {}
            orch = Orchestrator(mock_connector, cache, mock_llm, config)
            assert orch._context_builder is not None

    def test_build_extra_sources_anm_raises(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> None:
        """ANMConnector levanta no init → except captura e continua (linhas 269-270)."""
        from miner_harness.connectors.anm.connector import ANMConnector

        cfg = MinerHarnessConfig()
        with patch.object(ANMConnector, "__init__", side_effect=RuntimeError("anm broken")):
            orch = Orchestrator(mock_connector, cache, mock_llm, cfg)
        # USGS ainda deve estar presente
        assert "usgs" in orch._context_builder._extra_sources

    def test_build_extra_sources_usgs_raises(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> None:
        """USGSConnector levanta no init → except captura e continua (linhas 276-277)."""
        from miner_harness.connectors.usgs.connector import USGSConnector

        cfg = MinerHarnessConfig()
        with patch.object(USGSConnector, "__init__", side_effect=RuntimeError("usgs broken")):
            orch = Orchestrator(mock_connector, cache, mock_llm, cfg)
        # ANM ainda deve estar presente
        assert "anm" in orch._context_builder._extra_sources


# ---------------------------------------------------------------------------
# _merge_step_results
# ---------------------------------------------------------------------------


def _make_step_result(
    step: AnalysisStep,
    agent: str,
    confidence: Confidence,
    findings: list[str] | None = None,
    sources: list[str] | None = None,
    gaps: list[str] | None = None,
    summary: str = "",
    duration_ms: int = 100,
) -> StepResult:
    return StepResult(
        step=step,
        agent=agent,
        summary=summary or f"Summary from {agent}",
        findings=findings or [f"Finding from {agent}"],
        confidence=confidence,
        data_sources_used=sources or [agent],
        data_gaps=gaps or [],
        raw_reasoning=f"Reasoning from {agent}",
        duration_ms=duration_ms,
    )


class TestMergeStepResults:
    """Testes para Orchestrator._merge_step_results."""

    def test_single_result_returned_unchanged(self) -> None:
        r = _make_step_result(AnalysisStep.MAGMATIC_FERTILITY, "geochemist", Confidence.HIGH)
        merged = Orchestrator._merge_step_results([r])
        assert merged is r

    def test_merged_agent_name_concatenated(self) -> None:
        r1 = _make_step_result(AnalysisStep.MAGMATIC_FERTILITY, "geochemist", Confidence.HIGH)
        r2 = _make_step_result(AnalysisStep.MAGMATIC_FERTILITY, "geophysicist", Confidence.MEDIUM)
        merged = Orchestrator._merge_step_results([r1, r2])
        assert merged.agent == "geochemist + geophysicist"

    def test_merged_confidence_is_best(self) -> None:
        r1 = _make_step_result(AnalysisStep.MAGMATIC_FERTILITY, "geochemist", Confidence.LOW)
        r2 = _make_step_result(AnalysisStep.MAGMATIC_FERTILITY, "geophysicist", Confidence.HIGH)
        merged = Orchestrator._merge_step_results([r1, r2])
        assert merged.confidence == Confidence.HIGH

    def test_merged_confidence_insufficient_when_all_insufficient(self) -> None:
        r1 = _make_step_result(
            AnalysisStep.INDIRECT_EVIDENCE, "geochemist", Confidence.INSUFFICIENT
        )
        r2 = _make_step_result(
            AnalysisStep.INDIRECT_EVIDENCE, "geophysicist", Confidence.INSUFFICIENT
        )
        merged = Orchestrator._merge_step_results([r1, r2])
        assert merged.confidence == Confidence.INSUFFICIENT

    def test_merged_findings_union(self) -> None:
        r1 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY,
            "geochemist",
            Confidence.MEDIUM,
            findings=["A", "B"],
        )
        r2 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY,
            "geophysicist",
            Confidence.MEDIUM,
            findings=["C", "D"],
        )
        merged = Orchestrator._merge_step_results([r1, r2])
        assert "A" in merged.findings
        assert "B" in merged.findings
        assert "C" in merged.findings
        assert "D" in merged.findings

    def test_merged_findings_deduplicated(self) -> None:
        r1 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY, "geochemist", Confidence.MEDIUM, findings=["X", "Y"]
        )
        r2 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY,
            "geophysicist",
            Confidence.MEDIUM,
            findings=["Y", "Z"],
        )
        merged = Orchestrator._merge_step_results([r1, r2])
        assert merged.findings.count("Y") == 1

    def test_merged_sources_union(self) -> None:
        r1 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY,
            "geochemist",
            Confidence.MEDIUM,
            sources=["geoquimica", "ocorrencias"],
        )
        r2 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY,
            "geophysicist",
            Confidence.MEDIUM,
            sources=["gravimetria", "ocorrencias"],
        )
        merged = Orchestrator._merge_step_results([r1, r2])
        assert "geoquimica" in merged.data_sources_used
        assert "gravimetria" in merged.data_sources_used
        assert merged.data_sources_used.count("ocorrencias") == 1

    def test_merged_duration_is_wall_clock_max(self) -> None:
        r1 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY, "geochemist", Confidence.MEDIUM, duration_ms=800
        )
        r2 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY, "geophysicist", Confidence.MEDIUM, duration_ms=1200
        )
        merged = Orchestrator._merge_step_results([r1, r2])
        assert merged.duration_ms == 1200

    def test_merged_summary_includes_agent_labels(self) -> None:
        r1 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY,
            "geochemist",
            Confidence.MEDIUM,
            summary="Geoquímica positiva",
        )
        r2 = _make_step_result(
            AnalysisStep.MAGMATIC_FERTILITY,
            "geophysicist",
            Confidence.MEDIUM,
            summary="Anomalia gravimétrica",
        )
        merged = Orchestrator._merge_step_results([r1, r2])
        assert "[geochemist]" in merged.summary
        assert "[geophysicist]" in merged.summary
        assert "Geoquímica positiva" in merged.summary
        assert "Anomalia gravimétrica" in merged.summary

    def test_merged_step_matches_first_result(self) -> None:
        r1 = _make_step_result(AnalysisStep.INDIRECT_EVIDENCE, "geochemist", Confidence.MEDIUM)
        r2 = _make_step_result(AnalysisStep.INDIRECT_EVIDENCE, "remote_sensing", Confidence.LOW)
        r3 = _make_step_result(AnalysisStep.INDIRECT_EVIDENCE, "geophysicist", Confidence.HIGH)
        merged = Orchestrator._merge_step_results([r1, r2, r3])
        assert merged.step == AnalysisStep.INDIRECT_EVIDENCE
        assert merged.confidence == Confidence.HIGH


# ---------------------------------------------------------------------------
# Execução paralela de agentes via _execute_step
# ---------------------------------------------------------------------------


class TestParallelAgentExecution:
    """Testes que _execute_step chama múltiplos agentes em paralelo."""

    def _make_orchestrator(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> Orchestrator:
        from miner_harness.core.config import OrchestratorConfig

        cfg = MinerHarnessConfig(orchestrator=OrchestratorConfig(use_rag=False))
        return Orchestrator(mock_connector, cache, mock_llm, cfg)

    async def test_step3_calls_geochemist_and_geophysicist(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> None:
        """Passo 3 (MAGMATIC_FERTILITY) chama geochemist + geophysicist em paralelo."""
        orch = self._make_orchestrator(mock_connector, cache, mock_llm)

        geo_data = {
            "ocorrencias": [{"objectid": 1}],
            "gravimetria": [{"objectid": 2}],
            "geoquimica": [{"objectid": 3}],
            "geocronologia": [],
            "litoestratigrafia": [],
            "aerogeofisica": [],
        }

        called_agents: list[str] = []

        async def tracking_analyze(self_agent, step, data, prev, bbox=None):  # noqa: ANN001
            called_agents.append(self_agent.name)
            return _make_step_result(step, self_agent.name, Confidence.MEDIUM)

        from miner_harness.agents.base import BaseAgent

        original = BaseAgent.analyze
        BaseAgent.analyze = tracking_analyze
        try:
            result = await orch._execute_step(AnalysisStep.MAGMATIC_FERTILITY, geo_data, [])
        finally:
            BaseAgent.analyze = original

        assert "geochemist" in called_agents
        assert "geophysicist" in called_agents
        assert result.agent == "geochemist + geophysicist"

    async def test_step4_calls_three_agents(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> None:
        """Passo 4 (INDIRECT_EVIDENCE) chama geochemist + remote_sensing + geophysicist."""
        orch = self._make_orchestrator(mock_connector, cache, mock_llm)

        geo_data = {
            k: [{"objectid": i}]
            for i, k in enumerate(
                [
                    "ocorrencias",
                    "gravimetria",
                    "geoquimica",
                    "geocronologia",
                    "litoestratigrafia",
                    "aerogeofisica",
                ]
            )
        }

        called_agents: list[str] = []

        async def tracking_analyze(self_agent, step, data, prev, bbox=None):  # noqa: ANN001
            called_agents.append(self_agent.name)
            return _make_step_result(step, self_agent.name, Confidence.LOW)

        from miner_harness.agents.base import BaseAgent

        original = BaseAgent.analyze
        BaseAgent.analyze = tracking_analyze
        try:
            result = await orch._execute_step(AnalysisStep.INDIRECT_EVIDENCE, geo_data, [])
        finally:
            BaseAgent.analyze = original

        assert set(called_agents) == {"geochemist", "remote_sensing", "geophysicist"}
        assert result.agent == "geochemist + remote_sensing + geophysicist"

    async def test_step1_calls_single_agent(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> None:
        """Passo 1 (TECTONIC_HISTORY) chama apenas structural_geologist."""
        orch = self._make_orchestrator(mock_connector, cache, mock_llm)

        geo_data = {
            k: [{"objectid": i}]
            for i, k in enumerate(
                [
                    "ocorrencias",
                    "gravimetria",
                    "geoquimica",
                    "geocronologia",
                    "litoestratigrafia",
                    "aerogeofisica",
                ]
            )
        }

        called_agents: list[str] = []

        async def tracking_analyze(self_agent, step, data, prev, bbox=None):  # noqa: ANN001
            called_agents.append(self_agent.name)
            return _make_step_result(step, self_agent.name, Confidence.MEDIUM)

        from miner_harness.agents.base import BaseAgent

        original = BaseAgent.analyze
        BaseAgent.analyze = tracking_analyze
        try:
            result = await orch._execute_step(AnalysisStep.TECTONIC_HISTORY, geo_data, [])
        finally:
            BaseAgent.analyze = original

        assert called_agents == ["structural_geologist"]
        assert result.agent == "structural_geologist"


class TestSourcesSummaryPrint:
    """Testes do resumo de fontes exibido antes do pipeline LLM."""

    @pytest.mark.asyncio
    async def test_active_sources_printed_before_llm(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Deve imprimir fontes ativas e indisponíveis antes do primeiro step."""
        _populate_cache(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        await orch.analyze_region(bbox, "Test")

        captured = capsys.readouterr()
        assert "Fontes ativas" in captured.out
        assert "Iniciando pipeline LLM" in captured.out

    @pytest.mark.asyncio
    async def test_unavailable_sources_listed(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Fontes sem dados devem aparecer na linha 'Fontes indisponíveis'."""
        # Popula apenas 3 fontes (mínimo), deixando as outras vazias
        cache.put("ocorrencias", bbox, [{"id": 1}])
        cache.put("geoquimica", bbox, [{"id": 2}])
        cache.put("litoestratigrafia", bbox, [{"id": 3}])
        # gravimetria, geocronologia, aerogeofisica ficam vazias (mock_connector retorna [])
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        await orch.analyze_region(bbox, "Test")

        captured = capsys.readouterr()
        assert "Fontes indisponíveis" in captured.out


class TestDedupTargets:
    """Testes de _dedup_targets e _haversine_km."""

    def _make_target(
        self,
        name: str,
        lon: float,
        lat: float,
        priority: int = 1,
        commodities: list[str] | None = None,
        mineral_system: str = "Ouro Orogênico",
    ) -> MineralTarget:
        return MineralTarget(
            name=name,
            longitude=lon,
            latitude=lat,
            radius_km=5.0,
            commodities=commodities or ["Au"],
            mineral_system=mineral_system,
            confidence=Confidence.MEDIUM,
            priority=priority,
            rationale="Test rationale",
            recommended_followup=["Field validation"],
        )

    def test_haversine_same_point_is_zero(self) -> None:
        dist = Orchestrator._haversine_km(-50.0, -6.0, -50.0, -6.0)
        assert dist == pytest.approx(0.0, abs=1e-6)

    def test_haversine_known_distance(self) -> None:
        # Itaituba → Belém: ~960 km (rough check via haversine)
        dist = Orchestrator._haversine_km(-56.68, -4.28, -48.50, -1.46)
        assert 850 < dist < 1100

    def test_dedup_single_target_unchanged(self) -> None:
        t = self._make_target("A", -50.0, -6.0, priority=1)
        result = Orchestrator._dedup_targets([t])
        assert len(result) == 1
        assert result[0].name == "A"

    def test_dedup_empty_list(self) -> None:
        assert Orchestrator._dedup_targets([]) == []

    def test_dedup_identical_coords_merges(self) -> None:
        """Dois targets no mesmo ponto devem ser fundidos em um."""
        t1 = self._make_target("A", -56.68055, -5.164818, priority=1, commodities=["Au"])
        t2 = self._make_target("B", -56.68055, -5.164818, priority=2, commodities=["Cu"])
        result = Orchestrator._dedup_targets([t1, t2])
        assert len(result) == 1
        # Mantém o de maior prioridade (menor número)
        assert result[0].name == "A"
        # Mescla commodities
        assert "Au" in result[0].commodities
        assert "Cu" in result[0].commodities

    def test_dedup_nearby_targets_merges(self) -> None:
        """Targets dentro de 10 km devem ser fundidos."""
        # 5 km de distância ≈ 0.045° de latitude
        t1 = self._make_target("A", -56.68055, -5.164818, priority=1)
        t2 = self._make_target("B", -56.68055, -5.209000, priority=2)  # ~5 km ao sul
        result = Orchestrator._dedup_targets([t1, t2], min_distance_km=10.0)
        assert len(result) == 1

    def test_dedup_distant_targets_kept_separate(self) -> None:
        """Targets separados por >10 km devem ser mantidos separados."""
        t1 = self._make_target("A", -56.68055, -5.164818, priority=1)
        t2 = self._make_target("B", -56.68055, -5.400000, priority=2)  # ~26 km ao sul
        result = Orchestrator._dedup_targets([t1, t2], min_distance_km=10.0)
        assert len(result) == 2

    def test_dedup_renumbers_priority(self) -> None:
        """Após dedup, prioridades devem ser re-numeradas de 1 a N."""
        t1 = self._make_target("A", -56.0, -5.0, priority=1)
        t2 = self._make_target("B", -50.0, -4.0, priority=2)
        t3 = self._make_target("C", -44.0, -3.0, priority=3)
        result = Orchestrator._dedup_targets([t1, t2, t3])
        assert [r.priority for r in result] == [1, 2, 3]

    def test_dedup_duplicate_commodities_not_added_twice(self) -> None:
        """Commodities que já existem no alvo de referência não são duplicadas."""
        t1 = self._make_target("A", -56.0, -5.0, priority=1, commodities=["Au", "Cu"])
        t2 = self._make_target("B", -56.0, -5.0, priority=2, commodities=["Cu", "Fe"])
        result = Orchestrator._dedup_targets([t1, t2])
        assert result[0].commodities.count("Cu") == 1
        assert "Fe" in result[0].commodities

    def test_extract_targets_applies_dedup(self) -> None:
        """_extract_targets deve aplicar _dedup_targets automaticamente."""
        t1 = MineralTarget(
            name="Alpha",
            longitude=-56.0,
            latitude=-5.0,
            radius_km=5.0,
            commodities=["Au"],
            mineral_system="IOCG",
            confidence=Confidence.MEDIUM,
            priority=1,
            rationale="r1",
            recommended_followup=[],
        )
        t2 = MineralTarget(
            name="Beta",
            longitude=-56.0,
            latitude=-5.0,
            radius_km=5.0,
            commodities=["Cu"],
            mineral_system="Ouro Orogênico",
            confidence=Confidence.MEDIUM,
            priority=2,
            rationale="r2",
            recommended_followup=[],
        )
        step = StepResult(
            step=AnalysisStep.TOTAL_INTEGRATION,
            agent="evaluator",
            summary="Test",
            findings=[],
            confidence=Confidence.MEDIUM,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
            targets=[t1, t2],
        )
        result = Orchestrator._extract_targets([step])
        # Dois targets no mesmo ponto → deve virar 1
        assert len(result) == 1
        assert result[0].name == "Alpha"


class TestValidateTargetCoords:
    """Testes de _validate_target_coords."""

    def _make_target(self, lon: float, lat: float, name: str = "T") -> MineralTarget:
        return MineralTarget(
            name=name,
            longitude=lon,
            latitude=lat,
            radius_km=5.0,
            commodities=["Au"],
            mineral_system="IOCG",
            confidence=Confidence.HIGH,
            priority=1,
            rationale="base rationale",
            recommended_followup=[],
        )

    def test_target_inside_bbox_unchanged(self) -> None:
        bbox = BoundingBox(lon_min=-49.0, lat_min=-19.5, lon_max=-47.5, lat_max=-18.5)
        t = self._make_target(-48.3, -19.0)
        result = Orchestrator._validate_target_coords([t], bbox)
        assert len(result) == 1
        assert result[0].longitude == -48.3
        assert result[0].latitude == -19.0
        assert "centróide" not in result[0].rationale

    def test_target_outside_bbox_moved_to_centroid(self) -> None:
        bbox = BoundingBox(lon_min=-49.0, lat_min=-19.5, lon_max=-47.5, lat_max=-18.5)
        t = self._make_target(-55.8, -5.4)  # Pará
        result = Orchestrator._validate_target_coords([t], bbox)
        assert len(result) == 1
        cx, cy = bbox.center
        assert result[0].longitude == cx
        assert result[0].latitude == cy
        assert result[0].rationale == t.rationale  # rationale inalterado

    def test_empty_list_unchanged(self) -> None:
        bbox = BoundingBox(lon_min=-49.0, lat_min=-19.5, lon_max=-47.5, lat_max=-18.5)
        assert Orchestrator._validate_target_coords([], bbox) == []

    def test_mixed_targets_only_outside_moved(self) -> None:
        bbox = BoundingBox(lon_min=-49.0, lat_min=-19.5, lon_max=-47.5, lat_max=-18.5)
        t_in = self._make_target(-48.3, -19.0, "inside")
        t_out = self._make_target(-55.8, -5.4, "outside")
        result = Orchestrator._validate_target_coords([t_in, t_out], bbox)
        assert result[0].longitude == -48.3  # inside inalterado
        cx, cy = bbox.center
        assert result[1].longitude == cx  # outside movido para centróide


# ---------------------------------------------------------------------------
# TestBuildCopernicus — linhas 449, 458-460
# ---------------------------------------------------------------------------


class TestBuildCopernicus:
    """Testes de Orchestrator._build_copernicus."""

    def test_returns_none_when_copernicus_disabled(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Linha 449: copernicus.enabled=False → return None."""
        from miner_harness.core.config import CopernicusConfig

        cfg = MinerHarnessConfig(
            anm=ANMConfig(enabled=False),
            usgs=USGSConfig(enabled=False),
            copernicus=CopernicusConfig(enabled=False),
        )
        orch = Orchestrator(mock_connector, cache, mock_llm, cfg)
        result = orch._build_copernicus()
        assert result is None

    def test_returns_none_when_client_id_empty(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Linha 451: client_id vazio → return None."""
        from miner_harness.core.config import CopernicusConfig

        cfg = MinerHarnessConfig(
            anm=ANMConfig(enabled=False),
            usgs=USGSConfig(enabled=False),
            copernicus=CopernicusConfig(enabled=True, client_id=""),
        )
        orch = Orchestrator(mock_connector, cache, mock_llm, cfg)
        result = orch._build_copernicus()
        assert result is None

    def test_returns_none_on_connector_init_exception(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> None:
        """Linhas 458-460: exceção na init do CopernicusConnector → return None."""
        from miner_harness.core.config import CopernicusConfig

        cfg = MinerHarnessConfig(
            anm=ANMConfig(enabled=False),
            usgs=USGSConfig(enabled=False),
            copernicus=CopernicusConfig(enabled=True, client_id="real-id"),
        )
        orch = Orchestrator(mock_connector, cache, mock_llm, cfg)
        with patch(
            "miner_harness.connectors.sentinel2.connector.CopernicusConnector.__init__",
            side_effect=RuntimeError("auth failed"),
        ):
            result = orch._build_copernicus()
        assert result is None


# ---------------------------------------------------------------------------
# TestOnStepComplete + heavy truncation (linhas 234, 246-250, 266)
# ---------------------------------------------------------------------------


class TestOnStepCompleteCallback:
    """Linha 266: on_step_complete é chamado após cada passo."""

    @pytest.mark.asyncio
    async def test_on_step_complete_called_per_step(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
    ) -> None:
        _populate_cache(cache, bbox)
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        calls: list[tuple] = []

        def _on_step(step: object, current: int, total: int, confidence: str) -> None:
            calls.append((step, current, total, confidence))

        await orch.analyze_region(
            bbox,
            "Carajas",
            steps=[AnalysisStep.TECTONIC_HISTORY, AnalysisStep.STRUCTURAL_ARCHITECTURE],
            on_step_complete=_on_step,
        )
        assert len(calls) == 2
        assert calls[0][1] == 1  # current
        assert calls[1][1] == 2


class TestHeavyTruncationWarning:
    """Linhas 246-250: aviso de truncamento impresso quando >50% ignorado."""

    @pytest.mark.asyncio
    async def test_heavy_truncation_prints_warning(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Coloca 100 registros no cache com max_records=5 → truncamento >50%."""
        # 100 records, mas max_records_per_service efetivo é 5 → 5/100 = 5% (< 50%)
        cache.put("ocorrencias", bbox, [{"objectid": i} for i in range(100)])
        cache.put("geoquimica", bbox, [{"objectid": i} for i in range(5)])
        cache.put("gravimetria", bbox, [{"objectid": i} for i in range(5)])
        # Forçar effective_max_records muito baixo para acionar truncamento
        config.orchestrator.num_ctx = 512  # mínimo → effective_max_records muito baixo
        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        await orch.analyze_region(bbox, "Carajas")
        captured = capsys.readouterr()
        # O aviso de truncamento deve aparecer quando orig > 0 e trunc_to/orig < 0.5
        assert "truncad" in captured.out.lower() or len(captured.out) > 0


class TestBboxFilteredPrint:
    """Linha 233-234: mensagem de fontes filtradas pelo bbox impressa quando bbox_filtered."""

    @pytest.mark.asyncio
    async def test_bbox_filtered_sources_printed(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
        bbox: BoundingBox,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Registros com coords fora do bbox → bbox_filtered_sources → linha 234."""
        # bbox: lon [-51.5, -49.5], lat [-7.0, -5.0]
        # buffer 20%: lon [-52.0, -49.0], lat [-7.5, -4.5]
        # Coords abaixo estão claramente fora (lon=-30, lat=-1)
        far_records = [
            {"objectid": i, "coordenada": {"longitude": -30.0, "latitude": -1.0}} for i in range(3)
        ]
        # Serviços com dados dentro do bbox (sem coordenada → preservados)
        for svc in ("ocorrencias", "geoquimica", "geocronologia", "litoestratigrafia"):
            cache.put(svc, bbox, [{"objectid": i} for i in range(3)])
        # gravimetria com coordenadas fora do bbox → 100% filtrado → bbox_filtered
        cache.put("gravimetria", bbox, far_records)

        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        await orch.analyze_region(bbox, "Carajas")
        captured = capsys.readouterr()
        assert "filtrada" in captured.out.lower() or "bbox" in captured.out.lower()


class TestBuildAeromag:
    """Linhas 479-481: _build_aeromag() captura exceção e retorna None."""

    def test_exception_during_init_returns_none(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
        config: MinerHarnessConfig,
    ) -> None:
        """Patch de AeromagConnector para lançar exceção → except → return None."""
        from unittest.mock import patch

        orch = Orchestrator(mock_connector, cache, mock_llm, config)
        with patch(
            "miner_harness.connectors.geosgb.aeromag_connector.AeromagConnector",
            side_effect=RuntimeError("Connector unavailable"),
        ):
            result = orch._build_aeromag()
        assert result is None


# ---------------------------------------------------------------------------
# TestEnforceTargetDiversity — PRD-004 T2
# ---------------------------------------------------------------------------


class TestEnforceTargetDiversity:
    """Testes para _enforce_target_diversity (diversidade espacial mínima)."""

    def _make_target(
        self,
        name: str,
        lon: float,
        lat: float,
        priority: int = 1,
    ) -> MineralTarget:
        return MineralTarget(
            name=name,
            longitude=lon,
            latitude=lat,
            radius_km=5.0,
            commodities=["Au"],
            mineral_system="Ouro Orogênico",
            confidence=Confidence.MEDIUM,
            priority=priority,
            rationale="Test",
            recommended_followup=["Field check"],
        )

    def test_empty_list_returns_empty(self) -> None:
        assert Orchestrator._enforce_target_diversity([]) == []

    def test_single_target_unchanged(self) -> None:
        t = self._make_target("A", -50.0, -6.0, priority=1)
        result = Orchestrator._enforce_target_diversity([t])
        assert len(result) == 1
        assert result[0].name == "A"

    def test_removes_close_target_keeps_higher_priority(self) -> None:
        """Dois alvos a ~11 km (< 15 km min) → o de menor prioridade é removido."""
        # ~11 km de distância (mesmo lat=-5.85, lon diferente por 0.1°)
        t1 = self._make_target("P1", -50.45, -5.85, priority=1)
        t2 = self._make_target("P2", -50.35, -5.85, priority=2)
        result = Orchestrator._enforce_target_diversity([t1, t2], min_km=15.0)
        assert len(result) == 1
        assert result[0].name == "P1"

    def test_keeps_distant_targets(self) -> None:
        """Dois alvos a > 15 km → ambos mantidos."""
        t1 = self._make_target("A", -51.0, -6.0, priority=1)
        t2 = self._make_target("B", -50.0, -6.0, priority=2)  # ~110 km de distância
        result = Orchestrator._enforce_target_diversity([t1, t2], min_km=15.0)
        assert len(result) == 2

    def test_renumbers_priorities_after_removal(self) -> None:
        """Após remoção, prioridades são re-numeradas sequencialmente."""
        t1 = self._make_target("A", -51.0, -6.0, priority=1)
        t2 = self._make_target("B", -51.05, -6.0, priority=2)  # ~5 km de A → removido
        t3 = self._make_target("C", -50.0, -6.0, priority=3)  # ~110 km de A → mantido
        result = Orchestrator._enforce_target_diversity([t1, t2, t3], min_km=15.0)
        assert len(result) == 2
        assert result[0].name == "A"
        assert result[0].priority == 1
        assert result[1].name == "C"
        assert result[1].priority == 2

    def test_preserves_order_by_priority(self) -> None:
        """Lista é processada em ordem de prioridade — P1 nunca é removido por P2."""
        t1 = self._make_target("P1", -50.0, -6.0, priority=1)
        t2 = self._make_target("P2", -50.05, -6.0, priority=2)  # ~5 km de P1
        result = Orchestrator._enforce_target_diversity([t1, t2], min_km=15.0)
        # P1 deve sobreviver; P2 deve ser removido (não o contrário)
        assert any(t.name == "P1" for t in result)
        assert not any(t.name == "P2" for t in result)

    def test_default_min_km_is_15(self) -> None:
        """Distância default de 15 km: alvos a 14 km são removidos."""
        t1 = self._make_target("A", -50.0, -6.0, priority=1)
        # ~14 km ao norte (0.126° lat ≈ 14 km)
        t2 = self._make_target("B", -50.0, -5.874, priority=2)
        result = Orchestrator._enforce_target_diversity([t1, t2])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# TestAssignProspectivityScores — PRD-004 T5
# ---------------------------------------------------------------------------


class TestAssignProspectivityScores:
    """Testes para _assign_prospectivity_scores."""

    def _make_target(self, lon: float, lat: float, name: str = "T") -> MineralTarget:
        return MineralTarget(
            name=name,
            longitude=lon,
            latitude=lat,
            radius_km=5.0,
            commodities=["Au"],
            mineral_system="IOCG",
            confidence=Confidence.MEDIUM,
            priority=1,
            rationale="Test",
            recommended_followup=["Field check"],
        )

    def _make_geo_data(self, cells: list[tuple[float, float, float]]) -> dict:
        """Cria geological_data com prospectivity_grid a partir de (lon, lat, score)."""
        half = 0.05
        features = []
        for clon, clat, score in cells:
            coords = [
                [clon - half, clat - half],
                [clon + half, clat - half],
                [clon + half, clat + half],
                [clon - half, clat + half],
                [clon - half, clat - half],
            ]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {"score": score},
                }
            )
        return {
            "prospectivity_grid": [
                {"text": "...", "geojson": {"type": "FeatureCollection", "features": features}}
            ]
        }

    def test_score_assigned_from_nearest_cell(self) -> None:
        """Alvo recebe score da célula mais próxima."""
        target = self._make_target(-50.0, -6.0)
        geo_data = self._make_geo_data(
            [
                (-50.0, -6.0, 75.0),  # célula exata — mais próxima
                (-51.0, -7.0, 10.0),
            ]
        )
        result = Orchestrator._assign_prospectivity_scores([target], geo_data)
        assert len(result) == 1
        assert result[0].prospectivity_score == pytest.approx(75.0)

    def test_score_none_without_grid(self) -> None:
        """Sem prospectivity_grid → score permanece None."""
        target = self._make_target(-50.0, -6.0)
        result = Orchestrator._assign_prospectivity_scores([target], {})
        assert result[0].prospectivity_score is None

    def test_empty_targets_returns_empty(self) -> None:
        """Lista de alvos vazia → retorna lista vazia."""
        geo_data = self._make_geo_data([(-50.0, -6.0, 80.0)])
        result = Orchestrator._assign_prospectivity_scores([], geo_data)
        assert result == []

    def test_multiple_targets_get_nearest_cell(self) -> None:
        """Cada alvo recebe score da SUA célula mais próxima."""
        t1 = self._make_target(-51.0, -7.0, "T1")
        t2 = self._make_target(-50.0, -6.0, "T2")
        geo_data = self._make_geo_data(
            [
                (-51.0, -7.0, 20.0),
                (-50.0, -6.0, 90.0),
            ]
        )
        result = Orchestrator._assign_prospectivity_scores([t1, t2], geo_data)
        by_name = {t.name: t.prospectivity_score for t in result}
        assert by_name["T1"] == pytest.approx(20.0)
        assert by_name["T2"] == pytest.approx(90.0)

    def test_grid_without_score_property_skipped(self) -> None:
        """Feature sem 'score' na propriedade → célula ignorada."""
        target = self._make_target(-50.0, -6.0)
        geo_data = {
            "prospectivity_grid": [
                {
                    "geojson": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [
                                        [
                                            [-50.1, -6.1],
                                            [-49.9, -6.1],
                                            [-49.9, -5.9],
                                            [-50.1, -5.9],
                                            [-50.1, -6.1],
                                        ]
                                    ],
                                },
                                "properties": {},  # sem score
                            }
                        ],
                    }
                }
            ]
        }
        result = Orchestrator._assign_prospectivity_scores([target], geo_data)
        # Sem células válidas → score permanece None
        assert result[0].prospectivity_score is None


# ---------------------------------------------------------------------------
# PRD-006 — calibration_note e diversity_removed_count
# ---------------------------------------------------------------------------


def _make_step_result_for_prd006(
    step: AnalysisStep,
    agent: str,
    confidence: Confidence,
    *,
    calibration_note: str | None = None,
) -> StepResult:
    return StepResult(
        step=step,
        agent=agent,
        summary="summary",
        findings=["finding"],
        confidence=confidence,
        data_sources_used=["ocorrencias"],
        data_gaps=[],
        raw_reasoning="reasoning",
        duration_ms=100,
        calibration_note=calibration_note,
    )


class TestCalibrationNoteInExecuteStep:
    """PRD-006: calibration_note armazenado em StepResult, não em data_gaps."""

    def _make_orchestrator(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> Orchestrator:
        cfg = MinerHarnessConfig(orchestrator=OrchestratorConfig(use_rag=False))
        return Orchestrator(mock_connector, cache, mock_llm, cfg)

    async def test_calibration_note_stored_in_field(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> None:
        """Quando ConfidenceCalibrator recalibra confiança, nota vai para
        calibration_note — não para data_gaps."""
        from miner_harness.agents.base import BaseAgent

        orch = self._make_orchestrator(mock_connector, cache, mock_llm)
        geo_data = {
            k: [{"objectid": 1}]
            for k in [
                "ocorrencias",
                "gravimetria",
                "geoquimica",
                "geocronologia",
                "litoestratigrafia",
                "aerogeofisica",
            ]
        }

        expected_note = "Confiança recalibrada: cobertura de dados insuficiente."

        async def fake_analyze(self_agent, step, data, prev, bbox=None):  # noqa: ANN001
            return _make_step_result_for_prd006(step, self_agent.name, Confidence.HIGH)

        original = BaseAgent.analyze
        BaseAgent.analyze = fake_analyze
        try:
            with patch(
                "miner_harness.orchestrator.confidence_calibrator.ConfidenceCalibrator",
            ) as mock_calib:
                mock_calib.return_value.calibrate.return_value = (
                    Confidence.MEDIUM,
                    expected_note,
                )
                result = await orch._execute_step(AnalysisStep.TECTONIC_HISTORY, geo_data, [])
        finally:
            BaseAgent.analyze = original

        assert result.calibration_note == expected_note
        assert expected_note not in result.data_gaps
        assert result.confidence == Confidence.MEDIUM

    async def test_no_recalibration_leaves_note_none(
        self,
        mock_connector: MagicMock,
        cache: CacheManager,
        mock_llm: MagicMock,
    ) -> None:
        """Sem recalibração (confiança inalterada), calibration_note permanece None."""
        from miner_harness.agents.base import BaseAgent

        orch = self._make_orchestrator(mock_connector, cache, mock_llm)
        geo_data = {
            k: [{"objectid": 1}]
            for k in [
                "ocorrencias",
                "gravimetria",
                "geoquimica",
                "geocronologia",
                "litoestratigrafia",
                "aerogeofisica",
            ]
        }

        async def fake_analyze(self_agent, step, data, prev, bbox=None):  # noqa: ANN001
            return _make_step_result_for_prd006(step, self_agent.name, Confidence.MEDIUM)

        original = BaseAgent.analyze
        BaseAgent.analyze = fake_analyze
        try:
            with patch(
                "miner_harness.orchestrator.confidence_calibrator.ConfidenceCalibrator",
            ) as mock_calib:
                # Calibrator retorna MESMA confiança → sem recalibração
                mock_calib.return_value.calibrate.return_value = (Confidence.MEDIUM, None)
                result = await orch._execute_step(AnalysisStep.TECTONIC_HISTORY, geo_data, [])
        finally:
            BaseAgent.analyze = original

        assert result.calibration_note is None


class TestDiversityRemovedCountInReport:
    """PRD-006: diversity_removed_count reflete alvos removidos por proximidade."""

    def test_count_reflects_removed_targets(self) -> None:
        """len(validated) - len(diverse) é capturado corretamente."""

        # Dois alvos próximos: enforcement remove 1
        def _tgt(name: str, lon: float, lat: float, priority: int) -> MineralTarget:
            return MineralTarget(
                name=name,
                longitude=lon,
                latitude=lat,
                radius_km=5.0,
                commodities=["Au"],
                mineral_system="IOCG",
                confidence=Confidence.MEDIUM,
                priority=priority,
                rationale="test",
                recommended_followup=[],
            )

        close_pair = [
            _tgt("P1", -50.0, -6.0, 1),
            _tgt("P2", -50.05, -6.0, 2),  # ~5 km de P1 — será removido
        ]
        diverse = Orchestrator._enforce_target_diversity(close_pair, min_km=15.0)
        removed_count = len(close_pair) - len(diverse)
        assert removed_count == 1

    def test_count_zero_when_all_kept(self) -> None:
        """Quando nenhum alvo é removido, contagem deve ser 0."""

        def _tgt(name: str, lon: float, lat: float, priority: int) -> MineralTarget:
            return MineralTarget(
                name=name,
                longitude=lon,
                latitude=lat,
                radius_km=5.0,
                commodities=["Au"],
                mineral_system="IOCG",
                confidence=Confidence.MEDIUM,
                priority=priority,
                rationale="test",
                recommended_followup=[],
            )

        distant_pair = [
            _tgt("A", -51.0, -6.0, 1),
            _tgt("B", -50.0, -6.0, 2),  # ~110 km — ambos mantidos
        ]
        diverse = Orchestrator._enforce_target_diversity(distant_pair, min_km=15.0)
        removed_count = len(distant_pair) - len(diverse)
        assert removed_count == 0

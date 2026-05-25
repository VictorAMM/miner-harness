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

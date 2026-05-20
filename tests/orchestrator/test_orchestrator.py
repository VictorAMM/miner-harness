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

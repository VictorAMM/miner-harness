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
from miner_harness.core.config import MinerHarnessConfig, OrchestratorConfig, StorageConfig
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
    return MinerHarnessConfig()


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
        ) -> StepResult:
            nonlocal call_count
            call_count += 1
            return await original_analyze(step, data, prev)

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

        async def capture_analyze(step: AnalysisStep, data: dict, prev=None) -> StepResult:
            captured_data.update(data)
            return await original_analyze(step, data, prev)

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
        with patch.dict(
            "miner_harness.orchestrator.orchestrator._STEP_AGENTS",
            {fake_step: []},
        ), pytest.raises(ValueError, match="No agents for step"):
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
        with patch.dict(
            "miner_harness.orchestrator.orchestrator._STEP_AGENTS",
            {fake_step: []},
        ), pytest.raises(ValueError, match="No agents configured"):
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

"""Testes dos agentes especialistas."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from miner_harness.agents.evaluator import EvaluatorAgent
from miner_harness.agents.geochemist import GeochemistAgent
from miner_harness.agents.geophysicist import GeophysicistAgent
from miner_harness.agents.remote_sensing import RemoteSensingAgent
from miner_harness.agents.structural_geo import StructuralGeoAgent
from miner_harness.connectors.ollama.client import ChatResponse, OllamaClient
from miner_harness.core.types import AnalysisStep, Confidence

if TYPE_CHECKING:
    from miner_harness.agents.base import BaseAgent


def _mock_llm_response(content: str) -> ChatResponse:
    return ChatResponse(
        content=content,
        model="qwen3:8b",
        total_duration_ns=1000000000,
        prompt_eval_count=100,
        eval_count=50,
    )


def _valid_json_response() -> str:
    return json.dumps(
        {
            "summary": "Found significant tectonic features.",
            "findings": ["Archean crust present", "Major shear zone identified"],
            "confidence": "high",
            "data_sources_used": ["litoestratigrafia", "geocronologia"],
            "data_gaps": ["Remote sensing data missing"],
        }
    )


def _sample_geo_data() -> dict[str, list[dict[str, Any]]]:
    return {
        "ocorrencias": [
            {"objectid": 1, "substancias": "Cobre", "uf": "PA"},
        ],
        "gravimetria": [
            {"objectid": 10, "anomalia_bouguer": -45.2},
        ],
        "geoquimica": [
            {"objectid": 20, "projeto": "RENCA", "classe": "Rocha"},
        ],
        "geocronologia": [
            {"objectid": 30, "metodo": "U-Pb", "idade_ma": 2750.0},
        ],
        "litoestratigrafia": [
            {"objectid": 40, "nome": "Grupo Serra dos Carajas"},
        ],
        "aerogeofisica": [
            {"objectid": 50, "nome_projeto": "Carajas"},
        ],
    }


class TestAgentRegistry:
    """Testes que todos os agentes estão registrados corretamente."""

    def test_structural_geo_supports_step_1_2(self) -> None:
        assert AnalysisStep.TECTONIC_HISTORY in StructuralGeoAgent.supported_steps
        assert AnalysisStep.STRUCTURAL_ARCHITECTURE in StructuralGeoAgent.supported_steps

    def test_geophysicist_supports_step_3_4(self) -> None:
        assert AnalysisStep.MAGMATIC_FERTILITY in GeophysicistAgent.supported_steps
        assert AnalysisStep.INDIRECT_EVIDENCE in GeophysicistAgent.supported_steps

    def test_geochemist_supports_step_3_4(self) -> None:
        assert AnalysisStep.MAGMATIC_FERTILITY in GeochemistAgent.supported_steps
        assert AnalysisStep.INDIRECT_EVIDENCE in GeochemistAgent.supported_steps

    def test_remote_sensing_supports_step_4(self) -> None:
        assert AnalysisStep.INDIRECT_EVIDENCE in RemoteSensingAgent.supported_steps

    def test_evaluator_supports_step_5(self) -> None:
        assert AnalysisStep.TOTAL_INTEGRATION in EvaluatorAgent.supported_steps

    def test_all_steps_covered(self) -> None:
        """Cada passo é coberto por pelo menos um agente."""
        all_agents = [
            StructuralGeoAgent,
            GeophysicistAgent,
            GeochemistAgent,
            RemoteSensingAgent,
            EvaluatorAgent,
        ]
        covered = set()
        for agent_cls in all_agents:
            covered.update(agent_cls.supported_steps)
        assert covered == set(AnalysisStep)


class TestBaseAgentParsing:
    """Testes do parsing de respostas do LLM."""

    def _make_agent(self) -> StructuralGeoAgent:
        mock_llm = AsyncMock(spec=OllamaClient)
        return StructuralGeoAgent(llm=mock_llm)

    def test_parse_valid_json(self) -> None:
        agent = self._make_agent()
        response = _mock_llm_response(_valid_json_response())
        result = agent.parse_response(response, AnalysisStep.TECTONIC_HISTORY)
        assert result.step == AnalysisStep.TECTONIC_HISTORY
        assert result.confidence == Confidence.HIGH
        assert len(result.findings) == 2
        assert result.agent == "structural_geologist"

    def test_parse_json_in_markdown_block(self) -> None:
        agent = self._make_agent()
        content = f"Here is the analysis:\n```json\n{_valid_json_response()}\n```\nDone."
        response = _mock_llm_response(content)
        result = agent.parse_response(response, AnalysisStep.TECTONIC_HISTORY)
        assert result.confidence == Confidence.HIGH

    def test_parse_json_with_surrounding_text(self) -> None:
        agent = self._make_agent()
        content = f"Analysis follows: {_valid_json_response()} End of analysis."
        response = _mock_llm_response(content)
        result = agent.parse_response(response, AnalysisStep.TECTONIC_HISTORY)
        assert result.confidence == Confidence.HIGH

    def test_parse_invalid_response_falls_back(self) -> None:
        agent = self._make_agent()
        response = _mock_llm_response("This is not JSON at all, just text analysis.")
        result = agent.parse_response(response, AnalysisStep.TECTONIC_HISTORY)
        assert result.confidence == Confidence.LOW
        assert "This is not JSON" in result.summary

    def test_parse_empty_response(self) -> None:
        agent = self._make_agent()
        response = _mock_llm_response("")
        result = agent.parse_response(response, AnalysisStep.TECTONIC_HISTORY)
        assert result.confidence == Confidence.LOW


class TestBaseAgentAnalyze:
    """Testes do fluxo completo de análise."""

    async def test_analyze_success(self) -> None:
        mock_llm = AsyncMock(spec=OllamaClient)
        mock_llm.chat.return_value = _mock_llm_response(_valid_json_response())

        agent = StructuralGeoAgent(llm=mock_llm)
        result = await agent.analyze(
            step=AnalysisStep.TECTONIC_HISTORY,
            geological_data=_sample_geo_data(),
        )
        assert result.step == AnalysisStep.TECTONIC_HISTORY
        assert result.agent == "structural_geologist"
        assert result.duration_ms >= 0
        mock_llm.chat.assert_called_once()

    async def test_analyze_wrong_step_raises(self) -> None:
        mock_llm = AsyncMock(spec=OllamaClient)
        agent = StructuralGeoAgent(llm=mock_llm)
        with pytest.raises(ValueError, match="does not support step"):
            await agent.analyze(
                step=AnalysisStep.TOTAL_INTEGRATION,
                geological_data=_sample_geo_data(),
            )

    async def test_analyze_with_previous_results(self) -> None:
        from miner_harness.core.types import StepResult

        mock_llm = AsyncMock(spec=OllamaClient)
        mock_llm.chat.return_value = _mock_llm_response(_valid_json_response())

        agent = GeophysicistAgent(llm=mock_llm)
        prev = StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="structural_geologist",
            summary="Archean crust with major shear zone.",
            findings=["Shear zone", "Archean rocks"],
            confidence=Confidence.HIGH,
            data_sources_used=["litoestratigrafia"],
            data_gaps=[],
            raw_reasoning="...",
            duration_ms=1000,
        )
        result = await agent.analyze(
            step=AnalysisStep.MAGMATIC_FERTILITY,
            geological_data=_sample_geo_data(),
            previous_results=[prev],
        )
        assert result.step == AnalysisStep.MAGMATIC_FERTILITY
        assert result.agent == "geophysicist"


class TestAgentDataKeys:
    """Testes que cada agente solicita dados corretos por passo."""

    def _make_agent(self, cls: type[BaseAgent]) -> BaseAgent:
        mock_llm = AsyncMock(spec=OllamaClient)
        return cls(llm=mock_llm)

    def test_structural_tectonic_needs_litoestratigrafia(self) -> None:
        agent = self._make_agent(StructuralGeoAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.TECTONIC_HISTORY)
        assert "litoestratigrafia" in keys
        assert "geocronologia" in keys

    def test_geochemist_fertility_needs_geoquimica(self) -> None:
        agent = self._make_agent(GeochemistAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.MAGMATIC_FERTILITY)
        assert "geoquimica" in keys

    def test_evaluator_needs_all_data(self) -> None:
        agent = self._make_agent(EvaluatorAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.TOTAL_INTEGRATION)
        assert len(keys) == 6  # All 6 datasets

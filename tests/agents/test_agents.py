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


class TestEvaluatorTargetExtraction:
    """Testes da extração de targets estruturados pelo EvaluatorAgent."""

    def _make_evaluator(self) -> EvaluatorAgent:
        mock_llm = AsyncMock(spec=OllamaClient)
        return EvaluatorAgent(llm=mock_llm)

    def _evaluator_json_with_targets(self) -> str:
        return json.dumps(
            {
                "summary": "Integração completa — 3 alvos identificados.",
                "findings": ["Anomalia de Cu-Au no setor NW", "Controle estrutural NW-SE"],
                "confidence": "medium",
                "data_sources_used": ["ocorrencias", "geoquimica"],
                "data_gaps": [],
                "targets": [
                    {
                        "name": "Alvo Cuiabá Norte",
                        "longitude": -44.1,
                        "latitude": -20.1,
                        "radius_km": 3.0,
                        "commodities": ["Au", "Cu"],
                        "mineral_system": "Ouro Orogênico",
                        "confidence": "medium",
                        "priority": 1,
                        "rationale": "Anomalia geoquímica de Au coincide com estrutura NW-SE.",
                        "recommended_followup": ["Sondagem rotativa", "IP"],
                    },
                    {
                        "name": "Alvo Serra Leste",
                        "longitude": -50.2,
                        "latitude": -6.3,
                        "radius_km": 5.0,
                        "commodities": ["Fe", "Mn"],
                        "mineral_system": "BIF",
                        "confidence": "high",
                        "priority": 2,
                        "rationale": "Ocorrência mineral de alto grau associada a BIF.",
                        "recommended_followup": ["Mapeamento geológico"],
                    },
                ],
            }
        )

    def test_evaluator_extracts_structured_targets(self) -> None:
        agent = self._make_evaluator()
        response = _mock_llm_response(self._evaluator_json_with_targets())
        result = agent.parse_response(response, AnalysisStep.TOTAL_INTEGRATION)

        assert len(result.targets) == 2
        assert result.targets[0].name == "Alvo Cuiabá Norte"
        assert result.targets[0].commodities == ["Au", "Cu"]
        assert result.targets[0].mineral_system == "Ouro Orogênico"
        assert result.targets[0].priority == 1
        assert result.targets[1].name == "Alvo Serra Leste"
        assert result.targets[1].commodities == ["Fe", "Mn"]

    def test_evaluator_targets_empty_when_llm_omits_field(self) -> None:
        agent = self._make_evaluator()
        response = _mock_llm_response(_valid_json_response())
        result = agent.parse_response(response, AnalysisStep.TECTONIC_HISTORY)
        assert result.targets == []

    def test_evaluator_targets_empty_when_targets_key_missing(self) -> None:
        agent = self._make_evaluator()
        content = json.dumps(
            {
                "summary": "Sem alvos definidos.",
                "findings": [],
                "confidence": "low",
                "data_sources_used": [],
                "data_gaps": ["Sem dados suficientes"],
            }
        )
        response = _mock_llm_response(content)
        result = agent.parse_response(response, AnalysisStep.TOTAL_INTEGRATION)
        assert result.targets == []

    def test_evaluator_skips_invalid_targets_gracefully(self) -> None:
        """Targets com campos inválidos são ignorados; os válidos são mantidos."""
        agent = self._make_evaluator()
        content = json.dumps(
            {
                "summary": "Mixed targets.",
                "findings": [],
                "confidence": "medium",
                "data_sources_used": [],
                "data_gaps": [],
                "targets": [
                    {
                        "name": "Bom",
                        "longitude": -44.0,
                        "latitude": -20.0,
                        "radius_km": 2.0,
                        "commodities": ["Au"],
                        "mineral_system": "Ouro",
                        "confidence": "high",
                        "priority": 1,
                        "rationale": "Válido",
                        "recommended_followup": [],
                    },
                    {
                        "name": "Ruim — priority fora do range",
                        "longitude": -44.0,
                        "latitude": -20.0,
                        "radius_km": 2.0,
                        "commodities": [],
                        "mineral_system": "X",
                        "confidence": "high",
                        "priority": 99,
                        "rationale": "",
                        "recommended_followup": [],
                    },
                ],
            }
        )
        response = _mock_llm_response(content)
        result = agent.parse_response(response, AnalysisStep.TOTAL_INTEGRATION)
        assert len(result.targets) == 1
        assert result.targets[0].name == "Bom"


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
        assert len(keys) == 9  # 6 GeoSGB + furos + anm + usgs
        assert "furos" in keys
        assert "anm" in keys
        assert "usgs" in keys

    def test_remote_sensing_data_keys(self) -> None:
        """_get_relevant_data_keys de RemoteSensing inclui anm."""
        agent = self._make_agent(RemoteSensingAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.INDIRECT_EVIDENCE)
        assert "aerogeofisica" in keys
        assert "litoestratigrafia" in keys
        assert "anm" in keys

    def test_geophysicist_indirect_evidence_keys(self) -> None:
        """_get_relevant_data_keys com INDIRECT_EVIDENCE inclui usgs."""
        agent = self._make_agent(GeophysicistAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.INDIRECT_EVIDENCE)
        assert "gravimetria" in keys
        assert "aerogeofisica" in keys
        assert "usgs" in keys

    def test_structural_tectonic_includes_usgs(self) -> None:
        agent = self._make_agent(StructuralGeoAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.TECTONIC_HISTORY)
        assert "usgs" in keys

    def test_structural_architectural_includes_usgs(self) -> None:
        agent = self._make_agent(StructuralGeoAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.STRUCTURAL_ARCHITECTURE)
        assert "usgs" in keys

    def test_geochemist_fertility_includes_anm(self) -> None:
        agent = self._make_agent(GeochemistAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.MAGMATIC_FERTILITY)
        assert "anm" in keys

    def test_geochemist_indirect_includes_anm(self) -> None:
        agent = self._make_agent(GeochemistAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.INDIRECT_EVIDENCE)
        assert "anm" in keys

    def test_geophysicist_fertility_includes_usgs(self) -> None:
        agent = self._make_agent(GeophysicistAgent)
        keys = agent._get_relevant_data_keys(AnalysisStep.MAGMATIC_FERTILITY)
        assert "usgs" in keys

    def test_source_label_used_in_build_prompt(self) -> None:
        """build_prompt usa ANM/SIGMINE em vez de GeoSGB/anm."""
        from miner_harness.agents.base import _SOURCE_LABELS

        assert _SOURCE_LABELS["anm"] == "ANM/SIGMINE — Concessões Minerárias"
        assert _SOURCE_LABELS["usgs"] == "USGS — Eventos Sísmicos"


class TestEvaluatorTargetsBlockException:
    """Cobre bloco except externo de _extract_targets (linhas 59-60)."""

    def _make_evaluator(self) -> EvaluatorAgent:
        mock_llm = AsyncMock(spec=OllamaClient)
        return EvaluatorAgent(llm=mock_llm)

    def test_non_json_content_with_total_integration(self) -> None:
        """Conteúdo sem JSON com TOTAL_INTEGRATION → except outer (linhas 59-60)."""
        agent = self._make_evaluator()
        response = _mock_llm_response("Análise descritiva sem JSON algum para extrair.")
        result = agent.parse_response(response, AnalysisStep.TOTAL_INTEGRATION)
        assert result.targets == []


class TestNormalizeSources:
    """Testes unitários de BaseAgent._normalize_sources (Q6)."""

    def _make_agent(self) -> StructuralGeoAgent:
        mock_llm = AsyncMock(spec=OllamaClient)
        return StructuralGeoAgent(llm=mock_llm)

    def test_canonical_keys_unchanged(self) -> None:
        """Chaves canônicas já corretas não são alteradas."""
        agent = self._make_agent()
        result = agent._normalize_sources(["ocorrencias", "gravimetria", "anm", "usgs"])
        assert result == ["ocorrencias", "gravimetria", "anm", "usgs"]

    def test_human_label_mapped_to_key(self) -> None:
        """Rótulo humanizado é mapeado para chave canônica."""
        agent = self._make_agent()
        result = agent._normalize_sources(["GeoSGB/Ocorrências Minerais"])
        assert result == ["ocorrencias"]

    def test_geosgb_prefix_stripped(self) -> None:
        """Prefixo 'GeoSGB/' é removido para obter chave canônica."""
        agent = self._make_agent()
        result = agent._normalize_sources(["GeoSGB/Geoquímica", "GeoSGB/Aerogeofísica"])
        assert result == ["geoquimica", "aerogeofisica"]

    def test_alias_mapped_to_canonical(self) -> None:
        """Alias como 'ANM/SIGMINE' e 'Sentinel-2' são normalizados."""
        agent = self._make_agent()
        result = agent._normalize_sources(["ANM/SIGMINE", "Sentinel-2", "RAG"])
        assert result == ["anm", "sentinel2_indices", "rag_context"]

    def test_duplicates_removed(self) -> None:
        """Entradas duplicadas (após normalização) são deduplicadas."""
        agent = self._make_agent()
        # 'GeoSGB/Geoquímica' e 'geoquimica' normalizam para a mesma chave
        result = agent._normalize_sources(["geoquimica", "GeoSGB/Geoquímica", "gravimetria"])
        assert result == ["geoquimica", "gravimetria"]

    def test_unknown_source_lowercased(self) -> None:
        """Fonte desconhecida é mantida como lowercase stripped."""
        agent = self._make_agent()
        result = agent._normalize_sources(["FooBar Source", "gravimetria"])
        assert result == ["foobar source", "gravimetria"]

    def test_mixed_case_canonical(self) -> None:
        """Chave canônica em maiúsculas é normalizada."""
        agent = self._make_agent()
        result = agent._normalize_sources(["USGS", "ANM"])
        assert result == ["usgs", "anm"]

    def test_parse_response_normalizes_sources(self) -> None:
        """parse_response aplica normalização ao campo data_sources_used."""
        agent = self._make_agent()
        content = json.dumps(
            {
                "summary": "test",
                "findings": [],
                "confidence": "high",
                "data_sources_used": ["GeoSGB/Geoquímica", "ANM/SIGMINE"],
                "data_gaps": [],
            }
        )
        response = _mock_llm_response(content)
        result = agent.parse_response(response, AnalysisStep.TECTONIC_HISTORY)
        assert "geoquimica" in result.data_sources_used
        assert "anm" in result.data_sources_used
        # Nenhum rótulo humanizado deve restar
        assert "GeoSGB/Geoquímica" not in result.data_sources_used
        assert "ANM/SIGMINE" not in result.data_sources_used

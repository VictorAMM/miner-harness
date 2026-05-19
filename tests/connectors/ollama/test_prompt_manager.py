"""Testes do PromptManager."""

from __future__ import annotations

from miner_harness.connectors.ollama.prompt_manager import PromptManager
from miner_harness.core.types import AnalysisStep


class TestPromptManager:
    """Testes da construção de prompts."""

    def test_system_prompt_known_agent(self) -> None:
        pm = PromptManager()
        prompt = pm.system_prompt("structural_geologist")
        assert "Dr. Augusto Valen" in prompt
        assert "estrutural" in prompt.lower()

    def test_system_prompt_unknown_agent(self) -> None:
        pm = PromptManager()
        prompt = pm.system_prompt("unknown_agent")
        assert "Dr. Augusto Valen" in prompt  # Falls back to base

    def test_build_messages_has_system_and_user(self) -> None:
        pm = PromptManager()
        messages = pm.build_messages(
            agent_name="geochemist",
            step=AnalysisStep.MAGMATIC_FERTILITY,
            geological_data="<data>test</data>",
        )
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"

    def test_build_messages_includes_step_instruction(self) -> None:
        pm = PromptManager()
        messages = pm.build_messages(
            agent_name="evaluator",
            step=AnalysisStep.TOTAL_INTEGRATION,
            geological_data="<data>test</data>",
        )
        assert "PASSO 5" in messages[1].content

    def test_build_messages_includes_previous_results(self) -> None:
        pm = PromptManager()
        messages = pm.build_messages(
            agent_name="geochemist",
            step=AnalysisStep.MAGMATIC_FERTILITY,
            geological_data="<data>test</data>",
            previous_results="Step 1 found X, Y, Z.",
        )
        assert "<previous_analysis>" in messages[1].content
        assert "Step 1 found" in messages[1].content

    def test_build_messages_includes_response_format(self) -> None:
        pm = PromptManager()
        messages = pm.build_messages(
            agent_name="structural_geologist",
            step=AnalysisStep.TECTONIC_HISTORY,
            geological_data="<data>test</data>",
        )
        assert "JSON" in messages[1].content
        assert '"summary"' in messages[1].content

    def test_evaluator_step_uses_dedicated_format(self) -> None:
        pm = PromptManager()
        messages = pm.build_messages(
            agent_name="evaluator",
            step=AnalysisStep.TOTAL_INTEGRATION,
            geological_data="<data>test</data>",
        )
        content = messages[1].content
        # Evaluator format has explicit priority rules
        assert '"priority": 1' in content
        assert "1 = melhor" in content
        assert "IOCG" in content  # Concrete mineral system examples required

    def test_non_evaluator_step_uses_basic_format(self) -> None:
        pm = PromptManager()
        messages = pm.build_messages(
            agent_name="structural_geologist",
            step=AnalysisStep.TECTONIC_HISTORY,
            geological_data="<data>test</data>",
        )
        content = messages[1].content
        # Basic format says targets should be empty list for steps 1-4
        assert '"targets": []' in content


class TestFormatGeologicalData:
    """Testes da formatação de dados geológicos."""

    def test_basic_format(self) -> None:
        records = [
            {"objectid": 1, "substancias": "Cobre", "uf": "PA"},
            {"objectid": 2, "substancias": "Ouro", "uf": "MG"},
        ]
        result = PromptManager.format_geological_data(records, "GeoSGB/ocorrencias")
        assert "GeoSGB/ocorrencias" in result
        assert "Cobre" in result
        assert "Ouro" in result

    def test_respects_max_records(self) -> None:
        records = [{"objectid": i, "val": "x"} for i in range(100)]
        result = PromptManager.format_geological_data(records, "test", max_records=5)
        assert result.count("<record") <= 5

    def test_respects_max_chars(self) -> None:
        records = [{"objectid": i, "data": "A" * 500} for i in range(50)]
        result = PromptManager.format_geological_data(records, "test", max_chars=1000)
        assert len(result) <= 1500  # Some overhead allowed

    def test_sanitizes_values(self) -> None:
        records = [{"objectid": 1, "name": "<script>alert(1)</script>"}]
        result = PromptManager.format_geological_data(records, "test")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestSummarizePreviousResults:
    """Testes do resumo de resultados anteriores."""

    def test_basic_summary(self) -> None:
        results = [
            {
                "step": "tectonic_history",
                "summary": "Found Archean crust",
                "confidence": "high",
                "findings": ["Finding A", "Finding B"],
            }
        ]
        summary = PromptManager.summarize_previous_results(results)
        assert "tectonic_history" in summary
        assert "high" in summary
        assert "Finding A" in summary

    def test_respects_max_chars(self) -> None:
        results = [
            {
                "step": f"step_{i}",
                "summary": "A" * 300,
                "confidence": "medium",
                "findings": ["F" * 200],
            }
            for i in range(20)
        ]
        summary = PromptManager.summarize_previous_results(results, max_chars=500)
        assert len(summary) <= 600  # Some overhead

    def test_empty_results(self) -> None:
        summary = PromptManager.summarize_previous_results([])
        assert summary == ""


class TestANMUSGSPromptGuidance:
    """Testes que os prompts dos agentes mencionam ANM/USGS corretamente."""

    def setup_method(self) -> None:
        self.pm = PromptManager()

    # System prompts --------------------------------------------------------

    def test_structural_geologist_mentions_usgs(self) -> None:
        prompt = self.pm.system_prompt("structural_geologist")
        assert "USGS" in prompt
        assert "falhas ativas" in prompt

    def test_geophysicist_mentions_usgs(self) -> None:
        prompt = self.pm.system_prompt("geophysicist")
        assert "USGS" in prompt
        assert "sismos" in prompt

    def test_geochemist_mentions_anm(self) -> None:
        prompt = self.pm.system_prompt("geochemist")
        assert "ANM" in prompt
        assert "concessões" in prompt.lower()

    def test_remote_sensing_mentions_anm(self) -> None:
        prompt = self.pm.system_prompt("remote_sensing")
        assert "ANM" in prompt
        assert "concessões" in prompt.lower()

    def test_evaluator_mentions_both(self) -> None:
        prompt = self.pm.system_prompt("evaluator")
        assert "ANM" in prompt
        assert "USGS" in prompt

    # Step instructions -----------------------------------------------------

    def test_tectonic_history_instruction_mentions_usgs(self) -> None:
        pm = PromptManager()
        msgs = pm.build_messages(
            "structural_geologist",
            AnalysisStep.TECTONIC_HISTORY,
            geological_data="<test/>",
        )
        user_content = msgs[1].content
        assert "USGS" in user_content
        assert "sismicidade" in user_content

    def test_structural_architecture_instruction_mentions_usgs(self) -> None:
        pm = PromptManager()
        msgs = pm.build_messages(
            "structural_geologist",
            AnalysisStep.STRUCTURAL_ARCHITECTURE,
            geological_data="<test/>",
        )
        user_content = msgs[1].content
        assert "USGS" in user_content
        assert "focal" in user_content

    def test_magmatic_fertility_instruction_mentions_anm_and_usgs(self) -> None:
        pm = PromptManager()
        msgs = pm.build_messages(
            "geochemist",
            AnalysisStep.MAGMATIC_FERTILITY,
            geological_data="<test/>",
        )
        user_content = msgs[1].content
        assert "ANM" in user_content
        assert "Lavra" in user_content
        assert "USGS" in user_content

    def test_indirect_evidence_instruction_mentions_anm_and_usgs(self) -> None:
        pm = PromptManager()
        msgs = pm.build_messages(
            "geochemist",
            AnalysisStep.INDIRECT_EVIDENCE,
            geological_data="<test/>",
        )
        user_content = msgs[1].content
        assert "ANM" in user_content
        assert "USGS" in user_content
        assert "Pesquisa" in user_content

    def test_total_integration_instruction_mentions_anm_and_usgs(self) -> None:
        pm = PromptManager()
        msgs = pm.build_messages(
            "evaluator",
            AnalysisStep.TOTAL_INTEGRATION,
            geological_data="<test/>",
        )
        user_content = msgs[1].content
        assert "ANM" in user_content
        assert "USGS" in user_content
        assert "regulatório" in user_content

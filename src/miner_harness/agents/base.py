"""BaseAgent — classe base abstrata para agentes especialistas.

Define o contrato que todos os agentes devem implementar:
analyze, build_prompt e parse_response.

Ref: RFC-002 §4.3
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import structlog

from miner_harness.connectors.ollama.prompt_manager import PromptManager
from miner_harness.core.exceptions import ResponseParseError
from miner_harness.core.types import AnalysisStep, Confidence, StepResult

if TYPE_CHECKING:
    from miner_harness.connectors.ollama.client import ChatMessage, ChatResponse, OllamaClient
    from miner_harness.core.types import BoundingBox

logger = structlog.get_logger(__name__)

# Rótulo legível por fonte de dados para o LLM
_SOURCE_LABELS: dict[str, str] = {
    "ocorrencias": "GeoSGB/Ocorrências Minerais",
    "gravimetria": "GeoSGB/Gravimetria",
    "geoquimica": "GeoSGB/Geoquímica",
    "geocronologia": "GeoSGB/Geocronologia",
    "litoestratigrafia": "GeoSGB/Litoestratigrafia",
    "aerogeofisica": "GeoSGB/Aerogeofísica",
    "anm": "ANM/SIGMINE — Concessões Minerárias",
    "usgs": "USGS — Eventos Sísmicos",
}


class BaseAgent(ABC):
    """Classe base para todos os agentes especialistas.

    Subclasses devem definir:
    - name: identificador do agente
    - specialty: descricao da especialidade
    - supported_steps: lista de AnalysisStep que o agente pode executar

    Usage:
        agent = StructuralGeoAgent(llm_client, config)
        result = await agent.analyze(step, geological_data, previous_results)
    """

    name: str
    specialty: str
    supported_steps: list[AnalysisStep]

    def __init__(
        self,
        llm: OllamaClient,
        model: str = "qwen3:8b",
        max_records: int = 50,
        max_chars: int = 8_000,
        max_prev_chars: int = 2_000,
    ) -> None:
        self._llm = llm
        self._model = model
        self._max_records = max_records
        self._max_chars = max_chars
        self._max_prev_chars = max_prev_chars
        self._prompt_manager = PromptManager()

    @abstractmethod
    def _get_relevant_data_keys(self, step: AnalysisStep) -> list[str]:
        """Retorna quais chaves de dados sao relevantes para o passo."""

    async def analyze(
        self,
        step: AnalysisStep,
        geological_data: dict[str, list[dict[str, Any]]],
        previous_results: list[StepResult] | None = None,
        bbox: BoundingBox | None = None,
    ) -> StepResult:
        """Executa analise especializada."""
        if step not in self.supported_steps:
            msg = f"Agent '{self.name}' does not support step '{step.value}'"
            raise ValueError(msg)

        start = time.monotonic()

        messages = self.build_prompt(step, geological_data, previous_results, bbox)
        response = await self._llm.chat(self._model, messages)
        result = self.parse_response(response, step)

        duration_ms = int((time.monotonic() - start) * 1000)
        result.duration_ms = duration_ms

        logger.info(
            "agent_analysis_complete",
            agent=self.name,
            step=step.value,
            confidence=result.confidence.value,
            findings_count=len(result.findings),
            duration_ms=duration_ms,
            prompt_tokens=response.prompt_eval_count,
            completion_tokens=response.eval_count,
        )

        return result

    def build_prompt(
        self,
        step: AnalysisStep,
        geological_data: dict[str, list[dict[str, Any]]],
        previous_results: list[StepResult] | None = None,
        bbox: BoundingBox | None = None,
    ) -> list[ChatMessage]:
        """Constroi mensagens para o LLM."""
        relevant_keys = self._get_relevant_data_keys(step)
        data_parts: list[str] = []
        for key in relevant_keys:
            records = geological_data.get(key, [])
            if records:
                source_label = _SOURCE_LABELS.get(key, f"GeoSGB/{key}")
                formatted = PromptManager.format_geological_data(
                    records,
                    source=source_label,
                    max_records=self._max_records,
                    max_chars=self._max_chars,
                )
                data_parts.append(formatted)

        geo_data_str = "\n\n".join(data_parts) if data_parts else "Sem dados disponiveis."

        # Injetar contexto RAG se disponível (indexado previamente pelo ContextBuilder)
        rag_records = geological_data.get("rag_context", [])
        if rag_records:
            rag_text = rag_records[0].get("text", "")
            if rag_text:
                _rag_note = (
                    "Documentos recuperados por similaridade semântica"
                    " — interprete através da sua especialidade geológica"
                )
                geo_data_str = (
                    geo_data_str
                    + f"\n\n<rag_context note='{_rag_note}'>\n{rag_text}\n</rag_context>"
                )

        prev_str = ""
        if previous_results:
            prev_dicts = [r.model_dump() for r in previous_results]
            prev_str = PromptManager.summarize_previous_results(
                prev_dicts, max_chars=self._max_prev_chars
            )

        return self._prompt_manager.build_messages(
            agent_name=self.name,
            step=step,
            geological_data=geo_data_str,
            previous_results=prev_str,
            bbox=bbox,
        )

    def parse_response(
        self,
        response: ChatResponse,
        step: AnalysisStep,
    ) -> StepResult:
        """Extrai resultado estruturado da resposta do LLM.

        Tenta parsear JSON da resposta. Se falhar, cria resultado
        com confianca LOW e a resposta crua como summary.
        """
        content = response.content.strip()

        try:
            parsed = self._extract_json(content)
            return StepResult(
                step=step,
                agent=self.name,
                summary=str(parsed.get("summary", "")),
                findings=list(parsed.get("findings", [])),
                confidence=Confidence(parsed.get("confidence", "low")),
                data_sources_used=list(parsed.get("data_sources_used", [])),
                data_gaps=list(parsed.get("data_gaps", [])),
                raw_reasoning=content,
                duration_ms=0,
            )
        except (
            json.JSONDecodeError,
            ValueError,
            KeyError,
            ResponseParseError,
        ) as exc:
            logger.warning(
                "response_parse_fallback",
                agent=self.name,
                step=step.value,
                error=str(exc),
            )
            return StepResult(
                step=step,
                agent=self.name,
                summary=content[:500] if content else "Sem resposta do LLM.",
                findings=[],
                confidence=Confidence.LOW,
                data_sources_used=[],
                data_gaps=["Resposta nao pode ser parseada"],
                raw_reasoning=content,
                duration_ms=0,
            )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extrai bloco JSON de uma resposta que pode conter texto extra."""
        # Primeiro tenta parsear o texto inteiro
        try:
            result: dict[str, Any] = json.loads(text)
            return result
        except json.JSONDecodeError:
            pass

        # Procura bloco JSON entre ```json e ```
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                result = json.loads(text[start:end].strip())
                return result

        # Procura primeiro { e ultimo }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            result = json.loads(text[first_brace : last_brace + 1])
            return result

        raise ResponseParseError("No JSON found in LLM response")

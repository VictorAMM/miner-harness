"""Orchestrator — orquestrador principal da análise de prospecção.

Coordena o pipeline completo:
GeoSGB → Cache → Agents (5 passos) → Report.

Ref: RFC-002 §4.2, §6
"""

from __future__ import annotations

import time
from datetime import datetime, timezone  # noqa: UP017
from typing import TYPE_CHECKING, Any

import structlog

from miner_harness.agents import (
    EvaluatorAgent,
    GeochemistAgent,
    GeophysicistAgent,
    RemoteSensingAgent,
    StructuralGeoAgent,
)
from miner_harness.core.config import MinerHarnessConfig
from miner_harness.core.exceptions import InsufficientDataError
from miner_harness.core.types import (
    AnalysisStep,
    Confidence,
    MineralTarget,
    ProspectionReport,
    StepResult,
)
from miner_harness.orchestrator.context_builder import ContextBuilder

if TYPE_CHECKING:
    from miner_harness.agents.base import BaseAgent
    from miner_harness.cache.manager import CacheManager
    from miner_harness.connectors.geosgb.connector import GeoSGBConnector
    from miner_harness.connectors.ollama.client import OllamaClient
    from miner_harness.core.types import BoundingBox

logger = structlog.get_logger(__name__)

# Mínimo de fontes de dados para prosseguir (RFC-002 §6)
MIN_DATA_SOURCES = 3

# Mapeamento passo → agentes (RFC-002 §3)
_STEP_AGENTS: dict[AnalysisStep, list[str]] = {
    AnalysisStep.TECTONIC_HISTORY: ["structural_geologist"],
    AnalysisStep.STRUCTURAL_ARCHITECTURE: ["structural_geologist"],
    AnalysisStep.MAGMATIC_FERTILITY: ["geochemist", "geophysicist"],
    AnalysisStep.INDIRECT_EVIDENCE: ["geochemist", "remote_sensing", "geophysicist"],
    AnalysisStep.TOTAL_INTEGRATION: ["evaluator"],
}


class Orchestrator:
    """Orquestrador principal da análise de prospecção mineral.

    Executa o pipeline Dr. Augusto Valen em 5 passos sequenciais,
    coordenando coleta de dados, agentes especialistas e geração
    do relatório final.

    Usage:
        config = MinerHarnessConfig()
        orchestrator = Orchestrator(connector, cache, llm, config)
        report = await orchestrator.analyze_region(bbox, "Carajás")
    """

    def __init__(
        self,
        connector: GeoSGBConnector,
        cache: CacheManager,
        llm: OllamaClient,
        config: MinerHarnessConfig | None = None,
    ) -> None:
        self._config = config or MinerHarnessConfig()
        self._connector = connector
        self._cache = cache
        self._llm = llm
        self._context_builder = ContextBuilder(connector, cache)

        model = self._config.orchestrator.model

        # Inicializar agentes
        self._agents: dict[str, BaseAgent] = {
            "structural_geologist": StructuralGeoAgent(llm, model),
            "geophysicist": GeophysicistAgent(llm, model),
            "geochemist": GeochemistAgent(llm, model),
            "remote_sensing": RemoteSensingAgent(llm, model),
            "evaluator": EvaluatorAgent(llm, model),
        }

    async def analyze_region(
        self,
        bbox: BoundingBox,
        region_name: str,
        steps: list[AnalysisStep] | None = None,
    ) -> ProspectionReport:
        """Executa análise completa de prospecção mineral.

        Args:
            bbox: Bounding box da região.
            region_name: Nome descritivo da região (ex: "Carajás").
            steps: Passos a executar. None = todos os 5.

        Returns:
            ProspectionReport com resultados integrados.

        Raises:
            InsufficientDataError: Se dados insuficientes para análise.
        """
        start = time.monotonic()
        steps = steps or list(AnalysisStep)

        logger.info(
            "analysis_start",
            region=region_name,
            bbox=bbox.as_tuple(),
            steps=[s.value for s in steps],
        )

        # 1. Coletar dados geológicos
        geological_data = await self._context_builder.build(bbox)

        # 2. Validar dados mínimos
        active_sources = [k for k, v in geological_data.items() if v]
        if len(active_sources) < MIN_DATA_SOURCES:
            raise InsufficientDataError(
                agent="orchestrator",
                missing=[k for k, v in geological_data.items() if not v],
            )

        # 3. Executar passos sequencialmente
        step_results: list[StepResult] = []
        for step in steps:
            result = await self._execute_step(step, geological_data, step_results)
            step_results.append(result)

        # 4. Extrair targets do resultado do Evaluator
        targets = self._extract_targets(step_results)

        # 5. Montar relatório
        total_ms = int((time.monotonic() - start) * 1000)
        report = ProspectionReport(
            region_name=region_name,
            bbox=bbox,
            analysis_date=datetime.now(tz=timezone.utc),  # noqa: UP017
            steps=step_results,
            targets=targets,
            integrated_summary=self._build_summary(step_results),
            caveats=self._collect_caveats(step_results, geological_data),
            data_quality_score=self._compute_quality(step_results, geological_data),
            total_duration_ms=total_ms,
            model_used=self._config.orchestrator.model,
        )

        logger.info(
            "analysis_complete",
            region=region_name,
            steps_completed=len(step_results),
            targets_found=len(targets),
            total_duration_ms=total_ms,
            data_quality=report.data_quality_score,
        )

        return report

    async def _execute_step(
        self,
        step: AnalysisStep,
        geological_data: dict[str, list[dict[str, Any]]],
        previous_results: list[StepResult],
    ) -> StepResult:
        """Executa um passo individual da análise.

        Para passos com múltiplos agentes (3 e 4), executa o
        primeiro agente que suporta o passo.
        """
        agent_names = _STEP_AGENTS.get(step, [])
        if not agent_names:
            msg = f"No agents configured for step {step.value}"
            raise ValueError(msg)

        # Usar o primeiro agente disponível para o passo
        agent_name = agent_names[0]
        agent = self._agents[agent_name]

        logger.info(
            "step_start",
            step=step.value,
            agent=agent_name,
        )

        result = await agent.analyze(step, geological_data, previous_results or None)

        logger.info(
            "step_complete",
            step=step.value,
            agent=agent_name,
            confidence=result.confidence.value,
            findings=len(result.findings),
            duration_ms=result.duration_ms,
        )

        return result

    def get_agent_for_step(self, step: AnalysisStep) -> BaseAgent:
        """Retorna o agente principal para um passo."""
        agent_names = _STEP_AGENTS.get(step, [])
        if not agent_names:
            msg = f"No agents for step {step.value}"
            raise ValueError(msg)
        return self._agents[agent_names[0]]

    # ------------------------------------------------------------------
    # Helpers para montagem do relatório
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_targets(step_results: list[StepResult]) -> list[MineralTarget]:
        """Extrai MineralTargets do resultado do Evaluator.

        O Evaluator (passo 5) deve incluir targets no seu resultado.
        Se não houver dados estruturados, retorna lista vazia.
        """
        # Procurar resultado do TOTAL_INTEGRATION
        for result in step_results:
            if result.step == AnalysisStep.TOTAL_INTEGRATION:
                # Tentar extrair targets dos findings
                # Em produção, o Evaluator retornará JSON estruturado
                # Por ora, retornamos targets placeholder baseados nos findings
                return Orchestrator._findings_to_targets(result)
        return []

    @staticmethod
    def _findings_to_targets(evaluator_result: StepResult) -> list[MineralTarget]:
        """Converte findings do Evaluator em MineralTargets.

        Versão simplificada — em produção o Evaluator retornará
        targets estruturados diretamente.
        """
        targets: list[MineralTarget] = []
        for i, finding in enumerate(evaluator_result.findings[:5], start=1):
            targets.append(
                MineralTarget(
                    name=f"Alvo {i}",
                    longitude=-50.0,  # Placeholder — será extraído do LLM
                    latitude=-6.0,
                    radius_km=5.0,
                    commodities=["Indeterminado"],
                    mineral_system="Indeterminado",
                    confidence=evaluator_result.confidence,
                    priority=i,
                    rationale=finding,
                    recommended_followup=["Validação de campo"],
                )
            )
        return targets

    @staticmethod
    def _build_summary(step_results: list[StepResult]) -> str:
        """Monta resumo integrado a partir dos resultados dos passos."""
        if not step_results:
            return "Análise não executada."

        parts: list[str] = []
        for result in step_results:
            if result.summary:
                parts.append(f"[{result.step.value}] {result.summary}")

        return " | ".join(parts) if parts else "Sem resumo disponível."

    @staticmethod
    def _collect_caveats(
        step_results: list[StepResult],
        geological_data: dict[str, list[dict[str, Any]]],
    ) -> list[str]:
        """Coleta caveats (ressalvas) sobre a análise."""
        caveats: list[str] = []

        # Dados faltantes
        empty_services = [k for k, v in geological_data.items() if not v]
        if empty_services:
            caveats.append(f"Dados indisponíveis para: {', '.join(empty_services)}")

        # Baixa confiança
        low_confidence = [
            r for r in step_results if r.confidence in (Confidence.LOW, Confidence.INSUFFICIENT)
        ]
        if low_confidence:
            steps_str = ", ".join(r.step.value for r in low_confidence)
            caveats.append(f"Baixa confiança em: {steps_str}")

        # Data gaps reportados pelos agentes
        all_gaps: list[str] = []
        for r in step_results:
            all_gaps.extend(r.data_gaps)
        if all_gaps:
            unique_gaps = list(dict.fromkeys(all_gaps))[:5]
            caveats.append(f"Lacunas de dados: {'; '.join(unique_gaps)}")

        return caveats

    @staticmethod
    def _compute_quality(
        step_results: list[StepResult],
        geological_data: dict[str, list[dict[str, Any]]],
    ) -> float:
        """Calcula score de qualidade dos dados (0-1).

        Considera:
        - Cobertura de serviços (40%)
        - Confiança média dos passos (40%)
        - Volume de dados (20%)
        """
        if not step_results:
            return 0.0

        # Cobertura de serviços
        total_services = 6
        active = sum(1 for v in geological_data.values() if v)
        coverage_score = active / total_services

        # Confiança média
        confidence_map = {
            Confidence.HIGH: 1.0,
            Confidence.MEDIUM: 0.7,
            Confidence.LOW: 0.3,
            Confidence.INSUFFICIENT: 0.0,
        }
        avg_confidence = sum(confidence_map.get(r.confidence, 0.0) for r in step_results) / len(
            step_results
        )

        # Volume (normalizado: 100+ registros = 1.0)
        total_records = sum(len(v) for v in geological_data.values())
        volume_score = min(1.0, total_records / 100)

        quality = coverage_score * 0.4 + avg_confidence * 0.4 + volume_score * 0.2
        return round(quality, 3)

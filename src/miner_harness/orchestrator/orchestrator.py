"""Orchestrator — orquestrador principal da análise de prospecção.

Coordena o pipeline completo:
GeoSGB → Cache → Agents (5 passos) → Report.

Ref: RFC-002 §4.2, §6
"""

from __future__ import annotations

import asyncio
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
from miner_harness.orchestrator.context_builder import ContextBuilder, ExtraSourcesMap

if TYPE_CHECKING:
    from miner_harness.agents.base import BaseAgent
    from miner_harness.cache.manager import CacheManager
    from miner_harness.connectors.geosgb.connector import GeoSGBConnector
    from miner_harness.connectors.ollama.client import OllamaClient
    from miner_harness.core.types import BoundingBox
    from miner_harness.index.search_engine import SearchEngine

logger = structlog.get_logger(__name__)

# Queries RAG por passo — termos geológicos para busca semântica
_STEP_RAG_QUERIES: dict[AnalysisStep, str] = {
    AnalysisStep.TECTONIC_HISTORY: (
        "história tectônica evolução crustal litoestratigrafia geocronologia"
    ),
    AnalysisStep.STRUCTURAL_ARCHITECTURE: (
        "estruturas falhas zonas cisalhamento lineamentos controle estrutural"
    ),
    AnalysisStep.MAGMATIC_FERTILITY: (
        "magmatismo intrusões fertilidade magmática anomalias geoquímicas gravimetria"
    ),
    AnalysisStep.INDIRECT_EVIDENCE: (
        "alteração hidrotermal anomalias geofísicas indícios mineralização pathfinder"
    ),
    AnalysisStep.TOTAL_INTEGRATION: (
        "alvos prospecção mineral potencial econômico ocorrências minerais"
    ),
}

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

        model = self._config.orchestrator.model

        # Inicializar SearchEngine para RAG quando habilitado
        self._search_engine: SearchEngine | None = None
        if self._config.orchestrator.use_rag:
            try:
                from miner_harness.index.document_store import DocumentStore
                from miner_harness.index.embedder import Embedder
                from miner_harness.index.search_engine import SearchEngine
                from miner_harness.index.types import EmbeddingConfig

                self._config.storage.ensure_dirs()
                embed_cfg = EmbeddingConfig(
                    model=self._config.storage.embedding_model,
                    dimensions=self._config.storage.embedding_dimensions,
                )
                self._search_engine = SearchEngine(
                    Embedder(llm, embed_cfg),
                    DocumentStore(self._config.storage.index_dir),
                )
            except Exception:
                logger.warning("rag_init_failed", exc_info=True)

        extra_sources = self._build_extra_sources()
        self._context_builder = ContextBuilder(connector, cache, self._search_engine, extra_sources)

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
        await self._on_data_fetched(geological_data)

        # 2. Validar dados mínimos
        min_sources = self._config.orchestrator.min_data_sources
        active_sources = [k for k, v in geological_data.items() if v]
        if len(active_sources) < min_sources:
            raise InsufficientDataError(
                agent="orchestrator",
                missing=[k for k, v in geological_data.items() if not v],
                min_sources=min_sources,
                active_count=len(active_sources),
            )

        # 3. Executar passos sequencialmente
        step_results: list[StepResult] = []
        for step in steps:
            result = await self._execute_step(step, geological_data, step_results, bbox)
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
            geological_data=geological_data,
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
        bbox: BoundingBox | None = None,
    ) -> StepResult:
        """Executa um passo individual da análise.

        Para passos com múltiplos agentes (3 e 4), todos os agentes rodam
        em paralelo via asyncio.gather() e seus resultados são fundidos.
        """
        agent_names = _STEP_AGENTS.get(step, [])
        if not agent_names:
            msg = f"No agents configured for step {step.value}"
            raise ValueError(msg)

        logger.info(
            "step_start",
            step=step.value,
            agents=agent_names,
        )

        # Enriquecer dados com contexto RAG antes de chamar os agentes
        effective_data = geological_data
        if self._search_engine is not None:
            query = _STEP_RAG_QUERIES.get(step, step.value)
            try:
                rag_context = await self._search_engine.get_context(query)
                effective_data = {**geological_data, "rag_context": [{"text": rag_context}]}
            except Exception:
                logger.warning("rag_context_failed", step=step.value, exc_info=True)

        if len(agent_names) == 1:
            result = await self._agents[agent_names[0]].analyze(
                step, effective_data, previous_results or None, bbox
            )
        else:
            results = await asyncio.gather(
                *(
                    self._agents[name].analyze(step, effective_data, previous_results or None, bbox)
                    for name in agent_names
                )
            )
            result = self._merge_step_results(list(results))

        logger.info(
            "step_complete",
            step=step.value,
            agent=result.agent,
            confidence=result.confidence.value,
            findings=len(result.findings),
            duration_ms=result.duration_ms,
        )

        return result

    @staticmethod
    def _merge_step_results(results: list[StepResult]) -> StepResult:
        """Funde resultados de múltiplos agentes num único StepResult.

        Estratégia: melhor confiança, union de findings/sources/gaps,
        duration_ms = tempo de parede (max, pois correm em paralelo).
        """
        if len(results) == 1:
            return results[0]

        _confidence_rank = {
            Confidence.HIGH: 3,
            Confidence.MEDIUM: 2,
            Confidence.LOW: 1,
            Confidence.INSUFFICIENT: 0,
        }
        best = max(results, key=lambda r: _confidence_rank[r.confidence])

        all_findings: list[str] = []
        all_sources: list[str] = []
        all_gaps: list[str] = []
        summaries: list[str] = []
        all_targets = []

        for r in results:
            all_findings.extend(r.findings)
            all_sources.extend(r.data_sources_used)
            all_gaps.extend(r.data_gaps)
            all_targets.extend(r.targets)
            if r.summary:
                summaries.append(f"[{r.agent}] {r.summary}")

        return StepResult(
            step=results[0].step,
            agent=" + ".join(r.agent for r in results),
            summary=" | ".join(summaries),
            findings=list(dict.fromkeys(all_findings)),
            confidence=best.confidence,
            data_sources_used=list(dict.fromkeys(all_sources)),
            data_gaps=list(dict.fromkeys(all_gaps)),
            raw_reasoning=" | ".join(r.raw_reasoning for r in results),
            duration_ms=max(r.duration_ms for r in results),
            targets=all_targets,
        )

    async def _on_data_fetched(self, geological_data: dict[str, list[dict[str, Any]]]) -> None:
        """Hook chamado após coleta de dados; sobrescrito por subclasses."""

    def _build_extra_sources(self) -> ExtraSourcesMap:
        """Instancia conectores adicionais (ANM, USGS) quando habilitados."""
        sources: ExtraSourcesMap = {}
        try:
            from miner_harness.connectors.anm.connector import ANMConnector

            if self._config.anm.enabled:
                sources["anm"] = (ANMConnector(self._config.anm), "concessoes")
        except Exception:
            logger.warning("anm_connector_init_failed", exc_info=True)
        try:
            from miner_harness.connectors.usgs.connector import USGSConnector

            if self._config.usgs.enabled:
                sources["usgs"] = (USGSConnector(self._config.usgs), "sismos")
        except Exception:
            logger.warning("usgs_connector_init_failed", exc_info=True)
        return sources

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

        Usa os targets estruturados que o EvaluatorAgent extraiu do JSON do LLM.
        Cai para _findings_to_targets() apenas se o LLM não retornou targets válidos.
        """
        for result in step_results:
            if result.step == AnalysisStep.TOTAL_INTEGRATION:
                if result.targets:
                    return result.targets
                return Orchestrator._findings_to_targets(result)
        return []

    @staticmethod
    def _findings_to_targets(evaluator_result: StepResult) -> list[MineralTarget]:
        """Fallback: converte findings em targets genéricos quando o LLM não estruturou targets."""
        targets: list[MineralTarget] = []
        for i, finding in enumerate(evaluator_result.findings[:5], start=1):
            targets.append(
                MineralTarget(
                    name=f"Alvo {i}",
                    longitude=-50.0,
                    latitude=-6.0,
                    radius_km=5.0,
                    commodities=Orchestrator._extract_commodities(finding),
                    mineral_system="Indeterminado",
                    confidence=evaluator_result.confidence,
                    priority=i,
                    rationale=finding,
                    recommended_followup=["Validação de campo"],
                )
            )
        return targets

    # Vocabulário de commodities minerais em PT-BR e EN (lowercase → nome canônico)
    _COMMODITY_KEYWORDS: dict[str, str] = {
        "ouro": "Ouro",
        "gold": "Ouro",
        "cobre": "Cobre",
        "copper": "Cobre",
        "ferro": "Ferro",
        "iron": "Ferro",
        "níquel": "Níquel",
        "niquel": "Níquel",
        "nickel": "Níquel",
        "zinco": "Zinco",
        "zinc": "Zinco",
        "chumbo": "Chumbo",
        "lead": "Chumbo",
        "prata": "Prata",
        "silver": "Prata",
        "titânio": "Titânio",
        "titanio": "Titânio",
        "titanium": "Titânio",
        "manganês": "Manganês",
        "manganes": "Manganês",
        "manganese": "Manganês",
        "bauxita": "Bauxita",
        "bauxite": "Bauxita",
        "cromo": "Cromo",
        "chromium": "Cromo",
        "cobalto": "Cobalto",
        "cobalt": "Cobalto",
        "platina": "Platina",
        "platinum": "Platina",
        "diamante": "Diamante",
        "diamond": "Diamante",
        "estanho": "Estanho",
        "tin": "Estanho",
        "tungstênio": "Tungstênio",
        "tungstenio": "Tungstênio",
        "tungsten": "Tungstênio",
        "molibdênio": "Molibdênio",
        "molibdenio": "Molibdênio",
        "molybdenum": "Molibdênio",
        "urânio": "Urânio",
        "uranio": "Urânio",
        "uranium": "Urânio",
        "fosfato": "Fosfato",
        "phosphate": "Fosfato",
        "terras raras": "Terras Raras",
        "rare earth": "Terras Raras",
        "lítio": "Lítio",
        "litio": "Lítio",
        "lithium": "Lítio",
        "iocg": "IOCG",
        "epitermal": "Ouro",
        "epithermal": "Ouro",
    }

    @staticmethod
    def _extract_commodities(text: str) -> list[str]:
        """Extrai nomes de commodities do texto livre usando vocabulário controlado."""
        lower = text.lower()
        found: list[str] = []
        seen: set[str] = set()
        for keyword, canonical in Orchestrator._COMMODITY_KEYWORDS.items():
            if keyword in lower and canonical not in seen:
                found.append(canonical)
                seen.add(canonical)
        return found if found else ["Indeterminado"]

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

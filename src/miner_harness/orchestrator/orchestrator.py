"""Orchestrator — orquestrador principal da análise de prospecção.

Coordena o pipeline completo:
GeoSGB → Cache → Agents (5 passos) → Report.

Ref: RFC-002 §4.2, §6
"""

from __future__ import annotations

import asyncio
import math
import re
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
    from collections.abc import Callable

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

# Chaves derivadas/computadas — não contam como fontes de dados brutas.
# Devem ser ignoradas ao calcular active_sources para o limiar min_data_sources.
# Espelha _COMPUTED_KEYS de confidence_calibrator (definido aqui para evitar
# importação circular).
_DERIVED_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "geoquimica_normalizada",
        "prospectivity_grid",
        "bouguer_gradient",
        "rag_context",
        "user_drillholes",
        "sentinel2_indices",
        "ml_prospectivity",  # PRD-002 F8
        "aeromag_grid",  # PRD-003 F10
    }
)

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
        orch_cfg = self._config.orchestrator
        max_records = orch_cfg.effective_max_records
        max_chars = orch_cfg.effective_max_chars
        max_prev_chars = orch_cfg.effective_max_prev_chars

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
        copernicus = self._build_copernicus()
        aeromag = self._build_aeromag()
        self._context_builder = ContextBuilder(
            connector,
            cache,
            self._search_engine,
            extra_sources,
            copernicus,
            ml_model_path=self._config.ml.model_path,
            ml_enabled=self._config.ml.enabled,
            aeromag=aeromag,
        )

        # Inicializar agentes com limites de dados escalados com num_ctx
        _agent_kwargs = dict(
            max_records=max_records,
            max_chars=max_chars,
            max_prev_chars=max_prev_chars,
        )
        self._agents: dict[str, BaseAgent] = {
            "structural_geologist": StructuralGeoAgent(llm, model, **_agent_kwargs),
            "geophysicist": GeophysicistAgent(llm, model, **_agent_kwargs),
            "geochemist": GeochemistAgent(llm, model, **_agent_kwargs),
            "remote_sensing": RemoteSensingAgent(llm, model, **_agent_kwargs),
            "evaluator": EvaluatorAgent(llm, model, **_agent_kwargs),
        }

    async def analyze_region(
        self,
        bbox: BoundingBox,
        region_name: str,
        steps: list[AnalysisStep] | None = None,
        user_drillholes: list[dict[str, Any]] | None = None,
        on_step_complete: Callable[[AnalysisStep, int, int, str], None] | None = None,
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
        geological_data = await self._context_builder.build(
            bbox,
            max_records_per_service=self._config.orchestrator.effective_max_records,
            user_drillholes=user_drillholes,
        )
        await self._on_data_fetched(geological_data)

        # 2. Validar dados mínimos (somente fontes brutas — excluir chaves derivadas)
        bbox_filtered = self._context_builder.bbox_filtered_sources
        min_sources = self._config.orchestrator.min_data_sources
        active_sources = [
            k for k, v in geological_data.items() if v and k not in _DERIVED_CONTEXT_KEYS
        ]
        unavailable = [
            k for k, v in geological_data.items() if not v and k not in _DERIVED_CONTEXT_KEYS
        ]
        if len(active_sources) < min_sources:
            raise InsufficientDataError(
                agent="orchestrator",
                missing=unavailable,
                min_sources=min_sources,
                active_count=len(active_sources),
            )

        # Resumo de fontes antes do pipeline LLM
        avail_str = ", ".join(f"{k}({len(geological_data[k])})" for k in active_sources)
        print(f"\nFontes ativas ({len(active_sources)}): {avail_str}", flush=True)
        truly_unavailable = [k for k in unavailable if k not in bbox_filtered]
        if bbox_filtered:
            print(f"Fontes filtradas (fora do bbox): {', '.join(bbox_filtered)}", flush=True)
        if truly_unavailable:
            print(f"Fontes indisponíveis: {', '.join(truly_unavailable)}", flush=True)

        # Aviso de truncamento — quando >50% dos registros foram descartados
        trunc = self._context_builder.truncation_info
        heavy_trunc = {
            svc: (orig, trunc_to)
            for svc, (orig, trunc_to) in trunc.items()
            if orig > 0 and trunc_to / orig < 0.5
        }
        if heavy_trunc:
            parts = [
                f"{svc}: {orig}→{trunc_to} ({100 * trunc_to // orig}%)"
                for svc, (orig, trunc_to) in heavy_trunc.items()
            ]
            print(
                f"⚠ Dados truncados (>50% ignorados): {', '.join(parts)}. "
                "Use --ctx-size 32768 para análise mais completa.",
                flush=True,
            )

        print(f"\n{'─' * 50}", flush=True)
        print(f"Iniciando pipeline LLM — {len(steps)} passos...", flush=True)
        print(f"{'─' * 50}\n", flush=True)

        # 3. Executar passos sequencialmente
        step_results: list[StepResult] = []
        for i, step in enumerate(steps, 1):
            result = await self._execute_step(step, geological_data, step_results, bbox)
            step_results.append(result)
            if on_step_complete is not None:
                on_step_complete(step, i, len(steps), result.confidence.value)

        # 4. Extrair targets do resultado do Evaluator
        raw_targets = self._extract_targets(step_results)
        validated = self._validate_target_coords(raw_targets, bbox)
        diverse = self._enforce_target_diversity(validated)
        diversity_removed = len(validated) - len(diverse)
        targets = self._assign_prospectivity_scores(diverse, geological_data)

        # 5. Montar relatório
        total_ms = int((time.monotonic() - start) * 1000)
        report = ProspectionReport(
            region_name=region_name,
            bbox=bbox,
            analysis_date=datetime.now(tz=timezone.utc),  # noqa: UP017
            steps=step_results,
            targets=targets,
            integrated_summary=self._build_summary(step_results),
            caveats=self._collect_caveats(step_results, geological_data, bbox_filtered),
            data_quality_score=self._compute_quality(step_results, geological_data),
            total_duration_ms=total_ms,
            model_used=self._config.orchestrator.model,
            missing_sources=[k for k in unavailable if k not in bbox_filtered],
            bbox_filtered_sources=list(bbox_filtered),
            geological_data=geological_data,
            diversity_removed_count=diversity_removed,
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

        # Recalibrar confiança com base na cobertura real de dados (PRD-002 v0.7.2)
        from miner_harness.orchestrator.confidence_calibrator import (  # noqa: PLC0415
            ConfidenceCalibrator,
        )

        original_conf = result.confidence
        calibrated_conf, calib_note = ConfidenceCalibrator().calibrate(
            step, result.confidence, effective_data
        )
        if calibrated_conf != original_conf:
            update: dict[str, Any] = {"confidence": calibrated_conf}
            if calib_note:
                update["calibration_note"] = calib_note
            result = result.model_copy(update=update)
            logger.info(
                "confidence_calibrated",
                step=step.value,
                original=original_conf.value,
                calibrated=calibrated_conf.value,
            )

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

    def _build_copernicus(self) -> Any:
        """Instancia CopernicusConnector quando credenciais estão disponíveis."""
        if not self._config.copernicus.enabled:
            return None
        if not self._config.copernicus.client_id:
            return None
        try:
            from miner_harness.connectors.sentinel2.connector import (  # noqa: PLC0415
                CopernicusConnector,
            )

            return CopernicusConnector(self._config.copernicus)
        except Exception:
            logger.warning("copernicus_connector_init_failed", exc_info=True)
            return None

    def _build_aeromag(self) -> Any:
        """Instancia AeromagConnector quando habilitado na configuração."""
        if not self._config.aeromag.enabled:
            return None
        try:
            from miner_harness.connectors.geosgb.aeromag_connector import (  # noqa: PLC0415
                AeromagConnector,
            )

            return AeromagConnector(
                timeout_s=self._config.aeromag.timeout_s,
                min_delay_ms=self._config.aeromag.min_delay_ms,
                grid_n=self._config.aeromag.grid_n,
            )
        except Exception:
            logger.warning("aeromag_connector_init_failed", exc_info=True)
            return None

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
        Aplica deduplicação geoespacial (10 km) mas NÃO diversidade espacial —
        ``_enforce_target_diversity`` é chamado separadamente no fluxo principal
        para permitir a contagem de alvos removidos.
        """
        for result in step_results:
            if result.step == AnalysisStep.TOTAL_INTEGRATION:
                if result.targets:
                    return Orchestrator._dedup_targets(result.targets)
                return Orchestrator._findings_to_targets(result)
        return []

    @staticmethod
    def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        """Distância haversine em km entre dois pontos geográficos."""
        r = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    @staticmethod
    def _dedup_targets(
        targets: list[MineralTarget], min_distance_km: float = 10.0
    ) -> list[MineralTarget]:
        """Remove/mescla alvos sobrepostos geograficamente.

        Dois alvos são considerados duplicatas se a distância entre seus centros
        for menor que ``min_distance_km`` (padrão: 10 km). Ao mesclar, mantém o
        alvo de maior prioridade (menor número) e une suas commodities.

        Args:
            targets: Lista de alvos (ordem priority asc preferível).
            min_distance_km: Raio mínimo de separação em km.

        Returns:
            Lista deduplicada, re-numerada por prioridade.
        """
        if len(targets) <= 1:
            return list(targets)

        # Ordenar por prioridade (menor = mais importante)
        ordered = sorted(targets, key=lambda t: t.priority)
        kept: list[MineralTarget] = []

        for candidate in ordered:
            merged = False
            for i, ref in enumerate(kept):
                dist = Orchestrator._haversine_km(
                    candidate.longitude,
                    candidate.latitude,
                    ref.longitude,
                    ref.latitude,
                )
                if dist < min_distance_km:
                    # Mesclar commodities no alvo de maior prioridade (ref)
                    extra = [c for c in candidate.commodities if c not in ref.commodities]
                    if extra:
                        merged_commodities = list(ref.commodities) + extra
                        kept[i] = ref.model_copy(update={"commodities": merged_commodities})
                    merged = True
                    logger.info(
                        "target_dedup_merged",
                        kept=ref.name,
                        dropped=candidate.name,
                        distance_km=round(dist, 2),
                    )
                    break
            if not merged:
                kept.append(candidate)

        # Re-numerar prioridades
        return [t.model_copy(update={"priority": i + 1}) for i, t in enumerate(kept)]

    @staticmethod
    def _enforce_target_diversity(
        targets: list[MineralTarget], min_km: float = 15.0
    ) -> list[MineralTarget]:
        """Remove alvos que estão a menos de ``min_km`` de um alvo de maior prioridade.

        Aplicado após ``_dedup_targets`` para garantir diversidade geográfica mínima.
        Alvos de menor prioridade que se sobrepõem espacialmente são descartados.

        Args:
            targets: Lista de alvos já deduplicados, ordem de prioridade asc.
            min_km: Distância mínima em km entre quaisquer dois alvos.

        Returns:
            Lista filtrada e re-numerada por prioridade.
        """
        if len(targets) <= 1:
            return list(targets)

        kept: list[MineralTarget] = []
        for candidate in sorted(targets, key=lambda t: t.priority):
            too_close = any(
                Orchestrator._haversine_km(
                    candidate.longitude,
                    candidate.latitude,
                    k.longitude,
                    k.latitude,
                )
                < min_km
                for k in kept
            )
            if too_close:
                logger.warning(
                    "target_diversity_removed",
                    name=candidate.name,
                    min_km=min_km,
                )
            else:
                kept.append(candidate)

        # Re-numerar prioridades
        return [t.model_copy(update={"priority": i + 1}) for i, t in enumerate(kept)]

    @staticmethod
    def _assign_prospectivity_scores(
        targets: list[MineralTarget],
        geological_data: dict[str, list[dict[str, Any]]],
    ) -> list[MineralTarget]:
        """Atribui score de prospectividade ao alvo com base na célula mais próxima.

        Consulta o ``prospectivity_grid`` presente em ``geological_data`` e
        associa a cada alvo o score da célula com menor distância haversine.
        Alvos sem correspondência mantêm ``prospectivity_score=None``.

        Args:
            targets: Lista de alvos validados.
            geological_data: Contexto geológico (contém ``prospectivity_grid``).

        Returns:
            Lista de alvos com ``prospectivity_score`` preenchido quando possível.
        """
        grid_entries = geological_data.get("prospectivity_grid", [])
        if not grid_entries or not targets:
            return targets

        # Extrair células (lon, lat, score) do GeoJSON no primeiro entry
        cells: list[tuple[float, float, float]] = []
        for entry in grid_entries:
            geojson = entry.get("geojson", {})
            for feat in geojson.get("features", []):
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [[]])[0]
                if not coords:
                    continue
                # Centro do polígono = média dos vértices (excluindo o repetido)
                lons = [p[0] for p in coords[:-1]]
                lats = [p[1] for p in coords[:-1]]
                if lons and lats:
                    clon = sum(lons) / len(lons)
                    clat = sum(lats) / len(lats)
                    score = props.get("score")
                    if score is not None:
                        cells.append((clon, clat, float(score)))

        if not cells:
            return targets

        result = []
        for target in targets:
            nearest_score = min(
                cells,
                key=lambda c: Orchestrator._haversine_km(
                    target.longitude, target.latitude, c[0], c[1]
                ),
            )[2]
            result.append(target.model_copy(update={"prospectivity_score": nearest_score}))
        return result

    @staticmethod
    def _validate_target_coords(
        targets: list[MineralTarget],
        bbox: BoundingBox,
    ) -> list[MineralTarget]:
        """Garante que todos os alvos têm coordenadas dentro do bbox.

        Se o LLM retornar coordenadas fora do bbox (contaminação por dados
        de outra região), o alvo é movido para o centróide do bbox.
        """
        cx, cy = bbox.center
        result = []
        for t in targets:
            if bbox.contains_point(t.longitude, t.latitude):
                result.append(t)
            else:
                logger.warning(
                    "target_coord_out_of_bbox",
                    name=t.name,
                    lon=t.longitude,
                    lat=t.latitude,
                    bbox=bbox.as_tuple(),
                )
                result.append(
                    t.model_copy(
                        update={
                            "longitude": cx,
                            "latitude": cy,
                        }
                    )
                )
        return result

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
        """Monta resumo integrado a partir dos resultados dos passos.

        Prioriza o resumo do Evaluator (total_integration), que é a síntese
        final produzida pelo agente avaliador. Recorre à concatenação dos
        passos individuais apenas se o Evaluator não produziu resumo.
        """
        if not step_results:
            return "Análise não executada."

        # Usar resumo do Evaluator como integrated_summary (síntese final)
        for result in step_results:
            if result.step == AnalysisStep.TOTAL_INTEGRATION and result.summary:
                # Remover prefixo [total_integration] se o _merge_step_results o adicionou
                summary = result.summary
                prefix = "[total_integration] "
                if summary.startswith(prefix):
                    summary = summary[len(prefix) :]
                return summary

        # Fallback: concatenar resumos dos passos individuais (sem total_integration)
        parts: list[str] = []
        for result in step_results:
            if result.step != AnalysisStep.TOTAL_INTEGRATION and result.summary:
                parts.append(f"[{result.step.value}] {result.summary}")

        return " | ".join(parts) if parts else "Sem resumo disponível."

    @staticmethod
    def _collect_caveats(
        step_results: list[StepResult],
        geological_data: dict[str, list[dict[str, Any]]],
        bbox_filtered_sources: list[str] | None = None,
    ) -> list[str]:
        """Coleta caveats (ressalvas) sobre a análise."""
        caveats: list[str] = []
        filtered = set(bbox_filtered_sources or [])

        # Dados faltantes (serviços que falharam ou não retornaram nada)
        empty_services = [k for k, v in geological_data.items() if not v and k not in filtered]
        if empty_services:
            caveats.append(f"Dados indisponíveis para: {', '.join(empty_services)}")

        # Dados fora do bbox (serviços que retornaram dados, mas todos estavam fora da área)
        if filtered:
            caveats.append(
                f"Dados retornados fora da área de interesse para: {', '.join(sorted(filtered))} "
                f"— registros descartados pelo filtro de bbox"
            )

        # Baixa confiança
        low_confidence = [
            r for r in step_results if r.confidence in (Confidence.LOW, Confidence.INSUFFICIENT)
        ]
        if low_confidence:
            steps_str = ", ".join(r.step.value for r in low_confidence)
            caveats.append(f"Baixa confiança em: {steps_str}")

        # Data gaps reportados pelos agentes — deduplicação semântica por palavras-chave
        all_gaps: list[str] = []
        for r in step_results:
            all_gaps.extend(r.data_gaps)
        if all_gaps:
            unique_gaps = Orchestrator._dedup_gaps_semantic(all_gaps, max_gaps=5)
            caveats.append(f"Lacunas de dados: {'; '.join(unique_gaps)}")

        return caveats

    # Stopwords PT-BR para dedup semântico de data_gaps
    _GAP_STOPWORDS: frozenset[str] = frozenset(
        [
            "de",
            "para",
            "e",
            "a",
            "o",
            "os",
            "as",
            "um",
            "uma",
            "com",
            "sem",
            "na",
            "no",
            "nas",
            "nos",
            "que",
            "ao",
            "da",
            "do",
            "das",
            "dos",
            "por",
            "em",
            "são",
            "é",
            "pela",
            "pelo",
            "pelas",
            "pelos",
        ]
    )

    @staticmethod
    def _dedup_gaps_semantic(gaps: list[str], max_gaps: int = 5) -> list[str]:
        """Remove gaps semanticamente similares preservando os mais informativos.

        Dois gaps são considerados duplicatas se compartilham ≥ 60% das
        palavras significativas (excluindo stopwords). Mantém o gap mais longo
        (mais informativo) e descarta os menores que sejam subconjunto dele.
        """

        def significant_words(text: str) -> frozenset[str]:
            words = re.findall(r"[a-záéíóúâêîôûãõàüç]+", text.lower())
            return frozenset(
                w for w in words if w not in Orchestrator._GAP_STOPWORDS and len(w) > 2
            )

        # Dedup exato primeiro
        seen: list[str] = list(dict.fromkeys(gaps))

        # Dedup semântico — O(n²) mas n é pequeno (≤20 gaps tipicamente)
        result: list[str] = []
        for gap in seen:
            gap_words = significant_words(gap)
            if not gap_words:
                result.append(gap)
                continue
            is_dup = False
            for kept in result:
                kept_words = significant_words(kept)
                if not kept_words:
                    continue
                intersection = gap_words & kept_words
                overlap = len(intersection) / max(len(gap_words), len(kept_words))
                if overlap >= 0.60:
                    is_dup = True
                    break
            if not is_dup:
                result.append(gap)

        # Ordenar por comprimento decrescente (mais informativos primeiro) e limitar
        result.sort(key=len, reverse=True)
        return result[:max_gaps]

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

        # Cobertura de serviços (geological_data pode conter chaves derivadas além
        # dos 6 serviços GeoSGB → cap em 1.0 para evitar score > 1)
        total_services = 6
        active = sum(1 for v in geological_data.values() if v)
        coverage_score = min(1.0, active / total_services)

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
        return min(1.0, round(quality, 3))

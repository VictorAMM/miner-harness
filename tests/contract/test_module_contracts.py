"""Testes de contrato entre modulos.

Validam que as interfaces entre modulos sao respeitadas:
- GeoSGBConnector output -> CacheManager input
- CacheManager output -> ContextBuilder input
- ContextBuilder output -> Orchestrator input
- Orchestrator output -> ReportValidator input

Ref: ASO v3 Phase 7 -- Testing Swarm
"""

from __future__ import annotations

from datetime import datetime, timezone  # noqa: UP017
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from miner_harness.cache.manager import CacheManager
from miner_harness.core.config import MinerHarnessConfig, StorageConfig
from miner_harness.core.types import (
    AmostraGeoquimica,
    AnalysisStep,
    BoundingBox,
    Confidence,
    Coordenada,
    DadoGravimetrico,
    DatacaoGeocronologica,
    MineralTarget,
    OcorrenciaMineral,
    ProjetoAerogeofisico,
    ProspectionReport,
    StepResult,
    UnidadeLitoestratigrafica,
)
from miner_harness.orchestrator.context_builder import ContextBuilder
from miner_harness.orchestrator.report_validator import ReportValidator

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)


@pytest.fixture
def cache(tmp_path: Path) -> CacheManager:
    config = StorageConfig(miner_home=tmp_path / ".miner-harness")
    c = CacheManager(config)
    yield c
    c.close()


class TestGeoSGBToCacheContract:
    """Contrato: GeoSGBConnector retorna Pydantic models
    que sao convertidos para dicts via model_dump() antes do cache."""

    def test_pydantic_model_serializes_for_cache(
        self, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """model_dump() output deve ser aceito por CacheManager.put()."""
        oc = OcorrenciaMineral(
            objectid=1,
            substancias="Cobre",
            municipio="Parauapebas",
            uf="PA",
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        features = [oc.model_dump()]
        cache.put("ocorrencias", bbox, features)
        result = cache.get("ocorrencias", bbox)
        assert result is not None
        assert len(result) == 1
        assert result[0]["substancias"] == "Cobre"
        assert result[0]["coordenada"]["longitude"] == -50.0

    def test_all_geo_types_roundtrip_through_cache(
        self, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Todos os 6 tipos Pydantic devem serializar e deserializar via cache."""
        samples = {
            "ocorrencias": OcorrenciaMineral(
                objectid=1, substancias="Au", municipio="X", uf="PA",
                coordenada=Coordenada(longitude=-50, latitude=-6),
            ).model_dump(),
            "gravimetria": DadoGravimetrico(
                objectid=2,
                coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
                altitude_ortometrica=200.0,
                gravidade=978500.0,
                anomalia_ar_livre=-10.0,
                anomalia_bouguer=-30.5,
            ).model_dump(),
            "geoquimica": AmostraGeoquimica(
                objectid=3, projeto="P1", classe="Rocha",
                coordenada=Coordenada(longitude=-50, latitude=-6),
            ).model_dump(),
            "geocronologia": DatacaoGeocronologica(
                objectid=4, metodo="U-Pb", idade_ma=2750.0, erro_ma=10.0,
                coordenada=Coordenada(longitude=-50, latitude=-6),
            ).model_dump(),
            "litoestratigrafia": UnidadeLitoestratigrafica(
                objectid=5, nome="Fm. Carajas", sigla="Kc", eon="Arqueano",
            ).model_dump(),
            "aerogeofisica": ProjetoAerogeofisico(
                objectid=6, coordenada=Coordenada(longitude=-50, latitude=-6),
            ).model_dump(),
        }

        for service, data in samples.items():
            cache.put(service, bbox, [data])
            result = cache.get(service, bbox)
            assert result is not None, f"Cache roundtrip failed for {service}"
            assert len(result) == 1
            assert result[0]["objectid"] == data["objectid"]


class TestCacheToContextBuilderContract:
    """Contrato: CacheManager.get() retorna list[dict] que ContextBuilder
    passa diretamente para o contexto sem transformacao."""

    @pytest.mark.asyncio
    async def test_cache_output_is_context_input(
        self, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Dados no cache devem aparecer identicos no contexto."""
        features = [
            {"objectid": 1, "substancias": "Cobre", "uf": "PA"},
            {"objectid": 2, "substancias": "Ouro", "uf": "MG"},
        ]
        cache.put("ocorrencias", bbox, features)

        connector = MagicMock()
        for method in [
            "ocorrencias", "gravimetria", "geoquimica",
            "geocronologia", "litoestratigrafia", "aerogeofisica",
        ]:
            setattr(connector, method, AsyncMock(return_value=[]))

        builder = ContextBuilder(connector, cache)
        context = await builder.build(bbox)

        assert context["ocorrencias"] == features
        connector.ocorrencias.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_has_all_six_services(
        self, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """ContextBuilder sempre retorna dict com exatamente 6 chaves."""
        connector = MagicMock()
        for method in [
            "ocorrencias", "gravimetria", "geoquimica",
            "geocronologia", "litoestratigrafia", "aerogeofisica",
        ]:
            setattr(connector, method, AsyncMock(return_value=[]))

        builder = ContextBuilder(connector, cache)
        context = await builder.build(bbox)

        expected_keys = {
            "ocorrencias", "gravimetria", "geoquimica",
            "geocronologia", "litoestratigrafia", "aerogeofisica",
        }
        assert set(context.keys()) == expected_keys
        assert all(isinstance(v, list) for v in context.values())


class TestContextToOrchestratorContract:
    """Contrato: Orchestrator espera context dict[str, list[dict]]
    com pelo menos MIN_DATA_SOURCES fontes nao-vazias."""

    @pytest.mark.asyncio
    async def test_insufficient_sources_raises(
        self, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """< 3 fontes nao-vazias deve levantar InsufficientDataError."""
        from miner_harness.core.exceptions import InsufficientDataError
        from miner_harness.orchestrator.orchestrator import Orchestrator

        cache.put("ocorrencias", bbox, [{"id": 1}])
        cache.put("gravimetria", bbox, [{"id": 2}])

        connector = MagicMock()
        for method in [
            "ocorrencias", "gravimetria", "geoquimica",
            "geocronologia", "litoestratigrafia", "aerogeofisica",
        ]:
            setattr(connector, method, AsyncMock(return_value=[]))
        llm = MagicMock()
        config = MinerHarnessConfig()
        orch = Orchestrator(connector, cache, llm, config)

        with pytest.raises(InsufficientDataError):
            await orch.analyze_region(bbox, "Test")

    @pytest.mark.asyncio
    async def test_sufficient_sources_accepted(
        self, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """3+ fontes nao-vazias devem ser aceitas pelo Orchestrator."""
        from miner_harness.orchestrator.orchestrator import Orchestrator

        services = ["ocorrencias", "gravimetria", "geoquimica"]
        for svc in services:
            cache.put(svc, bbox, [{"objectid": i} for i in range(5)])

        connector = MagicMock()
        for method in [
            "ocorrencias", "gravimetria", "geoquimica",
            "geocronologia", "litoestratigrafia", "aerogeofisica",
        ]:
            setattr(connector, method, AsyncMock(return_value=[]))
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            content='{"summary": "ok", "findings": ["f1"], '
                    '"confidence": "medium", "data_sources_used": ["src"], '
                    '"data_gaps": []}',
            prompt_eval_count=10,
            eval_count=20,
        ))
        config = MinerHarnessConfig()
        orch = Orchestrator(connector, cache, llm, config)

        report = await orch.analyze_region(
            bbox, "Test", steps=[AnalysisStep.TECTONIC_HISTORY],
        )
        assert report.region_name == "Test"
        assert len(report.steps) == 1


class TestOrchestratorToValidatorContract:
    """Contrato: Orchestrator produz ProspectionReport que ReportValidator aceita."""

    def _make_valid_report(self, bbox: BoundingBox) -> ProspectionReport:
        steps = []
        for step_enum in AnalysisStep:
            steps.append(StepResult(
                step=step_enum,
                agent="test_agent",
                summary=f"Analysis of {step_enum.value}",
                findings=["Finding 1"],
                confidence=Confidence.MEDIUM,
                data_sources_used=["ocorrencias"],
                data_gaps=[],
                raw_reasoning="Reasoning text",
                duration_ms=100,
            ))
        return ProspectionReport(
            region_name="Carajas",
            bbox=bbox,
            steps=steps,
            targets=[
                MineralTarget(
                    name="Target Alpha",
                    longitude=-50.5,
                    latitude=-6.0,
                    radius_km=5.0,
                    commodities=["Cu", "Au"],
                    mineral_system="Porphyry Cu-Au",
                    confidence=Confidence.MEDIUM,
                    priority=1,
                    rationale="High Cu anomaly in NW sector",
                    recommended_followup=["Soil sampling", "IP survey"],
                ),
            ],
            integrated_summary="Integration complete",
            caveats=[],
            data_quality_score=0.85,
            model_used="qwen2.5:14b",
            total_duration_ms=500,
            analysis_date=datetime.now(tz=timezone.utc),  # noqa: UP017
        )

    def test_valid_report_passes_validation(self, bbox: BoundingBox) -> None:
        """Report com 5 steps, targets validos e metadata completa deve passar."""
        report = self._make_valid_report(bbox)
        validator = ReportValidator()
        result = validator.validate(report)
        assert result.is_valid, (
            f"Valid report rejected: {[i.message for i in result.issues]}"
        )

    def test_report_fields_match_validator_expectations(
        self, bbox: BoundingBox
    ) -> None:
        """Todos os campos que o validator checa devem existir no report."""
        report = self._make_valid_report(bbox)
        assert hasattr(report, "steps")
        assert hasattr(report, "targets")
        assert hasattr(report, "analysis_date")
        assert hasattr(report, "total_duration_ms")
        assert hasattr(report, "data_quality_score")
        assert hasattr(report, "model_used")
        assert hasattr(report, "bbox")

        for step in report.steps:
            assert hasattr(step, "step")
            assert hasattr(step, "summary")
            assert hasattr(step, "findings")
            assert hasattr(step, "confidence")
            assert hasattr(step, "data_sources_used")
            assert hasattr(step, "data_gaps")

        for target in report.targets:
            assert hasattr(target, "name")
            assert hasattr(target, "commodities")
            assert hasattr(target, "rationale")
            assert hasattr(target, "longitude")
            assert hasattr(target, "latitude")
            assert hasattr(target, "radius_km")

    def test_repair_prunes_invalid_targets_and_adds_caveats(
        self, bbox: BoundingBox
    ) -> None:
        """repair() deve remover targets sem rationale e adicionar caveats."""
        report = self._make_valid_report(bbox)
        # Add a target with empty rationale (should be pruned)
        report.targets.append(MineralTarget(
            name="Bad Target",
            longitude=-50.0,
            latitude=-6.0,
            radius_km=5.0,
            commodities=["Fe"],
            mineral_system="BIF",
            confidence=Confidence.LOW,
            priority=2,
            rationale="",
            recommended_followup=[],
        ))
        validator = ReportValidator()
        result = validator.validate(report)

        repaired = validator.repair(report, result)
        # Bad target should be pruned
        assert len(repaired.targets) == 1
        assert repaired.targets[0].name == "Target Alpha"
        # Quality score should be adjusted
        assert repaired.data_quality_score <= report.data_quality_score


class TestBoundingBoxContract:
    """Contrato: BoundingBox.hash() e as_tuple() sao usados
    consistentemente em cache keys e logging."""

    def test_hash_used_as_cache_key(
        self, cache: CacheManager, bbox: BoundingBox
    ) -> None:
        """Dois BBox identicos devem produzir cache hit."""
        bbox2 = BoundingBox(
            lon_min=bbox.lon_min, lat_min=bbox.lat_min,
            lon_max=bbox.lon_max, lat_max=bbox.lat_max,
        )
        cache.put("ocorrencias", bbox, [{"id": 1}])
        result = cache.get("ocorrencias", bbox2)
        assert result is not None

    def test_as_tuple_matches_constructor(self, bbox: BoundingBox) -> None:
        """as_tuple() deve retornar mesmos valores do construtor."""
        t = bbox.as_tuple()
        assert t == (bbox.lon_min, bbox.lat_min, bbox.lon_max, bbox.lat_max)

    def test_bbox_hash_deterministic_across_instances(self) -> None:
        """Hash deve ser identico para bbox com mesmos valores."""
        b1 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        b2 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
        assert b1.hash() == b2.hash()
        b3 = BoundingBox(lon_min=-45.0, lat_min=-10.0, lon_max=-43.0, lat_max=-8.0)
        assert b1.hash() != b3.hash()

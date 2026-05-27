"""Testes para core/types.py — modelos de domínio."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    Coordenada,
    FuroSondagem,
    MineralTarget,
    OcorrenciaMineral,
    ProspectionReport,
    StepResult,
)


class TestCoordenada:
    """Testes para Coordenada."""

    def test_valid_coordinate(self) -> None:
        coord = Coordenada(longitude=-49.9, latitude=-6.07)
        assert coord.longitude == -49.9
        assert coord.latitude == -6.07
        assert coord.datum == "WGS84"

    def test_rejects_out_of_brazil(self) -> None:
        with pytest.raises(ValueError):
            Coordenada(longitude=0.0, latitude=0.0)

    def test_edge_of_brazil(self) -> None:
        coord = Coordenada(longitude=-74.0, latitude=-34.0)
        assert coord.longitude == -74.0


class TestBoundingBox:
    """Testes para BoundingBox."""

    def test_width_height(self, bbox_carajas: BoundingBox) -> None:
        assert bbox_carajas.width == pytest.approx(2.5)
        assert bbox_carajas.height == pytest.approx(2.0)

    def test_center(self, bbox_carajas: BoundingBox) -> None:
        lon, lat = bbox_carajas.center
        assert lon == pytest.approx(-50.25)
        assert lat == pytest.approx(-6.0)

    def test_hash_deterministic(self) -> None:
        bbox1 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        bbox2 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        assert bbox1.hash() == bbox2.hash()

    def test_hash_invariant_to_precision(self) -> None:
        bbox1 = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0)
        bbox2 = BoundingBox(lon_min=-51.500, lat_min=-7.000, lon_max=-49.000, lat_max=-5.000)
        assert bbox1.hash() == bbox2.hash()

    def test_contains_point(self, bbox_carajas: BoundingBox) -> None:
        assert bbox_carajas.contains_point(-50.0, -6.0)
        assert not bbox_carajas.contains_point(-48.0, -6.0)

    def test_as_tuple(self, bbox_carajas: BoundingBox) -> None:
        assert bbox_carajas.as_tuple() == (-51.5, -7.0, -49.0, -5.0)

    def test_inverted_lon_raises(self) -> None:
        with pytest.raises(ValueError, match="lon_min"):
            BoundingBox(lon_min=-49.0, lat_min=-7.0, lon_max=-51.5, lat_max=-5.0)

    def test_inverted_lat_raises(self) -> None:
        with pytest.raises(ValueError, match="lat_min"):
            BoundingBox(lon_min=-51.5, lat_min=-5.0, lon_max=-49.0, lat_max=-7.0)


class TestOcorrenciaMineral:
    """Testes para OcorrenciaMineral."""

    def test_valid_ocorrencia(self) -> None:
        oc = OcorrenciaMineral(
            objectid=12345,
            substancias="Cobre, Ouro",
            municipio="Parauapebas",
            uf="PA",
            provincia="Carajás",
            coordenada=Coordenada(longitude=-49.9, latitude=-6.07),
        )
        assert oc.substancias == "Cobre, Ouro"
        assert oc.uf == "PA"

    def test_optional_fields_default_none(self) -> None:
        oc = OcorrenciaMineral(
            objectid=1,
            substancias="Ferro",
            municipio="Marabá",
            uf="PA",
            coordenada=Coordenada(longitude=-49.1, latitude=-5.4),
        )
        assert oc.provincia is None
        assert oc.rochas_hospedeiras is None


class TestStepResult:
    """Testes para StepResult."""

    def test_serialization_roundtrip(self) -> None:
        result = StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="structural_geologist",
            summary="Região dominada por crosta arqueana.",
            findings=["Cráton Amazônico", "Greenstone belt"],
            confidence=Confidence.MEDIUM,
            data_sources_used=["litoestratigrafia", "geocronologia"],
            data_gaps=["magnetometria regional"],
            raw_reasoning="Raciocínio completo...",
            duration_ms=5000,
        )
        data = result.model_dump()
        restored = StepResult.model_validate(data)
        assert restored == result


class TestMineralTarget:
    """Testes para MineralTarget."""

    def test_priority_bounds(self) -> None:
        with pytest.raises(ValueError):
            MineralTarget(
                name="Alvo X",
                longitude=-50.0,
                latitude=-6.0,
                radius_km=5.0,
                commodities=["Cu"],
                mineral_system="IOCG",
                confidence=Confidence.HIGH,
                priority=0,  # inválido — mínimo é 1
                rationale="teste",
                recommended_followup=[],
            )

    def test_valid_target(self) -> None:
        target = MineralTarget(
            name="Alvo Serra Sul",
            longitude=-50.3,
            latitude=-6.4,
            radius_km=3.0,
            commodities=["Cu", "Au"],
            mineral_system="IOCG",
            confidence=Confidence.HIGH,
            priority=1,
            rationale="Forte assinatura IOCG.",
            recommended_followup=["IP/Res", "Sondagem"],
        )
        assert target.priority == 1
        assert len(target.commodities) == 2


class TestMineralTargetAliasValidator:
    """Testes do model_validator que normaliza variantes de mineral_system."""

    _BASE: dict = {
        "name": "Alvo Tucumã",
        "longitude": -51.19,
        "latitude": -6.87,
        "radius_km": 10.0,
        "commodities": ["Sn", "W"],
        "confidence": Confidence.MEDIUM,
        "priority": 2,
        "rationale": "Granito evoluído com casiterita.",
        "recommended_followup": ["Sondagem"],
    }

    def test_mineralization_system_alias(self) -> None:
        """LLM retorna 'mineralization_system' → deve mapear para mineral_system."""
        data = {**self._BASE, "mineralization_system": "Granito Estanífero"}
        t = MineralTarget(**data)
        assert t.mineral_system == "Granito Estanífero"

    def test_system_alias(self) -> None:
        """LLM retorna 'system' → deve mapear para mineral_system."""
        data = {**self._BASE, "system": "Pórfiro Cu-Au"}
        t = MineralTarget(**data)
        assert t.mineral_system == "Pórfiro Cu-Au"

    def test_mineralization_type_alias(self) -> None:
        """LLM retorna 'mineralization_type' → deve mapear para mineral_system."""
        data = {**self._BASE, "mineralization_type": "VMS"}
        t = MineralTarget(**data)
        assert t.mineral_system == "VMS"

    def test_canonical_field_takes_precedence(self) -> None:
        """Se mineral_system está presente, aliases são ignorados."""
        data = {**self._BASE, "mineral_system": "IOCG", "mineralization_system": "Outro"}
        t = MineralTarget(**data)
        assert t.mineral_system == "IOCG"

    def test_no_alias_no_field_still_raises(self) -> None:
        """Sem mineral_system nem alias, Pydantic deve rejeitar."""
        with pytest.raises(ValueError):
            MineralTarget(**self._BASE)

    def test_non_dict_data_passthrough(self) -> None:
        """Dados nao-dict (ex: string) sao passados adiante sem modificacao."""
        result = MineralTarget._normalize_field_aliases("not a dict")
        assert result == "not a dict"


class TestFuroSondagem:
    """Testes para FuroSondagem."""

    def test_valid_furo(self) -> None:
        furo = FuroSondagem(
            objectid=1,
            projeto="CARAJAS",
            tipo_furo="Diamantada",
            profundidade_m=350.0,
            azimute=90.0,
            mergulho=-60.0,
            ano=1985,
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        assert furo.objectid == 1
        assert furo.projeto == "CARAJAS"
        assert furo.profundidade_m == 350.0

    def test_optional_fields_default_none(self) -> None:
        furo = FuroSondagem(
            objectid=2,
            coordenada=Coordenada(longitude=-50.1, latitude=-6.1),
        )
        assert furo.projeto is None
        assert furo.tipo_furo is None
        assert furo.profundidade_m is None
        assert furo.azimute is None
        assert furo.mergulho is None
        assert furo.ano is None

    def test_serialization_roundtrip(self) -> None:
        furo = FuroSondagem(
            objectid=3,
            projeto="TEST",
            profundidade_m=100.0,
            coordenada=Coordenada(longitude=-49.9, latitude=-6.07),
        )
        data = furo.model_dump()
        restored = FuroSondagem.model_validate(data)
        assert restored == furo


# ---------------------------------------------------------------------------
# PRD-006 — calibration_note + diversity_removed_count
# ---------------------------------------------------------------------------


class TestStepResultCalibrationNote:
    """Testes PRD-006: campo calibration_note no StepResult."""

    def _make_step_result(self, **overrides: object) -> StepResult:
        base: dict[str, object] = {
            "step": AnalysisStep.TECTONIC_HISTORY,
            "agent": "structural_geologist",
            "summary": "Região arqueana.",
            "findings": ["Cráton Amazônico"],
            "confidence": Confidence.HIGH,
            "data_sources_used": ["litoestratigrafia"],
            "data_gaps": [],
            "raw_reasoning": "...",
            "duration_ms": 1000,
        }
        base.update(overrides)
        return StepResult(**base)  # type: ignore[arg-type]

    def test_calibration_note_defaults_to_none(self) -> None:
        """calibration_note deve ser None por padrão."""
        result = self._make_step_result()
        assert result.calibration_note is None

    def test_calibration_note_stores_value(self) -> None:
        """calibration_note armazena nota do ConfidenceCalibrator."""
        note = "Confiança recalibrada para LOW: cobertura de dados < 50%."
        result = self._make_step_result(calibration_note=note)
        assert result.calibration_note == note

    def test_calibration_note_roundtrip(self) -> None:
        """calibration_note sobrevive a serialização model_dump/model_validate."""
        note = "Nota de calibração de confiança."
        result = self._make_step_result(calibration_note=note)
        data = result.model_dump()
        restored = StepResult.model_validate(data)
        assert restored.calibration_note == note

    def test_calibration_note_not_in_data_gaps(self) -> None:
        """calibration_note NÃO deve aparecer em data_gaps."""
        note = "Confiança recalibrada de HIGH para MEDIUM."
        result = self._make_step_result(calibration_note=note, data_gaps=["lacuna A"])
        assert note not in result.data_gaps
        assert result.data_gaps == ["lacuna A"]


class TestProspectionReportDiversityCount:
    """Testes PRD-006: campo diversity_removed_count no ProspectionReport."""

    def _make_report(self, **overrides: object) -> ProspectionReport:
        step = StepResult(
            step=AnalysisStep.TECTONIC_HISTORY,
            agent="geo",
            summary="s",
            findings=[],
            confidence=Confidence.LOW,
            data_sources_used=[],
            data_gaps=[],
            raw_reasoning="",
            duration_ms=0,
        )
        target = MineralTarget(
            name="Alvo A",
            longitude=-50.0,
            latitude=-6.0,
            radius_km=5.0,
            commodities=["Cu"],
            mineral_system="IOCG",
            confidence=Confidence.MEDIUM,
            priority=1,
            rationale="teste",
            recommended_followup=[],
        )
        base: dict[str, object] = {
            "region_name": "Carajás",
            "bbox": BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
            "analysis_date": datetime.now(tz=timezone.utc),
            "steps": [step],
            "targets": [target],
            "integrated_summary": "Sumário.",
            "caveats": [],
            "data_quality_score": 0.7,
            "total_duration_ms": 5000,
            "model_used": "qwen3:8b",
        }
        base.update(overrides)
        return ProspectionReport(**base)  # type: ignore[arg-type]

    def test_diversity_removed_count_defaults_to_zero(self) -> None:
        """diversity_removed_count deve ser 0 por padrão."""
        report = self._make_report()
        assert report.diversity_removed_count == 0

    def test_diversity_removed_count_stores_value(self) -> None:
        """diversity_removed_count armazena contagem de alvos removidos."""
        report = self._make_report(diversity_removed_count=3)
        assert report.diversity_removed_count == 3

    def test_diversity_removed_count_roundtrip(self) -> None:
        """diversity_removed_count sobrevive a serialização."""
        report = self._make_report(diversity_removed_count=2)
        data = report.model_dump()
        restored = ProspectionReport.model_validate(data)
        assert restored.diversity_removed_count == 2


class TestProspectionReportEmptySources:
    """Testes PRD-008 T1: campo empty_sources no ProspectionReport."""

    def _make_report(self, **overrides: object) -> ProspectionReport:
        base: dict[str, object] = {
            "region_name": "Carajás",
            "bbox": BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.0, lat_max=-5.0),
            "analysis_date": datetime.now(tz=timezone.utc),
            "steps": [],
            "targets": [],
            "integrated_summary": "",
            "caveats": [],
            "data_quality_score": 0.5,
            "total_duration_ms": 0,
            "model_used": "qwen3:8b",
        }
        base.update(overrides)
        return ProspectionReport(**base)  # type: ignore[arg-type]

    def test_empty_sources_defaults_to_empty_list(self) -> None:
        """empty_sources deve ser [] por padrão."""
        report = self._make_report()
        assert report.empty_sources == []

    def test_empty_sources_stores_values(self) -> None:
        """empty_sources armazena lista de fontes sem dados."""
        report = self._make_report(empty_sources=["gravimetria", "geocronologia"])
        assert report.empty_sources == ["gravimetria", "geocronologia"]

    def test_empty_sources_roundtrip(self) -> None:
        """empty_sources sobrevive a serialização model_dump/model_validate."""
        report = self._make_report(empty_sources=["gravimetria"])
        data = report.model_dump()
        restored = ProspectionReport.model_validate(data)
        assert restored.empty_sources == ["gravimetria"]

    def test_empty_sources_independent_of_missing_sources(self) -> None:
        """empty_sources e missing_sources são listas independentes."""
        report = self._make_report(
            empty_sources=["gravimetria"],
            missing_sources=["aerogeofisica"],
        )
        assert "gravimetria" not in report.missing_sources
        assert "aerogeofisica" not in report.empty_sources

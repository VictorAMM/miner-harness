"""Testes para core/types.py — modelos de domínio."""

from __future__ import annotations

import pytest

from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    Coordenada,
    MineralTarget,
    OcorrenciaMineral,
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

"""Testes do text_builder — conversão de features para texto.

Ref: RFC-003 §4.5
"""

from __future__ import annotations

from miner_harness.core.types import (
    AmostraGeoquimica,
    Coordenada,
    DadoGravimetrico,
    DatacaoGeocronologica,
    OcorrenciaMineral,
    ProjetoAerogeofisico,
    UnidadeLitoestratigrafica,
)
from miner_harness.index.text_builder import dict_to_text, feature_to_text


class TestFeatureToTextOcorrencia:
    """Testes para OcorrenciaMineral."""

    def test_contains_key_fields(self) -> None:
        oc = OcorrenciaMineral(
            objectid=1,
            substancias="Cobre, Ouro",
            municipio="Parauapebas",
            uf="PA",
            provincia="Carajás",
            rochas_hospedeiras="Gabro",
            tipos_alteracao="Potássica",
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        text = feature_to_text(oc, "geosgb/ocorrencias")
        assert "Parauapebas" in text
        assert "Cobre, Ouro" in text
        assert "Carajás" in text
        assert "Gabro" in text
        assert "Potássica" in text

    def test_optional_fields_omitted(self) -> None:
        oc = OcorrenciaMineral(
            objectid=1,
            substancias="Ferro",
            municipio="Belo Horizonte",
            uf="MG",
            coordenada=Coordenada(longitude=-44.0, latitude=-20.0),
        )
        text = feature_to_text(oc, "geosgb/ocorrencias")
        assert "Ferro" in text
        assert "Provincia" not in text  # None → omitted


class TestFeatureToTextGravimetria:
    """Testes para DadoGravimetrico."""

    def test_contains_numeric_values(self) -> None:
        grav = DadoGravimetrico(
            objectid=1,
            coordenada=Coordenada(longitude=-50.12, latitude=-6.05),
            altitude_ortometrica=245.0,
            gravidade=978.5,
            anomalia_ar_livre=12.8,
            anomalia_bouguer=-35.2,
        )
        text = feature_to_text(grav, "geosgb/gravimetria")
        assert "-35.2" in text
        assert "12.8" in text
        assert "245" in text


class TestFeatureToTextGeoquimica:
    """Testes para AmostraGeoquimica."""

    def test_includes_analises(self) -> None:
        gq = AmostraGeoquimica(
            objectid=1,
            projeto="RENCA",
            classe="Sedimento de Corrente",
            material_coletado="Fração fina",
            coordenada=Coordenada(longitude=-52.0, latitude=-1.0),
            analises={"Cu_ppm": 45.0, "Au_ppb": 120.0, "Fe_pct": 8.5},
        )
        text = feature_to_text(gq, "geosgb/geoquimica")
        assert "RENCA" in text
        assert "Sedimento de Corrente" in text
        assert "Cu_ppm" in text


class TestFeatureToTextGeocronologia:
    """Testes para DatacaoGeocronologica."""

    def test_includes_age(self) -> None:
        gc = DatacaoGeocronologica(
            objectid=1,
            metodo="U-Pb",
            idade_ma=2750.0,
            erro_ma=15.0,
            material="Zircão",
            unidade_geologica="Suite Plaquê",
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        text = feature_to_text(gc, "geosgb/geocronologia")
        assert "U-Pb" in text
        assert "2750.0" in text
        assert "15.0" in text
        assert "Zircão" in text


class TestFeatureToTextLitoestratigrafia:
    """Testes para UnidadeLitoestratigrafica."""

    def test_includes_hierarchy(self) -> None:
        lit = UnidadeLitoestratigrafica(
            objectid=1,
            sigla="A4gr",
            nome="Grupo Grão Pará",
            hierarquia="Grupo",
            litologia_principal="Basalto",
            idade="Arqueano",
        )
        text = feature_to_text(lit, "geosgb/litoestratigrafia")
        assert "Grupo" in text
        assert "Basalto" in text
        assert "Arqueano" in text

    def test_includes_coord_when_present(self) -> None:
        lit = UnidadeLitoestratigrafica(
            objectid=2,
            sigla="A3f",
            hierarquia="Formação",
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        text = feature_to_text(lit, "geosgb/litoestratigrafia")
        assert "-50.0000" in text or "-50" in text
        assert "Coord" in text


class TestFeatureToTextAerogeofisica:
    """Testes para ProjetoAerogeofisico."""

    def test_includes_project_info(self) -> None:
        ag = ProjetoAerogeofisico(
            objectid=1,
            nome_projeto="PGBC",
            tipo_levantamento="Magnetometria",
            ano=2010,
            area_km2=15000.0,
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        text = feature_to_text(ag, "geosgb/aerogeofisica")
        assert "PGBC" in text
        assert "Magnetometria" in text
        assert "2010" in text
        assert "15000" in text


class TestFeatureToTextOcorrenciaExtraFields:
    """Cobre campos opcionais de OcorrenciaMineral não testados antes."""

    def test_rochas_encaixantes_status_morfologia(self) -> None:
        oc = OcorrenciaMineral(
            objectid=2,
            substancias="Ouro",
            municipio="Canaã dos Carajás",
            uf="PA",
            rochas_encaixantes="Granito",
            status_economico="Mina",
            morfologia="Veio",
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        text = feature_to_text(oc, "geosgb/ocorrencias")
        assert "Granito" in text
        assert "Mina" in text
        assert "Veio" in text


class TestFeatureToTextGeoquimicaRochaMatriz:
    """Cobre campo rocha_matriz de AmostraGeoquimica."""

    def test_rocha_matriz_presente(self) -> None:
        gq = AmostraGeoquimica(
            objectid=2,
            projeto="FOLIO",
            classe="Rocha",
            rocha_matriz="Granodiorito",
            coordenada=Coordenada(longitude=-50.0, latitude=-6.0),
        )
        text = feature_to_text(gq, "geosgb/geoquimica")
        assert "Granodiorito" in text


class TestFeatureToTextGenericFallback:
    """Cobre _generic_to_text para tipos não reconhecidos (linha 50 + 163-168)."""

    def test_unknown_basemodel_uses_generic(self) -> None:
        from pydantic import BaseModel as PydanticBaseModel

        class CustomFeature(PydanticBaseModel):
            objectid: int
            descricao: str
            valor: float | None = None

        feat = CustomFeature(objectid=99, descricao="teste", valor=1.5)
        text = feature_to_text(feat, "geosgb/custom")
        assert "geosgb/custom" in text
        assert "descricao" in text


class TestDictToText:
    """Testes do dict_to_text fallback."""

    def test_basic_dict(self) -> None:
        data = {"substancias": "Cobre", "uf": "PA", "vazio": None}
        text = dict_to_text(data, "geosgb/ocorrencias")
        assert "Cobre" in text
        assert "geosgb/ocorrencias" in text
        assert "vazio" not in text  # None omitted

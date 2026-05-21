"""Testes do AliasMapper — normalização de campos do GeoSGB."""

from __future__ import annotations

import pytest

from miner_harness.connectors.geosgb.alias_mapper import AliasMapper, _normalize_key


class TestNormalizeKey:
    """Testes da função de normalização de chaves."""

    def test_lowercase(self) -> None:
        assert _normalize_key("OBJECTID") == "objectid"

    def test_remove_accents(self) -> None:
        assert _normalize_key("Município") == "municipio"

    def test_spaces_to_underscores(self) -> None:
        assert _normalize_key("Substâncias minerais") == "substancias_minerais"

    def test_remove_special_chars(self) -> None:
        assert _normalize_key("campo (extra)") == "campo_extra"

    def test_combined(self) -> None:
        assert _normalize_key("Província mineral") == "provincia_mineral"


class TestAliasMapper:
    """Testes do AliasMapper por serviço."""

    def test_unknown_service_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown service"):
            AliasMapper("inexistente")

    def test_ocorrencias_basic_mapping(self) -> None:
        mapper = AliasMapper("ocorrencias")
        raw = {
            "OBJECTID": 123,
            "Substâncias minerais": "Cobre, Ouro",
            "Município": "Parauapebas",
            "UF": "PA",
        }
        mapped = mapper.map_record(raw)
        assert mapped["objectid"] == 123
        assert mapped["substancias"] == "Cobre, Ouro"
        assert mapped["municipio"] == "Parauapebas"
        assert mapped["uf"] == "PA"

    def test_gravimetria_alias_bouguer(self) -> None:
        mapper = AliasMapper("gravimetria")
        raw = {"anom_bougu": -45.2}
        mapped = mapper.map_record(raw)
        assert mapped["anomalia_bouguer"] == -45.2

    def test_unknown_fields_preserved_normalized(self) -> None:
        mapper = AliasMapper("ocorrencias")
        raw = {"Campo Desconhecido": "valor"}
        mapped = mapper.map_record(raw)
        assert mapped["campo_desconhecido"] == "valor"

    def test_map_records_batch(self) -> None:
        mapper = AliasMapper("ocorrencias")
        records = [
            {"OBJECTID": 1, "UF": "PA"},
            {"OBJECTID": 2, "UF": "MG"},
        ]
        mapped = mapper.map_records(records)
        assert len(mapped) == 2
        assert mapped[0]["objectid"] == 1
        assert mapped[1]["uf"] == "MG"

    def test_geoquimica_mapper_exists(self) -> None:
        mapper = AliasMapper("geoquimica")
        raw = {"Projeto": "RENCA", "Classe": "Sedimento de Corrente"}
        mapped = mapper.map_record(raw)
        assert mapped["projeto"] == "RENCA"
        assert mapped["classe"] == "Sedimento de Corrente"

    def test_geocronologia_metodo_alias(self) -> None:
        mapper = AliasMapper("geocronologia")
        raw = {"Método analítico": "U-Pb"}
        mapped = mapper.map_record(raw)
        assert mapped["metodo"] == "U-Pb"

    def test_furos_mapper_exists(self) -> None:
        mapper = AliasMapper("furos")
        raw = {"Projeto": "CARAJAS", "Profundidade": 350.0}
        mapped = mapper.map_record(raw)
        assert mapped["projeto"] == "CARAJAS"
        assert mapped["profundidade_m"] == 350.0

    def test_furos_tipo_furo_alias(self) -> None:
        mapper = AliasMapper("furos")
        raw = {"tipo": "Diamantada"}
        mapped = mapper.map_record(raw)
        assert mapped["tipo_furo"] == "Diamantada"

    def test_furos_azimute_alias(self) -> None:
        mapper = AliasMapper("furos")
        raw = {"az": 90.0}
        mapped = mapper.map_record(raw)
        assert mapped["azimute"] == 90.0

    def test_furos_dip_alias(self) -> None:
        mapper = AliasMapper("furos")
        raw = {"dip": -60.0}
        mapped = mapper.map_record(raw)
        assert mapped["mergulho"] == -60.0

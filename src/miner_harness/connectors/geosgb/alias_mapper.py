"""Mapeamento de aliases do MapServer/identify para campos internos.

O MapServer retorna campos com nomes inconsistentes (acentuados,
espaços, abreviações). O AliasMapper normaliza para os nomes
esperados pelos modelos Pydantic do domínio.

Ref: RFC-001 §4.1, §2 (AliasMapper)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalize_key(key: str) -> str:
    """Normaliza uma chave: remove acentos, lowercase, troca espaços por _."""
    # NFD decompõe acentos; Mn = nonspacing marks (acentos)
    nfkd = unicodedata.normalize("NFKD", key)
    ascii_only = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    # Lowercase, espaços → underscores, remove caracteres especiais
    cleaned = re.sub(r"[^a-z0-9_]", "", ascii_only.lower().replace(" ", "_"))
    return cleaned


# ---------------------------------------------------------------------------
# Mapas por serviço — alias MapServer → campo Pydantic
# ---------------------------------------------------------------------------

# Ocorrências minerais (MapServer aliases reais observados na Fase 1)
_OCORRENCIAS_MAP: dict[str, str] = {
    "objectid": "objectid",
    "substancias_minerais": "substancias",
    "substancias": "substancias",
    "municipio": "municipio",
    "uf": "uf",
    "provincia_mineral": "provincia",
    "provincia": "provincia",
    "status_economico": "status_economico",
    "importancia": "importancia",
    "rochas_hospedeiras": "rochas_hospedeiras",
    "rochas_encaixantes": "rochas_encaixantes",
    "tipos_alteracao": "tipos_alteracao",
    "tipos_de_alteracao": "tipos_alteracao",
    "morfologia": "morfologia",
    "texturas": "texturas",
    "longitude": "longitude",
    "latitude": "latitude",
}

# Gravimetria (FeatureServer — campos mais consistentes)
_GRAVIMETRIA_MAP: dict[str, str] = {
    "objectid": "objectid",
    "longitude": "longitude",
    "latitude": "latitude",
    "altitude_ortometrica": "altitude_ortometrica",
    "alt_ortometrica": "altitude_ortometrica",
    "gravidade": "gravidade",
    "anomalia_ar_livre": "anomalia_ar_livre",
    "anom_ar_livre": "anomalia_ar_livre",
    "anomalia_bouguer": "anomalia_bouguer",
    "anom_bougu": "anomalia_bouguer",
    "anom_bouguer": "anomalia_bouguer",
}

# Geoquímica
_GEOQUIMICA_MAP: dict[str, str] = {
    "objectid": "objectid",
    "projeto": "projeto",
    "classe": "classe",
    "material_coletado": "material_coletado",
    "rocha_matriz": "rocha_matriz",
    "longitude": "longitude",
    "latitude": "latitude",
}

# Geocronologia
_GEOCRONOLOGIA_MAP: dict[str, str] = {
    "objectid": "objectid",
    "metodo": "metodo",
    "metodo_analitico": "metodo",
    "idade_ma": "idade_ma",
    "idade": "idade_ma",
    "erro_ma": "erro_ma",
    "erro": "erro_ma",
    "material": "material",
    "unidade_geologica": "unidade_geologica",
    "longitude": "longitude",
    "latitude": "latitude",
}

# Litoestratigrafia
_LITOESTRATIGRAFIA_MAP: dict[str, str] = {
    "objectid": "objectid",
    "sigla": "sigla",
    "nome": "nome",
    "hierarquia": "hierarquia",
    "litologia_principal": "litologia_principal",
    "litologia": "litologia_principal",
    "idade": "idade",
}

# Aerogeofísica
_AEROGEOFISICA_MAP: dict[str, str] = {
    "objectid": "objectid",
    "nome_projeto": "nome_projeto",
    "nome": "nome_projeto",
    "ano": "ano",
    "tipo_levantamento": "tipo_levantamento",
    "tipo": "tipo_levantamento",
    "area_km2": "area_km2",
    "area": "area_km2",
    "longitude": "longitude",
    "latitude": "latitude",
}

# Registro central de mapas por serviço
SERVICE_ALIAS_MAPS: dict[str, dict[str, str]] = {
    "ocorrencias": _OCORRENCIAS_MAP,
    "gravimetria": _GRAVIMETRIA_MAP,
    "geoquimica": _GEOQUIMICA_MAP,
    "geocronologia": _GEOCRONOLOGIA_MAP,
    "litoestratigrafia": _LITOESTRATIGRAFIA_MAP,
    "aerogeofisica": _AEROGEOFISICA_MAP,
}


class AliasMapper:
    """Mapeia campos da resposta do GeoSGB para nomes internos.

    O MapServer/identify retorna aliases com acentos e espaços.
    Esta classe normaliza para os campos esperados pelos modelos Pydantic.

    Campos não reconhecidos são preservados no dict resultante com a
    chave normalizada — útil para campos extras de geoquímica (analises).
    """

    def __init__(self, service: str) -> None:
        """Inicializa mapper para um serviço específico.

        Args:
            service: Nome do serviço (ex: "ocorrencias", "gravimetria").

        Raises:
            ValueError: Se o serviço não tem mapa de aliases definido.
        """
        if service not in SERVICE_ALIAS_MAPS:
            msg = f"Unknown service '{service}'. Known: {sorted(SERVICE_ALIAS_MAPS)}"
            raise ValueError(msg)
        self._service = service
        self._alias_map = SERVICE_ALIAS_MAPS[service]

    def map_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Mapeia um registro cru para campos internos.

        Args:
            raw: Dicionário com chaves brutas da API.

        Returns:
            Dicionário com chaves normalizadas.
            Campos conhecidos → nome interno.
            Campos desconhecidos → chave normalizada preservada.
        """
        result: dict[str, Any] = {}
        for key, value in raw.items():
            normalized_key = _normalize_key(key)
            mapped = self._alias_map.get(normalized_key, normalized_key)
            result[mapped] = value
        return result

    def map_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Mapeia uma lista de registros."""
        return [self.map_record(r) for r in records]

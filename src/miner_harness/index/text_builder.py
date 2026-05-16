"""Conversão de features GeoSGB em texto descritivo para embedding.

Cada tipo de feature tem uma estratégia de textualização que
prioriza os campos mais relevantes para busca semântica.

Ref: RFC-003 §4.5
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from miner_harness.core.types import (
    AmostraGeoquimica,
    DadoGravimetrico,
    DatacaoGeocronologica,
    OcorrenciaMineral,
    ProjetoAerogeofisico,
    UnidadeLitoestratigrafica,
)

if TYPE_CHECKING:
    from pydantic import BaseModel


def feature_to_text(feature: BaseModel, source: str) -> str:
    """Converte feature GeoSGB em texto descritivo para embedding.

    Args:
        feature: Feature tipada do GeoSGB.
        source: Identificador da fonte (ex: "geosgb/ocorrencias").

    Returns:
        Texto descritivo combinando campos relevantes.
    """
    if isinstance(feature, OcorrenciaMineral):
        return _ocorrencia_to_text(feature)
    if isinstance(feature, DadoGravimetrico):
        return _gravimetria_to_text(feature)
    if isinstance(feature, AmostraGeoquimica):
        return _geoquimica_to_text(feature)
    if isinstance(feature, DatacaoGeocronologica):
        return _geocronologia_to_text(feature)
    if isinstance(feature, UnidadeLitoestratigrafica):
        return _litoestratigrafia_to_text(feature)
    if isinstance(feature, ProjetoAerogeofisico):
        return _aerogeofisica_to_text(feature)

    # Fallback genérico
    return _generic_to_text(feature, source)


def dict_to_text(data: dict[str, Any], source: str) -> str:
    """Converte dict bruto em texto descritivo.

    Usado quando não temos o modelo tipado.
    """
    parts = [f"Registro de {source}."]
    for key, value in data.items():
        if value is not None and str(value).strip():
            parts.append(f"{key}: {value}")
    return " ".join(parts)


# ------------------------------------------------------------------
# Conversores específicos por tipo
# ------------------------------------------------------------------


def _ocorrencia_to_text(f: OcorrenciaMineral) -> str:
    parts = [f"Ocorrencia mineral em {f.municipio}, {f.uf}."]
    if f.substancias:
        parts.append(f"Substancias: {f.substancias}.")
    if f.provincia:
        parts.append(f"Provincia: {f.provincia}.")
    if f.rochas_hospedeiras:
        parts.append(f"Rochas hospedeiras: {f.rochas_hospedeiras}.")
    if f.rochas_encaixantes:
        parts.append(f"Rochas encaixantes: {f.rochas_encaixantes}.")
    if f.tipos_alteracao:
        parts.append(f"Alteracao: {f.tipos_alteracao}.")
    if f.status_economico:
        parts.append(f"Status: {f.status_economico}.")
    if f.morfologia:
        parts.append(f"Morfologia: {f.morfologia}.")
    parts.append(f"Coord: {f.coordenada.latitude:.4f}, {f.coordenada.longitude:.4f}.")
    return " ".join(parts)


def _gravimetria_to_text(f: DadoGravimetrico) -> str:
    return (
        f"Dado gravimetrico em {f.coordenada.latitude:.4f}, {f.coordenada.longitude:.4f}. "
        f"Anomalia Bouguer: {f.anomalia_bouguer:.1f} mGal. "
        f"Anomalia ar livre: {f.anomalia_ar_livre:.1f} mGal. "
        f"Altitude: {f.altitude_ortometrica:.0f}m. "
        f"Gravidade: {f.gravidade:.2f}."
    )


def _geoquimica_to_text(f: AmostraGeoquimica) -> str:
    parts = [f"Amostra geoquimica do projeto {f.projeto}. Classe: {f.classe}."]
    if f.material_coletado:
        parts.append(f"Material: {f.material_coletado}.")
    if f.rocha_matriz:
        parts.append(f"Rocha matriz: {f.rocha_matriz}.")
    # Top analises (até 5)
    if f.analises:
        items = list(f.analises.items())[:5]
        analise_str = ", ".join(f"{k}: {v}" for k, v in items)
        parts.append(f"Analises: {analise_str}.")
    parts.append(f"Coord: {f.coordenada.latitude:.4f}, {f.coordenada.longitude:.4f}.")
    return " ".join(parts)


def _geocronologia_to_text(f: DatacaoGeocronologica) -> str:
    parts = ["Datacao geocronologica."]
    if f.metodo:
        parts.append(f"Metodo: {f.metodo}.")
    if f.idade_ma is not None:
        age_str = f"{f.idade_ma:.1f}"
        if f.erro_ma is not None:
            age_str += f" +/- {f.erro_ma:.1f}"
        parts.append(f"Idade: {age_str} Ma.")
    if f.material:
        parts.append(f"Material: {f.material}.")
    if f.unidade_geologica:
        parts.append(f"Unidade: {f.unidade_geologica}.")
    parts.append(f"Coord: {f.coordenada.latitude:.4f}, {f.coordenada.longitude:.4f}.")
    return " ".join(parts)


def _litoestratigrafia_to_text(f: UnidadeLitoestratigrafica) -> str:
    parts = ["Unidade litoestratigrafica."]
    if f.nome:
        parts.append(f"Nome: {f.nome}.")
    if f.sigla:
        parts.append(f"Sigla: {f.sigla}.")
    if f.hierarquia:
        parts.append(f"Hierarquia: {f.hierarquia}.")
    if f.litologia_principal:
        parts.append(f"Litologia: {f.litologia_principal}.")
    if f.idade:
        parts.append(f"Idade: {f.idade}.")
    return " ".join(parts)


def _aerogeofisica_to_text(f: ProjetoAerogeofisico) -> str:
    parts = ["Projeto aerogeofisico."]
    if f.nome_projeto:
        parts.append(f"Nome: {f.nome_projeto}.")
    if f.tipo_levantamento:
        parts.append(f"Tipo: {f.tipo_levantamento}.")
    if f.ano:
        parts.append(f"Ano: {f.ano}.")
    if f.area_km2:
        parts.append(f"Area: {f.area_km2:.0f} km2.")
    parts.append(f"Coord: {f.coordenada.latitude:.4f}, {f.coordenada.longitude:.4f}.")
    return " ".join(parts)


def _generic_to_text(feature: BaseModel, source: str) -> str:
    """Fallback: serializa campos não-None."""
    data = feature.model_dump(exclude_none=True)
    parts = [f"Registro de {source}."]
    for key, value in data.items():
        if key != "coordenada":
            parts.append(f"{key}: {value}")
    return " ".join(parts)

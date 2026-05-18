"""Testes e2e — GeoSGB API real.

Verifica conectividade e integridade dos dados retornados pelo
geoportal.sgb.gov.br usando a região de Carajás (PA) como referência.

Executar com: MINER_E2E=1 uv run pytest tests/e2e/test_geosgb_live.py -v
"""

from __future__ import annotations

import pytest

from miner_harness.connectors.geosgb.connector import GeoSGBConnector
from miner_harness.connectors.geosgb.grid_extractor import GridDensity
from miner_harness.core.types import (
    BoundingBox,
    DadoGravimetrico,
    OcorrenciaMineral,
)

from .conftest import skip_no_e2e

# ---------------------------------------------------------------------------
# Conectividade básica
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_geosgb_count_ocorrencias_carajas(bbox_carajas_small: BoundingBox) -> None:
    """GeoSGB retorna contagem não-zero de ocorrências em Carajás."""
    async with GeoSGBConnector() as conn:
        count = await conn.count_ocorrencias(bbox_carajas_small)

    assert count > 0, (
        f"Esperava ocorrências em Carajás, API retornou {count}. "
        "Verifique conectividade com geoportal.sgb.gov.br."
    )


@skip_no_e2e
@pytest.mark.asyncio
async def test_geosgb_count_total_ocorrencias() -> None:
    """GeoSGB tem ocorrências cadastradas no Brasil (base real: ~36 k em 2026-05)."""
    async with GeoSGBConnector() as conn:
        count = await conn.count_ocorrencias()

    assert count > 20_000, f"Contagem total inesperadamente baixa: {count}"


# ---------------------------------------------------------------------------
# Dados tipados — gravimetria (FeatureServer — mais confiável)
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_geosgb_gravimetria_returns_typed_data(bbox_carajas_small: BoundingBox) -> None:
    """Gravimetria retorna DadoGravimetrico bem formado quando há cobertura na BBox.

    Dados gravimétricos do GeoSGB têm cobertura esparsa; a ausência de dados em
    Carajás é válida — o teste valida a estrutura apenas quando dados existem.
    """
    async with GeoSGBConnector() as conn:
        dados = await conn.gravimetria(bbox_carajas_small)

    assert isinstance(dados, list)
    if not dados:
        pytest.skip("Sem cobertura gravimétrica em Carajás (esperado para esta BBox)")

    for d in dados[:5]:  # valida primeiros 5
        assert isinstance(d, DadoGravimetrico)
        assert d.objectid > 0
        assert -90.0 <= d.coordenada.latitude <= 90.0
        assert -180.0 <= d.coordenada.longitude <= 180.0
        assert -500.0 <= d.anomalia_bouguer <= 500.0


@skip_no_e2e
@pytest.mark.asyncio
async def test_geosgb_gravimetria_coordenadas_dentro_da_bbox(
    bbox_carajas_small: BoundingBox,
) -> None:
    """Coordenadas dos dados gravimétricos estão dentro da BBox solicitada."""
    async with GeoSGBConnector() as conn:
        dados = await conn.gravimetria(bbox_carajas_small)

    if not dados:
        pytest.skip("Sem cobertura gravimétrica em Carajás (esperado para esta BBox)")

    margin = 0.1
    for d in dados:
        assert bbox_carajas_small.lon_min - margin <= d.coordenada.longitude
        assert d.coordenada.longitude <= bbox_carajas_small.lon_max + margin
        assert bbox_carajas_small.lat_min - margin <= d.coordenada.latitude
        assert d.coordenada.latitude <= bbox_carajas_small.lat_max + margin


# ---------------------------------------------------------------------------
# Dados tipados — ocorrências minerais (MapServer/identify)
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_geosgb_ocorrencias_returns_typed_data(bbox_carajas_small: BoundingBox) -> None:
    """Ocorrências retornam lista de OcorrenciaMineral com campos básicos."""
    async with GeoSGBConnector() as conn:
        ocorrs = await conn.ocorrencias(bbox_carajas_small, density=GridDensity.LOW)

    assert isinstance(ocorrs, list)
    assert len(ocorrs) > 0, "Esperava ocorrências minerais em Carajás"

    for o in ocorrs[:5]:
        assert isinstance(o, OcorrenciaMineral)
        assert o.objectid > 0
        assert len(o.substancias) > 0
        assert -90.0 <= o.coordenada.latitude <= 90.0
        assert -180.0 <= o.coordenada.longitude <= 180.0


@skip_no_e2e
@pytest.mark.asyncio
async def test_geosgb_ocorrencias_ferro_presente_carajas(bbox_carajas_small: BoundingBox) -> None:
    """Carajás deve ter ocorrências com Fe (ferro) — validação geológica."""
    async with GeoSGBConnector() as conn:
        ocorrs = await conn.ocorrencias(bbox_carajas_small, density=GridDensity.LOW)

    # Verifica que pelo menos uma ocorrência menciona ferro (Fe)
    substancias_all = " ".join(o.substancias.upper() for o in ocorrs)
    has_iron = any(kw in substancias_all for kw in ["FE", "FERRO", "HEMATITA", "MAGNETITA"])
    assert has_iron, (
        f"Esperava ocorrências de ferro em Carajás. "
        f"Substâncias encontradas: {substancias_all[:200]}"
    )


# ---------------------------------------------------------------------------
# Deduplicação e consistência
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_geosgb_gravimetria_sem_duplicatas(bbox_carajas_small: BoundingBox) -> None:
    """Não deve haver objectids duplicados nos dados gravimétricos."""
    async with GeoSGBConnector() as conn:
        dados = await conn.gravimetria(bbox_carajas_small)

    if not dados:
        pytest.skip("Sem cobertura gravimétrica em Carajás (esperado para esta BBox)")

    ids = [d.objectid for d in dados]
    duplicates = len(ids) - len(set(ids))
    assert duplicates == 0, f"Duplicatas encontradas: {duplicates} registros"

"""Testes e2e — ANM/SIGMINE API real.

Verifica conectividade e integridade dos dados de concessões minerárias
retornados pelo ANM (Agência Nacional de Mineração) para a região de Carajás.

Executar com: MINER_E2E=1 uv run pytest tests/e2e/test_anm_live.py -v
"""

from __future__ import annotations

import pytest

from miner_harness.connectors.anm.connector import ANMConnector
from miner_harness.core.config import ANMConfig
from miner_harness.core.types import BoundingBox, ConcessaoMineira

from .conftest import skip_no_e2e

# BBox um pouco maior (1°×1°) para garantir retorno de concessões ANM
_BBOX_CARAJAS_ANM = BoundingBox(
    lon_min=-50.5,
    lat_min=-6.5,
    lon_max=-49.5,
    lat_max=-5.5,
)


# ---------------------------------------------------------------------------
# Conectividade básica
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_anm_retorna_concessoes_em_carajas() -> None:
    """ANM/SIGMINE retorna concessões minerárias em Carajás."""
    config = ANMConfig()
    async with ANMConnector(config) as conn:
        concessoes = await conn.concessoes(_BBOX_CARAJAS_ANM)

    assert isinstance(concessoes, list), "Esperava lista de concessões"
    assert len(concessoes) > 0, (
        "Esperava concessões em Carajás (PA) — área com mineração intensiva de Fe/Mn/Cu. "
        "Verifique conectividade com app.anm.gov.br."
    )


@skip_no_e2e
@pytest.mark.asyncio
async def test_anm_retorna_tipo_concessao_mineral() -> None:
    """Concessões ANM retornam objetos ConcessaoMineira bem tipados."""
    config = ANMConfig()
    async with ANMConnector(config) as conn:
        concessoes = await conn.concessoes(_BBOX_CARAJAS_ANM)

    if not concessoes:
        pytest.skip("ANM não retornou concessões — API instável ou área sem dados")

    for c in concessoes[:5]:
        assert isinstance(c, ConcessaoMineira), f"Tipo inesperado: {type(c)}"
        assert c.objectid >= 0
        assert c.coordenada is not None
        assert -90.0 <= c.coordenada.latitude <= 90.0
        assert -180.0 <= c.coordenada.longitude <= 180.0


# ---------------------------------------------------------------------------
# Integridade geológica — Carajás deve ter Fe/Mn/Cu
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_anm_carajas_tem_ferro_ou_cobre() -> None:
    """Carajás deve ter concessões de Fe ou Cu (validação geológica)."""
    config = ANMConfig()
    async with ANMConnector(config) as conn:
        concessoes = await conn.concessoes(_BBOX_CARAJAS_ANM)

    if not concessoes:
        pytest.skip("ANM não retornou concessões — API instável ou área sem dados")

    substancias_all = " ".join((c.substancias or "").upper() for c in concessoes)
    has_mineral = any(
        kw in substancias_all
        for kw in ["FE", "FERRO", "CU", "COBRE", "MN", "MANGANES", "MANGANÊS", "AU", "OURO"]
    )
    assert has_mineral, (
        f"Nenhuma concessão de Fe/Cu/Mn/Au encontrada em Carajás. "
        f"Substâncias: {substancias_all[:300]}"
    )


@skip_no_e2e
@pytest.mark.asyncio
async def test_anm_concessoes_com_fase_reconhecida() -> None:
    """Ao menos algumas concessões têm fase minerária reconhecida."""
    config = ANMConfig()
    async with ANMConnector(config) as conn:
        concessoes = await conn.concessoes(_BBOX_CARAJAS_ANM)

    if not concessoes:
        pytest.skip("ANM não retornou concessões — API instável ou área sem dados")

    fases_conhecidas = {
        "Concessão de Lavra",
        "Autorização de Pesquisa",
        "Requerimento de Pesquisa",
        "Licenciamento",
        "Permissão de Lavra Garimpeira",
    }
    fases_encontradas = {c.fase for c in concessoes if c.fase}
    tem_fase_conhecida = bool(fases_encontradas & fases_conhecidas)
    assert tem_fase_conhecida, (
        f"Nenhuma fase minerária conhecida. Fases encontradas: {fases_encontradas}"
    )


# ---------------------------------------------------------------------------
# Coordenadas dentro da BBox
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_anm_coordenadas_dentro_da_bbox() -> None:
    """Coordenadas das concessões estão dentro da BBox solicitada (margem 0.5°)."""
    config = ANMConfig()
    async with ANMConnector(config) as conn:
        concessoes = await conn.concessoes(_BBOX_CARAJAS_ANM)

    if not concessoes:
        pytest.skip("ANM não retornou concessões — API instável ou área sem dados")

    margin = 0.5  # Concessões podem ter centroide ligeiramente fora por geometrias complexas
    for c in concessoes:
        assert _BBOX_CARAJAS_ANM.lon_min - margin <= c.coordenada.longitude
        assert c.coordenada.longitude <= _BBOX_CARAJAS_ANM.lon_max + margin
        assert _BBOX_CARAJAS_ANM.lat_min - margin <= c.coordenada.latitude
        assert c.coordenada.latitude <= _BBOX_CARAJAS_ANM.lat_max + margin


# ---------------------------------------------------------------------------
# Deduplicação
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_anm_sem_duplicatas() -> None:
    """Concessões ANM não têm objectids duplicados."""
    config = ANMConfig()
    async with ANMConnector(config) as conn:
        concessoes = await conn.concessoes(_BBOX_CARAJAS_ANM)

    if not concessoes:
        pytest.skip("ANM não retornou concessões — API instável ou área sem dados")

    ids = [c.objectid for c in concessoes]
    duplicates = len(ids) - len(set(ids))
    assert duplicates == 0, f"{duplicates} objectids duplicados encontrados"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_anm_context_manager_fecha_sessao() -> None:
    """ANMConnector como context manager fecha a sessão corretamente."""
    config = ANMConfig()
    conn = ANMConnector(config)
    async with conn:
        result = await conn.concessoes(_BBOX_CARAJAS_ANM)
    # Se chegou aqui sem exceção, o context manager funcionou
    assert isinstance(result, list)

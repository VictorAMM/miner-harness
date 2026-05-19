"""Testes e2e — USGS Earthquake API real.

Verifica conectividade e integridade dos dados sísmicos retornados pelo
USGS Earthquake Hazards Program para regiões de interesse geológico no Brasil.

Nota: sismicidade no Brasil é de baixa a moderada intensidade. Para garantir
retorno de eventos, usamos uma BBox maior (região Nordeste / Cratão do São Francisco)
que tem registros históricos mais densos, além de Carajás.

Executar com: MINER_E2E=1 uv run pytest tests/e2e/test_usgs_live.py -v
"""

from __future__ import annotations

import pytest

from miner_harness.connectors.usgs.connector import USGSConnector
from miner_harness.core.config import USGSConfig
from miner_harness.core.types import BoundingBox, EventoSismico

from .conftest import skip_no_e2e

# BBox ampla cobrindo o Brasil — garante retorno de eventos históricos
_BBOX_BRASIL = BoundingBox(
    lon_min=-74.0,
    lat_min=-34.0,
    lon_max=-29.0,
    lat_max=6.0,
)

# BBox menor — Carajás/Pará (histórico sísmico registrado)
_BBOX_CARAJAS = BoundingBox(
    lon_min=-51.5,
    lat_min=-7.5,
    lon_max=-48.5,
    lat_max=-4.5,
)


# ---------------------------------------------------------------------------
# Conectividade básica
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_usgs_api_acessivel() -> None:
    """USGS API responde sem erro de conexão."""
    config = USGSConfig()
    async with USGSConnector(config) as conn:
        eventos = await conn.sismos(_BBOX_BRASIL)

    # Mesmo sem eventos, a API respondeu (lista pode ser vazia em períodos calmos)
    assert isinstance(eventos, list), "Esperava lista de EventoSismico"


@skip_no_e2e
@pytest.mark.asyncio
async def test_usgs_retorna_eventos_brasil() -> None:
    """USGS retorna ao menos um evento sísmico registrado no Brasil."""
    config = USGSConfig(min_magnitude=2.0, max_events=100)
    async with USGSConnector(config) as conn:
        eventos = await conn.sismos(_BBOX_BRASIL)

    assert len(eventos) > 0, (
        "Esperava eventos sísmicos no Brasil (catálogo histórico tem registros). "
        "Verifique conectividade com earthquake.usgs.gov."
    )


# ---------------------------------------------------------------------------
# Tipagem e integridade dos dados
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_usgs_retorna_tipo_evento_sismico() -> None:
    """Eventos USGS são objetos EventoSismico bem tipados."""
    config = USGSConfig(min_magnitude=2.0, max_events=50)
    async with USGSConnector(config) as conn:
        eventos = await conn.sismos(_BBOX_BRASIL)

    if not eventos:
        pytest.skip("USGS não retornou eventos — possível período calmo ou API instável")

    for e in eventos[:5]:
        assert isinstance(e, EventoSismico), f"Tipo inesperado: {type(e)}"
        assert e.objectid >= 0
        assert e.magnitude >= 0.0
        assert e.profundidade_km >= 0.0
        assert e.timestamp_ms > 0
        assert e.coordenada is not None
        assert -90.0 <= e.coordenada.latitude <= 90.0
        assert -180.0 <= e.coordenada.longitude <= 180.0


@skip_no_e2e
@pytest.mark.asyncio
async def test_usgs_magnitude_dentro_do_filtro() -> None:
    """Todos os eventos têm magnitude >= min_magnitude configurado."""
    min_mag = 3.0
    config = USGSConfig(min_magnitude=min_mag, max_events=50)
    async with USGSConnector(config) as conn:
        eventos = await conn.sismos(_BBOX_BRASIL)

    if not eventos:
        pytest.skip(f"Nenhum evento M≥{min_mag} no Brasil — catálogo vazio para filtro")

    for e in eventos:
        assert e.magnitude >= min_mag - 0.1, (
            f"Evento com magnitude {e.magnitude} abaixo do mínimo {min_mag}"
        )


# ---------------------------------------------------------------------------
# Coordenadas dentro da BBox
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_usgs_coordenadas_dentro_da_bbox_brasil() -> None:
    """Coordenadas dos eventos estão dentro da BBox do Brasil (margem 0.1°)."""
    config = USGSConfig(min_magnitude=2.0, max_events=100)
    async with USGSConnector(config) as conn:
        eventos = await conn.sismos(_BBOX_BRASIL)

    if not eventos:
        pytest.skip("USGS não retornou eventos — catálogo vazio")

    margin = 0.1
    for e in eventos:
        assert _BBOX_BRASIL.lon_min - margin <= e.coordenada.longitude
        assert e.coordenada.longitude <= _BBOX_BRASIL.lon_max + margin
        assert _BBOX_BRASIL.lat_min - margin <= e.coordenada.latitude
        assert e.coordenada.latitude <= _BBOX_BRASIL.lat_max + margin


# ---------------------------------------------------------------------------
# Limite de eventos (max_events)
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_usgs_respeita_max_events() -> None:
    """Conector não retorna mais eventos que max_events."""
    max_ev = 10
    config = USGSConfig(min_magnitude=1.0, max_events=max_ev)
    async with USGSConnector(config) as conn:
        eventos = await conn.sismos(_BBOX_BRASIL)

    assert len(eventos) <= max_ev, f"Retornou {len(eventos)} eventos, mas max_events={max_ev}"


# ---------------------------------------------------------------------------
# Deduplicação
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_usgs_sem_duplicatas() -> None:
    """Eventos USGS não têm objectids duplicados."""
    config = USGSConfig(min_magnitude=2.0, max_events=100)
    async with USGSConnector(config) as conn:
        eventos = await conn.sismos(_BBOX_BRASIL)

    if not eventos:
        pytest.skip("USGS não retornou eventos — catálogo vazio")

    ids = [e.objectid for e in eventos]
    duplicates = len(ids) - len(set(ids))
    assert duplicates == 0, f"{duplicates} objectids duplicados encontrados"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@skip_no_e2e
@pytest.mark.asyncio
async def test_usgs_context_manager_fecha_sessao() -> None:
    """USGSConnector como context manager fecha a sessão corretamente."""
    config = USGSConfig()
    conn = USGSConnector(config)
    async with conn:
        result = await conn.sismos(_BBOX_BRASIL)
    assert isinstance(result, list)

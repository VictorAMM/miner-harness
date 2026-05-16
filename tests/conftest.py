"""Fixtures compartilhadas para testes do miner-harness."""

from __future__ import annotations

import pytest

from miner_harness.core.config import (
    GeoSGBConfig,
    MinerHarnessConfig,
    OrchestratorConfig,
    StorageConfig,
)
from miner_harness.core.types import BoundingBox, Coordenada

# ---------------------------------------------------------------------------
# Bounding Boxes
# ---------------------------------------------------------------------------


@pytest.fixture()
def bbox_carajas() -> BoundingBox:
    """BoundingBox da região de Carajás (PA) — região piloto."""
    return BoundingBox(
        lon_min=-51.5,
        lat_min=-7.0,
        lon_max=-49.0,
        lat_max=-5.0,
    )


@pytest.fixture()
def bbox_small() -> BoundingBox:
    """BoundingBox pequeno para testes rápidos."""
    return BoundingBox(
        lon_min=-50.5,
        lat_min=-6.5,
        lon_max=-50.0,
        lat_max=-6.0,
    )


# ---------------------------------------------------------------------------
# Coordenadas
# ---------------------------------------------------------------------------


@pytest.fixture()
def coord_parauapebas() -> Coordenada:
    """Coordenada de Parauapebas (PA) — centro de Carajás."""
    return Coordenada(longitude=-49.9, latitude=-6.07)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@pytest.fixture()
def config(tmp_path: object) -> MinerHarnessConfig:
    """Configuração de teste usando diretório temporário."""
    from pathlib import Path

    return MinerHarnessConfig(
        storage=StorageConfig(
            miner_home=Path(str(tmp_path)) / ".miner-harness",
        ),
        orchestrator=OrchestratorConfig(),
        geosgb=GeoSGBConfig(),
    )

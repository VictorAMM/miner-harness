"""Fixtures e configuração para testes e2e.

Testes e2e requerem serviços externos (GeoSGB API, Ollama).
Por padrão são pulados. Para executar:

    MINER_E2E=1 uv run pytest tests/e2e/ -v

Ou somente GeoSGB (sem Ollama):

    MINER_E2E=1 MINER_E2E_NO_OLLAMA=1 uv run pytest tests/e2e/ -v -k "geosgb"
"""

from __future__ import annotations

import os

import pytest

from miner_harness.core.types import BoundingBox

# ---------------------------------------------------------------------------
# Skip logic — opt-in via env var
# ---------------------------------------------------------------------------

_E2E_ENABLED = bool(os.getenv("MINER_E2E"))
_OLLAMA_ENABLED = _E2E_ENABLED and not os.getenv("MINER_E2E_NO_OLLAMA")

skip_no_e2e = pytest.mark.skipif(
    not _E2E_ENABLED,
    reason="set MINER_E2E=1 to run end-to-end tests against live services",
)

skip_no_ollama = pytest.mark.skipif(
    not _OLLAMA_ENABLED,
    reason="set MINER_E2E=1 (and unset MINER_E2E_NO_OLLAMA) to run Ollama e2e tests",
)


# ---------------------------------------------------------------------------
# Bounding boxes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def bbox_carajas_small() -> BoundingBox:
    """BBox compacta no núcleo do Complexo Ferrífero de Carajás (PA).

    ~30×30 km — suficiente para retornar dados reais sem sobrecarregar a API.
    """
    return BoundingBox(
        lon_min=-50.3,
        lat_min=-6.3,
        lon_max=-50.0,
        lat_max=-6.0,
    )


@pytest.fixture(scope="session")
def ollama_url() -> str:
    return os.getenv("MINER_OLLAMA_URL", "http://localhost:11434")


@pytest.fixture(scope="session")
def ollama_model() -> str:
    return os.getenv("MINER_OLLAMA_MODEL", "qwen3:8b-q4_K_M")

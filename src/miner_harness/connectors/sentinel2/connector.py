"""CopernicusConnector — Sentinel-2 statistics via CDSE Statistics API.

Autentica via OAuth2 client_credentials (CDSE) e obtém estatísticas
de índices espectrais (NDVI, BSI, Clay Index, Iron Oxide) para uma bbox.
Nenhum raster é baixado — apenas estatísticas JSON da Statistics API.

Credenciais: MINER_COPERNICUS__CLIENT_ID / MINER_COPERNICUS__CLIENT_SECRET
Registro gratuito: https://dataspace.copernicus.eu/

Ref: PRD-002 F6
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from types import TracebackType

    from miner_harness.core.config import CopernicusConfig
    from miner_harness.core.types import BoundingBox

logger = structlog.get_logger(__name__)

_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
_STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

# ~60m resolução em graus (equador) — Sentinel-2 60m bands (B11, B12)
_RES_DEG: float = 0.00054

# Evalscript que calcula 4 índices + 4 máscaras binárias de anomalia.
# SCL (Scene Classification Layer) é usado para mascarar nuvens/sombras.
# Outputs _anom: 1.0 quando pixel é anômalo, 0.0 caso contrário, NaN em pixel inválido.
# - ndvi_anom: NDVI < 0.2   → vegetação esparsa/ausente (solo alterado ou mineralizado)
# - bsi_anom:  BSI > 0.1    → solo/rocha exposta (ausência de cobertura vegetal)
# - clay_anom: Clay > 1.5   → argilominerais SWIR (sericita, caolinita, alunita)
# - iron_anom: Iron > 2.0   → óxidos de ferro (gossã, cap ferrugíneo)
_EVALSCRIPT = """\
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B02","B04","B08","B11","B12","SCL"], units: "REFLECTANCE" }],
    output: [
      { id: "ndvi",      bands: 1, sampleType: "FLOAT32" },
      { id: "bsi",       bands: 1, sampleType: "FLOAT32" },
      { id: "clay",      bands: 1, sampleType: "FLOAT32" },
      { id: "iron",      bands: 1, sampleType: "FLOAT32" },
      { id: "ndvi_anom", bands: 1, sampleType: "FLOAT32" },
      { id: "bsi_anom",  bands: 1, sampleType: "FLOAT32" },
      { id: "clay_anom", bands: 1, sampleType: "FLOAT32" },
      { id: "iron_anom", bands: 1, sampleType: "FLOAT32" }
    ]
  };
}
function isCloud(scl) { return [3,7,8,9,10,11].indexOf(scl) !== -1; }
function evaluatePixel(s) {
  var nan = NaN;
  if (isCloud(s.SCL)) {
    return { ndvi:[nan], bsi:[nan], clay:[nan], iron:[nan],
             ndvi_anom:[nan], bsi_anom:[nan], clay_anom:[nan], iron_anom:[nan] };
  }
  var eps = 1e-6;
  var b02 = s.B02, b04 = s.B04, b08 = s.B08, b11 = s.B11, b12 = s.B12;
  var ndvi = (b08 - b04) / (b08 + b04 + eps);
  var bsi  = ((b11 + b04) - (b08 + b02)) / ((b11 + b04) + (b08 + b02) + eps);
  var clay = b12 > 1e-4 ? b11 / b12 : nan;
  var iron = b02 > 1e-4 ? b04 / b02 : nan;
  var clay_v = (clay === clay) ? clay : nan;  // NaN identity check
  var iron_v = (iron === iron) ? iron : nan;
  var clay_a = (clay === clay) ? (clay > 1.5 ? 1.0 : 0.0) : nan;
  var iron_a = (iron === iron) ? (iron > 2.0 ? 1.0 : 0.0) : nan;
  return {
    ndvi: [ndvi], bsi: [bsi], clay: [clay_v], iron: [iron_v],
    ndvi_anom: [ndvi < 0.2 ? 1.0 : 0.0],
    bsi_anom:  [bsi > 0.1  ? 1.0 : 0.0],
    clay_anom: [clay_a],
    iron_anom: [iron_a]
  };
}
"""


class CopernicusConnector:
    """Conector para a Statistics API do Sentinel Hub (CDSE).

    Gerencia renovação automática do token OAuth2 e chama a Statistics API
    para obter estatísticas espectrais sem download de rasters. O token
    é cacheado em memória e renovado automaticamente 30s antes do vencimento.

    Usage:
        async with CopernicusConnector(config) as conn:
            raw = await conn.statistics(bbox)
            # raw = {"data": [...], "status": "OK"} or {}
    """

    def __init__(self, config: CopernicusConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=config.timeout_s)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def statistics(self, bbox: BoundingBox) -> dict[str, Any]:
        """Retorna resposta bruta da Statistics API, ou {} em caso de erro.

        Não faz download de rasters — apenas lê estatísticas JSON do endpoint
        /api/v1/statistics via evalscript personalizado.

        Args:
            bbox: Bounding box da região de análise.

        Returns:
            Dict com "data" (lista de intervalos com estatísticas por output)
            ou {} se desabilitado, sem credenciais, ou em caso de erro.
        """
        if not self._config.enabled:
            return {}

        if not self._config.client_id or not self._config.client_secret:
            logger.warning(
                "copernicus_no_credentials",
                hint="Defina MINER_COPERNICUS__CLIENT_ID e MINER_COPERNICUS__CLIENT_SECRET",
            )
            return {}

        token = await self._get_token()
        if not token:
            return {}

        now = datetime.now(timezone.utc)  # noqa: UP017
        date_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        date_from = (now - timedelta(days=self._config.days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload: dict[str, Any] = {
            "input": {
                "bounds": {
                    "bbox": [
                        bbox.lon_min,
                        bbox.lat_min,
                        bbox.lon_max,
                        bbox.lat_max,
                    ],
                    "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": date_from,
                                "to": date_to,
                            },
                            "maxCloudCoverage": self._config.max_cloud_pct,
                            "mosaickingOrder": "leastCC",
                        },
                    }
                ],
            },
            "aggregation": {
                "timeRange": {"from": date_from, "to": date_to},
                "aggregationInterval": {"of": f"P{self._config.days_back}D"},
                "evalscript": _EVALSCRIPT,
                "resx": _RES_DEG,
                "resy": _RES_DEG,
            },
            "calculations": {"default": {"statistics": {"default": {"percentiles": {"k": [90]}}}}},
        }

        try:
            resp = await self._client.post(
                _STATS_URL,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            logger.info(
                "copernicus_statistics_ok",
                bbox=bbox.as_tuple(),
                date_from=date_from,
                date_to=date_to,
            )
            return data
        except Exception:
            logger.warning("copernicus_statistics_failed", exc_info=True)
            return {}

    async def _get_token(self) -> str | None:
        """Retorna token Bearer OAuth2 válido, renovando automaticamente."""
        # Renova 30s antes do vencimento para evitar race conditions
        if self._token and time.monotonic() < self._token_expires_at - 30:
            return self._token

        try:
            resp = await self._client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
            self._token = str(body["access_token"])
            expires_in = int(body.get("expires_in", 3600))
            self._token_expires_at = time.monotonic() + expires_in
            logger.info("copernicus_token_refreshed", expires_in=expires_in)
            return self._token
        except Exception:
            logger.warning("copernicus_token_failed", exc_info=True)
            self._token = None
            return None

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        await self._client.aclose()

    async def __aenter__(self) -> CopernicusConnector:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

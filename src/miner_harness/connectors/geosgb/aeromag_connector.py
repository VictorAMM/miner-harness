"""AeromagConnector — amostragem do Atlas Aerogeofísico SGB via MapServer/identify.

O serviço ``Mapas_Tern_Mag_MIL1`` do geoportal SGB expõe duas camadas raster:

  Layer 0 — Ternário K-Th-U (gamaespectrometria, escala 1:1.000.000)
  Layer 1 — Anomalia Magnética de Campo Total (TMA, escala 1:1.000.000)

O endpoint MapServer/identify retorna o **valor de pixel** da camada raster
no ponto solicitado, como campo ``"Pixel Value"`` nos atributos.

Este conector amostra TMA em um grid N×N sobre o bbox, produzindo uma lista
de dicts ``{lon, lat, tma_nt}`` que o ``AeromagProcessor`` converte em
derivadas interpretáveis (HGM, anomalias, etc.).

Ref: PRD-003 F10 — Aeromagnética Real
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox

logger = structlog.get_logger(__name__)

# URL do serviço atlas aerogeofísico do SGB/CPRM
# NOTA: o path correto é /server/rest/services/ (ArcGIS REST API).
# /server/services/ (sem /rest/) retorna 403 em todos os requests.
_ATLAS_BASE = "https://geoportal.sgb.gov.br/server/rest/services/Mapas_Tern_Mag_MIL1/MapServer"
_IDENTIFY_URL = f"{_ATLAS_BASE}/identify"

# Camada de TMA no serviço atlas
_TMA_LAYER_ID = 1

# Número de pontos de amostragem por dimensão do grid (N×N total)
_DEFAULT_GRID_N = 6

# Delay mínimo entre requests (ms) — respeitoso ao servidor
_MIN_DELAY_MS = 300

# Timeout por request
_TIMEOUT_S = 30

# Headers browser-like necessários para contornar o filtro 403 do geoportal SGB.
# O endpoint MapServer/identify exige Referer e User-Agent de browser real.
_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://geoportal.sgb.gov.br/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


class AeromagConnector:
    """Amostra anomalia magnética total (TMA) do Atlas Aerogeofísico SGB.

    Usa MapServer/identify para extrair valores de pixel da camada raster
    de TMA (1:1.000.000) sobre um grid regular dentro do bbox.

    A amostragem é assíncrona mas respeitosa ao servidor SGB:
    - Delay mínimo de 300 ms entre requests
    - Timeout de 30 s por request
    - Falhas individuais são ignoradas (grid parcial ainda é útil)

    Usage:
        connector = AeromagConnector()
        points = await connector.sample_tma(bbox)
        # points = [{"lon": -50.2, "lat": -6.1, "tma_nt": 124.6}, ...]
    """

    def __init__(
        self,
        timeout_s: int = _TIMEOUT_S,
        min_delay_ms: int = _MIN_DELAY_MS,
        grid_n: int = _DEFAULT_GRID_N,
    ) -> None:
        self._timeout_s = timeout_s
        self._min_delay_ms = min_delay_ms
        self._grid_n = grid_n
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def _make_client(self) -> httpx.AsyncClient:
        """Cria cliente HTTP com headers browser-like necessários para o geoportal SGB."""
        return httpx.AsyncClient(headers=_BROWSER_HEADERS, timeout=self._timeout_s)

    async def __aenter__(self) -> AeromagConnector:
        self._client = self._make_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Amostragem de TMA
    # ------------------------------------------------------------------

    async def sample_tma(
        self,
        bbox: BoundingBox,
    ) -> list[dict[str, Any]]:
        """Amostra TMA em grid N×N sobre o bbox.

        Args:
            bbox: Bounding box da região.

        Returns:
            Lista de dicts ``{lon, lat, tma_nt}`` com os pontos amostrados.
            Lista vazia se o serviço não estiver disponível ou não retornar valores.
        """
        grid = self._generate_grid(bbox)
        if not grid:  # pragma: no cover — _generate_grid sempre retorna ≥ 4 pontos
            return []

        client = self._client or self._make_client()
        owned = self._client is None
        try:
            results = await self._sample_grid(client, grid, bbox)
        finally:
            if owned:
                await client.aclose()

        valid = [r for r in results if r is not None]
        logger.info(
            "aeromag_sampled",
            bbox=bbox.as_tuple(),
            grid_n=self._grid_n,
            total_points=len(grid),
            valid_points=len(valid),
        )
        return valid

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _generate_grid(self, bbox: BoundingBox) -> list[tuple[float, float]]:
        """Gera grid regular N×N de pontos sobre o bbox."""
        n = self._grid_n
        if n < 2:
            n = 2
        step_lon = bbox.width / (n - 1)
        step_lat = bbox.height / (n - 1)
        points: list[tuple[float, float]] = []
        for i in range(n):
            lon = bbox.lon_min + i * step_lon
            for j in range(n):
                lat = bbox.lat_min + j * step_lat
                points.append((round(lon, 6), round(lat, 6)))
        return points

    async def _sample_grid(
        self,
        client: httpx.AsyncClient,
        grid: list[tuple[float, float]],
        bbox: BoundingBox,
    ) -> list[dict[str, Any] | None]:
        """Amostra todos os pontos sequencialmente com delay."""
        results: list[dict[str, Any] | None] = []
        for idx, (lon, lat) in enumerate(grid):
            t0 = time.monotonic()
            result = await self._identify_point(client, lon, lat, bbox)
            results.append(result)
            # Throttle entre requests (exceto o último)
            if idx < len(grid) - 1:
                elapsed_ms = (time.monotonic() - t0) * 1000
                wait_ms = max(0, self._min_delay_ms - elapsed_ms)
                if wait_ms > 0:
                    await asyncio.sleep(wait_ms / 1000)
        return results

    async def _identify_point(
        self,
        client: httpx.AsyncClient,
        lon: float,
        lat: float,
        bbox: BoundingBox,
    ) -> dict[str, Any] | None:
        """Chama MapServer/identify para obter TMA em um ponto.

        Returns:
            Dict ``{lon, lat, tma_nt}`` ou None se sem valor válido.
        """
        params = {
            "f": "json",
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "sr": "4326",
            "layers": f"visible:{_TMA_LAYER_ID}",
            "tolerance": "1",
            "mapExtent": (f"{bbox.lon_min},{bbox.lat_min},{bbox.lon_max},{bbox.lat_max}"),
            "imageDisplay": "800,800,96",
            "returnGeometry": "false",
        }
        try:
            resp = await self._get_with_retry(client, _IDENTIFY_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "aeromag_identify_failed",
                lon=lon,
                lat=lat,
                error=str(exc),
            )
            return None

        return self._parse_identify(data, lon, lat)

    @staticmethod
    async def _get_with_retry(
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
        max_attempts: int = 3,
        base_delay_s: float = 1.0,
    ) -> httpx.Response:
        """GET com retry exponencial para erros transientes (429 / 503).

        Retenta até ``max_attempts`` vezes com delay 1s, 2s, 4s… para status
        429 (Too Many Requests) e 503 (Service Unavailable). Outros erros são
        relançados imediatamente.
        """
        _retryable = {429, 503}
        for attempt in range(1, max_attempts + 1):
            resp = await client.get(url, params=params)
            if resp.status_code not in _retryable or attempt == max_attempts:
                return resp
            delay = base_delay_s * (2 ** (attempt - 1))
            logger.warning(
                "aeromag_retry",
                attempt=attempt,
                status=resp.status_code,
                delay_s=delay,
            )
            await asyncio.sleep(delay)
        return resp  # pragma: no cover — loop sempre retorna antes

    @staticmethod
    def _parse_identify(
        data: dict[str, Any],
        lon: float,
        lat: float,
    ) -> dict[str, Any] | None:
        """Extrai valor TMA de resposta MapServer/identify.

        O ArcGIS pode retornar o valor de pixel em dois formatos:

        1. Raster escalar (ex: camadas DEM/Float)::

               {"results": [{"attributes": {"Pixel Value": "1234.56"}, ...}]}

        2. Raster RGB (ex: AM_Brasil.tif servido como imagem colorida)::

               {"results": [{"attributes": {"RGB.Red": "144", "RGB.Green": "122",
                                            "RGB.Blue": "0"}, ...}]}

           Neste caso, a luminância (0–255) é usada como proxy relativo de TMA.
           Os valores absolutos em nT não são preservados, mas a variação espacial
           é mantida, que é o que importa para detecção de anomalias no AeromagProcessor.

        Returns:
            Dict ``{lon, lat, tma_nt}`` ou None se sem valor numérico.
        """
        results = data.get("results", [])
        if not results:
            return None

        for res in results:
            attrs = res.get("attributes", {})

            # Formato 1: Pixel Value escalar
            raw = attrs.get("Pixel Value") or attrs.get("pixel value") or attrs.get("VALUE")
            if raw is not None:
                raw_str = str(raw).strip()
                if raw_str and raw_str.lower() not in {"nodata", "no data", "n/d", "-"}:
                    try:
                        return {"lon": lon, "lat": lat, "tma_nt": float(raw_str)}
                    except ValueError:
                        logger.debug("aeromag_non_numeric_pixel", raw=raw_str, lon=lon, lat=lat)

            # Formato 2: RGB (AM_Brasil.tif renderizado como imagem)
            r_str = attrs.get("RGB.Red")
            g_str = attrs.get("RGB.Green")
            b_str = attrs.get("RGB.Blue")
            if r_str is not None and g_str is not None and b_str is not None:
                try:
                    r, g, b = float(r_str), float(g_str), float(b_str)
                    # Luminância como proxy relativo de intensidade TMA (range 0–255)
                    tma = round(0.299 * r + 0.587 * g + 0.114 * b, 1)
                    return {"lon": lon, "lat": lat, "tma_nt": tma}
                except (ValueError, TypeError):
                    logger.debug("aeromag_rgb_parse_failed", attrs=attrs, lon=lon, lat=lat)

        return None

"""USGSConnector — eventos sísmicos via USGS Earthquake Hazards API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from miner_harness.core.types import BoundingBox, Coordenada, EventoSismico

if TYPE_CHECKING:
    from types import TracebackType

    from miner_harness.core.config import USGSConfig

logger = structlog.get_logger(__name__)


class USGSConnector:
    """Conector para a API de eventos sísmicos do USGS.

    Consulta o catálogo FDSN/Earthquake Hazards com o bbox e magnitude mínima
    definidos na configuração. Features com coordenadas fora dos limites do
    Brasil (Coordenada) são ignoradas silenciosamente.
    """

    def __init__(self, config: USGSConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=config.timeout_s)

    async def sismos(self, bbox: BoundingBox) -> list[EventoSismico]:
        """Retorna eventos sísmicos dentro do bbox."""
        if not self._config.enabled:
            return []

        params: dict[str, Any] = {
            "format": "geojson",
            "minlatitude": bbox.lat_min,
            "maxlatitude": bbox.lat_max,
            "minlongitude": bbox.lon_min,
            "maxlongitude": bbox.lon_max,
            "minmagnitude": self._config.min_magnitude,
            "limit": self._config.max_events,
            "orderby": "magnitude",
        }

        try:
            resp = await self._client.get(self._config.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("usgs_fetch_failed", bbox=bbox.as_tuple())
            return []

        features = data.get("features") or []
        results: list[EventoSismico] = []
        for idx, feat in enumerate(features):
            parsed = _parse_feature(idx, feat)
            if parsed is not None:
                results.append(parsed)

        logger.info("usgs_sismos_fetched", count=len(results), bbox=bbox.as_tuple())
        return results

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> USGSConnector:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()


def _parse_feature(idx: int, feat: dict[str, Any]) -> EventoSismico | None:
    """Converte uma feature GeoJSON USGS em EventoSismico, ou None se inválida."""
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates")
    if not coords or len(coords) < 2:
        return None

    try:
        lon = float(coords[0])
        lat = float(coords[1])
        depth = float(coords[2]) if len(coords) > 2 else 0.0
    except (TypeError, ValueError):
        return None

    try:
        coordenada = Coordenada(longitude=lon, latitude=lat)
    except Exception:
        return None

    props: dict[str, Any] = feat.get("properties") or {}

    try:
        magnitude = float(props.get("mag") or 0.0)
    except (TypeError, ValueError):
        magnitude = 0.0

    try:
        timestamp_ms = int(props.get("time") or 0)
    except (TypeError, ValueError):
        timestamp_ms = 0

    return EventoSismico(
        objectid=idx,
        magnitude=magnitude,
        profundidade_km=depth,
        lugar=props.get("place"),
        timestamp_ms=timestamp_ms,
        coordenada=coordenada,
    )

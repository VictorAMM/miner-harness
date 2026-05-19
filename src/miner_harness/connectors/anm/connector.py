"""ANMConnector — concessões minerárias via SIGMINE WFS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from miner_harness.core.types import BoundingBox, ConcessaoMineira, Coordenada

if TYPE_CHECKING:
    from types import TracebackType

    from miner_harness.core.config import ANMConfig

logger = structlog.get_logger(__name__)

_TYPENAME = "sigmine:SUP_REQUERIMENTO"
_OUTPUT_FORMAT = "application/json"


class ANMConnector:
    """Conector para a API WFS do ANM/SIGMINE.

    Busca concessões minerárias ativas na área definida pelo BoundingBox.
    Cada feature GeoJSON é convertida para ConcessaoMineira; features com
    geometria inválida ou coordenadas fora dos limites do Brasil são ignoradas.
    """

    def __init__(self, config: ANMConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=config.timeout_s)

    async def concessoes(self, bbox: BoundingBox) -> list[ConcessaoMineira]:
        """Retorna concessões minerárias dentro do bbox."""
        if not self._config.enabled:
            return []

        params: dict[str, Any] = {
            "service": "WFS",
            "version": "1.0.0",
            "request": "GetFeature",
            "typeName": _TYPENAME,
            "outputFormat": _OUTPUT_FORMAT,
            "maxFeatures": self._config.max_features,
            "bbox": f"{bbox.lon_min},{bbox.lat_min},{bbox.lon_max},{bbox.lat_max}",
        }

        try:
            resp = await self._client.get(self._config.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("anm_fetch_failed", bbox=bbox.as_tuple())
            return []

        features = data.get("features") or []
        results: list[ConcessaoMineira] = []
        for idx, feat in enumerate(features):
            parsed = _parse_feature(idx, feat)
            if parsed is not None:
                results.append(parsed)

        logger.info("anm_concessoes_fetched", count=len(results), bbox=bbox.as_tuple())
        return results

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ANMConnector:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()


def _parse_feature(idx: int, feat: dict[str, Any]) -> ConcessaoMineira | None:
    """Converte uma feature GeoJSON em ConcessaoMineira, ou None se inválida."""
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates")
    if not coords:
        return None

    geom_type = geom.get("type", "")
    try:
        lon, lat = _centroid(geom_type, coords)
    except Exception:
        return None

    try:
        coordenada = Coordenada(longitude=lon, latitude=lat)
    except Exception:
        return None

    props: dict[str, Any] = feat.get("properties") or {}

    area_raw = props.get("AREA_HA")
    try:
        area_ha: float | None = float(area_raw) if area_raw is not None else None
    except (TypeError, ValueError):
        area_ha = None

    ano_raw = props.get("ANO")
    try:
        ano: int | None = int(ano_raw) if ano_raw is not None else None
    except (TypeError, ValueError):
        ano = None

    uf_raw = props.get("UF")
    uf: str | None = str(uf_raw)[:2] if uf_raw else None

    return ConcessaoMineira(
        objectid=idx,
        processo=props.get("PROCESSO") or props.get("NR_PROCESSO"),
        fase=props.get("FASE"),
        nome_titular=props.get("NOME") or props.get("NOME_REQUERENTE"),
        substancias=props.get("SUBSTANCIA") or props.get("SUBSTANCIAS"),
        uf=uf,
        area_ha=area_ha,
        ano=ano,
        coordenada=coordenada,
    )


def _centroid(geom_type: str, coords: Any) -> tuple[float, float]:
    """Extrai centróide aproximado para tipos GeoJSON comuns."""
    if geom_type == "Point":
        return float(coords[0]), float(coords[1])
    if geom_type == "MultiPoint":
        lon = sum(float(c[0]) for c in coords) / len(coords)
        lat = sum(float(c[1]) for c in coords) / len(coords)
        return lon, lat
    if geom_type in ("LineString", "MultiLineString"):
        flat = coords if geom_type == "LineString" else [p for ring in coords for p in ring]
        lon = sum(float(c[0]) for c in flat) / len(flat)
        lat = sum(float(c[1]) for c in flat) / len(flat)
        return lon, lat
    if geom_type == "Polygon":
        ring = coords[0]
        lon = sum(float(c[0]) for c in ring) / len(ring)
        lat = sum(float(c[1]) for c in ring) / len(ring)
        return lon, lat
    if geom_type == "MultiPolygon":
        all_pts = [c for poly in coords for ring in poly for c in ring]
        lon = sum(float(c[0]) for c in all_pts) / len(all_pts)
        lat = sum(float(c[1]) for c in all_pts) / len(all_pts)
        return lon, lat
    msg = f"Unsupported geometry type: {geom_type}"
    raise ValueError(msg)

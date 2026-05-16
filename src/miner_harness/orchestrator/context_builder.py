"""ContextBuilder — coleta e organiza dados para análise.

Busca dados do GeoSGB via CacheManager, monta o contexto
geológico para os agentes, e controla o orçamento de tokens.

Ref: RFC-002 §6, §7.3
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from miner_harness.cache.manager import CacheManager
    from miner_harness.connectors.geosgb.connector import GeoSGBConnector
    from miner_harness.core.types import BoundingBox

logger = structlog.get_logger(__name__)

# Serviços e seus métodos no GeoSGBConnector
_SERVICE_METHODS = {
    "ocorrencias": "ocorrencias",
    "gravimetria": "gravimetria",
    "geoquimica": "geoquimica",
    "geocronologia": "geocronologia",
    "litoestratigrafia": "litoestratigrafia",
    "aerogeofisica": "aerogeofisica",
}

# Máximo de registros por serviço no prompt (RFC-002 §7.3)
MAX_RECORDS_PER_SERVICE = 50


class ContextBuilder:
    """Coleta dados geológicos e monta contexto para os agentes.

    Usa CacheManager para servir dados locais quando possível,
    e GeoSGBConnector para buscar dados faltantes.

    Usage:
        builder = ContextBuilder(connector, cache)
        context = await builder.build(bbox)
        # context = {"ocorrencias": [...], "gravimetria": [...], ...}
    """

    def __init__(
        self,
        connector: GeoSGBConnector,
        cache: CacheManager,
    ) -> None:
        self._connector = connector
        self._cache = cache

    async def build(
        self,
        bbox: BoundingBox,
        *,
        max_records_per_service: int = MAX_RECORDS_PER_SERVICE,
    ) -> dict[str, list[dict[str, Any]]]:
        """Coleta dados de todos os serviços para a região.

        Para cada serviço:
        1. Verifica cache
        2. Se miss, busca via GeoSGBConnector
        3. Salva no cache
        4. Trunca a max_records_per_service

        Args:
            bbox: Bounding box da região.
            max_records_per_service: Máximo de registros por serviço no contexto.

        Returns:
            Dict serviço → lista de features (dicts).
        """
        context: dict[str, list[dict[str, Any]]] = {}

        for service, method_name in _SERVICE_METHODS.items():
            features = await self._get_service_data(service, method_name, bbox)
            # Truncar para orçamento de tokens
            if len(features) > max_records_per_service:
                features = features[:max_records_per_service]
                logger.info(
                    "context_truncated",
                    service=service,
                    original=len(features),
                    truncated_to=max_records_per_service,
                )
            context[service] = features

        total = sum(len(v) for v in context.values())
        sources = sum(1 for v in context.values() if v)
        logger.info(
            "context_built",
            bbox=str(bbox.as_tuple()),
            total_features=total,
            active_sources=sources,
        )
        return context

    async def _get_service_data(
        self,
        service: str,
        method_name: str,
        bbox: BoundingBox,
    ) -> list[dict[str, Any]]:
        """Busca dados de um serviço, usando cache quando possível."""
        # 1. Check cache
        cached = self._cache.get(service, bbox)
        if cached is not None:
            logger.debug("context_cache_hit", service=service, records=len(cached))
            return cached

        # 2. Fetch from GeoSGB
        try:
            connector_method = getattr(self._connector, method_name)
            typed_features = await connector_method(bbox)
            # Convert to dicts for cache storage
            features = [f.model_dump() for f in typed_features]

            # 3. Save to cache
            method = "query" if service == "gravimetria" else "identify"
            self._cache.put(service, bbox, features, method)

            logger.info(
                "context_fetched",
                service=service,
                records=len(features),
            )
            return features

        except Exception:
            logger.warning(
                "context_fetch_failed",
                service=service,
                exc_info=True,
            )
            return []

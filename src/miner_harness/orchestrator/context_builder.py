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
    from miner_harness.index.search_engine import SearchEngine

# (connector_instance, method_name) — serviços adicionais além do GeoSGB
ExtraSourcesMap = dict[str, tuple[Any, str]]

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
        search_engine: SearchEngine | None = None,
        extra_sources: ExtraSourcesMap | None = None,
    ) -> None:
        self._connector = connector
        self._cache = cache
        self._search_engine = search_engine
        self._extra_sources: ExtraSourcesMap = extra_sources or {}

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
            features = await self._get_service_data(service, method_name, bbox, self._connector)
            if len(features) > max_records_per_service:
                features = features[:max_records_per_service]
                logger.info(
                    "context_truncated",
                    service=service,
                    original=len(features),
                    truncated_to=max_records_per_service,
                )
            context[service] = features

        for service, (connector, method_name) in self._extra_sources.items():
            features = await self._get_service_data(service, method_name, bbox, connector)
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

        if self._search_engine is not None:
            await self._index_features(context)

        return context

    async def _index_features(
        self,
        context: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Indexa features no SearchEngine para RAG (best-effort).

        Converte features para texto e gera embeddings em batch.
        Erros são logados e ignorados para não bloquear o pipeline.
        """
        from miner_harness.index.text_builder import dict_to_text
        from miner_harness.index.types import IndexDocument

        documents = []
        for service, features in context.items():
            source = f"geosgb/{service}"
            for i, feature in enumerate(features):
                doc_id = f"{source}:{feature.get('objectid', i)}"
                text = dict_to_text(feature, source)
                documents.append(IndexDocument(id=doc_id, source=source, text=text))

        if not documents:
            return

        try:
            # Processar em chunks respeitando o limite do DocumentStore
            chunk_size = 500
            total = 0
            for i in range(0, len(documents), chunk_size):
                chunk = documents[i : i + chunk_size]
                total += await self._search_engine.index_batch(chunk)  # type: ignore[union-attr]
            logger.info("context_indexed", documents=total)
        except Exception:
            logger.warning("context_index_failed", exc_info=True)

    async def _get_service_data(
        self,
        service: str,
        method_name: str,
        bbox: BoundingBox,
        connector: Any,
    ) -> list[dict[str, Any]]:
        """Busca dados de um serviço, usando cache quando possível."""
        # 1. Check cache
        cached = self._cache.get(service, bbox)
        if cached is not None:
            logger.debug("context_cache_hit", service=service, records=len(cached))
            return cached

        # 2. Fetch from connector
        print(f"  → {service}: buscando...", flush=True)
        try:
            connector_method = getattr(connector, method_name)
            typed_features = await connector_method(bbox)
            # Convert to dicts for cache storage
            features = [f.model_dump() for f in typed_features]

            # 3. Save to cache
            method = "query" if service == "gravimetria" else "identify"
            self._cache.put(service, bbox, features, method)

            print(f"  ✓ {service}: {len(features)} registros", flush=True)
            logger.info(
                "context_fetched",
                service=service,
                records=len(features),
            )
            return features

        except Exception:
            print(f"  ✗ {service}: falhou (sem dados)", flush=True)
            logger.warning(
                "context_fetch_failed",
                service=service,
                exc_info=True,
            )
            # Cache the empty result so we don't retry a broken service every run.
            try:
                method = "query" if service == "gravimetria" else "identify"
                self._cache.put(service, bbox, [], method)
            except Exception:
                pass
            return []

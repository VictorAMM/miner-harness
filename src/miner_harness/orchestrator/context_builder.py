"""ContextBuilder — coleta e organiza dados para análise.

Busca dados do GeoSGB via CacheManager, monta o contexto
geológico para os agentes, e controla o orçamento de tokens.

Ref: RFC-002 §6, §7.3
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from miner_harness.cache.manager import CacheManager
    from miner_harness.connectors.geosgb.connector import GeoSGBConnector
    from miner_harness.connectors.sentinel2.connector import CopernicusConnector
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
    "furos": "furos_sondagem",
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
        copernicus: CopernicusConnector | None = None,
    ) -> None:
        self._connector = connector
        self._cache = cache
        self._search_engine = search_engine
        self._extra_sources: ExtraSourcesMap = extra_sources or {}
        self._copernicus = copernicus
        # Serviços filtrados pelo bbox na última chamada a build()
        # (dados obtidos, mas todos os registros estavam fora do bbox)
        self.bbox_filtered_sources: list[str] = []

    async def build(
        self,
        bbox: BoundingBox,
        *,
        max_records_per_service: int = MAX_RECORDS_PER_SERVICE,
        user_drillholes: list[dict[str, Any]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Coleta dados de todos os serviços para a região em paralelo.

        GeoSGB e fontes extras são buscadas via asyncio.gather() para
        aproveitar o semáforo de concorrência do ThrottledClient
        (max_concurrent=3 por padrão). Cache hits são resolvidos sem
        I/O e não consomem slots do semáforo.

        Args:
            bbox: Bounding box da região.
            max_records_per_service: Máximo de registros por serviço no contexto.

        Returns:
            Dict serviço → lista de features (dicts).
        """
        all_services: list[tuple[str, str, Any]] = [
            (svc, method, self._connector) for svc, method in _SERVICE_METHODS.items()
        ] + [(svc, method, connector) for svc, (connector, method) in self._extra_sources.items()]

        results: list[list[dict[str, Any]]] = await asyncio.gather(
            *(self._get_service_data(svc, method, bbox, conn) for svc, method, conn in all_services)
        )

        cx = (bbox.lon_min + bbox.lon_max) / 2
        cy = (bbox.lat_min + bbox.lat_max) / 2

        self.bbox_filtered_sources = []
        context: dict[str, list[dict[str, Any]]] = {}
        for (service, _, _), features in zip(all_services, results, strict=True):
            # Filtrar registros com coordenadas fora do bbox antes de truncar.
            # Registros sem coordenada são preservados (podem ser polígonos úteis).
            before = len(features)
            features = self._filter_by_bbox(features, bbox)
            dropped = before - len(features)
            if dropped:
                logger.warning(
                    "context_bbox_filter",
                    service=service,
                    dropped=dropped,
                    kept=len(features),
                )
                if before > 0 and len(features) == 0:
                    # Dados retornados mas 100% fora do bbox — registrar separado de "falhou"
                    self.bbox_filtered_sources.append(service)

            if len(features) > max_records_per_service:
                features = self._sort_by_proximity(features, cx, cy)
                logger.info(
                    "context_truncated",
                    service=service,
                    original=len(features),
                    truncated_to=max_records_per_service,
                )
                features = features[:max_records_per_service]
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

        # Normalização geoquímica regional (PRD-002 F2)
        geo_records = context.get("geoquimica", [])
        if geo_records:
            from miner_harness.geochemistry import GeochemistryNormalizer  # noqa: PLC0415

            norm = GeochemistryNormalizer().normalize(geo_records)
            if norm and norm.elements:
                context["geoquimica_normalizada"] = [{"text": norm.format_for_prompt()}]
                logger.info(
                    "geoquimica_normalizada",
                    n_records=norm.n_records,
                    n_anomalous=len(norm.anomalous_elements),
                )

        # Score de prospectividade por weighted overlay (PRD-002 F3)
        from miner_harness.prospectivity import ProspectivityScorer  # noqa: PLC0415

        grid = ProspectivityScorer().score(bbox, context)
        if grid:
            context["prospectivity_grid"] = [
                {"text": grid.format_for_prompt(), "geojson": grid.to_geojson()}
            ]
            logger.info(
                "prospectivity_grid",
                n_cells=len(grid.cells),
                max_score=round(max(c.score for c in grid.cells), 1),
            )

        # Derivadas gravimétricas Bouguer (PRD-002 F5)
        grav_records = context.get("gravimetria", [])
        if grav_records:
            from miner_harness.geophysics import BouguerProcessor  # noqa: PLC0415

            bgrid = BouguerProcessor().process(grav_records, bbox)
            if bgrid:
                context["bouguer_gradient"] = [
                    {"text": bgrid.format_for_prompt(), "geojson": bgrid.to_geojson()}
                ]
                logger.info(
                    "bouguer_gradient",
                    n_source=bgrid.n_source_points,
                    n_lineaments=len(bgrid.lineament_cells),
                )

        # Furos de sondagem do usuário (PRD-002 F7)
        if user_drillholes:
            from miner_harness.ingestion.drillhole_parser import DrillholeParser  # noqa: PLC0415

            dh_text = DrillholeParser.format_for_prompt(user_drillholes)
            dh_geojson = DrillholeParser.to_geojson(user_drillholes)
            context["user_drillholes"] = [{"text": dh_text, "geojson": dh_geojson}]
            logger.info(
                "user_drillholes_injected",
                n_records=len(user_drillholes),
                n_collar_points=len(dh_geojson["features"]),
            )

        # Índices espectrais Sentinel-2 via CDSE (PRD-002 F6)
        if self._copernicus is not None:
            s2_result = await self._get_sentinel2_indices(bbox)
            if s2_result is not None:
                context["sentinel2_indices"] = [
                    {"text": s2_result.format_for_prompt(), "stats": s2_result.to_dict()}
                ]
                logger.info(
                    "sentinel2_indices_injected",
                    cloud_free_pct=round(s2_result.cloud_free_pct, 1),
                    available=len(s2_result.available_indices),
                )

        return context

    @staticmethod
    def _filter_by_bbox(
        features: list[dict[str, Any]],
        bbox: BoundingBox,
        tolerance_fraction: float = 0.20,
    ) -> list[dict[str, Any]]:
        """Remove registros cujas coordenadas estão claramente fora do bbox.

        Registros sem coordenada são preservados — podem corresponder a
        polígonos cujo centróide não foi calculado ou atributos tabulares
        sem geometria.

        Um buffer de 20% do tamanho do bbox é aplicado para tolerar
        centroides de polígonos que extrapolam levemente a janela de consulta.
        Registros de outra região (diferença de graus) são removidos.
        """
        buf_lon = max(bbox.width * tolerance_fraction, 0.5)
        buf_lat = max(bbox.height * tolerance_fraction, 0.5)
        lon_min = bbox.lon_min - buf_lon
        lon_max = bbox.lon_max + buf_lon
        lat_min = bbox.lat_min - buf_lat
        lat_max = bbox.lat_max + buf_lat

        kept = []
        for f in features:
            coord = f.get("coordenada")
            if not isinstance(coord, dict):
                kept.append(f)
                continue
            try:
                lon = float(coord["longitude"])
                lat = float(coord["latitude"])
            except (KeyError, TypeError, ValueError):
                kept.append(f)
                continue
            if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                kept.append(f)
        return kept

    @staticmethod
    def _sort_by_proximity(
        features: list[dict[str, Any]],
        cx: float,
        cy: float,
    ) -> list[dict[str, Any]]:
        """Ordena registros por distância ao centróide do bbox (mais próximo primeiro).

        Registros sem coordenadas válidas vão para o final da lista.
        Usa distância euclidiana ao quadrado (evita sqrt, suficiente para ranking).
        """

        def _dist2(f: dict[str, Any]) -> float:
            coord = f.get("coordenada")
            if not isinstance(coord, dict):
                return float("inf")
            try:
                lon = float(coord["longitude"])
                lat = float(coord["latitude"])
            except (KeyError, TypeError, ValueError):
                return float("inf")
            return (lon - cx) ** 2 + (lat - cy) ** 2

        return sorted(features, key=_dist2)

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

        search_engine = self._search_engine  # narrowing: caller garante não-None
        assert search_engine is not None
        try:
            # Processar em chunks respeitando o limite do DocumentStore
            chunk_size = 500
            total = 0
            for i in range(0, len(documents), chunk_size):
                chunk = documents[i : i + chunk_size]
                total += await search_engine.index_batch(chunk)
            logger.info("context_indexed", documents=total)
        except Exception:
            logger.warning("context_index_failed", exc_info=True)

    async def _get_sentinel2_indices(
        self,
        bbox: BoundingBox,
    ) -> Any:
        """Obtém índices Sentinel-2 via CDSE, usando cache quando possível.

        Returns:
            Sentinel2Indices ou None se indisponível/erro.
        """
        from miner_harness.connectors.sentinel2.processor import (  # noqa: PLC0415
            Sentinel2Indices,
            SentinelIndexProcessor,
        )

        # 1. Tentar cache
        cached = self._cache.get("sentinel2", bbox)
        if cached is not None and cached:
            logger.debug("sentinel2_cache_hit")
            try:
                return Sentinel2Indices.from_dict(cached[0])
            except Exception:
                logger.warning("sentinel2_cache_deserialize_failed", exc_info=True)

        # 2. Buscar do conector
        copernicus = self._copernicus  # narrowing
        assert copernicus is not None
        print("  → sentinel2: buscando índices espectrais...", flush=True)
        try:
            raw = await copernicus.statistics(bbox)
            if not raw:
                print("  ✗ sentinel2: sem dados disponíveis", flush=True)
                return None

            result = SentinelIndexProcessor().process(raw)
            if result is None:
                print("  ✗ sentinel2: resposta sem outputs válidos", flush=True)
                return None

            # 3. Salvar no cache
            self._cache.put("sentinel2", bbox, [result.to_dict()], "statistics")
            print(
                f"  ✓ sentinel2: {len(result.available_indices)} índices"
                f" ({result.cloud_free_pct:.0f}% livre de nuvens)",
                flush=True,
            )
            return result

        except Exception:
            logger.warning("sentinel2_fetch_failed", exc_info=True)
            print("  ✗ sentinel2: falhou (tentará na próxima execução)", flush=True)
            return None

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
            print(f"  ✗ {service}: falhou (tentará novamente na próxima execução)", flush=True)
            logger.warning(
                "context_fetch_failed",
                service=service,
                exc_info=True,
            )
            # Não cacheamos falhas — um erro transitório não deve bloquear análises
            # futuras; o serviço será retentado na próxima execução.
            return []

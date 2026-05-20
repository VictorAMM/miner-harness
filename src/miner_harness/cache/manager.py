"""CacheManager — fachada do subsistema de cache.

Orquestra SQLiteStore e TTLPolicy, provendo interface
unificada para o Orchestrator e GeoSGBConnector.

Ref: RFC-003 §3.4
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from miner_harness.cache.sqlite_store import SQLiteStore
from miner_harness.cache.ttl_policy import TTLPolicy
from miner_harness.cache.types import CacheStats, CoverageReport
from miner_harness.core.config import StorageConfig

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox

logger = structlog.get_logger(__name__)

# Serviços essenciais para análise offline
_ESSENTIAL_SERVICES = [
    "ocorrencias",
    "gravimetria",
    "geoquimica",
    "geocronologia",
    "litoestratigrafia",
    "aerogeofisica",
]


class CacheManager:
    """Fachada do subsistema de cache.

    Integra SQLiteStore (features pontuais) com TTLPolicy.
    GeoPackageStore será adicionado quando geopandas estiver disponível.

    Usage:
        config = StorageConfig()
        cache = CacheManager(config)
        features = cache.get("ocorrencias", bbox)
        if features is None:
            # fetch from GeoSGB
            features = await connector.ocorrencias(bbox)
            cache.put("ocorrencias", bbox, [f.model_dump() for f in features])
    """

    def __init__(self, config: StorageConfig | None = None) -> None:
        self._config = config or StorageConfig()
        self._config.ensure_dirs()
        self._sqlite = SQLiteStore(self._config.cache_dir / "geosgb.db")
        self._ttl = TTLPolicy()
        # Evict expired entries on startup so stale data never blocks fresh fetches.
        if self._config.auto_evict:
            evicted = self._sqlite.evict_expired()
            if evicted:
                logger.info("cache_startup_evict", evicted=evicted)

    @property
    def sqlite_store(self) -> SQLiteStore:
        """Acesso direto ao SQLiteStore (para testes/debug)."""
        return self._sqlite

    def get(
        self,
        service: str,
        bbox: BoundingBox,
    ) -> list[dict[str, Any]] | None:
        """Busca features no cache.

        Args:
            service: Nome do serviço GeoSGB.
            bbox: Bounding box da consulta.

        Returns:
            Lista de features ou None se cache miss/expirado.
        """
        return self._sqlite.get(service, bbox)

    def put(
        self,
        service: str,
        bbox: BoundingBox,
        features: list[dict[str, Any]],
        method: str = "identify",
    ) -> None:
        """Salva features no cache.

        Args:
            service: Nome do serviço GeoSGB.
            bbox: Bounding box da consulta.
            features: Features a cachear.
            method: Método de extração.
        """
        self._sqlite.put(service, bbox, features, method)

        # Auto-evict se configurado
        if self._config.auto_evict:
            stats = self._sqlite.stats()
            max_bytes = int(self._config.max_cache_size_gb * 1024 * 1024 * 1024)
            if stats.size_bytes > max_bytes:
                evicted = self._sqlite.evict_expired()
                logger.info(
                    "cache_auto_evict",
                    evicted=evicted,
                    size_bytes=stats.size_bytes,
                    max_bytes=max_bytes,
                )

    def contains(self, service: str, bbox: BoundingBox) -> bool:
        """Verifica se bbox está coberto e fresco no cache."""
        return self._sqlite.contains(service, bbox)

    def evict_expired(self) -> int:
        """Remove entradas expiradas. Retorna contagem."""
        return self._sqlite.evict_expired()

    def stats(self) -> CacheStats:
        """Estatísticas do cache."""
        return self._sqlite.stats()

    def coverage_report(self, bbox: BoundingBox) -> CoverageReport:
        """Gera relatório de cobertura para uma região.

        Args:
            bbox: Bounding box da região.

        Returns:
            CoverageReport indicando quais serviços estão cacheados/frescos.
        """
        services_cached: dict[str, bool] = {}
        services_fresh: dict[str, bool] = {}
        missing: list[str] = []
        total_features = 0

        for service in _ESSENTIAL_SERVICES:
            cached_data = self._sqlite.get(service, bbox)
            is_cached = cached_data is not None
            services_cached[service] = is_cached
            services_fresh[service] = is_cached  # get() já verifica TTL

            if is_cached and cached_data is not None:
                total_features += len(cached_data)
            else:
                missing.append(service)

        can_offline = len(missing) == 0

        report = CoverageReport(
            region=bbox,
            services_cached=services_cached,
            services_fresh=services_fresh,
            total_features=total_features,
            indexed_features=0,  # Será preenchido pelo VectorIndex
            can_run_offline=can_offline,
            missing_services=missing,
        )

        logger.info(
            "coverage_report",
            can_offline=can_offline,
            cached=sum(1 for v in services_cached.values() if v),
            total=len(_ESSENTIAL_SERVICES),
            missing=missing,
        )
        return report

    def clear(self) -> int:
        """Limpa todo o cache. Retorna entradas removidas."""
        removed = self._sqlite.clear()
        logger.info("cache_cleared", removed=removed)
        return removed

    def close(self) -> None:
        """Fecha conexões."""
        self._sqlite.close()

    def __enter__(self) -> CacheManager:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

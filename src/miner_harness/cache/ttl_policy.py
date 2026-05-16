"""Política de TTL (Time-To-Live) do cache por tipo de dado.

Ref: RFC-003 §3.3
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from miner_harness.cache.types import CacheEntry


class TTLPolicy:
    """Política de expiração do cache por tipo de dado.

    Dados mais estáveis (litoestratigrafia) têm TTL longo.
    Contagens e metadados voláteis expiram rápido.
    """

    POLICIES: dict[str, int] = {
        # Dados pontuais que podem ser atualizados
        "ocorrencias": 30,
        "geoquimica": 30,
        "geocronologia": 60,
        "gravimetria": 90,
        # Dados de polígonos (mudam muito raramente)
        "litoestratigrafia": 365,
        "bacias_sedimentares": 365,
        "provincias": 365,
        "aerogeofisica": 90,
        # Metadados voláteis
        "count": 7,
        "service_info": 30,
    }

    DEFAULT_TTL: int = 30

    def get_ttl(self, service: str) -> int:
        """Retorna TTL em dias para o serviço."""
        return self.POLICIES.get(service, self.DEFAULT_TTL)

    def is_expired(self, entry: CacheEntry) -> bool:
        """Verifica se entrada expirou."""
        from datetime import timedelta

        now = datetime.now(tz=timezone.utc)  # noqa: UP017
        # Ensure fetched_at is timezone-aware
        fetched = entry.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)  # noqa: UP017
        expiry = fetched + timedelta(days=entry.ttl_days)
        return now > expiry

"""Cliente HTTP com throttling, retry e backoff exponencial.

Todas as requisições ao GeoSGB passam por aqui para garantir
rate limiting defensivo e resiliência a erros transientes.

Ref: RFC-001 §6 (Rate limiting defensivo)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

from miner_harness.core.config import GeoSGBConfig
from miner_harness.core.exceptions import (
    GeoSGBConnectionError,
    GeoSGBRateLimitError,
    GeoSGBTimeoutError,
)

logger = structlog.get_logger(__name__)


class ThrottledClient:
    """Cliente HTTP async com throttling e retry automático.

    Garante:
    - Delay mínimo entre requests (min_delay_ms)
    - Máximo de requests concorrentes (semáforo)
    - Retry com backoff exponencial em erros transientes (429, 503)
    - Logging estruturado de cada request
    """

    def __init__(self, config: GeoSGBConfig | None = None) -> None:
        self._config = config or GeoSGBConfig()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent)
        self._last_request_time: float = 0.0
        self._client: httpx.AsyncClient | None = None

    @property
    def min_delay_s(self) -> float:
        """Delay mínimo entre requests em segundos."""
        return self._config.min_delay_ms / 1000.0

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init do httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._config.timeout_s),
                headers={"User-Agent": "miner-harness/0.1.0"},
                follow_redirects=True,
            )
        return self._client

    async def _throttle(self) -> None:
        """Aguarda tempo mínimo desde o último request."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.min_delay_s:
            await asyncio.sleep(self.min_delay_s - elapsed)
        self._last_request_time = time.monotonic()

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Faz GET com throttling, retry e parsing JSON.

        Args:
            url: URL completa do endpoint.
            params: Query parameters.

        Returns:
            Resposta parseada como dict.

        Raises:
            GeoSGBConnectionError: Falha de conexão.
            GeoSGBRateLimitError: Rate limit após todos os retries.
            GeoSGBTimeoutError: Timeout após todos os retries.
        """
        last_exc: Exception | None = None

        for attempt in range(1, self._config.max_retries + 1):
            async with self._semaphore:
                await self._throttle()
                start = time.monotonic()
                try:
                    client = await self._get_client()
                    response = await client.get(url, params=params)
                    latency_ms = int((time.monotonic() - start) * 1000)

                    if response.status_code == 429:
                        logger.warning(
                            "geosgb_rate_limit",
                            url=url,
                            attempt=attempt,
                            latency_ms=latency_ms,
                        )
                        last_exc = GeoSGBRateLimitError(
                            f"Rate limited on {url} (attempt {attempt})"
                        )
                        await self._backoff(attempt)
                        continue

                    if response.status_code == 503:
                        logger.warning(
                            "geosgb_service_unavailable",
                            url=url,
                            attempt=attempt,
                            latency_ms=latency_ms,
                        )
                        last_exc = GeoSGBConnectionError(
                            f"Service unavailable on {url} (attempt {attempt})"
                        )
                        await self._backoff_503(attempt)
                        continue

                    response.raise_for_status()

                    data: dict[str, Any] = response.json()

                    logger.debug(
                        "geosgb_request",
                        url=url,
                        status=response.status_code,
                        latency_ms=latency_ms,
                        attempt=attempt,
                    )
                    return data

                except httpx.TimeoutException:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    logger.warning(
                        "geosgb_timeout",
                        url=url,
                        attempt=attempt,
                        latency_ms=latency_ms,
                    )
                    last_exc = GeoSGBTimeoutError(
                        f"Timeout on {url} after {latency_ms}ms (attempt {attempt})"
                    )
                    await self._backoff(attempt)

                except httpx.ConnectError as exc:
                    logger.error(
                        "geosgb_connection_error",
                        url=url,
                        attempt=attempt,
                        error=str(exc),
                    )
                    raise GeoSGBConnectionError(f"Connection failed to {url}: {exc}") from exc

        # Todos os retries esgotados
        if last_exc is not None:
            raise last_exc
        msg = f"All {self._config.max_retries} retries exhausted for {url}"  # pragma: no cover
        raise GeoSGBConnectionError(msg)  # pragma: no cover

    async def _backoff(self, attempt: int) -> None:
        """Backoff exponencial entre retries."""
        delay = self._config.min_delay_ms / 1000.0 * (self._config.backoff_factor ** (attempt - 1))
        logger.debug("geosgb_backoff", attempt=attempt, delay_s=round(delay, 2))
        await asyncio.sleep(delay)

    async def _backoff_503(self, attempt: int) -> None:
        """Backoff para 503 — base maior para dar tempo ao servidor recuperar."""
        # Usa 5x o delay mínimo como base (min 2s) para 503 (servidor sobrecarregado)
        base = max(2.0, self._config.min_delay_ms / 1000.0 * 5)
        delay = base * (self._config.backoff_factor ** (attempt - 1))
        logger.debug("geosgb_backoff_503", attempt=attempt, delay_s=round(delay, 2))
        await asyncio.sleep(delay)

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> ThrottledClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

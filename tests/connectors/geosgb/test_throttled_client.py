"""Testes do ThrottledClient — throttling, retry e backoff."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from miner_harness.connectors.geosgb.throttled_client import ThrottledClient
from miner_harness.core.config import GeoSGBConfig
from miner_harness.core.exceptions import (
    GeoSGBConnectionError,
    GeoSGBRateLimitError,
    GeoSGBTimeoutError,
)


@pytest.fixture()
def fast_config() -> GeoSGBConfig:
    """Config com delays mínimos para testes rápidos."""
    return GeoSGBConfig(
        min_delay_ms=0,
        max_concurrent=10,
        max_retries=2,
        backoff_factor=1.0,
        timeout_s=5,
    )


class TestThrottledClient:
    """Testes do cliente com throttling."""

    async def test_successful_get(self, fast_config: GeoSGBConfig) -> None:
        client = ThrottledClient(fast_config)
        mock_response = httpx.Response(
            200,
            json={"results": [{"id": 1}]},
            request=httpx.Request("GET", "https://example.com"),
        )

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            data = await client.get("https://example.com/api")
            assert data == {"results": [{"id": 1}]}

        await client.close()

    async def test_retry_on_429(self, fast_config: GeoSGBConfig) -> None:
        client = ThrottledClient(fast_config)
        responses = [
            httpx.Response(
                429,
                request=httpx.Request("GET", "https://example.com"),
            ),
            httpx.Response(
                200,
                json={"ok": True},
                request=httpx.Request("GET", "https://example.com"),
            ),
        ]

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = responses
            data = await client.get("https://example.com/api")
            assert data == {"ok": True}
            assert mock_get.call_count == 2

        await client.close()

    async def test_retry_on_503(self, fast_config: GeoSGBConfig) -> None:
        client = ThrottledClient(fast_config)
        responses = [
            httpx.Response(
                503,
                request=httpx.Request("GET", "https://example.com"),
            ),
            httpx.Response(
                200,
                json={"ok": True},
                request=httpx.Request("GET", "https://example.com"),
            ),
        ]

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = responses
            data = await client.get("https://example.com/api")
            assert data == {"ok": True}

        await client.close()

    async def test_raises_after_max_retries_429(self, fast_config: GeoSGBConfig) -> None:
        client = ThrottledClient(fast_config)
        responses = [
            httpx.Response(429, request=httpx.Request("GET", "https://example.com")),
            httpx.Response(429, request=httpx.Request("GET", "https://example.com")),
        ]

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = responses
            with pytest.raises(GeoSGBRateLimitError):
                await client.get("https://example.com/api")

        await client.close()

    async def test_raises_on_timeout(self, fast_config: GeoSGBConfig) -> None:
        client = ThrottledClient(fast_config)

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timeout")
            with pytest.raises(GeoSGBTimeoutError):
                await client.get("https://example.com/api")

        await client.close()

    async def test_raises_on_connection_error(self, fast_config: GeoSGBConfig) -> None:
        client = ThrottledClient(fast_config)

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("refused")
            with pytest.raises(GeoSGBConnectionError):
                await client.get("https://example.com/api")

        await client.close()

    async def test_context_manager(self, fast_config: GeoSGBConfig) -> None:
        async with ThrottledClient(fast_config) as client:
            assert client._client is None  # Lazy init
        # After exit, client should be closed (or None)

    def test_min_delay_property(self) -> None:
        config = GeoSGBConfig(min_delay_ms=500)
        client = ThrottledClient(config)
        assert client.min_delay_s == 0.5

    async def test_throttle_sleeps_on_rapid_requests(self, fast_config: GeoSGBConfig) -> None:
        """asyncio.sleep é chamado quando elapsed < min_delay_s (linha 64)."""
        import time as time_module

        config = GeoSGBConfig(min_delay_ms=500, max_retries=1, backoff_factor=1.0)
        client = ThrottledClient(config)
        mock_response = httpx.Response(
            200, json={"ok": True}, request=httpx.Request("GET", "https://example.com")
        )
        # 4 monotonic() calls per get(): _throttle×2, start, latency
        # First call: elapsed=1000.0 (no sleep); second call: elapsed=0.05 < 0.5 (sleep)
        mono_seq = [1000.0, 1000.0, 1000.0, 1000.0, 1000.05, 1000.05, 1000.05, 1000.05]
        with (
            patch.object(time_module, "monotonic", side_effect=mono_seq),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.return_value = mock_response
            await client.get("https://example.com/1")
            await client.get("https://example.com/2")
        mock_sleep.assert_called()
        await client.close()

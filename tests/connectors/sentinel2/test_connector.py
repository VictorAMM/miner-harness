"""Testes do CopernicusConnector — OAuth2 token + Statistics API (mockado)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from miner_harness.connectors.sentinel2.connector import CopernicusConnector
from miner_harness.core.config import CopernicusConfig
from miner_harness.core.types import BoundingBox

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**kwargs: Any) -> CopernicusConfig:
    defaults: dict[str, Any] = {
        "enabled": True,
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "max_cloud_pct": 20.0,
        "days_back": 90,
        "timeout_s": 30,
    }
    defaults.update(kwargs)
    return CopernicusConfig(**defaults)


def _make_bbox() -> BoundingBox:
    return BoundingBox(lon_min=-51.0, lat_min=-6.5, lon_max=-50.5, lat_max=-6.0)


def _make_token_response(access_token: str = "tok123", expires_in: int = 3600) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"access_token": access_token, "expires_in": expires_in}
    return resp


def _make_stats_response(data: list | None = None) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "data": data if data is not None else [{"interval": {}, "outputs": {}}],
        "status": "OK",
    }
    return resp


# ---------------------------------------------------------------------------
# TestDisabledConnector
# ---------------------------------------------------------------------------


class TestDisabledConnector:
    @pytest.mark.asyncio
    async def test_returns_empty_when_disabled(self) -> None:
        config = _make_config(enabled=False)
        conn = CopernicusConnector(config)
        result = await conn.statistics(_make_bbox())
        assert result == {}
        await conn.close()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_client_id(self) -> None:
        config = _make_config(client_id="")
        conn = CopernicusConnector(config)
        result = await conn.statistics(_make_bbox())
        assert result == {}
        await conn.close()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_secret(self) -> None:
        config = _make_config(client_secret="")
        conn = CopernicusConnector(config)
        result = await conn.statistics(_make_bbox())
        assert result == {}
        await conn.close()


# ---------------------------------------------------------------------------
# TestTokenRefresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_token_cached_on_success(self) -> None:
        config = _make_config()
        conn = CopernicusConnector(config)

        mock_post = AsyncMock(return_value=_make_token_response("tok-abc"))
        with patch.object(conn._client, "post", mock_post):
            t1 = await conn._get_token()
            t2 = await conn._get_token()  # should use cached

        assert t1 == "tok-abc"
        assert t2 == "tok-abc"
        assert mock_post.call_count == 1  # only one HTTP call
        await conn.close()

    @pytest.mark.asyncio
    async def test_token_refresh_on_expiry(self) -> None:
        config = _make_config()
        conn = CopernicusConnector(config)
        # Simulate expired token
        conn._token = "old-token"
        conn._token_expires_at = 0.0  # already expired

        mock_post = AsyncMock(return_value=_make_token_response("new-token"))
        with patch.object(conn._client, "post", mock_post):
            token = await conn._get_token()

        assert token == "new-token"
        assert mock_post.call_count == 1
        await conn.close()

    @pytest.mark.asyncio
    async def test_token_failure_returns_none(self) -> None:
        config = _make_config()
        conn = CopernicusConnector(config)

        mock_post = AsyncMock(side_effect=Exception("network error"))
        with patch.object(conn._client, "post", mock_post):
            token = await conn._get_token()

        assert token is None
        assert conn._token is None
        await conn.close()

    @pytest.mark.asyncio
    async def test_statistics_returns_empty_when_token_fails(self) -> None:
        config = _make_config()
        conn = CopernicusConnector(config)

        mock_post = AsyncMock(side_effect=Exception("auth error"))
        with patch.object(conn._client, "post", mock_post):
            result = await conn.statistics(_make_bbox())

        assert result == {}
        await conn.close()


# ---------------------------------------------------------------------------
# TestStatisticsAPI
# ---------------------------------------------------------------------------


class TestStatisticsAPI:
    @pytest.mark.asyncio
    async def test_statistics_calls_correct_endpoints(self) -> None:
        config = _make_config()
        conn = CopernicusConnector(config)

        responses = [
            _make_token_response("tok-xyz"),
            _make_stats_response(),
        ]
        mock_post = AsyncMock(side_effect=responses)

        with patch.object(conn._client, "post", mock_post):
            result = await conn.statistics(_make_bbox())

        assert result != {}
        # Two calls: token + statistics
        assert mock_post.call_count == 2
        token_call = mock_post.call_args_list[0]
        stats_call = mock_post.call_args_list[1]
        assert "token" in str(token_call.args[0])
        assert "statistics" in str(stats_call.args[0])
        await conn.close()

    @pytest.mark.asyncio
    async def test_statistics_passes_bbox_in_payload(self) -> None:
        config = _make_config()
        conn = CopernicusConnector(config)
        bbox = _make_bbox()

        responses = [_make_token_response(), _make_stats_response()]
        mock_post = AsyncMock(side_effect=responses)

        with patch.object(conn._client, "post", mock_post):
            await conn.statistics(bbox)

        stats_call = mock_post.call_args_list[1]
        payload = stats_call.kwargs["json"]
        bbox_sent = payload["input"]["bounds"]["bbox"]
        assert bbox_sent[0] == pytest.approx(bbox.lon_min)
        assert bbox_sent[1] == pytest.approx(bbox.lat_min)
        assert bbox_sent[2] == pytest.approx(bbox.lon_max)
        assert bbox_sent[3] == pytest.approx(bbox.lat_max)
        await conn.close()

    @pytest.mark.asyncio
    async def test_statistics_passes_cloud_filter(self) -> None:
        config = _make_config(max_cloud_pct=15.0)
        conn = CopernicusConnector(config)

        responses = [_make_token_response(), _make_stats_response()]
        mock_post = AsyncMock(side_effect=responses)

        with patch.object(conn._client, "post", mock_post):
            await conn.statistics(_make_bbox())

        stats_call = mock_post.call_args_list[1]
        payload = stats_call.kwargs["json"]
        cloud_filter = payload["input"]["data"][0]["dataFilter"]["maxCloudCoverage"]
        assert cloud_filter == pytest.approx(15.0)
        await conn.close()

    @pytest.mark.asyncio
    async def test_statistics_passes_days_back_in_interval(self) -> None:
        config = _make_config(days_back=60)
        conn = CopernicusConnector(config)

        responses = [_make_token_response(), _make_stats_response()]
        mock_post = AsyncMock(side_effect=responses)

        with patch.object(conn._client, "post", mock_post):
            await conn.statistics(_make_bbox())

        stats_call = mock_post.call_args_list[1]
        payload = stats_call.kwargs["json"]
        interval_str = payload["aggregation"]["aggregationInterval"]["of"]
        assert interval_str == "P60D"
        await conn.close()

    @pytest.mark.asyncio
    async def test_statistics_error_returns_empty(self) -> None:
        config = _make_config()
        conn = CopernicusConnector(config)

        token_resp = _make_token_response()
        error_resp = MagicMock()
        error_resp.raise_for_status.side_effect = Exception("HTTP 403")
        responses = [token_resp, error_resp]
        mock_post = AsyncMock(side_effect=responses)

        with patch.object(conn._client, "post", mock_post):
            result = await conn.statistics(_make_bbox())

        assert result == {}
        await conn.close()

    @pytest.mark.asyncio
    async def test_bearer_token_in_auth_header(self) -> None:
        config = _make_config()
        conn = CopernicusConnector(config)

        responses = [_make_token_response("my-token-xyz"), _make_stats_response()]
        mock_post = AsyncMock(side_effect=responses)

        with patch.object(conn._client, "post", mock_post):
            await conn.statistics(_make_bbox())

        stats_call = mock_post.call_args_list[1]
        headers = stats_call.kwargs["headers"]
        assert headers["Authorization"] == "Bearer my-token-xyz"
        await conn.close()


# ---------------------------------------------------------------------------
# TestContextManager
# ---------------------------------------------------------------------------


class TestContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        config = _make_config(enabled=False)
        async with CopernicusConnector(config) as conn:
            result = await conn.statistics(_make_bbox())
        assert result == {}

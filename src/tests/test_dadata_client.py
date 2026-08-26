import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.app.config import settings
from src.app.services.dadata.client import (
    DadataRateLimitError,
    DadataRuntimeError,
    _post_party_request,
    find_party_by_inn,
)


def _party_response(*, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://example.test/findById/party"),
        json={"suggestions": [{"data": {"inn": "7719402047"}}]},
    )


def test_client_retries_server_error_and_maps_success():
    request_mock = AsyncMock(side_effect=[_party_response(status_code=500), _party_response()])
    with (
        patch.object(settings, "DADATA_API_KEY", "test-token"),
        patch.object(settings, "DADATA_MAX_RETRIES", 2),
        patch("src.app.services.dadata.client._post_party_request", request_mock),
        patch("src.app.services.dadata.client.asyncio.sleep", new=AsyncMock()) as sleep_mock,
    ):
        result = asyncio.run(find_party_by_inn("7719402047"))

    assert result is not None
    assert result.inn == "7719402047"
    assert request_mock.await_count == 2
    sleep_mock.assert_awaited_once()


def test_client_returns_429_to_worker_without_sleeping_in_request_slot():
    request_mock = AsyncMock(return_value=_party_response(status_code=429))
    with (
        patch.object(settings, "DADATA_API_KEY", "test-token"),
        patch.object(settings, "DADATA_MAX_RETRIES", 1),
        patch("src.app.services.dadata.client._post_party_request", request_mock),
        patch("src.app.services.dadata.client.asyncio.sleep", new=AsyncMock()),
        pytest.raises(DadataRateLimitError),
    ):
        asyncio.run(find_party_by_inn("7719402047"))

    assert request_mock.await_count == 1


def test_fallback_mode_uses_at_most_one_retry():
    request_mock = AsyncMock(return_value=_party_response(status_code=429))
    with (
        patch.object(settings, "DADATA_API_KEY", "test-token"),
        patch.object(settings, "DADATA_MAX_RETRIES", 5),
        patch(
            "src.app.services.dadata.client.require_redis_client",
            new=AsyncMock(side_effect=DadataRuntimeError("Redis недоступен")),
        ),
        patch("src.app.services.dadata.client._post_party_request", request_mock),
        patch("src.app.services.dadata.client.asyncio.sleep", new=AsyncMock()),
        pytest.raises(DadataRateLimitError),
    ):
        asyncio.run(find_party_by_inn("7719402047"))

    assert request_mock.await_count == 1


def test_single_refresh_reserves_request_from_manual_daily_budget():
    http_client = AsyncMock()
    http_client.post.return_value = _party_response()
    with (
        patch(
            "src.app.services.dadata.client.reserve_daily_request",
            new=AsyncMock(return_value=True),
        ) as reserve_mock,
        patch(
            "src.app.services.dadata.client.require_redis_client",
            new=AsyncMock(return_value=object()),
        ),
        patch("src.app.services.dadata.client.wait_for_rps_slot", new=AsyncMock()),
        patch(
            "src.app.services.dadata.client.get_http_client",
            new=AsyncMock(return_value=http_client),
        ),
    ):
        asyncio.run(_post_party_request("7719402047", keep_daily_reserve=False))

    reserve_mock.assert_awaited_once_with(keep_reserve=False)
    http_client.post.assert_awaited_once()


def test_single_refresh_uses_database_limiter_when_redis_is_unavailable():
    http_client = AsyncMock()
    http_client.post.return_value = _party_response()
    with (
        patch(
            "src.app.services.dadata.client.require_redis_client",
            new=AsyncMock(side_effect=DadataRuntimeError("Redis недоступен")),
        ),
        patch(
            "src.app.services.dadata.client.wait_for_fallback_rps_slot",
            new=AsyncMock(),
        ) as fallback_limiter,
        patch(
            "src.app.services.dadata.client.reserve_daily_request",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "src.app.services.dadata.client.get_http_client",
            new=AsyncMock(return_value=http_client),
        ),
    ):
        asyncio.run(_post_party_request("7719402047", keep_daily_reserve=False))

    fallback_limiter.assert_awaited_once()


def test_bulk_refresh_never_falls_back_to_database_limiter_without_redis():
    fallback_limiter = AsyncMock()
    with (
        patch(
            "src.app.services.dadata.client.require_redis_client",
            new=AsyncMock(side_effect=DadataRuntimeError("Redis недоступен")),
        ),
        patch(
            "src.app.services.dadata.client.wait_for_fallback_rps_slot",
            fallback_limiter,
        ),
        pytest.raises(DadataRateLimitError, match="Redis недоступен"),
    ):
        asyncio.run(_post_party_request("7719402047", keep_daily_reserve=True))

    fallback_limiter.assert_not_awaited()

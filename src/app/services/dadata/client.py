from __future__ import annotations

import asyncio
import random
from contextlib import suppress
from typing import Any

import httpx

from src.app.config import settings
from src.app.services.dadata.mapper import map_party_response
from src.app.services.dadata.normalization import DadataValidationError, normalize_inn
from src.app.services.dadata.runtime import (
    DadataRuntimeError,
    require_redis_client,
    reserve_daily_request,
    wait_for_fallback_rps_slot,
    wait_for_full_refresh_rps_slot,
    wait_for_new_connection_slot,
    wait_for_rps_slot,
)
from src.app.services.dadata.schemas import DadataOrganizationData


class DadataConfigurationError(RuntimeError):
    """Raised when Dadata credentials are missing or invalid."""


class DadataRateLimitError(RuntimeError):
    """Raised when local or remote Dadata limits reject a request."""

    def __init__(self, message: str, *, retry_after_seconds: float = 0) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(0, retry_after_seconds)


class DadataClientError(RuntimeError):
    """Raised when Dadata lookup fails."""


_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        # A direct lookup remains available when Redis is unavailable.  The
        # fallback request limiter below protects Dadata in that mode; opening
        # the single pooled HTTP client does not require a Redis connection.
        with suppress(DadataRuntimeError):
            await wait_for_new_connection_slot()
        limits = httpx.Limits(
            max_connections=max(settings.DADATA_MAX_CONCURRENT_REQUESTS, 1),
            max_keepalive_connections=max(settings.DADATA_MAX_CONCURRENT_REQUESTS, 1),
        )
        _http_client = httpx.AsyncClient(
            base_url=settings.DADATA_BASE_URL.rstrip("/"),
            timeout=settings.DADATA_LOOKUP_TIMEOUT_SECONDS,
            limits=limits,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    return _http_client


async def close_dadata_client() -> None:
    global _http_client
    if _http_client is not None:
        with suppress(RuntimeError):
            await _http_client.aclose()
    _http_client = None


async def _post_party_request(
    requested_inn: str,
    *,
    keep_daily_reserve: bool,
) -> httpx.Response:
    try:
        try:
            await require_redis_client()
        except DadataRuntimeError:
            # A complete refresh is deliberately Redis-only.  Falling back
            # halfway through it would strand its parent progress tracking and
            # turn a bulk run into slow synchronous database-limited traffic.
            if keep_daily_reserve:
                raise
            await wait_for_fallback_rps_slot()
        else:
            if keep_daily_reserve:
                await wait_for_full_refresh_rps_slot()
            await wait_for_rps_slot()
        if not await reserve_daily_request(keep_reserve=keep_daily_reserve):
            raise DadataRateLimitError("Дневной лимит запросов к Dadata исчерпан.")
        client = await get_http_client()
    except DadataRuntimeError as error:
        raise DadataRateLimitError(str(error)) from error
    return await client.post(
        "/findById/party",
        headers={"Authorization": f"Token {settings.DADATA_API_KEY}"},
        json={
            "query": requested_inn,
            "branch_type": "MAIN",
            "type": "LEGAL",
            "count": 1,
        },
    )


def _retry_delay(response: httpx.Response | None, *, attempt: int) -> float:
    retry_after = 0.0
    if response is not None:
        try:
            retry_after = float(response.headers.get("Retry-After", "0"))
        except ValueError:
            retry_after = 0.0
    backoff = settings.DADATA_RETRY_BASE_DELAY_SECONDS * (2**attempt)
    return max(retry_after, backoff) + random.uniform(0, 0.2)


async def _request_with_retries(
    requested_inn: str,
    *,
    keep_daily_reserve: bool,
    max_retries: int | None = None,
) -> httpx.Response:
    response: httpx.Response | None = None
    last_error: Exception | None = None
    attempts = max(settings.DADATA_MAX_RETRIES if max_retries is None else max_retries, 0) + 1
    for attempt in range(attempts):
        try:
            response = await _post_party_request(
                requested_inn,
                keep_daily_reserve=keep_daily_reserve,
            )
        except DadataRateLimitError:
            raise
        except (httpx.TimeoutException, httpx.HTTPError) as error:
            last_error = error
            response = None

        # 429 is retried by the worker through its delayed Redis queue.  Do not
        # occupy a worker slot with Retry-After sleep here.
        retryable = response is None or response.status_code >= 500
        if not retryable:
            break
        if attempt >= attempts - 1:
            break
        await asyncio.sleep(_retry_delay(response, attempt=attempt))

    if response is None:
        raise DadataClientError("Не удалось выполнить запрос к Dadata.") from last_error
    return response


def _raise_for_dadata_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        try:
            retry_after = float(response.headers.get("Retry-After", "0"))
        except ValueError:
            retry_after = 0
        raise DadataRateLimitError(
            "Dadata вернула ограничение частоты запросов.",
            retry_after_seconds=retry_after,
        )
    if response.status_code in {401, 403}:
        raise DadataConfigurationError("Dadata отклонила API-ключ или исчерпан лимит тарифа.")
    if response.status_code >= 500:
        raise DadataClientError("Dadata временно недоступна после повторных попыток.")
    if response.status_code >= 400:
        raise DadataClientError(f"Dadata вернула ошибку {response.status_code}.")


async def find_party_by_inn(
    inn: str,
    *,
    keep_daily_reserve: bool = False,
) -> DadataOrganizationData | None:
    requested_inn = normalize_inn(inn)
    if not settings.DADATA_API_KEY:
        raise DadataConfigurationError("Не задан DADATA_API_KEY.")
    try:
        await require_redis_client()
        fallback_mode = False
    except DadataRuntimeError:
        fallback_mode = True
    response = await _request_with_retries(
        requested_inn,
        keep_daily_reserve=keep_daily_reserve,
        max_retries=1 if fallback_mode else None,
    )
    _raise_for_dadata_status(response)

    try:
        payload: Any = response.json()
    except ValueError as error:
        raise DadataClientError("Dadata вернула некорректный JSON.") from error
    if not isinstance(payload, dict):
        raise DadataClientError("Dadata вернула неожиданный формат ответа.")
    result = map_party_response(payload, requested_inn=requested_inn)
    if result and result.inn != requested_inn:
        raise DadataValidationError("Dadata вернула организацию с другим ИНН.")
    return result

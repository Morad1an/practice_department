from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.models.organization_detaillogotype import OrganizationDetailLogotype
from src.app.services.logotype_utils import build_logo_data_url

try:
    from redis.asyncio import Redis as RedisClient
    from redis.exceptions import RedisError as ImportedRedisError
except ImportError:  # pragma: no cover - optional dependency
    RedisClient = None  # type: ignore[assignment,misc]
    ImportedRedisError = Exception  # type: ignore[assignment,misc]


RedisErrorType: Any = ImportedRedisError


_LOGO_NONE_SENTINEL = "__none__"
_LOGO_REDIS_PREFIX = "active_org_logo:v1:"
_redis_client = None
_redis_client_loop = None


def _redis_key(logotype_id: int) -> str:
    return f"{_LOGO_REDIS_PREFIX}{logotype_id}"


async def _get_redis_client():
    global _redis_client, _redis_client_loop

    if RedisClient is None or not settings.REDIS_URL:
        return None

    current_loop = asyncio.get_running_loop()
    if (
        _redis_client is not None
        and _redis_client_loop is not None
        and _redis_client_loop is not current_loop
    ):
        close_method = getattr(_redis_client, "aclose", None)
        if close_method is not None:
            with suppress(RuntimeError, RedisErrorType):
                await close_method()
        _redis_client = None
        _redis_client_loop = None

    if _redis_client is None:
        redis_class: Any = RedisClient
        _redis_client = redis_class.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
        _redis_client_loop = current_loop
    return _redis_client


def _normalize_logo_ids(raw_ids: Iterable[int], max_ids: int) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw in raw_ids:
        if raw <= 0 or raw in seen:
            continue
        seen.add(raw)
        normalized.append(raw)
        if len(normalized) >= max_ids:
            break
    return normalized


async def _set_cache_values(cache_payload: dict[int, str]) -> None:
    if not cache_payload:
        return

    redis = await _get_redis_client()
    if redis is None:
        return

    try:
        pipeline = redis.pipeline()
        for logotype_id, value in cache_payload.items():
            pipeline.setex(
                _redis_key(logotype_id),
                settings.LOGO_CACHE_TTL_SECONDS,
                value,
            )
        await pipeline.execute()
    except RedisErrorType:
        pass


async def cache_logotype_data(
    *,
    logotype_id: int | None,
    raw_data: bytes | None,
) -> None:
    normalized_ids = _normalize_logo_ids([logotype_id or 0], 1)
    if not normalized_ids:
        return

    data_url = build_logo_data_url(raw_data)
    await _set_cache_values(
        {
            normalized_ids[0]: data_url if data_url is not None else _LOGO_NONE_SENTINEL,
        }
    )


async def invalidate_logotype_cache(*, logotype_ids: Iterable[int]) -> None:
    normalized_ids = _normalize_logo_ids(logotype_ids, settings.LOGO_BATCH_MAX_IDS * 4)
    if not normalized_ids:
        return

    redis = await _get_redis_client()
    if redis is None:
        return

    try:
        await redis.delete(*[_redis_key(logotype_id) for logotype_id in normalized_ids])
    except RedisErrorType:
        pass


async def fetch_logotypes_batch(
    session: AsyncSession,
    *,
    ids: Iterable[int],
) -> dict[str, str | None]:
    logo_ids = _normalize_logo_ids(ids, settings.LOGO_BATCH_MAX_IDS)
    if not logo_ids:
        return {}

    resolved: dict[int, str | None] = {}
    missing_ids = list(logo_ids)

    redis = await _get_redis_client()
    if redis is not None:
        try:
            cached_values = await redis.mget([_redis_key(logotype_id) for logotype_id in logo_ids])
            missing_ids = []
            for logotype_id, cached in zip(logo_ids, cached_values):
                if cached is None:
                    missing_ids.append(logotype_id)
                    continue
                if cached == _LOGO_NONE_SENTINEL:
                    resolved[logotype_id] = None
                    continue
                resolved[logotype_id] = cached
        except RedisErrorType:
            missing_ids = list(logo_ids)

    if missing_ids:
        db_stmt = select(
            OrganizationDetailLogotype.id,
            OrganizationDetailLogotype.compressed,
        ).where(OrganizationDetailLogotype.id.in_(missing_ids))
        db_result = await session.execute(db_stmt)
        raw_by_id = {row.id: row.compressed for row in db_result}

        cache_payload: dict[int, str] = {}
        for logotype_id in missing_ids:
            data_url = build_logo_data_url(raw_by_id.get(logotype_id))
            resolved[logotype_id] = data_url
            cache_payload[logotype_id] = data_url if data_url is not None else _LOGO_NONE_SENTINEL

        await _set_cache_values(cache_payload)

    return {str(logotype_id): resolved.get(logotype_id) for logotype_id in logo_ids}


async def close_logo_cache() -> None:
    global _redis_client, _redis_client_loop
    if _redis_client is None:
        return
    close_method = getattr(_redis_client, "aclose", None)
    if close_method is not None:
        with suppress(RuntimeError, RedisErrorType):
            await close_method()
    _redis_client = None
    _redis_client_loop = None

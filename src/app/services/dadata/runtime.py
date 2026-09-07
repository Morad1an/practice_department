from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Literal

from sqlalchemy import text

from src.app.config import settings
from src.app.database import async_session_maker

try:
    from redis.asyncio import Redis as RedisClient
    from redis.exceptions import RedisError as ImportedRedisError
except ImportError:  # pragma: no cover
    RedisClient = None  # type: ignore[assignment,misc]
    ImportedRedisError = Exception  # type: ignore[assignment,misc]


JobKind = Literal["lookup", "refresh_one", "refresh_all", "refresh_all_item"]
JobOrigin = Literal["manual", "scheduled"]
TERMINAL_JOB_STATUSES = {"success", "failed", "rate_limited", "not_found", "skipped"}
QUEUE_KEY = "dadata:stream:manual-normal"
HIGH_PRIORITY_QUEUE_KEY = "dadata:stream:manual-high"
LOW_PRIORITY_QUEUE_KEY = "dadata:stream:full-refresh-low"
STREAM_GROUP = "dadata-workers"
STREAM_CONSUMER = f"worker-{uuid.uuid4().hex}"
ACTIVE_JOBS_KEY = "dadata:jobs:active"
SCHEDULED_JOBS_KEY = "dadata:jobs:scheduled"
JOB_KEY_PREFIX = "dadata:job:"
FULL_REFRESH_PROGRESS_PREFIX = "dadata:full-refresh:progress:"
JOB_LEASE_SECONDS = 120

_HEARTBEAT_JOB_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local job = cjson.decode(raw)
if job.status ~= 'running' then return 0 end
if job.claim_token ~= ARGV[3] then return 0 end
return redis.call('ZADD', KEYS[2], ARGV[1], ARGV[2])
"""

_FINISH_JOB_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local job = cjson.decode(raw)
if job.status ~= 'running' or job.claim_token ~= ARGV[2] then return 0 end

job.status = ARGV[3]
job.result = cjson.decode(ARGV[4])
job.message = cjson.decode(ARGV[5])
job.updated_at = tonumber(ARGV[6])
job.claim_token = nil
redis.call('SET', KEYS[1], cjson.encode(job), 'EX', ARGV[7])
redis.call('ZREM', KEYS[2], ARGV[1])
if type(job.stream_key) == 'string' and type(job.stream_entry_id) == 'string' then
    redis.call('XACK', job.stream_key, ARGV[8], job.stream_entry_id)
end

if type(job.payload) == 'table' and job.payload.parent_job_id then
    local progress_key = ARGV[9] .. tostring(job.payload.parent_job_id)
    local progress_weight = tonumber(job.payload.progress_weight) or 1
    if progress_weight < 1 then progress_weight = 1 end
    redis.call('HINCRBY', progress_key, 'processed', progress_weight)
    redis.call('HINCRBY', progress_key, 'status:' .. ARGV[3], progress_weight)
    redis.call('EXPIRE', progress_key, ARGV[7])
end
if type(job.active_user_key) == 'string' and job.active_user_key ~= '' then
    redis.call('ZREM', job.active_user_key, ARGV[1])
end
if type(job.dedupe_key) == 'string' then
    local dedupe_key = ARGV[10] .. job.dedupe_key
    if redis.call('GET', dedupe_key) == ARGV[1] then
        redis.call('DEL', dedupe_key)
    end
end
return 1
"""

_RECOVER_JOB_SCRIPT = """
local claimed_stream = ARGV[5]
local claimed_entry = ARGV[6]
local function acknowledge_claimed_entry()
    if claimed_stream ~= '' and claimed_entry ~= '' then
        redis.call('XACK', claimed_stream, ARGV[4], claimed_entry)
    end
end

local raw = redis.call('GET', KEYS[1])
if not raw then
    redis.call('ZREM', KEYS[2], ARGV[1])
    acknowledge_claimed_entry()
    return 0
end

local job = cjson.decode(raw)
if job.status == 'success'
    or job.status == 'failed'
    or job.status == 'rate_limited'
    or job.status == 'not_found'
    or job.status == 'skipped' then
    redis.call('ZREM', KEYS[2], ARGV[1])
    acknowledge_claimed_entry()
    return 0
end

local lease = redis.call('ZSCORE', KEYS[2], ARGV[1])
if job.status == 'running' and lease and tonumber(lease) > tonumber(ARGV[2]) then
    return 0
end
if claimed_stream == '' and job.status ~= 'running' then
    redis.call('ZREM', KEYS[2], ARGV[1])
    return 0
end

local source_stream = claimed_stream
local source_entry = claimed_entry
if source_stream == '' and type(job.stream_key) == 'string' then
    source_stream = job.stream_key
end
if source_entry == '' and type(job.stream_entry_id) == 'string' then
    source_entry = job.stream_entry_id
end
if claimed_stream ~= '' then
    job.stream_key = claimed_stream
    job.stream_entry_id = claimed_entry
end

job.status = 'queued'
job.message = ARGV[3]
job.updated_at = tonumber(ARGV[2])
job.claim_token = nil
redis.call('SET', KEYS[1], cjson.encode(job), 'EX', ARGV[8])
redis.call('ZREM', KEYS[2], ARGV[1])
if source_stream ~= '' and source_entry ~= '' then
    redis.call('XACK', source_stream, ARGV[4], source_entry)
end
local queue_key = job.queue_key
if type(queue_key) ~= 'string' or queue_key == '' then
    queue_key = ARGV[7]
end
redis.call('XADD', queue_key, '*', 'job_id', ARGV[1])
return 1
"""


class DadataRuntimeError(RuntimeError):
    """Raised when Redis-backed Dadata coordination is unavailable."""


class DadataQueueLimitError(DadataRuntimeError):
    """Raised when a user already has too many active manual jobs."""


@dataclass(slots=True)
class FullRefreshLease:
    """Lease returned to the full-refresh parent while its Redis lock is renewed."""

    renewal_task: asyncio.Task[None]

    async def ensure_active(self) -> None:
        """Fail promptly if the background renewal has lost the lock."""
        if self.renewal_task.done() and not self.renewal_task.cancelled():
            await self.renewal_task


RedisErrorType: Any = ImportedRedisError
_redis_client = None
_redis_client_loop = None
_memory_daily_count = 0
_memory_daily_key = ""
_memory_rps_timestamps: list[float] = []


async def _reserve_daily_request_in_database(*, keep_reserve: bool) -> bool:
    """Persist the daily budget independently of Redis availability."""
    today = datetime.now(timezone.utc).date()
    limit = settings.DADATA_DAILY_REQUEST_LIMIT - (
        settings.DADATA_DAILY_REQUEST_RESERVE if keep_reserve else 0
    )
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                text(
                    "INSERT INTO dadata_usage (usage_date, requests_count, updated_at) "
                    "VALUES (:usage_date, 1, UTC_TIMESTAMP()) "
                    "ON DUPLICATE KEY UPDATE "
                    "updated_at = IF(requests_count < :request_limit, UTC_TIMESTAMP(), updated_at), "
                    "requests_count = IF(requests_count < :request_limit, requests_count + 1, "
                    "requests_count)"
                ),
                {"usage_date": today, "request_limit": limit},
            )
            reserved = bool(getattr(result, "rowcount", 0))
            await session.commit()

            # Storage remains bounded even though the counter must survive Redis restarts.
            await session.execute(
                text(
                    "DELETE FROM dadata_usage WHERE usage_date < DATE_SUB(UTC_DATE(), INTERVAL 90 DAY)"
                )
            )
            await session.commit()
            return reserved
    except Exception as error:
        raise DadataRuntimeError("Не удалось зарезервировать дневной лимит Dadata в БД.") from error


async def wait_for_fallback_rps_slot() -> None:
    """A conservative global limiter for direct calls when Redis is unavailable."""
    lock_name = "dadata:fallback-rps"
    try:
        async with async_session_maker() as session:
            acquired = await session.scalar(
                text("SELECT GET_LOCK(:lock_name, 10)"), {"lock_name": lock_name}
            )
            if not acquired:
                raise DadataRuntimeError("Не удалось получить limiter Dadata без Redis.")
            try:
                await asyncio.sleep(1 / settings.DADATA_FALLBACK_REQUESTS_PER_SECOND)
            finally:
                await session.execute(
                    text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name}
                )
    except DadataRuntimeError:
        raise
    except Exception as error:
        raise DadataRuntimeError("Fallback limiter Dadata в БД недоступен.") from error


def _utc_day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _seconds_until_next_utc_day() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).date()
    next_midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc)
    return max(1, int((next_midnight - now).total_seconds()))


async def get_redis_client():
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
        )
        _redis_client_loop = current_loop
    return _redis_client


async def require_redis_client():
    redis = await get_redis_client()
    if redis is None:
        raise DadataRuntimeError("Для задач Dadata требуется настроенный Redis.")
    try:
        await redis.ping()
    except RedisErrorType as error:
        raise DadataRuntimeError("Redis для задач Dadata недоступен.") from error
    return redis


async def close_dadata_runtime() -> None:
    global _redis_client, _redis_client_loop
    if _redis_client is None:
        return
    close_method = getattr(_redis_client, "aclose", None)
    if close_method is not None:
        with suppress(RuntimeError, RedisErrorType):
            await close_method()
    _redis_client = None
    _redis_client_loop = None


async def record_metric(name: str) -> None:
    redis = await get_redis_client()
    if redis is None:
        return
    key = f"dadata:metrics:{_utc_day_key()}"
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.hincrby(key, name, 1)
            pipe.expire(key, 60 * 60 * 24 * 32)
            await pipe.execute()
    except RedisErrorType:
        return


async def enqueue_job(
    *,
    kind: JobKind,
    payload: dict[str, Any],
    dedupe_key: str,
    origin: JobOrigin = "manual",
) -> tuple[dict[str, Any], bool]:
    redis = await require_redis_client()
    job_id = uuid.uuid4().hex
    now = time.time()
    queue_key = (
        HIGH_PRIORITY_QUEUE_KEY
        if kind == "lookup"
        else LOW_PRIORITY_QUEUE_KEY if kind in {"refresh_all", "refresh_all_item"} else QUEUE_KEY
    )
    job = {
        "job_id": job_id,
        "kind": kind,
        "origin": origin,
        "status": "queued",
        "payload": payload,
        "dedupe_key": dedupe_key,
        "result": None,
        "message": None,
        "created_at": now,
        "updated_at": now,
        "queue_key": queue_key,
    }
    user_id = payload.get("created_by_user_id") if kind in {"lookup", "refresh_one"} else None
    if user_id is not None:
        job["subscriber_user_ids"] = [user_id]
    active_user_key = f"dadata:active-user:{user_id}" if user_id is not None else ""
    job["active_user_key"] = active_user_key or None
    script = """
    local existing = redis.call('GET', KEYS[1])
    if existing then
        local existing_job = redis.call('GET', ARGV[1] .. existing)
        if existing_job then
            local subscriber_id = ARGV[7]
            if subscriber_id ~= '' then
                local existing_payload = cjson.decode(existing_job)
                local subscribers = existing_payload.subscriber_user_ids
                if type(subscribers) ~= 'table' then subscribers = {} end
                local already_subscribed = false
                for _, current_id in ipairs(subscribers) do
                    if tostring(current_id) == subscriber_id then
                        already_subscribed = true
                        break
                    end
                end
                if not already_subscribed then
                    table.insert(subscribers, tonumber(subscriber_id))
                    existing_payload.subscriber_user_ids = subscribers
                    redis.call('SET', ARGV[1] .. existing, cjson.encode(existing_payload), 'EX', ARGV[3])
                end
            end
            return {existing, '0'}
        end
        redis.call('DEL', KEYS[1])
    end
    if KEYS[4] ~= '' then
        redis.call('ZREMRANGEBYSCORE', KEYS[4], 0, ARGV[5])
        if redis.call('ZCARD', KEYS[4]) >= tonumber(ARGV[6]) then return {'', '-1'} end
    end
    redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
    redis.call('SET', KEYS[1], ARGV[4], 'EX', ARGV[3])
    redis.call('XADD', KEYS[3], '*', 'job_id', ARGV[4])
    if KEYS[4] ~= '' then
        redis.call('ZADD', KEYS[4], ARGV[5] + ARGV[3], ARGV[4])
        redis.call('EXPIRE', KEYS[4], ARGV[3])
    end
    return {ARGV[4], '1'}
    """
    try:
        response = await redis.eval(
            script,
            4,
            f"dadata:dedupe:{dedupe_key}",
            f"{JOB_KEY_PREFIX}{job_id}",
            queue_key,
            active_user_key,
            JOB_KEY_PREFIX,
            json.dumps(job, ensure_ascii=False),
            settings.DADATA_JOB_STATUS_TTL_SECONDS,
            job_id,
            now,
            settings.DADATA_MAX_ACTIVE_MANUAL_JOBS_PER_USER,
            str(user_id) if user_id is not None else "",
        )
        resolved_id = str(response[0])
        if str(response[1]) == "-1":
            raise DadataQueueLimitError(
                "Слишком много активных задач синхронизации. Дождитесь завершения предыдущих."
            )
        created = str(response[1]) == "1"
        resolved = job if created else await get_job(resolved_id)
        if resolved is None:
            raise DadataRuntimeError("Не удалось создать задачу Dadata.")
        if created:
            await record_metric("jobs_queued")
        return resolved, created
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось поставить задачу Dadata в очередь.") from error


async def get_job(job_id: str) -> dict[str, Any] | None:
    redis = await require_redis_client()
    try:
        raw = await redis.get(f"{JOB_KEY_PREFIX}{job_id}")
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось получить состояние задачи Dadata.") from error
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


async def _save_job(job: dict[str, Any]) -> None:
    redis = await require_redis_client()
    job_id = str(job["job_id"])
    job["updated_at"] = time.time()
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(
                f"{JOB_KEY_PREFIX}{job_id}",
                json.dumps(job, ensure_ascii=False),
                ex=settings.DADATA_JOB_STATUS_TTL_SECONDS,
            )
            await pipe.execute()
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось сохранить состояние задачи Dadata.") from error


async def initialize_full_refresh_progress(parent_job_id: str, *, total: int) -> None:
    redis = await require_redis_client()
    key = f"{FULL_REFRESH_PROGRESS_PREFIX}{parent_job_id}"
    try:
        await redis.hset(key, mapping={"total": total, "processed": 0})
        await redis.expire(key, settings.DADATA_JOB_STATUS_TTL_SECONDS)
    except RedisErrorType as error:
        raise DadataRuntimeError(
            "Не удалось инициализировать прогресс полного обновления."
        ) from error


async def get_full_refresh_progress(parent_job_id: str) -> dict[str, int]:
    redis = await require_redis_client()
    try:
        values = await redis.hgetall(f"{FULL_REFRESH_PROGRESS_PREFIX}{parent_job_id}")
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось прочитать прогресс полного обновления.") from error
    return {str(key): int(value) for key, value in values.items()}


async def claim_next_job(*, timeout_seconds: int = 5) -> dict[str, Any] | None:  # noqa: C901
    redis = await require_redis_client()
    deadline = time.monotonic() + max(timeout_seconds, 1)
    try:
        for queue_key in (HIGH_PRIORITY_QUEUE_KEY, QUEUE_KEY, LOW_PRIORITY_QUEUE_KEY):
            try:
                await redis.xgroup_create(queue_key, STREAM_GROUP, id="0", mkstream=True)
            except RedisErrorType as error:
                if "BUSYGROUP" not in str(error):
                    raise
        while time.monotonic() < deadline:
            for queue_key in (HIGH_PRIORITY_QUEUE_KEY, QUEUE_KEY, LOW_PRIORITY_QUEUE_KEY):
                entries = await redis.xreadgroup(
                    STREAM_GROUP,
                    STREAM_CONSUMER,
                    {queue_key: ">"},
                    count=1,
                    block=1,
                )
                if entries:
                    _, records = entries[0]
                    entry_id, fields = records[0]
                    job_id = str(fields.get("job_id", ""))
                    if not job_id:
                        await redis.xack(queue_key, STREAM_GROUP, entry_id)
                        continue
                    break
            else:
                await asyncio.sleep(0.05)
                continue
            break
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось получить задачу Dadata из очереди.") from error
    if "job_id" not in locals():
        return None
    now = time.time()
    claim_token = uuid.uuid4().hex
    claim_script = """
    local raw = redis.call('GET', KEYS[1])
    if not raw then return nil end
    local job = cjson.decode(raw)
    if job.status ~= 'queued' then return nil end
    job.status = 'running'
    job.updated_at = tonumber(ARGV[1])
    job.claim_token = ARGV[5]
    local encoded = cjson.encode(job)
    redis.call('SET', KEYS[1], encoded, 'EX', ARGV[2])
    redis.call('ZADD', KEYS[2], ARGV[3], ARGV[4])
    return encoded
    """
    try:
        raw = await redis.eval(
            claim_script,
            2,
            f"{JOB_KEY_PREFIX}{job_id}",
            ACTIVE_JOBS_KEY,
            now,
            settings.DADATA_JOB_STATUS_TTL_SECONDS,
            now + JOB_LEASE_SECONDS,
            job_id,
            claim_token,
        )
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось захватить задачу Dadata.") from error
    if not raw:
        await redis.xack(queue_key, STREAM_GROUP, entry_id)
        return None
    try:
        job = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        await redis.xack(queue_key, STREAM_GROUP, entry_id)
        return None
    job["stream_key"] = queue_key
    job["stream_entry_id"] = str(entry_id)
    await _save_job(job)
    await record_metric("jobs_running")
    return job


async def heartbeat_job(job_id: str, *, claim_token: str) -> None:
    redis = await require_redis_client()
    try:
        await redis.eval(
            _HEARTBEAT_JOB_SCRIPT,
            2,
            f"{JOB_KEY_PREFIX}{job_id}",
            ACTIVE_JOBS_KEY,
            time.time() + JOB_LEASE_SECONDS,
            job_id,
            claim_token,
        )
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось продлить задачу Dadata.") from error


async def finish_job(
    job_id: str,
    *,
    claim_token: str,
    status: str,
    result: dict[str, Any] | None = None,
    message: str | None = None,
) -> bool:
    if status not in TERMINAL_JOB_STATUSES:
        raise ValueError("Завершить задачу можно только с terminal-статусом.")
    redis = await require_redis_client()
    try:
        finished = await redis.eval(
            _FINISH_JOB_SCRIPT,
            2,
            f"{JOB_KEY_PREFIX}{job_id}",
            ACTIVE_JOBS_KEY,
            job_id,
            claim_token,
            status,
            json.dumps(result, ensure_ascii=False),
            json.dumps(message, ensure_ascii=False),
            time.time(),
            settings.DADATA_JOB_STATUS_TTL_SECONDS,
            STREAM_GROUP,
            FULL_REFRESH_PROGRESS_PREFIX,
            "dadata:dedupe:",
        )
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось завершить задачу Dadata.") from error
    if not finished:
        return False
    await record_metric(f"jobs_{status}")
    return True


async def requeue_job(
    job_id: str,
    *,
    message: str | None = None,
    stream_key: str | None = None,
    stream_entry_id: str | None = None,
    delay_seconds: float = 0,
    retry_count: int | None = None,
) -> None:
    redis = await require_redis_client()
    job = await get_job(job_id)
    if job is None:
        return
    if stream_key is not None:
        job["stream_key"] = stream_key
    if stream_entry_id is not None:
        job["stream_entry_id"] = stream_entry_id
    if retry_count is not None:
        job["retry_count"] = retry_count
    job.pop("claim_token", None)
    job["status"] = "queued"
    job["message"] = message
    await _save_job(job)
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.zrem(ACTIVE_JOBS_KEY, job_id)
            if job.get("stream_key") and job.get("stream_entry_id"):
                pipe.xack(job["stream_key"], STREAM_GROUP, job["stream_entry_id"])
            if delay_seconds > 0:
                pipe.zadd(SCHEDULED_JOBS_KEY, {job_id: time.time() + delay_seconds})
            else:
                pipe.xadd(job.get("queue_key", QUEUE_KEY), {"job_id": job_id})
            await pipe.execute()
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось вернуть задачу Dadata в очередь.") from error


async def promote_scheduled_jobs(*, limit: int = 100) -> int:
    """Move due retry jobs back to their priority stream exactly once."""
    redis = await require_redis_client()
    try:
        job_ids = await redis.zrangebyscore(SCHEDULED_JOBS_KEY, 0, time.time(), start=0, num=limit)
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось прочитать отложенные задачи Dadata.") from error
    promoted = 0
    for job_id in job_ids:
        if not await redis.zrem(SCHEDULED_JOBS_KEY, job_id):
            continue
        job = await get_job(str(job_id))
        if job is None or job.get("status") != "queued":
            continue
        try:
            await redis.xadd(job.get("queue_key", QUEUE_KEY), {"job_id": str(job_id)})
        except RedisErrorType as error:
            await redis.zadd(SCHEDULED_JOBS_KEY, {str(job_id): time.time() + 1})
            raise DadataRuntimeError("Не удалось вернуть отложенную задачу в stream.") from error
        promoted += 1
    return promoted


async def _recover_job_if_lease_expired(
    redis,
    job_id: str,
    *,
    claimed_stream: str = "",
    claimed_entry: str = "",
) -> bool:
    try:
        recovered = await redis.eval(
            _RECOVER_JOB_SCRIPT,
            2,
            f"{JOB_KEY_PREFIX}{job_id}",
            ACTIVE_JOBS_KEY,
            job_id,
            time.time(),
            "Задача восстановлена после остановки worker-а.",
            STREAM_GROUP,
            claimed_stream,
            claimed_entry,
            QUEUE_KEY,
            settings.DADATA_JOB_STATUS_TTL_SECONDS,
        )
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось восстановить задачу Dadata.") from error
    return bool(recovered)


async def recover_stale_jobs() -> int:
    redis = await require_redis_client()
    try:
        stale_ids = await redis.zrangebyscore(ACTIVE_JOBS_KEY, 0, time.time())
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось проверить зависшие задачи Dadata.") from error
    recovered = 0
    for stream_key in (HIGH_PRIORITY_QUEUE_KEY, QUEUE_KEY, LOW_PRIORITY_QUEUE_KEY):
        try:
            claim_result = await redis.xautoclaim(
                stream_key,
                STREAM_GROUP,
                STREAM_CONSUMER,
                min_idle_time=JOB_LEASE_SECONDS * 1000,
                start_id="0-0",
                count=100,
            )
        except RedisErrorType as error:
            if "NOGROUP" in str(error):
                continue
            raise DadataRuntimeError("Не удалось восстановить pending задачи Dadata.") from error
        entries = claim_result[1] if isinstance(claim_result, (tuple, list)) else []
        for entry_id, fields in entries:
            job_id = str(fields.get("job_id", ""))
            if not job_id:
                await redis.xack(stream_key, STREAM_GROUP, entry_id)
                continue
            if await _recover_job_if_lease_expired(
                redis,
                job_id,
                claimed_stream=stream_key,
                claimed_entry=str(entry_id),
            ):
                recovered += 1
    for job_id in stale_ids:
        if await _recover_job_if_lease_expired(redis, str(job_id)):
            recovered += 1
    return recovered


async def get_daily_request_count() -> int:
    today = datetime.now(timezone.utc).date()
    try:
        async with async_session_maker() as session:
            value = await session.scalar(
                text("SELECT requests_count FROM dadata_usage WHERE usage_date = :usage_date"),
                {"usage_date": today},
            )
            return int(value or 0)
    except Exception as error:
        raise DadataRuntimeError("Не удалось прочитать дневной лимит Dadata из БД.") from error


async def reserve_daily_request(*, keep_reserve: bool = False) -> bool:
    return await _reserve_daily_request_in_database(keep_reserve=keep_reserve)


async def _wait_for_sliding_window_slot(*, key: str, limit: int, window_ms: int) -> None:
    redis = await get_redis_client()
    if redis is None:
        if settings.is_production_like:
            raise DadataRuntimeError("Redis обязателен для лимитов Dadata.")
        return
    script = """
    redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1] - ARGV[2])
    local count = redis.call('ZCARD', KEYS[1])
    if count < tonumber(ARGV[3]) then
        redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
        redis.call('PEXPIRE', KEYS[1], ARGV[2] + 1000)
        return 1
    end
    return 0
    """
    while True:
        now_ms = int(time.time() * 1000)
        try:
            acquired = await redis.eval(
                script,
                1,
                key,
                now_ms,
                window_ms,
                max(limit, 1),
                f"{now_ms}:{uuid.uuid4().hex}",
            )
        except RedisErrorType as error:
            raise DadataRuntimeError("Redis limiter Dadata недоступен.") from error
        if acquired:
            return
        await asyncio.sleep(min(0.1, window_ms / 1000 / max(limit, 1)))


async def wait_for_rps_slot() -> None:
    if await get_redis_client() is not None or settings.is_production_like:
        await _wait_for_sliding_window_slot(
            key="dadata:rps",
            limit=settings.DADATA_MAX_REQUESTS_PER_SECOND,
            window_ms=1000,
        )
        return
    while True:
        now = time.monotonic()
        _memory_rps_timestamps[:] = [
            timestamp for timestamp in _memory_rps_timestamps if now - timestamp < 1
        ]
        if len(_memory_rps_timestamps) < settings.DADATA_MAX_REQUESTS_PER_SECOND:
            _memory_rps_timestamps.append(now)
            return
        await asyncio.sleep(0.05)


async def wait_for_full_refresh_rps_slot() -> None:
    """Reserve the portion of global Dadata capacity assigned to bulk work."""
    if await get_redis_client() is None:
        return
    await _wait_for_sliding_window_slot(
        key="dadata:full-refresh-rps",
        limit=settings.DADATA_FULL_REFRESH_REQUESTS_PER_SECOND,
        window_ms=1000,
    )


async def wait_for_new_connection_slot() -> None:
    await _wait_for_sliding_window_slot(
        key="dadata:new-connections",
        limit=settings.DADATA_MAX_NEW_CONNECTIONS_PER_MINUTE,
        window_ms=60_000,
    )


@asynccontextmanager
async def full_refresh_lock(*, manual: bool) -> AsyncIterator[FullRefreshLease | None]:
    redis = await require_redis_client()
    today = _utc_day_key()
    count_key = f"dadata:full-refresh-count:{today}"
    last_origin_key = f"dadata:full-refresh-last-origin:{today}"
    lock_key = "dadata:full-refresh-lock"
    token = uuid.uuid4().hex
    script = """
    if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
    local count = tonumber(redis.call('GET', KEYS[2]) or '0')
    local allow_override = ARGV[3] == '1'
        and redis.call('GET', KEYS[3]) == 'scheduled'
    if count >= tonumber(ARGV[2]) and not allow_override then return 0 end
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[4])
    return 1
    """
    try:
        acquired = await redis.eval(
            script,
            3,
            lock_key,
            count_key,
            last_origin_key,
            token,
            settings.DADATA_FULL_REFRESH_DAILY_LIMIT,
            ("1" if manual and settings.DADATA_ALLOW_MANUAL_FULL_REFRESH_AFTER_SCHEDULED else "0"),
            settings.DADATA_FULL_REFRESH_LOCK_TTL_SECONDS,
        )
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось захватить блокировку полного обновления.") from error
    if not acquired:
        yield None
        return

    async def renew_lock() -> None:
        renew_script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('EXPIRE', KEYS[1], ARGV[2])
        end
        return 0
        """
        while True:
            await asyncio.sleep(max(20, settings.DADATA_FULL_REFRESH_LOCK_TTL_SECONDS // 3))
            renewed = await redis.eval(
                renew_script,
                1,
                lock_key,
                token,
                settings.DADATA_FULL_REFRESH_LOCK_TTL_SECONDS,
            )
            if not renewed:
                raise DadataRuntimeError("Потеряна блокировка полного обновления.")

    renewal_task = asyncio.create_task(renew_lock())
    lease = FullRefreshLease(renewal_task=renewal_task)
    try:
        yield lease
    finally:
        renewal_error: BaseException | None = None
        if renewal_task.done() and not renewal_task.cancelled():
            try:
                await renewal_task
            except BaseException as error:
                renewal_error = error
        renewal_task.cancel()
        with suppress(asyncio.CancelledError, RedisErrorType):
            await renewal_task
        release_script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        with suppress(RedisErrorType):
            await redis.eval(release_script, 1, lock_key, token)
        if renewal_error is not None:
            raise renewal_error


async def mark_full_refresh_done(*, origin: JobOrigin) -> None:
    redis = await require_redis_client()
    today = _utc_day_key()
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(f"dadata:full-refresh-count:{today}")
            pipe.expire(
                f"dadata:full-refresh-count:{today}",
                _seconds_until_next_utc_day(),
            )
            pipe.set(
                f"dadata:full-refresh-last-origin:{today}",
                origin,
                ex=_seconds_until_next_utc_day(),
            )
            await pipe.execute()
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось зафиксировать полный прогон Dadata.") from error


async def get_last_full_refresh_timestamp() -> float | None:
    redis = await require_redis_client()
    try:
        value = await redis.get("dadata:last-full-refresh-at")
        return float(value) if value else None
    except (RedisErrorType, ValueError) as error:
        raise DadataRuntimeError("Не удалось прочитать расписание Dadata.") from error


async def mark_last_full_refresh_now() -> None:
    redis = await require_redis_client()
    try:
        await redis.set("dadata:last-full-refresh-at", str(time.time()))
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось обновить расписание Dadata.") from error


async def initialize_full_refresh_schedule() -> None:
    redis = await require_redis_client()
    try:
        await redis.set("dadata:last-full-refresh-at", str(time.time()), nx=True)
    except RedisErrorType as error:
        raise DadataRuntimeError("Не удалось инициализировать расписание Dadata.") from error

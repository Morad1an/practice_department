import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from src.app.config import settings
from src.app.database import async_session_maker, engine
from src.app.services.dadata.runtime import (
    _reserve_daily_request_in_database,
    enqueue_job,
    promote_scheduled_jobs,
    recover_stale_jobs,
    wait_for_full_refresh_rps_slot,
    wait_for_rps_slot,
)


class _FakePipeline:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def hincrby(self, *args):
        return self

    def expire(self, *args):
        return self

    async def execute(self):
        return []


class _FakeRedis:
    def __init__(self):
        self.scripts: list[str] = []

    async def eval(self, script, numkeys, *args):
        del numkeys
        self.scripts.append(script)
        if "XADD" in script:
            return [args[-1], "1"]
        return 1

    def pipeline(self, *, transaction=True):
        del transaction
        return _FakePipeline()


def test_enqueue_job_creates_redis_backed_status_and_dedupe():
    redis = _FakeRedis()
    with (
        patch(
            "src.app.services.dadata.runtime.require_redis_client",
            new=AsyncMock(return_value=redis),
        ),
        patch(
            "src.app.services.dadata.runtime.get_redis_client",
            new=AsyncMock(return_value=redis),
        ),
    ):
        job, created = asyncio.run(
            enqueue_job(
                kind="lookup",
                payload={"inn": "7719402047"},
                dedupe_key="inn:7719402047",
            )
        )

    assert created is True
    assert job["status"] == "queued"
    assert job["kind"] == "lookup"
    assert any("dadata:dedupe" not in script and "XADD" in script for script in redis.scripts)


def test_rps_check_and_reservation_are_atomic_in_one_script():
    redis = _FakeRedis()
    with patch(
        "src.app.services.dadata.runtime.get_redis_client",
        new=AsyncMock(return_value=redis),
    ):
        asyncio.run(wait_for_rps_slot())

    limiter_script = redis.scripts[-1]
    assert "ZCARD" in limiter_script
    assert "ZADD" in limiter_script


def test_recovery_reclaims_pending_stream_entry_after_worker_failure():
    class RecoveryRedis:
        async def zrangebyscore(self, *args):
            return []

        async def xautoclaim(self, stream, *args, **kwargs):
            if stream.endswith("manual-high"):
                return ("0-0", [("1-0", {"job_id": "job-1"})], [])
            return ("0-0", [], [])

        async def xack(self, *args):
            return 1

    redis = RecoveryRedis()
    requeue_mock = AsyncMock()
    with (
        patch(
            "src.app.services.dadata.runtime.require_redis_client",
            new=AsyncMock(return_value=redis),
        ),
        patch(
            "src.app.services.dadata.runtime.get_job",
            new=AsyncMock(return_value={"job_id": "job-1", "status": "running"}),
        ),
        patch("src.app.services.dadata.runtime.requeue_job", requeue_mock),
    ):
        recovered = asyncio.run(recover_stale_jobs())

    assert recovered == 1
    requeue_mock.assert_awaited_once()
    assert requeue_mock.await_args.kwargs["stream_entry_id"] == "1-0"


def test_due_retry_is_promoted_back_to_its_priority_stream_once():
    class ScheduledRedis:
        def __init__(self):
            self.added = []

        async def zrangebyscore(self, *args, **kwargs):
            return ["job-1"]

        async def zrem(self, *args):
            return 1

        async def xadd(self, stream, fields):
            self.added.append((stream, fields))

    redis = ScheduledRedis()
    with (
        patch(
            "src.app.services.dadata.runtime.require_redis_client",
            new=AsyncMock(return_value=redis),
        ),
        patch(
            "src.app.services.dadata.runtime.get_job",
            new=AsyncMock(return_value={"status": "queued", "queue_key": "manual-high"}),
        ),
    ):
        promoted = asyncio.run(promote_scheduled_jobs())

    assert promoted == 1
    assert redis.added == [("manual-high", {"job_id": "job-1"})]


def test_bulk_and_global_limiters_reserve_five_requests_per_second_for_manual_jobs():
    redis = _FakeRedis()
    with patch(
        "src.app.services.dadata.runtime.get_redis_client",
        new=AsyncMock(return_value=redis),
    ):
        asyncio.run(wait_for_full_refresh_rps_slot())
        asyncio.run(wait_for_rps_slot())

    limiter_calls = [script for script in redis.scripts if "ZCARD" in script]
    assert len(limiter_calls) == 2
    assert (
        settings.DADATA_MAX_REQUESTS_PER_SECOND - settings.DADATA_FULL_REFRESH_REQUESTS_PER_SECOND
        == 5
    )


def test_mysql_daily_counter_is_atomic_for_parallel_web_requests():
    """Separate sessions emulate concurrent requests from different web processes."""
    usage_date = datetime(2099, 1, 1, tzinfo=timezone.utc).date()

    class _FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            del tz
            return datetime(2099, 1, 1, tzinfo=timezone.utc)

    async def reserve_in_parallel_and_check_cap():
        try:
            with patch("src.app.services.dadata.runtime.datetime", _FixedDatetime):
                reservations = await asyncio.gather(
                    *(_reserve_daily_request_in_database(keep_reserve=False) for _ in range(10))
                )

            async with async_session_maker() as session:
                requests_count = await session.scalar(
                    text(
                        "SELECT requests_count FROM dadata_usage " "WHERE usage_date = :usage_date"
                    ),
                    {"usage_date": usage_date},
                )
                await session.execute(
                    text("DELETE FROM dadata_usage WHERE usage_date = :usage_date"),
                    {"usage_date": usage_date},
                )
                await session.commit()
            with (
                patch("src.app.services.dadata.runtime.datetime", _FixedDatetime),
                patch.object(settings, "DADATA_DAILY_REQUEST_LIMIT", 2),
                patch.object(settings, "DADATA_DAILY_REQUEST_RESERVE", 0),
            ):
                capped_reservations = [
                    await _reserve_daily_request_in_database(keep_reserve=False) for _ in range(3)
                ]
            return reservations, requests_count, capped_reservations
        finally:
            async with async_session_maker() as session:
                await session.execute(
                    text("DELETE FROM dadata_usage WHERE usage_date = :usage_date"),
                    {"usage_date": usage_date},
                )
                await session.commit()
            await engine.dispose()

    reservations, requests_count, capped_reservations = asyncio.run(
        reserve_in_parallel_and_check_cap()
    )

    assert all(reservations)
    assert requests_count == 10
    assert capped_reservations == [True, True, False]

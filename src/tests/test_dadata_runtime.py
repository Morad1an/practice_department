import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from src.app.config import settings
from src.app.database import async_session_maker, engine
from src.app.services.dadata.runtime import (
    _reserve_daily_request_in_database,
    enqueue_job,
    finish_job,
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


class _FinishRedis:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.scripts = []

    async def eval(self, script, numkeys, *args):
        del numkeys, args
        self.scripts.append(script)
        return self.outcomes.pop(0)


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


def test_enqueue_job_adds_second_manual_requester_to_an_existing_job():
    redis = _FakeRedis()
    existing_job = {
        "job_id": "existing-job",
        "kind": "lookup",
        "status": "queued",
        "payload": {"created_by_user_id": 1},
        "subscriber_user_ids": [1],
    }
    redis.eval = AsyncMock(return_value=["existing-job", "0"])
    with (
        patch(
            "src.app.services.dadata.runtime.require_redis_client",
            new=AsyncMock(return_value=redis),
        ),
        patch(
            "src.app.services.dadata.runtime.get_job",
            new=AsyncMock(return_value=existing_job),
        ),
    ):
        job, created = asyncio.run(
            enqueue_job(
                kind="lookup",
                payload={"inn": "7719402047", "created_by_user_id": 2},
                dedupe_key="inn:7719402047",
            )
        )

    assert created is False
    assert job == existing_job
    script = redis.eval.await_args.args[0]
    assert "subscriber_user_ids" in script
    assert redis.eval.await_args.args[-1] == "2"


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


def test_finish_job_counts_repeated_terminal_result_once():
    redis = _FinishRedis([1, 0])
    metric_mock = AsyncMock()

    async def finish_twice():
        with (
            patch(
                "src.app.services.dadata.runtime.require_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch("src.app.services.dadata.runtime.record_metric", metric_mock),
        ):
            first = await finish_job("child-1", status="success", claim_token="attempt-1")
            second = await finish_job("child-1", status="success", claim_token="attempt-1")
        return first, second

    assert asyncio.run(finish_twice()) == (True, False)
    metric_mock.assert_awaited_once_with("jobs_success")
    assert all("claim_token" in script and "HINCRBY" in script for script in redis.scripts)


def test_finish_job_keeps_first_terminal_result_from_competing_attempts():
    redis = _FinishRedis([1, 0])
    metric_mock = AsyncMock()

    async def finish_with_different_results():
        with (
            patch(
                "src.app.services.dadata.runtime.require_redis_client",
                new=AsyncMock(return_value=redis),
            ),
            patch("src.app.services.dadata.runtime.record_metric", metric_mock),
        ):
            first = await finish_job("child-1", status="success", claim_token="attempt-1")
            second = await finish_job("child-1", status="failed", claim_token="attempt-2")
        return first, second

    assert asyncio.run(finish_with_different_results()) == (True, False)
    metric_mock.assert_awaited_once_with("jobs_success")


def test_recovery_reclaims_pending_stream_entry_after_worker_failure():
    class RecoveryRedis:
        def __init__(self):
            self.recovery_calls = []

        async def zrangebyscore(self, *args):
            return []

        async def xautoclaim(self, stream, *args, **kwargs):
            if stream.endswith("manual-high"):
                return ("0-0", [("1-0", {"job_id": "job-1"})], [])
            return ("0-0", [], [])

        async def xack(self, *args):
            return 1

        async def eval(self, script, numkeys, *args):
            del script, numkeys
            self.recovery_calls.append(args)
            return 1

    redis = RecoveryRedis()
    with patch(
        "src.app.services.dadata.runtime.require_redis_client",
        new=AsyncMock(return_value=redis),
    ):
        recovered = asyncio.run(recover_stale_jobs())

    assert recovered == 1
    assert len(redis.recovery_calls) == 1
    assert redis.recovery_calls[0][6].endswith("manual-high")
    assert redis.recovery_calls[0][7] == "1-0"


def test_recovery_keeps_pending_stream_entry_with_live_heartbeat_lease():
    class RecoveryRedis:
        def __init__(self):
            self.recovery_scripts = []

        async def zrangebyscore(self, *args):
            return []

        async def xautoclaim(self, stream, *args, **kwargs):
            if stream.endswith("manual-high"):
                return ("0-0", [("1-0", {"job_id": "job-1"})], [])
            return ("0-0", [], [])

        async def xack(self, *args):
            return 1

        async def eval(self, script, numkeys, *args):
            del numkeys, args
            self.recovery_scripts.append(script)
            return 0

    redis = RecoveryRedis()
    with patch(
        "src.app.services.dadata.runtime.require_redis_client",
        new=AsyncMock(return_value=redis),
    ):
        recovered = asyncio.run(recover_stale_jobs())

    assert recovered == 0
    assert len(redis.recovery_scripts) == 1
    assert "ZSCORE" in redis.recovery_scripts[0]


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

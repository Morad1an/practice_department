from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time
from contextlib import suppress
from typing import Any

from src.app.config import settings
from src.app.database import async_session_maker, engine
from src.app.services.dadata.client import close_dadata_client
from src.app.services.dadata.runtime import (
    DadataRuntimeError,
    claim_next_job,
    close_dadata_runtime,
    finish_job,
    get_last_full_refresh_timestamp,
    heartbeat_job,
    initialize_full_refresh_schedule,
    promote_scheduled_jobs,
    record_metric,
    recover_stale_jobs,
    requeue_job,
)
from src.app.services.dadata.sync import (
    lookup_organization_by_inn,
    queue_full_refresh,
    refresh_all_organizations_from_dadata,
    refresh_organization_from_dadata,
)

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process queued and scheduled Dadata organization jobs.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Check the schedule, drain the current queue and exit.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=3600,
        help="How often to check the monthly refresh schedule.",
    )
    return parser.parse_args()


async def _schedule_refresh_if_due() -> None:
    last_refresh_at = await get_last_full_refresh_timestamp()
    if last_refresh_at is None:
        if settings.DADATA_SCHEDULE_INITIAL_REFRESH:
            await queue_full_refresh(manual=False)
            logger.info("dadata_initial_full_refresh_queued")
        else:
            await initialize_full_refresh_schedule()
            logger.info("dadata_full_refresh_schedule_initialized")
        return
    interval_seconds = settings.DADATA_REFRESH_INTERVAL_DAYS * 24 * 60 * 60
    if time.time() - last_refresh_at < interval_seconds:
        return
    result = await queue_full_refresh(manual=False)
    logger.info(
        "dadata_scheduled_full_refresh_queue_result",
        extra={"status": result.status, "job_id": result.job_id},
    )


async def _heartbeat_loop(job_id: str) -> None:
    while True:
        await asyncio.sleep(30)
        await heartbeat_job(job_id)


def _terminal_status(result_status: str) -> str:
    if result_status in {"ready", "updated", "completed"}:
        return "success"
    if result_status in {"rate_limited", "not_found", "skipped"}:
        return result_status
    return "failed"


async def _execute_job(job: dict[str, Any]):
    payload = job.get("payload") or {}
    async with async_session_maker() as session:
        if job["kind"] == "lookup":
            return await lookup_organization_by_inn(
                session,
                inn=str(payload["inn"]),
                force_refresh=bool(payload.get("force_refresh", False)),
            )
        if job["kind"] in {"refresh_one", "refresh_all_item"}:
            return await refresh_organization_from_dadata(
                session,
                organization_id=int(payload["organization_id"]),
                inn=str(payload["inn"]),
                keep_daily_reserve=job["kind"] == "refresh_all_item",
            )
        if job["kind"] == "refresh_all":
            return await refresh_all_organizations_from_dadata(
                session,
                manual=bool(payload.get("manual", job.get("origin") == "manual")),
                parent_job_id=str(job["job_id"]),
            )
    raise ValueError("Неизвестный тип задачи Dadata.")


async def process_job(job: dict[str, Any]) -> None:
    job_id = str(job["job_id"])
    heartbeat_task = asyncio.create_task(_heartbeat_loop(job_id))
    try:
        if job["kind"] == "refresh_all":
            await record_metric("full_refresh_started")
        result = await _execute_job(job)
        if result.status == "rate_limited" and job["kind"] != "refresh_all":
            retries = int(job.get("retry_count", 0))
            if retries < settings.DADATA_MAX_RETRIES:
                await requeue_job(
                    job_id,
                    message="Ограничение Dadata; задача будет повторена автоматически.",
                    delay_seconds=max(
                        float(getattr(result, "retry_after_seconds", 0)),
                        min(60, 2 ** (retries + 1)),
                    ),
                    retry_count=retries + 1,
                )
                return
        result_payload = result.model_dump(mode="json")
        await finish_job(
            job_id,
            status=_terminal_status(result.status),
            result=result_payload,
            message=result.message,
        )
        if job["kind"] == "refresh_all":
            await record_metric(f"full_refresh_{_terminal_status(result.status)}")
        logger.info(
            "dadata_job_finished",
            extra={"job_id": job_id, "kind": job["kind"], "status": result.status},
        )
    except asyncio.CancelledError:
        with suppress(DadataRuntimeError):
            await requeue_job(job_id, message="Worker остановлен; задача возвращена в очередь.")
        raise
    except Exception as error:
        logger.exception(
            "dadata_job_failed",
            extra={"job_id": job_id, "kind": job.get("kind"), "error_type": type(error).__name__},
        )
        with suppress(DadataRuntimeError):
            if job.get("kind") == "refresh_all":
                await record_metric("full_refresh_failed")
            await finish_job(
                job_id,
                status="failed",
                message="Внутренняя ошибка обработки задачи Dadata.",
            )
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task


async def run_worker(*, once: bool, schedule_interval_seconds: int) -> None:
    next_schedule_check = 0.0
    next_recovery_check = 0.0
    full_refresh_tasks: set[asyncio.Task[None]] = set()

    def start_full_refresh(job: dict[str, Any]) -> None:
        task = asyncio.create_task(process_job(job))
        full_refresh_tasks.add(task)
        task.add_done_callback(full_refresh_tasks.discard)

    try:
        while True:
            now = time.monotonic()
            if now >= next_recovery_check:
                await promote_scheduled_jobs()
                recovered = await recover_stale_jobs()
                if recovered:
                    logger.warning("dadata_stale_jobs_recovered", extra={"count": recovered})
                next_recovery_check = now + 60
            if now >= next_schedule_check:
                await _schedule_refresh_if_due()
                next_schedule_check = now + max(schedule_interval_seconds, 60)

            job = await claim_next_job(timeout_seconds=1 if once else 5)
            if job is not None:
                # A full refresh internally uses bounded concurrency.  Running its
                # parent in the background keeps this single worker responsive to
                # high-priority lookup and one-organization jobs.
                if job["kind"] in {"refresh_all", "refresh_all_item"}:
                    if (
                        job["kind"] == "refresh_all_item"
                        and len(full_refresh_tasks) >= settings.DADATA_FULL_REFRESH_CONCURRENCY
                    ):
                        await asyncio.wait(full_refresh_tasks, return_when=asyncio.FIRST_COMPLETED)
                    start_full_refresh(job)
                else:
                    await process_job(job)
                continue
            if once:
                if full_refresh_tasks:
                    await asyncio.gather(*full_refresh_tasks)
                    continue
                return
    finally:
        for task in full_refresh_tasks:
            task.cancel()
        if full_refresh_tasks:
            await asyncio.gather(*full_refresh_tasks, return_exceptions=True)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signal_name, stop_event.set)

    worker_task = asyncio.create_task(
        run_worker(
            once=args.once,
            schedule_interval_seconds=args.interval_seconds,
        )
    )
    stop_task = asyncio.create_task(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            {worker_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done and not worker_task.done():
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
        else:
            await worker_task
    finally:
        stop_task.cancel()
        with suppress(asyncio.CancelledError):
            await stop_task
        await close_dadata_client()
        await close_dadata_runtime()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

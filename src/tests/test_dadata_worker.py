import asyncio
from unittest.mock import AsyncMock, patch

from src.app.config import settings
from src.app.scripts.dadata_worker import _schedule_refresh_if_due


def test_first_worker_start_initializes_schedule_without_mass_refresh():
    with (
        patch.object(settings, "DADATA_SCHEDULE_INITIAL_REFRESH", False),
        patch(
            "src.app.scripts.dadata_worker.get_last_full_refresh_timestamp",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.app.scripts.dadata_worker.initialize_full_refresh_schedule",
            new=AsyncMock(),
        ) as initialize_mock,
        patch("src.app.scripts.dadata_worker.queue_full_refresh", new=AsyncMock()) as queue_mock,
    ):
        asyncio.run(_schedule_refresh_if_due())

    initialize_mock.assert_awaited_once()
    queue_mock.assert_not_awaited()


def test_initial_mass_refresh_requires_explicit_setting():
    with (
        patch.object(settings, "DADATA_SCHEDULE_INITIAL_REFRESH", True),
        patch(
            "src.app.scripts.dadata_worker.get_last_full_refresh_timestamp",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.app.scripts.dadata_worker.initialize_full_refresh_schedule",
            new=AsyncMock(),
        ) as initialize_mock,
        patch("src.app.scripts.dadata_worker.queue_full_refresh", new=AsyncMock()) as queue_mock,
    ):
        asyncio.run(_schedule_refresh_if_due())

    queue_mock.assert_awaited_once_with(manual=False)
    initialize_mock.assert_not_awaited()


def test_scheduled_full_refresh_is_queued_after_configured_interval():
    interval_seconds = settings.DADATA_REFRESH_INTERVAL_DAYS * 24 * 60 * 60
    with (
        patch(
            "src.app.scripts.dadata_worker.get_last_full_refresh_timestamp",
            new=AsyncMock(return_value=1000.0),
        ),
        patch(
            "src.app.scripts.dadata_worker.time.time",
            return_value=1000.0 + interval_seconds + 1,
        ),
        patch("src.app.scripts.dadata_worker.queue_full_refresh", new=AsyncMock()) as queue_mock,
    ):
        asyncio.run(_schedule_refresh_if_due())

    queue_mock.assert_awaited_once_with(manual=False)

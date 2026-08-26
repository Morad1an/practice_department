import asyncio
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.models.organization import OrganizationOrm
from src.app.services.dadata.runtime import DadataRuntimeError
from src.app.services.dadata.schemas import DadataOrganizationData, DadataRefreshResponse
from src.app.services.dadata.sync import (
    apply_dadata_to_organization,
    refresh_all_organizations_from_dadata,
    refresh_organization_from_dadata,
)


@asynccontextmanager
async def _granted_lock(*, manual: bool):
    del manual
    yield True


@asynccontextmanager
async def _lost_lock(*, manual: bool):
    del manual

    class _LostLease:
        async def ensure_active(self) -> None:
            raise DadataRuntimeError("Потеряна блокировка полного обновления.")

    yield _LostLease()


def test_missing_dadata_values_do_not_clear_existing_fields():
    session = AsyncMock()
    organization = OrganizationOrm(
        id=1,
        inn="7719402047",
        name_long="Существующее полное имя",
        name_short="Существующее имя",
        chief_name="Существующий руководитель",
        chief_post="Существующая должность",
    )
    data = DadataOrganizationData(inn="7719402047")
    with (
        patch(
            "src.app.services.dadata.sync._upsert_requisite",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "src.app.services.dadata.sync._upsert_email_contact",
            new=AsyncMock(return_value=False),
        ),
    ):
        result = asyncio.run(
            apply_dadata_to_organization(session, organization=organization, data=data)
        )

    assert organization.name_long == "Существующее полное имя"
    assert organization.chief_name == "Существующий руководитель"
    assert result.updated_fields == []


def test_apply_dadata_upserts_primary_okved_into_existing_requisite():
    session = AsyncMock()
    organization = OrganizationOrm(id=1, inn="7719402047")
    data = DadataOrganizationData(
        inn="7719402047",
        okved="64.20",
        okved_name="Деятельность холдинговых компаний",
    )
    with (
        patch(
            "src.app.services.dadata.sync._upsert_requisite",
            new=AsyncMock(return_value=True),
        ) as upsert_requisite,
        patch(
            "src.app.services.dadata.sync._upsert_email_contact",
            new=AsyncMock(return_value=False),
        ),
    ):
        result = asyncio.run(
            apply_dadata_to_organization(session, organization=organization, data=data)
        )

    okved_call = next(
        call
        for call in upsert_requisite.await_args_list
        if call.kwargs["type_names"] == ("ОКВЭД (ОСНОВНОЙ)", "ОКВЭД")
    )
    assert okved_call.kwargs["value"] == "64.20 Деятельность холдинговых компаний"
    assert "okved" in result.updated_fields


def test_duplicate_inn_group_uses_one_lookup_and_preserves_card_names():
    session = AsyncMock()
    head_office = OrganizationOrm(id=1, inn="7719402047", name_short="Попка")
    branch = OrganizationOrm(id=2, inn="7719402047", name_short="Попка, филиал Москва")
    scalar_result = Mock()
    scalar_result.all.return_value = [head_office, branch]
    session.get.return_value = head_office
    session.scalars.return_value = scalar_result
    data = DadataOrganizationData(
        inn="7719402047",
        name_short="ООО Попка",
        name_long="Общество с ограниченной ответственностью «Попка»",
        chief_name="Новый руководитель",
    )
    with (
        patch(
            "src.app.services.dadata.sync.find_party_by_inn", new=AsyncMock(return_value=data)
        ) as lookup,
        patch("src.app.services.dadata.sync._upsert_requisite", new=AsyncMock(return_value=False)),
        patch(
            "src.app.services.dadata.sync._upsert_email_contact", new=AsyncMock(return_value=False)
        ),
    ):
        result = asyncio.run(
            refresh_organization_from_dadata(
                session,
                organization_id=1,
                inn="7719402047",
            )
        )

    lookup.assert_awaited_once_with("7719402047", keep_daily_reserve=False)
    assert result.status == "updated"
    assert result.processed_organizations_count == 2
    assert head_office.name_short == "Попка"
    assert branch.name_short == "Попка, филиал Москва"
    assert head_office.chief_name == "Новый руководитель"
    assert branch.chief_name == "Новый руководитель"


def test_failed_full_refresh_does_not_move_schedule():
    session = AsyncMock()
    with (
        patch("src.app.services.dadata.sync.full_refresh_lock", _granted_lock),
        patch(
            "src.app.services.dadata.sync._fetch_organization_groups_with_inn",
            new=AsyncMock(return_value=[("7719402047", [1])]),
        ),
        patch(
            "src.app.services.dadata.sync.get_daily_request_count",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "src.app.services.dadata.sync.refresh_organization_from_dadata",
            new=AsyncMock(return_value=DadataRefreshResponse(status="failed", organization_id=1)),
        ),
        patch("src.app.services.dadata.sync.mark_full_refresh_done", new=AsyncMock()) as mark_done,
        patch(
            "src.app.services.dadata.sync.mark_last_full_refresh_now", new=AsyncMock()
        ) as mark_last,
    ):
        result = asyncio.run(refresh_all_organizations_from_dadata(session, manual=False))

    assert result.status == "failed"
    mark_done.assert_not_awaited()
    mark_last.assert_not_awaited()


def test_successful_full_refresh_moves_schedule():
    session = AsyncMock()
    with (
        patch("src.app.services.dadata.sync.full_refresh_lock", _granted_lock),
        patch(
            "src.app.services.dadata.sync._fetch_organization_groups_with_inn",
            new=AsyncMock(return_value=[("7719402047", [1])]),
        ),
        patch(
            "src.app.services.dadata.sync.get_daily_request_count",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "src.app.services.dadata.sync.refresh_organization_from_dadata",
            new=AsyncMock(return_value=DadataRefreshResponse(status="updated", organization_id=1)),
        ) as refresh_mock,
        patch("src.app.services.dadata.sync.mark_full_refresh_done", new=AsyncMock()) as mark_done,
        patch(
            "src.app.services.dadata.sync.mark_last_full_refresh_now", new=AsyncMock()
        ) as mark_last,
    ):
        result = asyncio.run(refresh_all_organizations_from_dadata(session, manual=True))

    assert result.status == "completed"
    refresh_mock.assert_awaited_once()
    assert refresh_mock.await_args.kwargs == {
        "organization_id": 1,
        "inn": "7719402047",
        "keep_daily_reserve": True,
    }
    mark_done.assert_awaited_once_with(origin="manual")
    mark_last.assert_awaited_once()


def test_parent_full_refresh_aggregates_low_priority_child_jobs():
    session = AsyncMock()
    queued_child = {"job_id": "child"}
    with (
        patch("src.app.services.dadata.sync.full_refresh_lock", _granted_lock),
        patch(
            "src.app.services.dadata.sync._fetch_organization_groups_with_inn",
            new=AsyncMock(return_value=[("7719402047", [1]), ("7707083893", [2])]),
        ),
        patch(
            "src.app.services.dadata.sync.get_daily_request_count", new=AsyncMock(return_value=0)
        ),
        patch("src.app.services.dadata.sync.initialize_full_refresh_progress", new=AsyncMock()),
        patch(
            "src.app.services.dadata.sync.enqueue_job",
            new=AsyncMock(return_value=(queued_child, True)),
        ) as enqueue_mock,
        patch(
            "src.app.services.dadata.sync.get_full_refresh_progress",
            new=AsyncMock(return_value={"processed": 2, "status:success": 2}),
        ),
        patch("src.app.services.dadata.sync.mark_full_refresh_done", new=AsyncMock()) as mark_done,
        patch(
            "src.app.services.dadata.sync.mark_last_full_refresh_now", new=AsyncMock()
        ) as mark_last,
    ):
        result = asyncio.run(
            refresh_all_organizations_from_dadata(session, manual=True, parent_job_id="parent")
        )

    assert result.status == "completed"
    assert result.processed == 2
    assert enqueue_mock.await_count == 2
    mark_done.assert_awaited_once()
    mark_last.assert_awaited_once()


def test_parent_full_refresh_queues_one_child_job_per_inn_group():
    session = AsyncMock()
    with (
        patch("src.app.services.dadata.sync.full_refresh_lock", _granted_lock),
        patch(
            "src.app.services.dadata.sync._fetch_organization_groups_with_inn",
            new=AsyncMock(return_value=[("7719402047", [1, 2]), ("7707083893", [3])]),
        ),
        patch(
            "src.app.services.dadata.sync.get_daily_request_count", new=AsyncMock(return_value=0)
        ),
        patch(
            "src.app.services.dadata.sync.initialize_full_refresh_progress", new=AsyncMock()
        ) as init,
        patch(
            "src.app.services.dadata.sync.enqueue_job",
            new=AsyncMock(return_value=({"job_id": "child"}, True)),
        ) as enqueue_mock,
        patch(
            "src.app.services.dadata.sync.get_full_refresh_progress",
            new=AsyncMock(return_value={"processed": 3, "status:success": 3}),
        ),
        patch("src.app.services.dadata.sync.mark_full_refresh_done", new=AsyncMock()),
        patch("src.app.services.dadata.sync.mark_last_full_refresh_now", new=AsyncMock()),
    ):
        result = asyncio.run(
            refresh_all_organizations_from_dadata(session, manual=True, parent_job_id="parent")
        )

    assert result.status == "completed"
    assert result.total_candidates == 3
    init.assert_awaited_once_with("parent", total=3)
    assert enqueue_mock.await_count == 2
    assert enqueue_mock.await_args_list[0].kwargs["payload"]["progress_weight"] == 2
    assert enqueue_mock.await_args_list[0].kwargs["dedupe_key"] == "full-refresh:parent:7719402047"


def test_parent_full_refresh_stops_before_queueing_children_when_lease_is_lost():
    session = AsyncMock()
    with (
        patch("src.app.services.dadata.sync.full_refresh_lock", _lost_lock),
        patch(
            "src.app.services.dadata.sync._fetch_organization_groups_with_inn",
            new=AsyncMock(return_value=[("7719402047", [1])]),
        ),
        patch(
            "src.app.services.dadata.sync.get_daily_request_count", new=AsyncMock(return_value=0)
        ),
        patch("src.app.services.dadata.sync.initialize_full_refresh_progress", new=AsyncMock()),
        patch("src.app.services.dadata.sync.enqueue_job", new=AsyncMock()) as enqueue_mock,
        pytest.raises(DadataRuntimeError, match="Потеряна блокировка"),
    ):
        asyncio.run(
            refresh_all_organizations_from_dadata(session, manual=True, parent_job_id="parent")
        )

    enqueue_mock.assert_not_awaited()


def test_parent_full_refresh_queues_three_thousand_low_priority_items_without_serial_requests():
    session = AsyncMock()
    organizations = [(f"77{index:08d}", [index]) for index in range(1, 3001)]
    with (
        patch("src.app.services.dadata.sync.full_refresh_lock", _granted_lock),
        patch(
            "src.app.services.dadata.sync._fetch_organization_groups_with_inn",
            new=AsyncMock(return_value=organizations),
        ),
        patch(
            "src.app.services.dadata.sync.get_daily_request_count", new=AsyncMock(return_value=0)
        ),
        patch("src.app.services.dadata.sync.initialize_full_refresh_progress", new=AsyncMock()),
        patch(
            "src.app.services.dadata.sync.enqueue_job",
            new=AsyncMock(return_value=({"job_id": "child"}, True)),
        ) as enqueue_mock,
        patch(
            "src.app.services.dadata.sync.get_full_refresh_progress",
            new=AsyncMock(return_value={"processed": 3000, "status:success": 3000}),
        ),
        patch("src.app.services.dadata.sync.mark_full_refresh_done", new=AsyncMock()),
        patch("src.app.services.dadata.sync.mark_last_full_refresh_now", new=AsyncMock()),
    ):
        started_at = time.monotonic()
        result = asyncio.run(
            refresh_all_organizations_from_dadata(session, manual=True, parent_job_id="parent")
        )

    assert result.status == "completed"
    assert enqueue_mock.await_count == 3000
    assert time.monotonic() - started_at < 5
    assert enqueue_mock.await_args_list[0].kwargs["kind"] == "refresh_all_item"

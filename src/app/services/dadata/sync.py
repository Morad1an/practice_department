from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.database import async_session_maker
from src.app.models.detailname_contactdata import DetailnameContactData
from src.app.models.detailname_legalinformation import DetailnameLegalInformation
from src.app.models.organization import OrganizationOrm
from src.app.models.organization_detailcontactdata import OrganizationDetailContactData
from src.app.models.organization_detailcontactentity import OrganizationDetailContactEntity
from src.app.models.organization_detaillegalinformation import OrganizationDetailLegalInformation
from src.app.services.dadata.client import (
    DadataClientError,
    DadataConfigurationError,
    DadataRateLimitError,
    find_party_by_inn,
)
from src.app.services.dadata.mapper import missing_fields
from src.app.services.dadata.normalization import DadataValidationError, normalize_inn
from src.app.services.dadata.runtime import (
    DadataQueueLimitError,
    DadataRuntimeError,
    JobOrigin,
    enqueue_job,
    full_refresh_lock,
    get_daily_request_count,
    get_full_refresh_progress,
    initialize_full_refresh_progress,
    mark_full_refresh_done,
    mark_last_full_refresh_now,
)
from src.app.services.dadata.schemas import (
    DadataLookupResponse,
    DadataOrganizationData,
    DadataRefreshAllResponse,
    DadataRefreshResponse,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ApplyResult:
    updated_fields: list[str]
    warnings: list[str]


def _format_okved(data: DadataOrganizationData) -> str | None:
    code = (data.okved or "").strip()
    name = (data.okved_name or "").strip()
    if code and name:
        return f"{code} {name}"
    return code or name or None


def _normalize_label(value: str | None) -> str:
    return (value or "").strip().lower()


def _is_label(label: str | None, expected: str) -> bool:
    return _normalize_label(label) == expected.strip().lower()


async def _find_requisite_type_id(session: AsyncSession, names: tuple[str, ...]) -> int | None:
    normalized_names = [name.lower() for name in names]
    return await session.scalar(
        select(DetailnameLegalInformation.id)
        .where(func.lower(DetailnameLegalInformation.name).in_(normalized_names))
        .order_by(DetailnameLegalInformation.priority.asc(), DetailnameLegalInformation.id.asc())
        .limit(1)
    )


async def _find_contact_type_id(session: AsyncSession, names: tuple[str, ...]) -> int | None:
    normalized_names = [name.lower() for name in names]
    return await session.scalar(
        select(DetailnameContactData.id)
        .where(func.lower(DetailnameContactData.name).in_(normalized_names))
        .order_by(DetailnameContactData.display_priority.asc(), DetailnameContactData.id.asc())
        .limit(1)
    )


async def _upsert_requisite(
    session: AsyncSession,
    *,
    organization_id: int,
    type_names: tuple[str, ...],
    value: str | None,
) -> bool:
    prepared = (value or "").strip()
    if not prepared:
        return False
    type_id = await _find_requisite_type_id(session, type_names)
    if type_id is None:
        return False
    existing = await session.scalar(
        select(OrganizationDetailLegalInformation).where(
            OrganizationDetailLegalInformation.organization_id == organization_id,
            OrganizationDetailLegalInformation.type_id == type_id,
        )
    )
    if existing is None:
        session.add(
            OrganizationDetailLegalInformation(
                organization_id=organization_id,
                type_id=type_id,
                data=prepared,
            )
        )
        return True
    if (existing.data or "").strip() == prepared:
        return False
    existing.data = prepared
    return True


async def _upsert_email_contact(
    session: AsyncSession,
    *,
    organization_id: int,
    email: str | None,
) -> bool:
    prepared = (email or "").strip()
    if not prepared:
        return False
    type_id = await _find_contact_type_id(
        session,
        ("Email", "E-mail", "Электронная почта", "Почта"),
    )
    if type_id is None:
        return False
    existing = await session.scalar(
        select(OrganizationDetailContactData)
        .join(
            OrganizationDetailContactEntity,
            OrganizationDetailContactEntity.id == OrganizationDetailContactData.entity_id,
        )
        .where(
            OrganizationDetailContactEntity.organization_id == organization_id,
            OrganizationDetailContactData.type_id == type_id,
        )
        .order_by(OrganizationDetailContactData.id.asc())
        .limit(1)
    )
    if existing is not None:
        if (existing.data or "").strip() == prepared:
            return False
        existing.data = prepared
        return True

    entity = OrganizationDetailContactEntity(organization_id=organization_id)
    session.add(entity)
    await session.flush()
    session.add(
        OrganizationDetailContactData(
            entity_id=entity.id,
            type_id=type_id,
            data=prepared,
        )
    )
    return True


async def find_existing_organization_by_inn(
    session: AsyncSession,
    *,
    inn: str,
) -> OrganizationOrm | None:
    normalized_inn = normalize_inn(inn)
    return await session.scalar(
        select(OrganizationOrm)
        .where(OrganizationOrm.inn == normalized_inn)
        .order_by(OrganizationOrm.id.asc())
        .limit(1)
    )


async def queue_lookup_organization_by_inn(
    session: AsyncSession,
    *,
    inn: str,
    force_refresh: bool = False,
    created_by_user_id: int | None = None,
) -> DadataLookupResponse:
    normalized_inn = normalize_inn(inn)
    existing = await find_existing_organization_by_inn(session, inn=normalized_inn)
    try:
        if existing is not None:
            job, _ = await enqueue_job(
                kind="refresh_one",
                payload={
                    "organization_id": existing.id,
                    "inn": normalized_inn,
                    "created_by_user_id": created_by_user_id,
                },
                dedupe_key=f"inn-group:{normalized_inn}",
            )
            return DadataLookupResponse(
                status="queued",
                job_id=job["job_id"],
                existing_organization_id=existing.id,
                existing_organization_url=f"/organizations/{existing.id}",
                message="Организация уже существует; обновление поставлено в очередь.",
            )
        job, _ = await enqueue_job(
            kind="lookup",
            payload={
                "inn": normalized_inn,
                "force_refresh": force_refresh,
                "created_by_user_id": created_by_user_id,
            },
            dedupe_key=f"inn-group:{normalized_inn}",
        )
        return DadataLookupResponse(
            status="queued",
            job_id=job["job_id"],
            message="Поиск данных поставлен в очередь.",
        )
    except DadataQueueLimitError as error:
        return DadataLookupResponse(status="failed", message=str(error))
    except DadataRuntimeError:
        return await lookup_organization_by_inn(
            session, inn=normalized_inn, force_refresh=force_refresh
        )


async def queue_organization_refresh(
    session: AsyncSession,
    *,
    organization_id: int,
    created_by_user_id: int | None = None,
) -> DadataRefreshResponse:
    organization = await session.get(OrganizationOrm, organization_id)
    if organization is None:
        return DadataRefreshResponse(
            status="failed",
            organization_id=organization_id,
            message="Организация не найдена.",
        )
    try:
        inn = await _find_organization_inn(session, organization_id)
    except DadataValidationError:
        inn = None
    if inn is None:
        return DadataRefreshResponse(
            status="failed",
            organization_id=organization_id,
            message="У организации не заполнен корректный ИНН.",
        )
    try:
        job, _ = await enqueue_job(
            kind="refresh_one",
            payload={
                "organization_id": organization_id,
                "inn": inn,
                "created_by_user_id": created_by_user_id,
            },
            dedupe_key=f"inn-group:{inn}",
        )
    except DadataQueueLimitError as error:
        return DadataRefreshResponse(
            status="failed", organization_id=organization_id, message=str(error)
        )
    except DadataRuntimeError:
        return await refresh_organization_from_dadata(
            session,
            organization_id=organization_id,
            inn=inn,
        )
    return DadataRefreshResponse(
        status="queued",
        job_id=job["job_id"],
        organization_id=organization_id,
        message="Обновление организации поставлено в очередь.",
    )


async def queue_full_refresh(*, manual: bool) -> DadataRefreshAllResponse:
    try:
        job, _ = await enqueue_job(
            kind="refresh_all",
            payload={"manual": manual},
            dedupe_key="full-refresh",
            origin="manual" if manual else "scheduled",
        )
    except DadataRuntimeError as error:
        return DadataRefreshAllResponse(status="failed", message=str(error))
    return DadataRefreshAllResponse(
        status="queued",
        job_id=job["job_id"],
        message="Полное обновление поставлено в очередь.",
    )


async def apply_dadata_to_organization(
    session: AsyncSession,
    *,
    organization: OrganizationOrm,
    data: DadataOrganizationData,
    update_names: bool = True,
) -> ApplyResult:
    updated: list[str] = []
    warnings = list(data.warnings)

    scalar_fields = {
        "chief_name": data.chief_name,
        "chief_post": data.chief_post,
    }
    if update_names:
        scalar_fields = {
            "name_long": data.name_long,
            "name_short": data.name_short,
            **scalar_fields,
        }
    for field_name, value in scalar_fields.items():
        prepared = (value or "").strip()
        if not prepared:
            continue
        if (getattr(organization, field_name) or "").strip() == prepared:
            continue
        setattr(organization, field_name, prepared)
        updated.append(field_name)

    requisite_specs = [
        ("inn", ("ИНН",), data.inn),
        ("ogrn", ("ОГРН",), data.ogrn),
        ("kpp", ("КПП",), data.kpp),
        ("legal_address", ("Юридический адрес",), data.legal_address),
        (
            "okved",
            ("ОКВЭД (ОСНОВНОЙ)", "ОКВЭД"),
            _format_okved(data),
        ),
    ]
    for field_name, type_names, value in requisite_specs:
        if await _upsert_requisite(
            session,
            organization_id=organization.id,
            type_names=type_names,
            value=value,
        ):
            updated.append(field_name)

    if organization.inn != data.inn:
        organization.inn = data.inn
        if "inn" not in updated:
            updated.append("inn")

    if await _upsert_email_contact(session, organization_id=organization.id, email=data.email):
        updated.append("email")

    await session.flush()
    logger.info(
        "dadata_organization_applied",
        extra={
            "organization_id": organization.id,
            "inn": data.inn,
            "updated_fields": updated,
        },
    )
    return ApplyResult(updated_fields=updated, warnings=warnings)


async def lookup_organization_by_inn(
    session: AsyncSession,
    *,
    inn: str,
    force_refresh: bool = False,
) -> DadataLookupResponse:
    normalized_inn = normalize_inn(inn)
    existing = await find_existing_organization_by_inn(session, inn=normalized_inn)
    if existing is not None:
        refresh = await refresh_organization_from_dadata(
            session,
            organization_id=existing.id,
            inn=normalized_inn,
        )
        return DadataLookupResponse(
            status="ready" if refresh.status == "updated" else refresh.status,  # type: ignore[arg-type]
            existing_organization_id=existing.id,
            existing_organization_url=f"/organizations/{existing.id}",
            data=refresh.data,
            missing_fields=missing_fields(refresh.data) if refresh.data else [],
            warnings=refresh.data.warnings if refresh.data else [],
            message=(
                "Организация с таким ИНН уже есть. Данные существующей карточки обновлены."
                if refresh.status == "updated"
                else refresh.message
            ),
        )

    try:
        data = await find_party_by_inn(normalized_inn)
    except DadataRateLimitError as error:
        return DadataLookupResponse(
            status="rate_limited",
            message=str(error),
            retry_after_seconds=error.retry_after_seconds,
        )
    except (DadataClientError, DadataConfigurationError, DadataValidationError) as error:
        return DadataLookupResponse(status="failed", message=str(error))

    if data is None:
        return DadataLookupResponse(
            status="not_found",
            message="Организация по указанному ИНН не найдена.",
        )
    return DadataLookupResponse(
        status="ready",
        data=data,
        missing_fields=missing_fields(data),
        warnings=data.warnings,
    )


async def refresh_organization_from_dadata(
    session: AsyncSession,
    *,
    organization_id: int,
    inn: str | None = None,
    keep_daily_reserve: bool = False,
) -> DadataRefreshResponse:
    organization = await session.get(OrganizationOrm, organization_id)
    if organization is None:
        return DadataRefreshResponse(
            status="failed",
            organization_id=organization_id,
            message="Организация не найдена.",
        )

    try:
        normalized_inn = (
            normalize_inn(inn) if inn else await _find_organization_inn(session, organization_id)
        )
    except DadataValidationError:
        normalized_inn = None
    if normalized_inn is None:
        return DadataRefreshResponse(
            status="failed",
            organization_id=organization_id,
            message="У организации не заполнен ИНН.",
        )

    try:
        data = await find_party_by_inn(
            normalized_inn,
            keep_daily_reserve=keep_daily_reserve,
        )
    except DadataRateLimitError as error:
        logger.warning(
            "dadata_organization_rate_limited",
            extra={"organization_id": organization_id, "inn": normalized_inn},
        )
        return DadataRefreshResponse(
            status="rate_limited",
            organization_id=organization_id,
            message=str(error),
            retry_after_seconds=error.retry_after_seconds,
        )
    except (DadataClientError, DadataConfigurationError, DadataValidationError) as error:
        logger.warning(
            "dadata_organization_failed",
            extra={
                "organization_id": organization_id,
                "inn": normalized_inn,
                "error_type": type(error).__name__,
            },
        )
        return DadataRefreshResponse(
            status="failed",
            organization_id=organization_id,
            message=str(error),
        )

    if data is None:
        return DadataRefreshResponse(
            status="not_found",
            organization_id=organization_id,
            message="Организация по ИНН не найдена.",
        )

    organizations = list(
        (
            await session.scalars(
                select(OrganizationOrm)
                .where(OrganizationOrm.inn == normalized_inn)
                .order_by(OrganizationOrm.id.asc())
            )
        ).all()
    )
    if not organizations:
        organizations = [organization]
    update_names = len(organizations) == 1
    updated_fields: set[str] = set()
    for group_organization in organizations:
        apply_result = await apply_dadata_to_organization(
            session,
            organization=group_organization,
            data=data,
            update_names=update_names,
        )
        updated_fields.update(apply_result.updated_fields)
    await session.commit()
    return DadataRefreshResponse(
        status="updated",
        organization_id=organization_id,
        processed_organizations_count=len(organizations),
        updated_fields=sorted(updated_fields),
        data=data,
        message=(
            "Данные организации обновлены."
            if len(organizations) == 1
            else f"Данные синхронизированы для {len(organizations)} карточек с одним ИНН."
        ),
    )


async def _find_organization_inn(session: AsyncSession, organization_id: int) -> str | None:
    value = await session.scalar(
        select(OrganizationOrm.inn).where(OrganizationOrm.id == organization_id)
    )
    if not value:
        return None
    return normalize_inn(value)


async def _fetch_organization_groups_with_inn(
    session: AsyncSession,
) -> list[tuple[str, list[int]]]:
    rows = (
        await session.execute(
            select(OrganizationOrm.id, OrganizationOrm.inn)
            .where(OrganizationOrm.inn.is_not(None))
            .order_by(OrganizationOrm.id.asc())
        )
    ).all()
    groups: dict[str, list[int]] = {}
    for organization_id, inn in rows:
        try:
            normalized_inn = normalize_inn(inn)
        except DadataValidationError:
            continue
        groups.setdefault(normalized_inn, []).append(organization_id)
    return list(groups.items())


async def _ensure_full_refresh_lease(lease: object) -> None:
    """Keep compatibility with lightweight test lock context managers."""
    ensure_active = getattr(lease, "ensure_active", None)
    if ensure_active is not None:
        await ensure_active()


async def refresh_all_organizations_from_dadata(  # noqa: C901
    session: AsyncSession,
    *,
    manual: bool = True,
    parent_job_id: str | None = None,
) -> DadataRefreshAllResponse:
    async with full_refresh_lock(manual=manual) as lease:
        if lease is None:
            return DadataRefreshAllResponse(
                status="skipped",
                message="Полное обновление уже выполнялось сегодня или идет сейчас.",
            )

        groups = await _fetch_organization_groups_with_inn(session)
        total_organizations = sum(len(organization_ids) for _, organization_ids in groups)
        spent_today = await get_daily_request_count()
        available_budget = max(
            0,
            settings.DADATA_DAILY_REQUEST_LIMIT
            - spent_today
            - settings.DADATA_DAILY_REQUEST_RESERVE,
        )
        if len(groups) > available_budget:
            return DadataRefreshAllResponse(
                status="rate_limited",
                total_candidates=total_organizations,
                message=(
                    "Полное обновление не запущено: доступного дневного лимита "
                    f"хватит на {available_budget} из {len(groups)} ИНН-групп."
                ),
            )

        if parent_job_id is not None:
            await initialize_full_refresh_progress(parent_job_id, total=total_organizations)
            batch_size = max(settings.DADATA_REFRESH_BATCH_SIZE, 1)
            queued_organizations = 0
            for batch_start in range(0, len(groups), batch_size):
                await _ensure_full_refresh_lease(lease)
                batch = groups[batch_start : batch_start + batch_size]
                for inn, organization_ids in batch:
                    await enqueue_job(
                        kind="refresh_all_item",
                        payload={
                            "organization_id": organization_ids[0],
                            "inn": inn,
                            "parent_job_id": parent_job_id,
                            "progress_weight": len(organization_ids),
                        },
                        dedupe_key=f"full-refresh:{parent_job_id}:{inn}",
                        origin="manual" if manual else "scheduled",
                    )
                queued_organizations += sum(len(organization_ids) for _, organization_ids in batch)
                while True:
                    await _ensure_full_refresh_lease(lease)
                    progress = await get_full_refresh_progress(parent_job_id)
                    if progress.get("processed", 0) >= queued_organizations:
                        break
                    await asyncio.sleep(0.2)
            while True:
                await _ensure_full_refresh_lease(lease)
                progress = await get_full_refresh_progress(parent_job_id)
                if progress.get("processed", 0) >= total_organizations:
                    break
                await asyncio.sleep(0.2)
            processed = progress.get("processed", 0)
            updated = progress.get("status:success", 0)
            skipped = progress.get("status:not_found", 0) + progress.get("status:skipped", 0)
            failed = processed - updated - skipped
            if failed:
                rate_limited = progress.get("status:rate_limited", 0) > 0
                return DadataRefreshAllResponse(
                    status="rate_limited" if rate_limited else "failed",
                    total_candidates=total_organizations,
                    processed=processed,
                    updated=updated,
                    failed=failed,
                    skipped=skipped,
                    message=(
                        "Полное обновление остановлено из-за лимита Dadata."
                        if rate_limited
                        else "Полное обновление завершилось с ошибками и будет повторено позже."
                    ),
                )
            parent_origin: JobOrigin = "manual" if manual else "scheduled"
            await _ensure_full_refresh_lease(lease)
            await mark_full_refresh_done(origin=parent_origin)
            await mark_last_full_refresh_now()
            return DadataRefreshAllResponse(
                status="completed",
                total_candidates=total_organizations,
                processed=processed,
                updated=updated,
                skipped=skipped,
                message="Полное обновление данных организаций завершено.",
            )

        processed = 0
        updated = 0
        failed = 0
        skipped = 0
        batch_size = min(
            max(settings.DADATA_REFRESH_BATCH_SIZE, 1),
            max(settings.DADATA_FULL_REFRESH_CONCURRENCY, 1),
        )
        stopped_by_rate_limit = False
        for batch_start in range(0, len(groups), batch_size):
            await _ensure_full_refresh_lease(lease)
            batch = groups[batch_start : batch_start + batch_size]

            async def refresh_one(organization_id: int, inn: str) -> DadataRefreshResponse:
                async with async_session_maker() as task_session:
                    return await refresh_organization_from_dadata(
                        task_session,
                        organization_id=organization_id,
                        inn=inn,
                        keep_daily_reserve=True,
                    )

            if len(batch) == 1:
                inn, organization_ids = batch[0]
                organization_id = organization_ids[0]
                responses: list[DadataRefreshResponse | BaseException] = [
                    await refresh_organization_from_dadata(
                        session,
                        organization_id=organization_id,
                        inn=inn,
                        keep_daily_reserve=True,
                    )
                ]
            else:
                responses = list(
                    await asyncio.gather(
                        *(refresh_one(organization_ids[0], inn) for inn, organization_ids in batch),
                        return_exceptions=True,
                    )
                )
            for (inn, organization_ids), response in zip(batch, responses, strict=True):
                del inn
                group_size = len(organization_ids)
                processed += group_size
                if not isinstance(response, DadataRefreshResponse):
                    failed += group_size
                    logger.exception("dadata_full_refresh_item_failed", exc_info=response)
                    continue
                if response.status == "updated":
                    updated += group_size
                elif response.status in {"not_found", "skipped"}:
                    skipped += group_size
                else:
                    failed += group_size
                if response.status == "rate_limited":
                    stopped_by_rate_limit = True
                    break
            if stopped_by_rate_limit:
                break

        if failed or processed != total_organizations:
            logger.warning(
                "dadata_full_refresh_failed",
                extra={
                    "processed": processed,
                    "total_candidates": total_organizations,
                    "failed": failed,
                    "rate_limited": stopped_by_rate_limit,
                },
            )
            return DadataRefreshAllResponse(
                status="rate_limited" if stopped_by_rate_limit else "failed",
                total_candidates=total_organizations,
                processed=processed,
                updated=updated,
                failed=failed,
                skipped=skipped,
                message=(
                    "Полное обновление остановлено из-за лимита Dadata."
                    if stopped_by_rate_limit
                    else "Полное обновление завершилось с ошибками и будет повторено позже."
                ),
            )

        origin: JobOrigin = "manual" if manual else "scheduled"
        await _ensure_full_refresh_lease(lease)
        await mark_full_refresh_done(origin=origin)
        await mark_last_full_refresh_now()
        return DadataRefreshAllResponse(
            status="completed",
            total_candidates=total_organizations,
            processed=processed,
            updated=updated,
            failed=failed,
            skipped=skipped,
            message="Полное обновление данных организаций завершено.",
        )

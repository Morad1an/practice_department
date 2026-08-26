from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.app.api.auth_dependencies import (
    require_admin_user,
    require_authenticated_user,
    require_editor_user,
)
from src.app.database import async_session_maker
from src.app.services.auth import AuthenticatedUser
from src.app.services.dadata.normalization import DadataValidationError
from src.app.services.dadata.runtime import (
    DadataRuntimeError,
    get_full_refresh_progress,
    get_job,
    require_redis_client,
)
from src.app.services.dadata.schemas import (
    DadataJobStatusResponse,
    DadataLookupRequest,
    DadataLookupResponse,
    DadataRefreshAllResponse,
    DadataRefreshResponse,
)
from src.app.services.dadata.sync import (
    queue_full_refresh,
    queue_lookup_organization_by_inn,
    queue_organization_refresh,
)

router = APIRouter(tags=["Dadata"])


def _raise_validation_error(error: Exception) -> None:
    if isinstance(error, DadataValidationError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    raise error


@router.post(
    "/api/dadata/party/lookup",
    response_model=DadataLookupResponse,
    name="dadata_party_lookup_api",
)
async def dadata_party_lookup(
    payload: DadataLookupRequest,
    user: AuthenticatedUser = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        try:
            return await queue_lookup_organization_by_inn(
                session,
                inn=payload.inn,
                force_refresh=payload.force_refresh,
                created_by_user_id=user.id,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_validation_error(error)


@router.get(
    "/api/dadata/jobs/{job_id}",
    response_model=DadataJobStatusResponse,
    name="dadata_job_status_api",
)
async def dadata_job_status(
    job_id: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    try:
        job = await get_job(job_id)
    except DadataRuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if job is None:
        raise HTTPException(status_code=404, detail="Задача Dadata не найдена или устарела.")
    owner_id = (job.get("payload") or {}).get("created_by_user_id")
    if owner_id is None:
        if not user.can_admin:
            raise HTTPException(status_code=403, detail="Недостаточно прав для просмотра задачи.")
    elif owner_id != user.id and not user.can_admin:
        raise HTTPException(status_code=403, detail="Недостаточно прав для просмотра задачи.")
    result = job.get("result")
    parsed_result: (
        DadataLookupResponse | DadataRefreshResponse | DadataRefreshAllResponse | None
    ) = None
    if isinstance(result, dict):
        if job["kind"] == "lookup":
            parsed_result = DadataLookupResponse.model_validate(result)
        elif job["kind"] in {"refresh_one", "refresh_all_item"}:
            parsed_result = DadataRefreshResponse.model_validate(result)
        else:
            parsed_result = DadataRefreshAllResponse.model_validate(result)
    elif job["kind"] == "refresh_all" and job["status"] in {"queued", "running"}:
        try:
            progress = await get_full_refresh_progress(job_id)
        except DadataRuntimeError:
            progress = {}
        parsed_result = DadataRefreshAllResponse(
            status="running" if job["status"] == "running" else "queued",
            total_candidates=progress.get("total", 0),
            processed=progress.get("processed", 0),
            updated=progress.get("status:success", 0),
            failed=progress.get("status:failed", 0) + progress.get("status:rate_limited", 0),
            skipped=progress.get("status:not_found", 0) + progress.get("status:skipped", 0),
        )
    return DadataJobStatusResponse(
        status=job["status"],
        job_id=job_id,
        kind=job["kind"],
        result=parsed_result,
        message=job.get("message"),
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


@router.post(
    "/api/organizations/{organization_id}/dadata-refresh",
    response_model=DadataRefreshResponse,
    name="dadata_organization_refresh_api",
)
async def dadata_organization_refresh(
    organization_id: int,
    user: AuthenticatedUser = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        return await queue_organization_refresh(
            session,
            organization_id=organization_id,
            created_by_user_id=user.id,
        )


@router.post(
    "/api/dadata/refresh-all",
    response_model=DadataRefreshAllResponse,
    name="dadata_refresh_all_api",
)
async def dadata_refresh_all(
    _: None = Depends(require_admin_user),
):
    try:
        await require_redis_client()
    except DadataRuntimeError as error:
        raise HTTPException(
            status_code=503, detail="Полная синхронизация требует Redis."
        ) from error
    return await queue_full_refresh(manual=True)

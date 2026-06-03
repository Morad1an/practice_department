from datetime import date, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, Response

from src.app.api.auth_dependencies import require_editor_user
from src.app.api.organizations_common import (
    build_active_organizations_page_context,
    build_group_distribution_page_context,
    build_study_directions_page_context,
    templates,
)
from src.app.database import async_session_maker
from src.app.schemas.organizations import (
    ActiveOrganizationsFilterOptions,
    ActiveOrganizationsFilters,
    ActiveOrganizationsTableRequest,
    DistributionStatsChartResponse,
    DistributionStatsFilters,
    DistributionStatsTableResponse,
    DistributionStatsYearsResponse,
    GroupDistributionFilterOptions,
    GroupDistributionFilters,
    GroupDistributionTableRequest,
    OrganizationCardSavePayload,
    OrganizationCardSaveResult,
    OrganizationDeleteResult,
    OrganizationDocumentCreatePayload,
    OrganizationDocumentUpdatePayload,
    OrganizationHeaderSearchResponse,
    StudyDirectionsFilterOptions,
    StudyDirectionsFilters,
    StudyDirectionsTableRequest,
)
from src.app.services.active_organizations import (
    fetch_active_organizations_filter_options,
    fetch_all_active_organizations,
)
from src.app.services.distribution_stats import (
    fetch_distribution_stats_chart,
    fetch_distribution_stats_table,
    fetch_distribution_stats_years,
)
from src.app.services.group_distribution import (
    fetch_all_group_distribution,
    fetch_group_distribution_filter_options,
    resolve_group_distribution_filters,
)
from src.app.services.logotypes_batch import fetch_logotypes_batch
from src.app.services.organization_card_write import (
    OrganizationCardNotFoundError,
    OrganizationCardValidationError,
    OrganizationDeleteBlockedError,
    add_organization_document,
    archive_organization_document,
    delete_organization_document_pdf,
    delete_organization_logo,
    delete_organization_safely,
    get_organization_document_pdf,
    save_organization_card,
    save_organization_logo,
    update_organization_document,
)
from src.app.services.organization_search import search_organizations_for_header
from src.app.services.organizations_page import (
    serialize_active_row,
    serialize_group_distribution_row,
    serialize_study_direction_row,
)
from src.app.services.study_directions import (
    fetch_all_study_directions,
    fetch_study_directions_filter_options,
)
from src.app.services.xlsx_export import build_xlsx_bytes

router = APIRouter(tags=["Organizations API"])
_MAX_LOGO_SIZE_BYTES = 1 * 1024 * 1024
_MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024


def _raise_card_api_error(error: Exception) -> None:
    if isinstance(error, OrganizationCardNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, OrganizationDeleteBlockedError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(error),
                "reasons": error.reasons,
            },
        ) from error
    if isinstance(error, OrganizationCardValidationError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    raise error


async def _read_upload_bytes(upload_file: UploadFile, *, max_bytes: int) -> bytes:
    data = bytearray()
    total_size = 0

    while True:
        chunk = await upload_file.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_bytes:
            raise OrganizationCardValidationError(
                f"Файл превышает допустимый размер {max_bytes // (1024 * 1024)} МБ."
            )
        data.extend(chunk)

    return bytes(data)


@router.get("/api/organizations/active/logotypes/batch")
@router.get("/organizations/active/logotypes/batch", include_in_schema=False)
async def active_organizations_logotypes_batch(
    ids: Annotated[list[int], Query(description="Logotype ids")],
):
    async with async_session_maker() as session:
        logos = await fetch_logotypes_batch(session, ids=ids)
    return {"logos": logos}


@router.get("/api/organizations/study-directions/logotypes/batch")
async def study_directions_logotypes_batch(
    ids: Annotated[list[int], Query(description="Logotype ids")],
):
    async with async_session_maker() as session:
        logos = await fetch_logotypes_batch(session, ids=ids)
    return {"logos": logos}


@router.post(
    "/api/organizations/active/filter-options",
    response_model=ActiveOrganizationsFilterOptions,
)
@router.post(
    "/organizations/active/filter-options",
    response_model=ActiveOrganizationsFilterOptions,
    include_in_schema=False,
)
async def active_organizations_filter_options(
    filters: ActiveOrganizationsFilters,
):
    async with async_session_maker() as session:
        return await fetch_active_organizations_filter_options(session, filters)


@router.post(
    "/api/organizations/study-directions/filter-options",
    response_model=StudyDirectionsFilterOptions,
)
async def study_directions_filter_options(
    filters: StudyDirectionsFilters,
):
    async with async_session_maker() as session:
        return await fetch_study_directions_filter_options(session, filters)


@router.post(
    "/api/organizations/groups/filter-options",
    response_model=GroupDistributionFilterOptions,
)
async def groups_filter_options(
    _: GroupDistributionFilters,
):
    async with async_session_maker() as session:
        return await fetch_group_distribution_filter_options(session)


@router.get(
    "/api/organizations/distribution-stats/years",
    response_model=DistributionStatsYearsResponse,
)
async def distribution_stats_years():
    async with async_session_maker() as session:
        return await fetch_distribution_stats_years(session)


@router.post(
    "/api/organizations/distribution-stats/table",
    response_model=DistributionStatsTableResponse,
)
async def distribution_stats_table(
    filters: DistributionStatsFilters,
):
    async with async_session_maker() as session:
        return await fetch_distribution_stats_table(session, filters)


@router.post(
    "/api/organizations/distribution-stats/chart",
    response_model=DistributionStatsChartResponse,
)
async def distribution_stats_chart(
    filters: DistributionStatsFilters,
):
    async with async_session_maker() as session:
        return await fetch_distribution_stats_chart(session, filters)


@router.post("/api/organizations/active/table", response_class=HTMLResponse)
@router.post(
    "/organizations/active/table",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def active_organizations_table(
    request: Request,
    payload: ActiveOrganizationsTableRequest,
):
    context = await build_active_organizations_page_context(
        request,
        payload.filters,
        custom_sort_requested=payload.custom_sort_requested,
    )
    context.update({"active_tab": "active-organizations"})
    return templates.TemplateResponse(request, "organizations/active.html", context)


@router.post("/api/organizations/study-directions/table", response_class=HTMLResponse)
async def study_directions_table(
    request: Request,
    payload: StudyDirectionsTableRequest,
):
    context = await build_study_directions_page_context(
        request,
        payload.filters,
        custom_sort_requested=payload.custom_sort_requested,
    )
    context.update({"active_tab": "study-directions"})
    return templates.TemplateResponse(request, "organizations/study_directions.html", context)


@router.post("/api/organizations/groups/table", response_class=HTMLResponse)
async def groups_table(
    request: Request,
    payload: GroupDistributionTableRequest,
):
    context = await build_group_distribution_page_context(
        request,
        payload.filters,
        custom_sort_requested=payload.custom_sort_requested,
    )
    context.update({"active_tab": "groups"})
    return templates.TemplateResponse(request, "organizations/groups.html", context)


@router.post("/api/organizations/study-directions/export")
async def study_directions_export(
    payload: StudyDirectionsTableRequest,
):
    async with async_session_maker() as session:
        rows = await fetch_all_study_directions(
            session,
            payload.filters,
            custom_sort_requested=payload.custom_sort_requested,
        )

    serialized_rows = [serialize_study_direction_row(row) for row in rows]
    export_rows = [
        [
            row["faculty_name"] or "",
            row["department_name"] or "",
            row["study_direction_name"] or "",
            row["study_direction_code"] or "",
            "Да" if row["logotype_id"] else "",
            row["organization_name"] or "",
            "\n".join(row["phones"]),
            "\n".join(row["digitals"]),
        ]
        for row in serialized_rows
    ]

    workbook = build_xlsx_bytes(
        sheet_name="Направления подготовки",
        headers=[
            "Факультет",
            "Кафедра",
            "Наименование направления",
            "Шифры направления",
            "Логотип",
            "Наименование организации",
            "Телефонные контакты",
            "Цифровые контакты",
        ],
        rows=export_rows,
    )

    export_filename = "Направления_" + datetime.now().strftime("%d_%m_%Y_%H_%M_%S") + ".xlsx"
    quoted_filename = quote(export_filename)

    return Response(
        content=workbook,
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/organizations/groups/export")
async def groups_export(
    payload: GroupDistributionTableRequest,
):
    async with async_session_maker() as session:
        effective_filters = payload.filters
        if payload.filters.semester_id is None:
            filter_options = await fetch_group_distribution_filter_options(session)
            effective_filters, _ = resolve_group_distribution_filters(
                payload.filters,
                filter_options["semesters"],
            )
        rows = await fetch_all_group_distribution(
            session,
            effective_filters,
            custom_sort_requested=payload.custom_sort_requested,
        )

    serialized_rows = [serialize_group_distribution_row(row) for row in rows]
    export_rows = [
        [
            row["department_name"] or "",
            row["study_direction_code"] or "",
            row["study_direction_name"] or "",
            row["study_profile_name"] or "",
            row["group_name"] or "",
            row["course"] or "",
            row["distributed_quantity"] or "",
            row["organization_name"] or "",
            row["order_name"] or "",
            row["signing_date"] or "",
            row["practice_name"] or "",
            row["practice_date_begin"] or "",
            row["practice_date_end"] or "",
            row["practice_chief_name"] or "",
        ]
        for row in serialized_rows
    ]

    workbook = build_xlsx_bytes(
        sheet_name="Распределение по группам",
        headers=[
            "Кафедра",
            "Шифр направления",
            "Направление подготовки",
            "Профиль обучения",
            "Группа",
            "Курс",
            "Кол-во распределённых",
            "Наименование организации",
            "Номер приказа",
            "Дата подписания",
            "Наименование практики",
            "Дата начала",
            "Дата окончания",
            "Фамилия ИО руководителя",
        ],
        rows=export_rows,
    )

    export_filename = "Заявка_" + datetime.now().strftime("%d_%m_%Y_%H_%M_%S") + ".xlsx"
    quoted_filename = quote(export_filename)

    return Response(
        content=workbook,
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/organizations/active/export")
@router.post("/organizations/active/export", include_in_schema=False)
async def active_organizations_export(
    payload: ActiveOrganizationsTableRequest,
):
    async with async_session_maker() as session:
        rows = await fetch_all_active_organizations(
            session,
            payload.filters,
            custom_sort_requested=payload.custom_sort_requested,
        )

    serialized_rows = [serialize_active_row(row) for row in rows]
    export_rows = [
        [
            row["contract_number"] or "",
            row["signing_date"] or "",
            row["organization_name"] or "",
            row["settlement_name"] or "",
            "\n".join(row["study_fields"]),
            "\n".join(row["phones"]),
            "\n".join(row["digitals"]),
        ]
        for row in serialized_rows
    ]

    workbook = build_xlsx_bytes(
        sheet_name="Действующие организации",
        headers=[
            "Номер договора",
            "Дата заключения",
            "Наименование организации",
            "Населённый пункт",
            "Профильные направления",
            "Телефонные контакты",
            "Цифровые контакты",
        ],
        rows=export_rows,
    )

    export_filename = "Контакты_" + datetime.now().strftime("%d_%m_%Y_%H_%M_%S") + ".xlsx"
    quoted_filename = quote(export_filename)

    return Response(
        content=workbook,
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/api/organizations/search",
    response_model=OrganizationHeaderSearchResponse,
    name="organization_search_api",
)
async def organization_header_search(
    q: str = Query(default="", description="Search query by short name, full name or INN"),
    limit: int = Query(default=8, ge=1, le=20),
):
    normalized_query = q.strip()
    if len(normalized_query) < 2:
        return OrganizationHeaderSearchResponse(query=normalized_query, items=[])

    async with async_session_maker() as session:
        items = await search_organizations_for_header(
            session,
            query=normalized_query,
            limit=limit,
        )

    return OrganizationHeaderSearchResponse(query=normalized_query, items=items)


@router.post(
    "/api/organizations",
    response_model=OrganizationCardSaveResult,
    status_code=status.HTTP_201_CREATED,
    name="create_organization_api",
)
async def create_organization(
    payload: OrganizationCardSavePayload,
    _: None = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        try:
            organization_id = await save_organization_card(session, payload=payload)
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationCardSaveResult(
        organization_id=organization_id,
        message="Организация сохранена.",
        redirect_url=f"/organizations/{organization_id}",
    )


@router.put(
    "/api/organizations/{organization_id}",
    response_model=OrganizationCardSaveResult,
    name="update_organization_api",
)
async def update_organization(
    organization_id: int,
    payload: OrganizationCardSavePayload,
    _: None = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        try:
            saved_organization_id = await save_organization_card(
                session,
                organization_id=organization_id,
                payload=payload,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationCardSaveResult(
        organization_id=saved_organization_id,
        message="Изменения сохранены.",
    )


@router.post(
    "/api/organizations/{organization_id}/logo",
    response_model=OrganizationCardSaveResult,
    name="upload_organization_logo_api",
)
async def upload_organization_logo(
    organization_id: int,
    logo_file: UploadFile = File(...),
    _: None = Depends(require_editor_user),
):
    logo_bytes = await _read_upload_bytes(logo_file, max_bytes=_MAX_LOGO_SIZE_BYTES)
    async with async_session_maker() as session:
        try:
            await save_organization_logo(
                session,
                organization_id=organization_id,
                logo_bytes=logo_bytes,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationCardSaveResult(
        organization_id=organization_id,
        message="Логотип сохранён.",
    )


@router.delete(
    "/api/organizations/{organization_id}/logo",
    response_model=OrganizationCardSaveResult,
    name="delete_organization_logo_api",
)
async def remove_organization_logo(
    organization_id: int,
    _: None = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        try:
            await delete_organization_logo(
                session,
                organization_id=organization_id,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationCardSaveResult(
        organization_id=organization_id,
        message="Логотип удалён.",
    )


@router.post(
    "/api/organizations/{organization_id}/documents",
    response_model=OrganizationCardSaveResult,
    status_code=status.HTTP_201_CREATED,
    name="add_organization_document_api",
)
async def create_organization_document(
    organization_id: int,
    payload: OrganizationDocumentCreatePayload,
    _: None = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        try:
            await add_organization_document(
                session,
                organization_id=organization_id,
                payload=payload,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationCardSaveResult(
        organization_id=organization_id,
        message="Документ добавлен.",
    )


@router.put(
    "/api/organizations/{organization_id}/documents/{document_id}",
    response_model=OrganizationCardSaveResult,
    name="update_organization_document_api",
)
async def edit_organization_document(
    organization_id: int,
    document_id: int,
    name_primary: str | None = Form(default=None),
    name_secondary: str | None = Form(default=None),
    signing_date: date | None = Form(default=None),
    chief_name: str | None = Form(default=None),
    chief_post: str | None = Form(default=None),
    is_actual: bool = Form(default=False),
    pdf_file: UploadFile | None = File(default=None),
    _: None = Depends(require_editor_user),
):
    pdf_bytes = (
        await _read_upload_bytes(pdf_file, max_bytes=_MAX_PDF_SIZE_BYTES)
        if pdf_file is not None
        else None
    )
    payload = OrganizationDocumentUpdatePayload(
        name_primary=name_primary,
        name_secondary=name_secondary,
        signing_date=signing_date,
        chief_name=chief_name,
        chief_post=chief_post,
        is_actual=is_actual,
    )

    async with async_session_maker() as session:
        try:
            await update_organization_document(
                session,
                organization_id=organization_id,
                document_id=document_id,
                payload=payload,
                pdf_bytes=pdf_bytes,
                pdf_filename=pdf_file.filename if pdf_file is not None else None,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationCardSaveResult(
        organization_id=organization_id,
        message="Документ сохранён.",
    )


@router.get(
    "/api/organizations/{organization_id}/documents/{document_id}/pdf",
    name="organization_document_pdf_api",
)
async def get_document_pdf(
    organization_id: int,
    document_id: int,
):
    async with async_session_maker() as session:
        try:
            file_bytes, filename = await get_organization_document_pdf(
                session,
                organization_id=organization_id,
                document_id=document_id,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "/api/organizations/{organization_id}/documents/{document_id}/pdf",
    response_model=OrganizationCardSaveResult,
    name="delete_organization_document_pdf_api",
)
async def remove_document_pdf(
    organization_id: int,
    document_id: int,
    _: None = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        try:
            await delete_organization_document_pdf(
                session,
                organization_id=organization_id,
                document_id=document_id,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationCardSaveResult(
        organization_id=organization_id,
        message="PDF-файл документа удалён.",
    )


@router.post(
    "/api/organizations/{organization_id}/documents/{document_id}/archive",
    response_model=OrganizationCardSaveResult,
    name="archive_organization_document_api",
)
async def archive_document(
    organization_id: int,
    document_id: int,
    _: None = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        try:
            await archive_organization_document(
                session,
                organization_id=organization_id,
                document_id=document_id,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationCardSaveResult(
        organization_id=organization_id,
        message="Документ переведён в архив.",
    )


@router.delete(
    "/api/organizations/{organization_id}",
    response_model=OrganizationDeleteResult,
    name="delete_organization_api",
)
async def delete_organization(
    organization_id: int,
    _: None = Depends(require_editor_user),
):
    async with async_session_maker() as session:
        try:
            await delete_organization_safely(
                session,
                organization_id=organization_id,
            )
        except Exception as error:  # pragma: no cover - normalized below
            _raise_card_api_error(error)

    return OrganizationDeleteResult(
        organization_id=organization_id,
        message="Организация удалена.",
    )

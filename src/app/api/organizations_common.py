from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.app.database import async_session_maker
from src.app.schemas.organizations import (
    ActiveOrganizationsFilters,
    DistributionStatsFilters,
    GroupDistributionFilters,
    OrganizationCardPage,
    StudyDirectionsFilters,
)
from src.app.services.active_organizations import (
    fetch_active_organizations,
    fetch_active_organizations_count,
)
from src.app.services.distribution_stats import (
    fetch_distribution_stats_chart,
    fetch_distribution_stats_table,
    fetch_distribution_stats_years,
)
from src.app.services.group_distribution import (
    fetch_group_distribution,
    fetch_group_distribution_count,
    fetch_group_distribution_filter_options,
    resolve_group_distribution_filters,
)
from src.app.services.organization_card import fetch_organization_card_page
from src.app.services.organization_card_write import (
    fetch_contact_type_options,
    fetch_contract_type_options,
    fetch_requisite_type_options,
    fetch_settlement_options,
    fetch_study_field_options,
)
from src.app.services.organizations_page import (
    build_group_distribution_sort_links,
    build_sort_links,
    build_study_directions_sort_links,
    serialize_active_row,
    serialize_group_distribution_row,
    serialize_study_direction_row,
)
from src.app.services.study_directions import fetch_study_directions, fetch_study_directions_count

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


async def build_active_organizations_page_context(
    request: Request,
    filters: ActiveOrganizationsFilters,
    *,
    custom_sort_requested: bool,
) -> dict:
    async with async_session_maker() as session:
        rows, has_more = await fetch_active_organizations(
            session,
            filters,
            custom_sort_requested=custom_sort_requested,
        )
        result_count = await fetch_active_organizations_count(session, filters)

    prepared_rows = [serialize_active_row(row) for row in rows]
    rows_count = len(prepared_rows)
    next_offset = filters.offset + rows_count if has_more else None

    return {
        "request": request,
        "can_edit": bool(getattr(request.state, "can_edit", False)),
        "filters": filters,
        "custom_sort_requested": custom_sort_requested,
        "rows": prepared_rows,
        "result_count": result_count,
        "has_more": has_more,
        "next_offset": next_offset,
        "sort_links": build_sort_links(
            request,
            filters,
            custom_sort_requested=custom_sort_requested,
        ),
    }


async def build_study_directions_page_context(
    request: Request,
    filters: StudyDirectionsFilters,
    *,
    custom_sort_requested: bool,
) -> dict:
    async with async_session_maker() as session:
        rows, has_more = await fetch_study_directions(
            session,
            filters,
            custom_sort_requested=custom_sort_requested,
        )
        result_count = await fetch_study_directions_count(session, filters)

    prepared_rows = [serialize_study_direction_row(row) for row in rows]
    rows_count = len(prepared_rows)
    next_offset = filters.offset + rows_count if has_more else None

    return {
        "request": request,
        "can_edit": bool(getattr(request.state, "can_edit", False)),
        "filters": filters,
        "custom_sort_requested": custom_sort_requested,
        "rows": prepared_rows,
        "result_count": result_count,
        "has_more": has_more,
        "next_offset": next_offset,
        "sort_links": build_study_directions_sort_links(
            request,
            filters,
            custom_sort_requested=custom_sort_requested,
        ),
    }


async def build_group_distribution_page_context(
    request: Request,
    filters: GroupDistributionFilters,
    *,
    custom_sort_requested: bool,
) -> dict:
    async with async_session_maker() as session:
        filter_options = await fetch_group_distribution_filter_options(session)
        effective_filters, selected_semester = resolve_group_distribution_filters(
            filters,
            filter_options["semesters"],
        )
        rows, has_more = await fetch_group_distribution(
            session,
            effective_filters,
            custom_sort_requested=custom_sort_requested,
        )
        result_count = await fetch_group_distribution_count(session, effective_filters)

    prepared_rows = [serialize_group_distribution_row(row) for row in rows]
    rows_count = len(prepared_rows)
    next_offset = effective_filters.offset + rows_count if has_more else None

    return {
        "request": request,
        "can_edit": bool(getattr(request.state, "can_edit", False)),
        "filters": effective_filters,
        "custom_sort_requested": custom_sort_requested,
        "rows": prepared_rows,
        "result_count": result_count,
        "has_more": has_more,
        "next_offset": next_offset,
        "sort_links": build_group_distribution_sort_links(
            request,
            effective_filters,
            custom_sort_requested=custom_sort_requested,
        ),
        "semester_options": filter_options["semesters"],
        "selected_semester_label": (selected_semester["label"] if selected_semester else None),
    }


async def build_distribution_stats_page_context(
    request: Request,
    filters: DistributionStatsFilters,
) -> dict:
    async with async_session_maker() as session:
        years_payload = await fetch_distribution_stats_years(session)
        table_payload = await fetch_distribution_stats_table(session, filters)

    return {
        "request": request,
        "can_edit": bool(getattr(request.state, "can_edit", False)),
        "filters": filters,
        "years_payload": years_payload.model_dump(mode="json"),
        "table_payload": table_payload.model_dump(mode="json"),
    }


async def build_timeline_stats_page_context(
    request: Request,
    filters: DistributionStatsFilters,
) -> dict:
    async with async_session_maker() as session:
        years_payload = await fetch_distribution_stats_years(session)
        chart_payload = await fetch_distribution_stats_chart(session, filters)

    return {
        "request": request,
        "can_edit": bool(getattr(request.state, "can_edit", False)),
        "filters": filters,
        "years_payload": years_payload.model_dump(mode="json"),
        "chart_payload": chart_payload.model_dump(mode="json"),
    }


async def build_organization_detail_page_context(
    request: Request,
    organization_id: int,
) -> dict | None:
    async with async_session_maker() as session:
        organization = await fetch_organization_card_page(session, organization_id)
        contact_type_options = await fetch_contact_type_options(session)
        document_type_options = await fetch_contract_type_options(session)
        requisite_type_options = await fetch_requisite_type_options(session)
        settlement_options = await fetch_settlement_options(session)
        study_field_options = await fetch_study_field_options(session)

    if organization is None:
        return None

    organization_payload = organization.model_dump()
    return {
        "request": request,
        "can_edit": bool(getattr(request.state, "can_edit", False)),
        "active_tab": None,
        "create_mode": False,
        "organization": organization_payload,
        "contact_type_options": [option.model_dump() for option in contact_type_options],
        "document_type_options": [option.model_dump() for option in document_type_options],
        "requisite_type_options": [option.model_dump() for option in requisite_type_options],
        "settlement_options": [option.model_dump() for option in settlement_options],
        "study_field_options": [option.model_dump() for option in study_field_options],
        "page_title": (
            organization.name_short or organization.name_long or f"Организация #{organization.id}"
        ),
        "page_heading": (
            organization.name_short or organization.name_long or f"Организация #{organization.id}"
        ),
    }


async def build_new_organization_page_context(request: Request) -> dict:
    organization = OrganizationCardPage(id=0)
    async with async_session_maker() as session:
        contact_type_options = await fetch_contact_type_options(session)
        document_type_options = await fetch_contract_type_options(session)
        requisite_type_options = await fetch_requisite_type_options(session)
        settlement_options = await fetch_settlement_options(session)
        study_field_options = await fetch_study_field_options(session)
    return {
        "request": request,
        "can_edit": bool(getattr(request.state, "can_edit", False)),
        "active_tab": None,
        "create_mode": True,
        "organization": organization.model_dump(),
        "contact_type_options": [option.model_dump() for option in contact_type_options],
        "document_type_options": [option.model_dump() for option in document_type_options],
        "requisite_type_options": [option.model_dump() for option in requisite_type_options],
        "settlement_options": [option.model_dump() for option in settlement_options],
        "study_field_options": [option.model_dump() for option in study_field_options],
        "page_title": "Новая организация",
        "page_heading": "Создание организации",
    }

from datetime import date
from urllib.parse import urlencode

from fastapi import Request

from src.app.schemas.organizations import (
    ActiveOrganizationRow,
    ActiveOrganizationsFilters,
    GroupDistributionFilters,
    GroupDistributionRow,
    StudyDirectionRow,
    StudyDirectionsFilters,
)


def _build_sort_links(
    request: Request,
    *,
    sort_by: str,
    sort_dir: str,
    custom_sort_requested: bool = True,
    tracked_columns: list[str],
) -> dict[str, dict]:
    preserved_params = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key not in {"sort_by", "sort_dir"}
    ]

    def make(column: str) -> dict:
        is_active = custom_sort_requested and sort_by == column
        next_direction = "desc" if is_active and sort_dir == "asc" else "asc"
        current_direction = sort_dir if is_active else None

        query_items = preserved_params + [("sort_by", column), ("sort_dir", next_direction)]
        query_string = urlencode(query_items)
        url = f"{request.url.path}?{query_string}" if query_string else request.url.path

        return {
            "url": url,
            "is_active": is_active,
            "current_direction": current_direction,
            "next_direction": next_direction,
        }

    return {column: make(column) for column in tracked_columns}


def build_sort_links(
    request: Request,
    filters: ActiveOrganizationsFilters,
    custom_sort_requested: bool = True,
) -> dict[str, dict]:
    return _build_sort_links(
        request,
        sort_by=filters.sort_by,
        sort_dir=filters.sort_dir,
        custom_sort_requested=custom_sort_requested,
        tracked_columns=[
            "organization_name",
            "contract_number",
            "signing_date",
        ],
    )


def build_study_directions_sort_links(
    request: Request,
    filters: StudyDirectionsFilters,
    custom_sort_requested: bool = True,
) -> dict[str, dict]:
    return _build_sort_links(
        request,
        sort_by=filters.sort_by,
        sort_dir=filters.sort_dir,
        custom_sort_requested=custom_sort_requested,
        tracked_columns=[
            "faculty_name",
            "department_name",
            "study_direction_name",
            "study_direction_code",
            "organization_name",
        ],
    )


def build_group_distribution_sort_links(
    request: Request,
    filters: GroupDistributionFilters,
    custom_sort_requested: bool = True,
) -> dict[str, dict]:
    return _build_sort_links(
        request,
        sort_by=filters.sort_by,
        sort_dir=filters.sort_dir,
        custom_sort_requested=custom_sort_requested,
        tracked_columns=[
            "department_name",
            "study_direction_code",
            "study_direction_name",
            "study_profile_name",
            "group_name",
            "course",
            "distributed_quantity",
            "organization_name",
            "order_name",
            "signing_date",
            "practice_name",
            "practice_date_begin",
            "practice_date_end",
            "practice_chief_name",
        ],
    )


def _format_signing_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%d.%m.%Y")


def serialize_active_row(row_data: dict) -> dict:
    row = ActiveOrganizationRow.model_validate(dict(row_data))
    return {
        "organization_id": row.organization_id,
        "contract_number": row.contract_number,
        "signing_date": _format_signing_date(row.signing_date),
        "logotype_id": row.logotype_id,
        "organization_name": row.organization_name,
        "settlement_name": row.settlement_name,
        "study_fields": row.study_fields.splitlines() if row.study_fields else [],
        "phones": row.phones.splitlines() if row.phones else [],
        "digitals": row.digitals.splitlines() if row.digitals else [],
    }


def serialize_study_direction_row(row_data: dict) -> dict:
    row = StudyDirectionRow.model_validate(dict(row_data))
    return {
        "organization_id": row.organization_id,
        "logotype_id": row.logotype_id,
        "faculty_name": row.faculty_name,
        "department_name": row.department_name,
        "study_direction_name": row.study_direction_name,
        "study_direction_code": row.study_direction_code,
        "organization_name": row.organization_name,
        "phones": row.phones.splitlines() if row.phones else [],
        "digitals": row.digitals.splitlines() if row.digitals else [],
    }


def serialize_group_distribution_row(row_data: dict) -> dict:
    row = GroupDistributionRow.model_validate(dict(row_data))
    return {
        "organization_id": row.organization_id,
        "semester_id": row.semester_id,
        "department_name": row.department_name,
        "study_direction_code": row.study_direction_code,
        "study_direction_name": row.study_direction_name,
        "study_profile_name": row.study_profile_name,
        "group_name": row.group_name,
        "course": row.course,
        "distributed_quantity": row.distributed_quantity,
        "organization_name": row.organization_name,
        "order_name": row.order_name,
        "signing_date": row.signing_date,
        "practice_name": row.practice_name,
        "practice_date_begin": row.practice_date_begin,
        "practice_date_end": row.practice_date_end,
        "practice_chief_name": row.practice_chief_name,
    }

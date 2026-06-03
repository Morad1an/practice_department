from __future__ import annotations

import re
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.app.models.organization import OrganizationOrm
from src.app.models.practice_distributionorder import PracticeDistributionOrder
from src.app.models.practice_distributionorderblock import PracticeDistributionOrderBlock
from src.app.models.university_academicdepartment import UniversityAcademicDepartment
from src.app.models.university_studyfield import UniversityStudyField
from src.app.models.university_studysemester import UniversityStudySemester
from src.app.models.university_studyspeciality import UniversityStudySpeciality
from src.app.schemas.organizations import GroupDistributionFilters

SortBy = Literal[
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
]

_SEMESTER_NAME_RE = re.compile(r"^(?P<start>\d{4})/(?P<end>\d{4})\s*\|\s*(?P<season>.+)$")
_SEMESTER_SEASON_ORDER = {
    "Осенний семестр": 2,
    "Весенний семестр": 1,
}


def _semester_sort_key(option: dict) -> tuple[int, int, int, str]:
    label = str(option.get("label") or "").strip()
    match = _SEMESTER_NAME_RE.match(label)
    if not match:
        return (0, 0, 0, label)
    start_year = int(match.group("start"))
    end_year = int(match.group("end"))
    season = match.group("season").strip()
    season_order = _SEMESTER_SEASON_ORDER.get(season, 0)
    return (start_year, end_year, season_order, label)


def build_base_group_distribution_stmt() -> Select:
    return (
        select(
            PracticeDistributionOrderBlock.semester_id.label("semester_id"),
            PracticeDistributionOrderBlock.organization_id.label("organization_id"),
            UniversityAcademicDepartment.index_.label("department_name"),
            UniversityStudyField.code.label("study_direction_code"),
            UniversityStudyField.name.label("study_direction_name"),
            UniversityStudySpeciality.name.label("study_profile_name"),
            PracticeDistributionOrderBlock.group_.label("group_name"),
            PracticeDistributionOrderBlock.group_study_year.label("course"),
            PracticeDistributionOrderBlock.quantity.label("distributed_quantity"),
            OrganizationOrm.name_short.label("organization_name"),
            PracticeDistributionOrder.name_primary.label("order_name"),
            PracticeDistributionOrder.signing_date.label("signing_date"),
            PracticeDistributionOrderBlock.practice_name.label("practice_name"),
            PracticeDistributionOrderBlock.practice_date_begin.label("practice_date_begin"),
            PracticeDistributionOrderBlock.practice_date_end.label("practice_date_end"),
            PracticeDistributionOrderBlock.practice_chief_name.label("practice_chief_name"),
        )
        .select_from(PracticeDistributionOrderBlock)
        .outerjoin(
            UniversityAcademicDepartment,
            UniversityAcademicDepartment.id == PracticeDistributionOrderBlock.department_id,
        )
        .outerjoin(
            UniversityStudySpeciality,
            UniversityStudySpeciality.id == PracticeDistributionOrderBlock.study_speciality_id,
        )
        .outerjoin(
            UniversityStudyField,
            UniversityStudyField.id == UniversityStudySpeciality.study_field_id,
        )
        .outerjoin(
            OrganizationOrm,
            OrganizationOrm.id == PracticeDistributionOrderBlock.organization_id,
        )
        .outerjoin(
            PracticeDistributionOrder,
            PracticeDistributionOrder.id == PracticeDistributionOrderBlock.order_id,
        )
    )


def apply_filters(
    statement: Select,
    filters: GroupDistributionFilters,
) -> Select:
    if filters.semester_id is not None:
        statement = statement.where(
            PracticeDistributionOrderBlock.semester_id == filters.semester_id
        )
    return statement


def apply_sorting(
    statement: Select,
    filters: GroupDistributionFilters,
    custom_sort_requested: bool,
) -> Select:
    if not custom_sort_requested:
        return statement.order_by(
            UniversityAcademicDepartment.index_.asc(),
            UniversityStudyField.code.asc(),
            UniversityStudyField.name.asc(),
            UniversityStudySpeciality.name.asc(),
            PracticeDistributionOrderBlock.group_.asc(),
            PracticeDistributionOrderBlock.group_study_year.asc(),
            OrganizationOrm.name_short.asc(),
            PracticeDistributionOrderBlock.id.asc(),
            PracticeDistributionOrderBlock.order_id.asc(),
        )

    sort_columns: dict[SortBy, Any] = {
        "department_name": UniversityAcademicDepartment.index_,
        "study_direction_code": UniversityStudyField.code,
        "study_direction_name": UniversityStudyField.name,
        "study_profile_name": UniversityStudySpeciality.name,
        "group_name": PracticeDistributionOrderBlock.group_,
        "course": PracticeDistributionOrderBlock.group_study_year,
        "distributed_quantity": PracticeDistributionOrderBlock.quantity,
        "organization_name": OrganizationOrm.name_short,
        "order_name": PracticeDistributionOrder.name_primary,
        "signing_date": PracticeDistributionOrder.signing_date,
        "practice_name": PracticeDistributionOrderBlock.practice_name,
        "practice_date_begin": PracticeDistributionOrderBlock.practice_date_begin,
        "practice_date_end": PracticeDistributionOrderBlock.practice_date_end,
        "practice_chief_name": PracticeDistributionOrderBlock.practice_chief_name,
    }
    sort_column = sort_columns[filters.sort_by]
    sort_expr = sort_column.desc() if filters.sort_dir == "desc" else sort_column.asc()

    tie_breakers: list[Any] = [
        UniversityAcademicDepartment.index_.asc(),
        UniversityStudyField.code.asc(),
        UniversityStudyField.name.asc(),
        UniversityStudySpeciality.name.asc(),
        PracticeDistributionOrderBlock.group_.asc(),
        PracticeDistributionOrderBlock.group_study_year.asc(),
        PracticeDistributionOrderBlock.quantity.asc(),
        OrganizationOrm.name_short.asc(),
        PracticeDistributionOrder.name_primary.asc(),
        PracticeDistributionOrder.signing_date.asc(),
        PracticeDistributionOrderBlock.practice_name.asc(),
        PracticeDistributionOrderBlock.practice_date_begin.asc(),
        PracticeDistributionOrderBlock.practice_date_end.asc(),
        PracticeDistributionOrderBlock.practice_chief_name.asc(),
        PracticeDistributionOrderBlock.id.asc(),
        PracticeDistributionOrderBlock.order_id.asc(),
    ]
    excluded = {
        "department_name": {0},
        "study_direction_code": {1},
        "study_direction_name": {2},
        "study_profile_name": {3},
        "group_name": {4},
        "course": {5},
        "distributed_quantity": {6},
        "organization_name": {7},
        "order_name": {8},
        "signing_date": {9},
        "practice_name": {10},
        "practice_date_begin": {11},
        "practice_date_end": {12},
        "practice_chief_name": {13},
    }
    normalized_tie_breakers = [
        expr
        for index, expr in enumerate(tie_breakers)
        if index not in excluded.get(filters.sort_by, set())
    ]

    return statement.order_by(sort_expr, *normalized_tie_breakers)


def apply_pagination(
    statement: Select,
    filters: GroupDistributionFilters,
    fetch_extra_row: bool,
) -> Select:
    effective_limit = filters.limit + 1 if fetch_extra_row else filters.limit
    return statement.limit(effective_limit).offset(filters.offset)


def build_group_distribution_statement(
    filters: GroupDistributionFilters,
    *,
    custom_sort_requested: bool = False,
    fetch_extra_row: bool = False,
    paginate: bool = True,
) -> Select:
    statement = build_base_group_distribution_stmt()
    statement = apply_filters(statement, filters)
    statement = apply_sorting(
        statement=statement,
        filters=filters,
        custom_sort_requested=custom_sort_requested,
    )
    if not paginate:
        return statement
    return apply_pagination(statement, filters, fetch_extra_row=fetch_extra_row)


async def fetch_group_distribution(
    session: AsyncSession,
    filters: GroupDistributionFilters,
    *,
    custom_sort_requested: bool = False,
):
    statement = build_group_distribution_statement(
        filters=filters,
        custom_sort_requested=custom_sort_requested,
        fetch_extra_row=True,
    )
    result = await session.execute(statement)
    rows = result.mappings().all()
    has_more = len(rows) > filters.limit
    return rows[: filters.limit], has_more


async def fetch_all_group_distribution(
    session: AsyncSession,
    filters: GroupDistributionFilters,
    *,
    custom_sort_requested: bool = False,
):
    statement = build_group_distribution_statement(
        filters=filters,
        custom_sort_requested=custom_sort_requested,
        paginate=False,
    )
    result = await session.execute(statement)
    return result.mappings().all()


async def fetch_group_distribution_count(
    session: AsyncSession,
    filters: GroupDistributionFilters,
):
    count_statement = (
        apply_filters(build_base_group_distribution_stmt(), filters)
        .order_by(None)
        .subquery("group_distribution_count_sq")
    )
    result = await session.execute(select(func.count()).select_from(count_statement))
    return int(result.scalar_one())


async def fetch_group_distribution_filter_options(session: AsyncSession):
    statement = (
        select(
            UniversityStudySemester.id.label("value"),
            UniversityStudySemester.name.label("label"),
            func.count(PracticeDistributionOrderBlock.id).label("record_count"),
        )
        .select_from(UniversityStudySemester)
        .outerjoin(
            PracticeDistributionOrderBlock,
            PracticeDistributionOrderBlock.semester_id == UniversityStudySemester.id,
        )
        .group_by(UniversityStudySemester.id, UniversityStudySemester.name)
    )
    result = await session.execute(statement)
    rows = [
        {
            "value": int(row.value),
            "label": row.label or f"Семестр #{row.value}",
            "record_count": int(row.record_count or 0),
        }
        for row in result
    ]
    rows.sort(key=_semester_sort_key, reverse=True)
    return {"semesters": rows}


def resolve_group_distribution_filters(
    filters: GroupDistributionFilters,
    semester_options: list[dict],
) -> tuple[GroupDistributionFilters, dict | None]:
    if not semester_options:
        return filters, None

    selected_option = next(
        (option for option in semester_options if option["value"] == filters.semester_id),
        None,
    )
    if selected_option is not None:
        return filters, selected_option

    default_option = next(
        (option for option in semester_options if option.get("record_count", 0) > 0),
        semester_options[0],
    )
    normalized_filters = filters.model_copy(
        update={
            "semester_id": default_option["value"],
            "offset": 0,
        }
    )
    return normalized_filters, default_option

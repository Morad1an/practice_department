from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.app.models.detailname_contactdata import DetailnameContactData
from src.app.models.organization import OrganizationOrm
from src.app.models.organization_detailcontactdata import OrganizationDetailContactData
from src.app.models.organization_detailcontactentity import OrganizationDetailContactEntity
from src.app.models.organization_detailstudyfield import OrganizationDetailStudyField
from src.app.models.university_academicdepartment import UniversityAcademicDepartment
from src.app.models.university_academicfaculty import UniversityAcademicFaculty
from src.app.models.university_studyfield import UniversityStudyField
from src.app.models.university_studyspeciality import UniversityStudySpeciality
from src.app.schemas.organizations import StudyDirectionsFilters

SortBy = Literal[
    "faculty_name",
    "department_name",
    "study_direction_name",
    "study_direction_code",
    "organization_name",
]

PHONE_CONTACT_TYPE_IDS = (1, 2)
DIGITAL_CONTACT_TYPE_IDS = (3, 4, 5)


def build_phone_contacts_subquery():
    return (
        select(
            OrganizationDetailContactEntity.organization_id.label("organization_id"),
            func.group_concat(
                literal_column(
                    "organization_detailcontactdata.data "
                    "ORDER BY detailname_contactdata.id "
                    "SEPARATOR '\\n'"
                )
            ).label("phone_contacts"),
        )
        .select_from(OrganizationDetailContactEntity)
        .join(
            OrganizationDetailContactData,
            OrganizationDetailContactData.entity_id == OrganizationDetailContactEntity.id,
        )
        .outerjoin(
            DetailnameContactData,
            DetailnameContactData.id == OrganizationDetailContactData.type_id,
        )
        .where(OrganizationDetailContactData.type_id.in_(PHONE_CONTACT_TYPE_IDS))
        .group_by(OrganizationDetailContactEntity.organization_id)
        .subquery("study_directions_phone_contacts_sq")
    )


def build_digital_contacts_subquery():
    return (
        select(
            OrganizationDetailContactEntity.organization_id.label("organization_id"),
            func.group_concat(
                literal_column(
                    "organization_detailcontactdata.data "
                    "ORDER BY detailname_contactdata.id "
                    "SEPARATOR '\\n'"
                )
            ).label("digital_contacts"),
        )
        .select_from(OrganizationDetailContactEntity)
        .join(
            OrganizationDetailContactData,
            OrganizationDetailContactData.entity_id == OrganizationDetailContactEntity.id,
        )
        .outerjoin(
            DetailnameContactData,
            DetailnameContactData.id == OrganizationDetailContactData.type_id,
        )
        .where(OrganizationDetailContactData.type_id.in_(DIGITAL_CONTACT_TYPE_IDS))
        .group_by(OrganizationDetailContactEntity.organization_id)
        .subquery("study_directions_digital_contacts_sq")
    )


def build_study_field_department_subquery():
    return (
        select(
            UniversityStudySpeciality.study_field_id.label("study_field_id"),
            UniversityStudySpeciality.department_id.label("department_id"),
        )
        .distinct()
        .subquery("study_directions_speciality_sq")
    )


def _normalize_multi_text_filter(values: list[str] | None) -> list[str]:
    if not values:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        normalized.append(stripped)
    return normalized


def build_base_study_directions_stmt() -> Select:
    phone_contacts_sq = build_phone_contacts_subquery()
    digital_contacts_sq = build_digital_contacts_subquery()
    study_field_department_sq = build_study_field_department_subquery()

    return (
        select(
            UniversityAcademicFaculty.litera.label("faculty_name"),
            UniversityAcademicDepartment.index_.label("department_name"),
            UniversityStudyField.name.label("study_direction_name"),
            UniversityStudyField.code.label("study_direction_code"),
            OrganizationOrm.logotype_id.label("logotype_id"),
            OrganizationOrm.id.label("organization_id"),
            OrganizationOrm.name_short.label("organization_name"),
            phone_contacts_sq.c.phone_contacts.label("phones"),
            digital_contacts_sq.c.digital_contacts.label("digitals"),
        )
        .select_from(OrganizationOrm)
        .outerjoin(phone_contacts_sq, phone_contacts_sq.c.organization_id == OrganizationOrm.id)
        .outerjoin(digital_contacts_sq, digital_contacts_sq.c.organization_id == OrganizationOrm.id)
        .join(
            OrganizationDetailStudyField,
            OrganizationDetailStudyField.organization_id == OrganizationOrm.id,
        )
        .join(
            study_field_department_sq,
            study_field_department_sq.c.study_field_id
            == OrganizationDetailStudyField.study_field_id,
        )
        .join(
            UniversityStudyField,
            UniversityStudyField.id == OrganizationDetailStudyField.study_field_id,
        )
        .join(
            UniversityAcademicDepartment,
            UniversityAcademicDepartment.id == study_field_department_sq.c.department_id,
        )
        .join(
            UniversityAcademicFaculty,
            UniversityAcademicFaculty.id == UniversityAcademicDepartment.faculty_id,
        )
        .where(OrganizationOrm.is_active == 1)
    )


def apply_filters(
    statement: Select,
    filters: StudyDirectionsFilters,
    *,
    exclude_fields: set[str] | None = None,
) -> Select:
    excluded = exclude_fields or set()
    faculty_names = _normalize_multi_text_filter(filters.faculty_names)
    department_names = _normalize_multi_text_filter(filters.department_names)
    study_direction_names = _normalize_multi_text_filter(filters.study_direction_names)
    study_direction_codes = _normalize_multi_text_filter(filters.study_direction_codes)
    organization_names = _normalize_multi_text_filter(filters.organization_names)

    if faculty_names and "faculty_names" not in excluded:
        statement = statement.where(UniversityAcademicFaculty.litera.in_(faculty_names))

    if department_names and "department_names" not in excluded:
        statement = statement.where(UniversityAcademicDepartment.index_.in_(department_names))

    if study_direction_names and "study_direction_names" not in excluded:
        statement = statement.where(UniversityStudyField.name.in_(study_direction_names))

    if study_direction_codes and "study_direction_codes" not in excluded:
        statement = statement.where(UniversityStudyField.code.in_(study_direction_codes))

    if organization_names and "organization_names" not in excluded:
        statement = statement.where(OrganizationOrm.name_short.in_(organization_names))

    return statement


def apply_sorting(
    statement: Select,
    filters: StudyDirectionsFilters,
    custom_sort_requested: bool,
) -> Select:
    if not custom_sort_requested:
        return statement.order_by(
            OrganizationOrm.name_short.asc(),
            UniversityStudyField.name.asc(),
            UniversityAcademicDepartment.index_.asc(),
            UniversityAcademicFaculty.litera.asc(),
            OrganizationOrm.id.asc(),
        )

    sort_columns: dict[SortBy, Any] = {
        "faculty_name": UniversityAcademicFaculty.litera,
        "department_name": UniversityAcademicDepartment.index_,
        "study_direction_name": UniversityStudyField.name,
        "study_direction_code": UniversityStudyField.code,
        "organization_name": OrganizationOrm.name_short,
    }
    sort_column = sort_columns[filters.sort_by]
    sort_expr = sort_column.desc() if filters.sort_dir == "desc" else sort_column.asc()

    tie_breakers: list[Any] = [
        UniversityAcademicFaculty.litera.asc(),
        UniversityAcademicDepartment.index_.asc(),
        UniversityStudyField.name.asc(),
        UniversityStudyField.code.asc(),
        OrganizationOrm.name_short.asc(),
        OrganizationOrm.id.asc(),
    ]
    if filters.sort_by == "faculty_name":
        tie_breakers = tie_breakers[1:]
    elif filters.sort_by == "department_name":
        tie_breakers = [tie_breakers[0], *tie_breakers[2:]]
    elif filters.sort_by == "study_direction_name":
        tie_breakers = [tie_breakers[0], tie_breakers[1], *tie_breakers[3:]]
    elif filters.sort_by == "study_direction_code":
        tie_breakers = [tie_breakers[0], tie_breakers[1], tie_breakers[2], *tie_breakers[4:]]
    elif filters.sort_by == "organization_name":
        tie_breakers = tie_breakers[:-2]

    return statement.order_by(sort_expr, *tie_breakers)


def apply_pagination(
    statement: Select,
    filters: StudyDirectionsFilters,
    fetch_extra_row: bool,
) -> Select:
    effective_limit = filters.limit + 1 if fetch_extra_row else filters.limit
    return statement.limit(effective_limit).offset(filters.offset)


def build_study_directions_statement(
    filters: StudyDirectionsFilters,
    *,
    custom_sort_requested: bool = False,
    fetch_extra_row: bool = False,
    paginate: bool = True,
) -> Select:
    statement = build_base_study_directions_stmt()
    statement = apply_filters(statement, filters)
    statement = apply_sorting(
        statement=statement,
        filters=filters,
        custom_sort_requested=custom_sort_requested,
    )
    if not paginate:
        return statement
    return apply_pagination(statement, filters, fetch_extra_row=fetch_extra_row)


async def fetch_study_directions(
    session: AsyncSession,
    filters: StudyDirectionsFilters,
    *,
    custom_sort_requested: bool = False,
):
    statement = build_study_directions_statement(
        filters=filters,
        custom_sort_requested=custom_sort_requested,
        fetch_extra_row=True,
    )
    result = await session.execute(statement)
    rows = result.mappings().all()
    has_more = len(rows) > filters.limit
    return rows[: filters.limit], has_more


async def fetch_all_study_directions(
    session: AsyncSession,
    filters: StudyDirectionsFilters,
    *,
    custom_sort_requested: bool = False,
):
    statement = build_study_directions_statement(
        filters=filters,
        custom_sort_requested=custom_sort_requested,
        paginate=False,
    )
    result = await session.execute(statement)
    return result.mappings().all()


async def fetch_study_directions_count(
    session: AsyncSession,
    filters: StudyDirectionsFilters,
):
    count_statement = (
        apply_filters(build_base_study_directions_stmt(), filters)
        .order_by(None)
        .subquery("study_directions_count_sq")
    )
    result = await session.execute(select(func.count()).select_from(count_statement))
    return int(result.scalar_one())


def _build_filter_options_query(
    column_name: Literal[
        "faculty_name",
        "department_name",
        "study_direction_name",
        "study_direction_code",
        "organization_name",
    ],
    filters: StudyDirectionsFilters,
    *,
    exclude_fields: set[str],
) -> Select:
    filtered_base_sq = apply_filters(
        build_base_study_directions_stmt(),
        filters,
        exclude_fields=exclude_fields,
    ).subquery(f"{column_name}_study_directions_filter_options_sq")

    option_column = getattr(filtered_base_sq.c, column_name)
    return (
        select(option_column.label("value"))
        .where(option_column.is_not(None))
        .distinct()
        .order_by(option_column.asc())
    )


async def fetch_study_directions_filter_options(
    session: AsyncSession,
    filters: StudyDirectionsFilters,
):
    faculties_result = await session.execute(
        _build_filter_options_query(
            "faculty_name",
            filters,
            exclude_fields={"faculty_names"},
        )
    )
    departments_result = await session.execute(
        _build_filter_options_query(
            "department_name",
            filters,
            exclude_fields={"department_names"},
        )
    )
    study_direction_names_result = await session.execute(
        _build_filter_options_query(
            "study_direction_name",
            filters,
            exclude_fields={"study_direction_names"},
        )
    )
    study_direction_codes_result = await session.execute(
        _build_filter_options_query(
            "study_direction_code",
            filters,
            exclude_fields={"study_direction_codes"},
        )
    )
    organizations_result = await session.execute(
        _build_filter_options_query(
            "organization_name",
            filters,
            exclude_fields={"organization_names"},
        )
    )

    def serialize(values: list[str]) -> list[dict[str, str]]:
        return [{"value": value, "label": value} for value in values]

    return {
        "faculties": serialize(list(faculties_result.scalars().all())),
        "departments": serialize(list(departments_result.scalars().all())),
        "study_direction_names": serialize(list(study_direction_names_result.scalars().all())),
        "study_direction_codes": serialize(list(study_direction_codes_result.scalars().all())),
        "organizations": serialize(list(organizations_result.scalars().all())),
    }

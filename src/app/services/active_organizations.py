from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import Integer, cast, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.app.models.contract import ContractOrm
from src.app.models.contract_datatype import ContractDatatype
from src.app.models.detailname_contactdata import DetailnameContactData
from src.app.models.detailname_settlement import DetailnameSettlement
from src.app.models.organization import OrganizationOrm
from src.app.models.organization_detailcontactdata import OrganizationDetailContactData
from src.app.models.organization_detailcontactentity import OrganizationDetailContactEntity
from src.app.models.organization_detailstudyfield import OrganizationDetailStudyField
from src.app.models.university_studyfield import UniversityStudyField
from src.app.schemas.organizations import ActiveOrganizationsFilters

SortBy = Literal[
    "organization_name",
    "contract_number",
    "signing_date",
    "settlement_name",
]

PHONE_CONTACT_TYPE_IDS = (1, 2)
DIGITAL_CONTACT_TYPE_IDS = (3, 4, 5)
CONTRACT_DATATYPE_NAME_TO_ID = {
    "Договор о практической подготовке обучающихся": 1,
    "Соглашение о сотрудничестве": 2,
    "План мероприятий": 3,
    "Соглашение о сотрудничестве (целевое)": 4,
    "Соглашение о сотрудничестве в области образования и профориентационной работы (профориентация)": 5,
    "Лицензионный договор": 6,
    "Договор о сетевой форме реализации образовательных программ": 7,
    "Соглашение о конфиденциальности": 8,
    "Соглашение о научно-техническом сотрудничестве": 9,
    "Соглашение о международном сотрудничестве": 10,
    "Соглашения о намерениях реализации программы производственной аспирантуры": 11,
}


def build_study_fields_subquery():
    return (
        select(
            OrganizationDetailStudyField.organization_id.label("organization_id"),
            func.group_concat(
                literal_column(
                    "university_studyfield.code "
                    "ORDER BY university_studyfield.code "
                    "SEPARATOR '\\n'"
                )
            ).label("study_fields"),
        )
        .select_from(OrganizationDetailStudyField)
        .outerjoin(
            UniversityStudyField,
            UniversityStudyField.id == OrganizationDetailStudyField.study_field_id,
        )
        .group_by(OrganizationDetailStudyField.organization_id)
        .subquery("study_fields_sq")
    )


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
        .subquery("phone_contacts_sq")
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
        .subquery("digital_contacts_sq")
    )


def build_actual_datatype_count_subquery():
    return (
        select(
            ContractOrm.organization_id.label("organization_id"),
            func.count(func.distinct(ContractOrm.datatype_id)).label("actual_datatype_count"),
        )
        .where(ContractOrm.is_actual == 1)
        .group_by(ContractOrm.organization_id)
        .subquery("actual_datatype_count_sq")
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


def build_base_active_orgs_stmt():
    study_fields_sq = build_study_fields_subquery()
    phone_contacts_sq = build_phone_contacts_subquery()
    digital_contacts_sq = build_digital_contacts_subquery()

    statement = (
        select(
            OrganizationOrm.id.label("organization_id"),
            ContractOrm.name_primary.label("contract_number"),
            ContractOrm.signing_date.label("signing_date"),
            OrganizationOrm.logotype_id.label("logotype_id"),
            OrganizationOrm.name_short.label("organization_name"),
            DetailnameSettlement.name.label("settlement_name"),
            study_fields_sq.c.study_fields.label("study_fields"),
            phone_contacts_sq.c.phone_contacts.label("phones"),
            digital_contacts_sq.c.digital_contacts.label("digitals"),
        )
        .select_from(OrganizationOrm)
        .outerjoin(ContractOrm, ContractOrm.organization_id == OrganizationOrm.id)
        .outerjoin(ContractDatatype, ContractDatatype.id == ContractOrm.datatype_id)
        .outerjoin(DetailnameSettlement, DetailnameSettlement.id == OrganizationOrm.settlement_id)
        .outerjoin(study_fields_sq, study_fields_sq.c.organization_id == OrganizationOrm.id)
        .outerjoin(phone_contacts_sq, phone_contacts_sq.c.organization_id == OrganizationOrm.id)
        .outerjoin(digital_contacts_sq, digital_contacts_sq.c.organization_id == OrganizationOrm.id)
    )
    return statement


def build_filter_options_base_stmt() -> Select:
    return (
        select(
            OrganizationOrm.name_short.label("organization_name"),
            ContractOrm.name_primary.label("contract_number"),
            DetailnameSettlement.name.label("settlement_name"),
        )
        .select_from(OrganizationOrm)
        .outerjoin(ContractOrm, ContractOrm.organization_id == OrganizationOrm.id)
        .outerjoin(ContractDatatype, ContractDatatype.id == ContractOrm.datatype_id)
        .outerjoin(DetailnameSettlement, DetailnameSettlement.id == OrganizationOrm.settlement_id)
    )


def apply_filters(
    statement: Select,
    filters: ActiveOrganizationsFilters,
    *,
    exclude_fields: set[str] | None = None,
) -> Select:
    excluded = exclude_fields or set()
    organization_names = _normalize_multi_text_filter(filters.organization_names)
    contract_numbers = _normalize_multi_text_filter(filters.contract_numbers)
    settlement_names = _normalize_multi_text_filter(filters.settlement_names)
    contract_datatype_names = _normalize_multi_text_filter(filters.contract_datatype_names)
    university_department_mode = (
        filters.only_university_departments and "only_university_departments" not in excluded
    )
    should_filter_organization_status = (
        not university_department_mode and "only_active_organizations" not in excluded
    )
    should_filter_contract_status = (
        not university_department_mode and "only_actual_contracts" not in excluded
    )

    should_require_contract_details = (
        (bool(contract_numbers) and "contract_numbers" not in excluded)
        or (bool(contract_datatype_names) and "contract_datatype_names" not in excluded)
        or should_filter_contract_status
    )

    if should_require_contract_details:
        statement = statement.where(
            ContractOrm.name_primary.is_not(None),
            ContractOrm.signing_date.is_not(None),
        )

    if should_filter_organization_status:
        if filters.only_active_organizations:
            statement = statement.where(OrganizationOrm.is_active == 1)
        else:
            statement = statement.where(func.coalesce(OrganizationOrm.is_active, 0) != 1)

    if should_filter_contract_status:
        if filters.only_actual_contracts:
            statement = statement.where(ContractOrm.is_actual == 1)
        else:
            statement = statement.where(func.coalesce(ContractOrm.is_actual, 0) != 1)

    if university_department_mode:
        statement = statement.where(OrganizationOrm.is_university_department == 1)

    if organization_names and "organization_names" not in excluded:
        statement = statement.where(OrganizationOrm.name_short.in_(organization_names))

    if contract_numbers and "contract_numbers" not in excluded:
        statement = statement.where(ContractOrm.name_primary.in_(contract_numbers))

    if settlement_names and "settlement_names" not in excluded:
        statement = statement.where(DetailnameSettlement.name.in_(settlement_names))

    if contract_datatype_names and "contract_datatype_names" not in excluded:
        datatype_ids = [
            CONTRACT_DATATYPE_NAME_TO_ID[value]
            for value in contract_datatype_names
            if value in CONTRACT_DATATYPE_NAME_TO_ID
        ]
        if datatype_ids:
            statement = statement.where(ContractOrm.datatype_id.in_(datatype_ids))

    return statement


def apply_sorting(
    statement: Select,
    filters: ActiveOrganizationsFilters,
    actual_datatype_count_sq,
    custom_sort_requested: bool,
) -> Select:
    if not custom_sort_requested:
        if actual_datatype_count_sq is None:
            raise ValueError("actual_datatype_count_sq is required for default sorting")
        return statement.order_by(
            func.coalesce(actual_datatype_count_sq.c.actual_datatype_count, 0).desc(),
            OrganizationOrm.name_short.asc(),
            ContractOrm.id.asc(),
        )

    contract_number_digits = func.regexp_replace(
        func.coalesce(ContractOrm.name_primary, ""),
        "[^0-9]",
        "",
    )
    contract_number_as_int = func.coalesce(
        cast(func.nullif(contract_number_digits, ""), Integer),
        0,
    )

    sort_columns: dict[SortBy, Any] = {
        "organization_name": OrganizationOrm.name_short,
        "contract_number": contract_number_as_int,
        "signing_date": ContractOrm.signing_date,
        "settlement_name": DetailnameSettlement.name,
    }
    sort_column = sort_columns[filters.sort_by]
    sort_expr = sort_column.desc() if filters.sort_dir == "desc" else sort_column.asc()

    tie_breakers: list[Any] = [ContractOrm.id.asc()]
    if filters.sort_by == "contract_number":
        tie_breakers.insert(0, ContractOrm.name_primary.asc())
    if filters.sort_by != "organization_name":
        tie_breakers.insert(0, OrganizationOrm.name_short.asc())

    return statement.order_by(sort_expr, *tie_breakers)


def apply_pagination(
    statement: Select,
    filters: ActiveOrganizationsFilters,
    fetch_extra_row: bool,
) -> Select:
    effective_limit = filters.limit + 1 if fetch_extra_row else filters.limit
    return statement.limit(effective_limit).offset(filters.offset)


def build_active_organizations_statement(
    filters: ActiveOrganizationsFilters,
    *,
    custom_sort_requested: bool = False,
    fetch_extra_row: bool = False,
    paginate: bool = True,
) -> Select:
    statement = build_base_active_orgs_stmt()
    actual_datatype_count_sq = None
    if not custom_sort_requested:
        actual_datatype_count_sq = build_actual_datatype_count_subquery()
        statement = statement.outerjoin(
            actual_datatype_count_sq,
            actual_datatype_count_sq.c.organization_id == OrganizationOrm.id,
        )

    statement = apply_filters(statement, filters)
    statement = apply_sorting(
        statement=statement,
        filters=filters,
        actual_datatype_count_sq=actual_datatype_count_sq,
        custom_sort_requested=custom_sort_requested,
    )
    if not paginate:
        return statement
    return apply_pagination(statement, filters, fetch_extra_row=fetch_extra_row)


async def fetch_active_organizations(
    session: AsyncSession,
    filters: ActiveOrganizationsFilters,
    *,
    custom_sort_requested: bool = False,
):
    statement = build_active_organizations_statement(
        filters=filters,
        custom_sort_requested=custom_sort_requested,
        fetch_extra_row=True,
    )
    result = await session.execute(statement)
    rows = result.mappings().all()
    has_more = len(rows) > filters.limit
    return rows[: filters.limit], has_more


async def fetch_all_active_organizations(
    session: AsyncSession,
    filters: ActiveOrganizationsFilters,
    *,
    custom_sort_requested: bool = False,
):
    statement = build_active_organizations_statement(
        filters=filters,
        custom_sort_requested=custom_sort_requested,
        paginate=False,
    )
    result = await session.execute(statement)
    return result.mappings().all()


async def fetch_active_organizations_count(
    session: AsyncSession,
    filters: ActiveOrganizationsFilters,
):
    count_statement = (
        apply_filters(build_base_active_orgs_stmt(), filters)
        .order_by(None)
        .subquery("active_organizations_count_sq")
    )
    result = await session.execute(select(func.count()).select_from(count_statement))
    return int(result.scalar_one())


def _build_filter_options_query(
    column_name: Literal["organization_name", "contract_number", "settlement_name"],
    filters: ActiveOrganizationsFilters,
    *,
    exclude_fields: set[str],
) -> Select:
    filtered_base_sq = apply_filters(
        build_filter_options_base_stmt(),
        filters,
        exclude_fields=exclude_fields,
    ).subquery(f"{column_name}_filter_options_sq")

    option_column = getattr(filtered_base_sq.c, column_name)
    return (
        select(option_column.label("value"))
        .where(option_column.is_not(None))
        .distinct()
        .order_by(option_column.asc())
    )


async def fetch_active_organizations_filter_options(
    session: AsyncSession,
    filters: ActiveOrganizationsFilters,
):
    organizations_result = await session.execute(
        _build_filter_options_query(
            "organization_name",
            filters,
            exclude_fields={"organization_names"},
        )
    )
    contract_numbers_result = await session.execute(
        _build_filter_options_query(
            "contract_number",
            filters,
            exclude_fields={"contract_numbers"},
        )
    )
    settlements_result = await session.execute(
        _build_filter_options_query(
            "settlement_name",
            filters,
            exclude_fields={"settlement_names"},
        )
    )

    def serialize(values: list[str]) -> list[dict[str, str]]:
        return [{"value": value, "label": value} for value in values]

    return {
        "organizations": serialize(list(organizations_result.scalars().all())),
        "contract_numbers": serialize(list(contract_numbers_result.scalars().all())),
        "settlements": serialize(list(settlements_result.scalars().all())),
    }

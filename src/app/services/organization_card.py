from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.contract import ContractOrm
from src.app.models.contract_datatype import ContractDatatype
from src.app.models.contract_pdfdocument import ContractPdfDocument
from src.app.models.detailname_contactdata import DetailnameContactData
from src.app.models.detailname_legalinformation import DetailnameLegalInformation
from src.app.models.detailname_settlement import DetailnameSettlement
from src.app.models.organization import OrganizationOrm
from src.app.models.organization_detailcontactdata import OrganizationDetailContactData
from src.app.models.organization_detailcontactdata_local import OrganizationDetailContactDataLocal
from src.app.models.organization_detailcontactentity import OrganizationDetailContactEntity
from src.app.models.organization_detailcontactentity_local import (
    OrganizationDetailContactEntityLocal,
)
from src.app.models.organization_detaillegalinformation import OrganizationDetailLegalInformation
from src.app.models.organization_detaillogotype import OrganizationDetailLogotype
from src.app.models.organization_detailstudyfield import OrganizationDetailStudyField
from src.app.models.university_studyfield import UniversityStudyField
from src.app.schemas.organizations import (
    OrganizationCardContactGroup,
    OrganizationCardContactRow,
    OrganizationCardDocument,
    OrganizationCardDocumentGroup,
    OrganizationCardPage,
    OrganizationCardRequisite,
    OrganizationCardStudyField,
)
from src.app.services.logotype_utils import build_logo_data_url


def _build_study_field_label(code: str | None, name: str | None) -> str:
    code = (code or "").strip()
    name = (name or "").strip()
    if code and name:
        return f"{code} {name}"
    return code or name or "—"


def _build_document_title(
    primary_name: str | None,
    secondary_name: str | None,
    datatype_name: str | None,
) -> str:
    primary_name = (primary_name or "").strip()
    secondary_name = (secondary_name or "").strip()
    datatype_name = (datatype_name or "").strip()
    return primary_name or secondary_name or datatype_name or "Документ без названия"


def _build_document_subtitle(
    secondary_name: str | None,
    datatype_name: str | None,
) -> str | None:
    secondary_name = (secondary_name or "").strip()
    datatype_name = (datatype_name or "").strip()
    if secondary_name and datatype_name:
        return f"{datatype_name} · {secondary_name}"
    return datatype_name or secondary_name or None


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _group_contact_rows(
    rows: list[OrganizationCardContactRow],
) -> list[OrganizationCardContactGroup]:
    groups: list[OrganizationCardContactGroup] = []
    groups_by_entity_id: dict[int, OrganizationCardContactGroup] = {}
    for row in rows:
        group = groups_by_entity_id.get(row.entity_id)
        if group is None:
            group = OrganizationCardContactGroup(
                entity_id=row.entity_id,
                contact_name=row.contact_name,
                contact_post=row.contact_post,
            )
            groups_by_entity_id[row.entity_id] = group
            groups.append(group)
        group.contacts.append(row)
    return groups


def _split_custom_requisite_value(
    label: str,
    value: str | None,
) -> tuple[str, str | None, str | None]:
    base_label = _normalize_text(label) or "Реквизит"
    clean_value = _normalize_text(value)
    if base_label.lower() != "другое" or ":" not in clean_value:
        return base_label, None, value

    custom_label, custom_value = clean_value.split(":", 1)
    custom_label = _normalize_text(custom_label)
    custom_value = _normalize_text(custom_value)
    if not custom_label or not custom_value:
        return base_label, None, value

    return f"{base_label} ({custom_label})", custom_label, custom_value


def _extract_map_query(
    requisites: list[OrganizationCardRequisite],
    settlement_name: str | None,
) -> str | None:
    for requisite in requisites:
        label = _normalize_text(requisite.label).lower()
        if "фактичес" not in label or "адрес" not in label:
            continue
        value = _normalize_text(requisite.value)
        if value:
            return value

    return _normalize_text(settlement_name) or None


async def _fetch_logo_data_url(
    session: AsyncSession,
    logotype_id: int | None,
) -> str | None:
    if not logotype_id:
        return None

    result = await session.execute(
        select(OrganizationDetailLogotype.compressed).where(
            OrganizationDetailLogotype.id == logotype_id
        )
    )
    return build_logo_data_url(result.scalar_one_or_none())


async def _fetch_study_fields(
    session: AsyncSession,
    organization_id: int,
) -> list[OrganizationCardStudyField]:
    result = await session.execute(
        select(
            OrganizationDetailStudyField.study_field_id.label("id"),
            UniversityStudyField.code,
            UniversityStudyField.name,
        )
        .select_from(OrganizationDetailStudyField)
        .outerjoin(
            UniversityStudyField,
            UniversityStudyField.id == OrganizationDetailStudyField.study_field_id,
        )
        .where(OrganizationDetailStudyField.organization_id == organization_id)
        .order_by(
            UniversityStudyField.code.asc(),
            UniversityStudyField.name.asc(),
            OrganizationDetailStudyField.id.asc(),
        )
    )
    return [
        OrganizationCardStudyField(
            id=row.id,
            code=row.code,
            name=row.name,
            label=_build_study_field_label(row.code, row.name),
        )
        for row in result
    ]


async def _fetch_documents(
    session: AsyncSession,
    organization_id: int,
) -> tuple[list[OrganizationCardDocument], list[OrganizationCardDocumentGroup]]:
    result = await session.execute(
        select(
            ContractOrm.id,
            ContractOrm.datatype_id,
            ContractOrm.name_primary,
            ContractOrm.name_secondary,
            ContractOrm.chief_name,
            ContractOrm.chief_post,
            ContractOrm.signing_date,
            ContractOrm.is_actual,
            ContractOrm.meta_creator_name,
            ContractDatatype.name.label("datatype_name"),
        )
        .select_from(ContractOrm)
        .outerjoin(ContractDatatype, ContractDatatype.id == ContractOrm.datatype_id)
        .where(ContractOrm.organization_id == organization_id)
        .order_by(
            ContractOrm.is_actual.desc(),
            ContractOrm.signing_date.desc(),
            ContractOrm.id.desc(),
        )
    )
    rows = result.all()
    contract_ids = [row.id for row in rows]
    pdf_contract_ids: set[int] = set()
    if contract_ids:
        pdf_contract_ids = set(
            (
                await session.execute(
                    select(ContractPdfDocument.contract_id)
                    .where(ContractPdfDocument.contract_id.in_(contract_ids))
                    .distinct()
                )
            ).scalars()
        )
    documents = [
        OrganizationCardDocument(
            id=row.id,
            datatype_id=row.datatype_id,
            datatype_label=row.datatype_name,
            name_primary=row.name_primary,
            name_secondary=row.name_secondary,
            title=_build_document_title(
                row.name_primary,
                row.name_secondary,
                row.datatype_name,
            ),
            subtitle=_build_document_subtitle(row.name_secondary, row.datatype_name),
            signing_date=row.signing_date,
            chief_name=row.chief_name,
            chief_post=row.chief_post,
            is_actual=bool(row.is_actual),
            is_archived=not bool(row.is_actual),
            pdf_url=(
                f"/api/organizations/{organization_id}/documents/{row.id}/pdf"
                if row.id in pdf_contract_ids
                else None
            ),
            pdf_filename=row.meta_creator_name,
            has_pdf=row.id in pdf_contract_ids,
        )
        for row in rows
    ]

    groups_map: dict[int | None, OrganizationCardDocumentGroup] = {}
    group_order: list[int | None] = []
    for document in documents:
        group_key = document.datatype_id
        if group_key not in groups_map:
            groups_map[group_key] = OrganizationCardDocumentGroup(
                datatype_id=document.datatype_id,
                datatype_label=document.datatype_label or "Документы без типа",
            )
            group_order.append(group_key)
        group = groups_map[group_key]
        if document.is_actual and group.actual_document is None:
            group.actual_document = document
        else:
            group.archived_documents.append(document)

    document_groups = [groups_map[group_key] for group_key in group_order]
    visible_documents = [
        group.actual_document for group in document_groups if group.actual_document is not None
    ]
    return visible_documents, document_groups


async def _fetch_contact_rows(
    session: AsyncSession,
    *,
    entity_model,
    data_model,
    organization_id: int,
) -> list[OrganizationCardContactRow]:
    result = await session.execute(
        select(
            entity_model.id.label("entity_id"),
            entity_model.name.label("contact_name"),
            entity_model.post.label("contact_post"),
            DetailnameContactData.name.label("contact_type"),
            data_model.type_id.label("contact_type_id"),
            data_model.data.label("contact_value"),
            DetailnameContactData.display_priority.label("display_priority"),
            data_model.id.label("data_id"),
        )
        .select_from(entity_model)
        .outerjoin(data_model, data_model.entity_id == entity_model.id)
        .outerjoin(DetailnameContactData, DetailnameContactData.id == data_model.type_id)
        .where(entity_model.organization_id == organization_id)
        .order_by(
            entity_model.id.asc(),
            DetailnameContactData.display_priority.asc(),
            data_model.id.asc(),
        )
    )
    return [
        OrganizationCardContactRow(
            entity_id=row.entity_id,
            data_id=row.data_id,
            contact_name=row.contact_name,
            contact_post=row.contact_post,
            contact_type=row.contact_type,
            contact_type_id=row.contact_type_id,
            contact_value=row.contact_value,
        )
        for row in result
    ]


async def _fetch_requisites(
    session: AsyncSession,
    organization_id: int,
) -> list[OrganizationCardRequisite]:
    result = await session.execute(
        select(
            OrganizationDetailLegalInformation.id,
            OrganizationDetailLegalInformation.type_id,
            DetailnameLegalInformation.name.label("label"),
            OrganizationDetailLegalInformation.data.label("value"),
            DetailnameLegalInformation.priority.label("priority"),
        )
        .select_from(OrganizationDetailLegalInformation)
        .outerjoin(
            DetailnameLegalInformation,
            DetailnameLegalInformation.id == OrganizationDetailLegalInformation.type_id,
        )
        .where(OrganizationDetailLegalInformation.organization_id == organization_id)
        .order_by(
            DetailnameLegalInformation.priority.asc(),
            OrganizationDetailLegalInformation.id.asc(),
        )
    )
    requisites = []
    for row in result:
        label, custom_label, value = _split_custom_requisite_value(
            row.label or "Реквизит",
            row.value,
        )
        requisites.append(
            OrganizationCardRequisite(
                id=row.id,
                type_id=row.type_id,
                label=label,
                base_label=row.label or "Реквизит",
                custom_label=custom_label,
                value=value,
            )
        )
    return requisites


async def fetch_organization_card_page(
    session: AsyncSession,
    organization_id: int,
) -> OrganizationCardPage | None:
    result = await session.execute(
        select(
            OrganizationOrm.id,
            OrganizationOrm.name_short,
            OrganizationOrm.name_long,
            DetailnameSettlement.name.label("settlement_name"),
            OrganizationOrm.chief_name,
            OrganizationOrm.chief_post,
            OrganizationOrm.notes,
            OrganizationOrm.website,
            OrganizationOrm.logotype_id,
            OrganizationOrm.is_active,
            OrganizationOrm.is_university_department,
        )
        .select_from(OrganizationOrm)
        .outerjoin(
            DetailnameSettlement,
            DetailnameSettlement.id == OrganizationOrm.settlement_id,
        )
        .where(OrganizationOrm.id == organization_id)
    )
    organization = result.one_or_none()
    if organization is None:
        return None

    logo_data_url = await _fetch_logo_data_url(session, organization.logotype_id)
    study_fields = await _fetch_study_fields(session, organization_id)
    documents, document_groups = await _fetch_documents(session, organization_id)
    leader_contacts = await _fetch_contact_rows(
        session,
        entity_model=OrganizationDetailContactEntityLocal,
        data_model=OrganizationDetailContactDataLocal,
        organization_id=organization_id,
    )
    organization_contacts = await _fetch_contact_rows(
        session,
        entity_model=OrganizationDetailContactEntity,
        data_model=OrganizationDetailContactData,
        organization_id=organization_id,
    )
    organization_contact_groups = _group_contact_rows(organization_contacts)
    requisites = await _fetch_requisites(session, organization_id)
    map_query = _extract_map_query(requisites, organization.settlement_name)

    return OrganizationCardPage(
        id=organization.id,
        name_short=organization.name_short,
        name_long=organization.name_long,
        settlement_name=organization.settlement_name,
        chief_name=organization.chief_name,
        chief_post=organization.chief_post,
        notes=organization.notes,
        website=organization.website,
        map_query=map_query,
        logo_data_url=logo_data_url,
        is_active=bool(organization.is_active),
        is_university_department=bool(organization.is_university_department),
        study_fields=study_fields,
        documents=documents,
        document_groups=document_groups,
        leader_contacts=leader_contacts,
        organization_contacts=organization_contacts,
        organization_contact_groups=organization_contact_groups,
        requisites=requisites,
    )

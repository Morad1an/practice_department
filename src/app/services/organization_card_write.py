from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete, func, select
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
from src.app.models.organization_distributionstatistic import OrganizationDistributionStatistic
from src.app.models.organization_previousname import OrganizationPreviousName
from src.app.models.practice_distributionorderblock import PracticeDistributionOrderBlock
from src.app.models.university_academicdepartment import UniversityAcademicDepartment
from src.app.models.university_studyfield import UniversityStudyField
from src.app.schemas.organizations import (
    OrganizationCardContactInput,
    OrganizationCardReferenceOption,
    OrganizationCardRequisiteInput,
    OrganizationCardSavePayload,
    OrganizationDocumentCreatePayload,
    OrganizationDocumentUpdatePayload,
)
from src.app.services.logotype_utils import build_logo_preview_bytes, detect_logo_mime
from src.app.services.logotypes_batch import cache_logotype_data, invalidate_logotype_cache


class OrganizationCardError(Exception):
    """Base error for organization card mutations."""


class OrganizationCardNotFoundError(OrganizationCardError):
    """Raised when organization or nested entity is missing."""


class OrganizationCardValidationError(OrganizationCardError):
    """Raised when incoming payload is invalid."""


class OrganizationDeleteBlockedError(OrganizationCardError):
    def __init__(self, reasons: list[str]):
        super().__init__("Удаление организации заблокировано связанными данными.")
        self.reasons = reasons


@dataclass(slots=True)
class _PreparedContact:
    entity_id: int | None
    data_id: int | None
    client_entity_key: str | None
    contact_name: str | None
    contact_post: str | None
    contact_type_id: int
    contact_value: str


_MAX_LOGO_SIZE_BYTES = 1 * 1024 * 1024
_MAX_LOGO_PREVIEW_BYTES = 32 * 1024
_MAX_DOCUMENT_PDF_SIZE_BYTES = 20 * 1024 * 1024


def _normalize_text(value: str | None) -> str | None:
    prepared = (value or "").strip()
    return prepared or None


def _normalize_limited_text(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
) -> str | None:
    prepared = _normalize_text(value)
    if prepared and len(prepared) > max_length:
        raise OrganizationCardValidationError(
            f"Поле «{field_name}» превышает допустимую длину {max_length} символов."
        )
    return prepared


def _require_limited_text(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
) -> str:
    prepared = _normalize_limited_text(
        value,
        field_name=field_name,
        max_length=max_length,
    )
    if prepared is None:
        raise OrganizationCardValidationError(f"Поле «{field_name}» обязательно для заполнения.")
    return prepared


def _validate_logo_bytes(logo_bytes: bytes) -> bytes:
    if not logo_bytes:
        raise OrganizationCardValidationError("Файл логотипа пустой.")
    if len(logo_bytes) > _MAX_LOGO_SIZE_BYTES:
        raise OrganizationCardValidationError("Логотип превышает допустимый размер 1 МБ.")
    if detect_logo_mime(logo_bytes) is None:
        raise OrganizationCardValidationError("Поддерживаются только PNG, JPEG и GIF.")
    return logo_bytes


def _validate_document_pdf_bytes(pdf_bytes: bytes) -> bytes:
    if not pdf_bytes:
        raise OrganizationCardValidationError("PDF-файл пустой.")
    if len(pdf_bytes) > _MAX_DOCUMENT_PDF_SIZE_BYTES:
        raise OrganizationCardValidationError("PDF-файл превышает допустимый размер 20 МБ.")
    if not pdf_bytes.lstrip().startswith(b"%PDF-"):
        raise OrganizationCardValidationError("Поддерживаются только PDF-файлы.")
    return pdf_bytes


def _normalize_document_pdf_filename(filename: str | None, *, document_id: int) -> str:
    prepared = re.sub(r"[\r\n/\\\\]+", "_", (filename or "").strip()).strip()
    if not prepared:
        prepared = f"document_{document_id}.pdf"
    if not prepared.lower().endswith(".pdf"):
        prepared = f"{prepared}.pdf"
    return prepared


async def _replace_document_pdf_blob(
    session: AsyncSession,
    *,
    contract_id: int,
    pdf_bytes: bytes,
) -> None:
    await session.execute(
        delete(ContractPdfDocument).where(ContractPdfDocument.contract_id == contract_id)
    )
    session.add(
        ContractPdfDocument(
            contract_id=contract_id,
            file=pdf_bytes,
        )
    )


async def _fetch_document_pdf_blob(
    session: AsyncSession,
    *,
    contract_id: int,
) -> bytes | None:
    result = await session.execute(
        select(ContractPdfDocument.file)
        .where(ContractPdfDocument.contract_id == contract_id)
        .order_by(ContractPdfDocument.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _prepare_document_fields(
    *,
    name_primary: str | None,
    name_secondary: str | None,
    chief_name: str | None,
    chief_post: str | None,
    require_primary: bool = False,
) -> tuple[str | None, str | None, str | None, str | None]:
    prepared_name_primary = _normalize_limited_text(
        name_primary,
        field_name="Номер договора (внутренний)",
        max_length=255,
    )
    prepared_name_secondary = _normalize_limited_text(
        name_secondary,
        field_name="Номер договора (внешний)",
        max_length=255,
    )
    prepared_chief_name = _normalize_limited_text(
        chief_name,
        field_name="ФИО руководителя по договору",
        max_length=255,
    )
    prepared_chief_post = _normalize_limited_text(
        chief_post,
        field_name="Должность руководителя по договору",
        max_length=255,
    )
    if require_primary and prepared_name_primary is None:
        raise OrganizationCardValidationError(
            "Поле «Номер договора (внутренний)» обязательно для заполнения."
        )
    if prepared_name_primary is None and prepared_name_secondary is None:
        raise OrganizationCardValidationError(
            "Заполните номер договора (внутренний) или номер договора (внешний)."
        )
    return (
        prepared_name_primary,
        prepared_name_secondary,
        prepared_chief_name,
        prepared_chief_post,
    )


async def _sync_actual_document_with_type(
    session: AsyncSession,
    *,
    organization_id: int,
    datatype_id: int,
    current_document_id: int,
) -> None:
    sibling_documents = (
        await session.execute(
            select(ContractOrm).where(
                ContractOrm.organization_id == organization_id,
                ContractOrm.datatype_id == datatype_id,
                ContractOrm.id != current_document_id,
            )
        )
    ).scalars()
    for sibling in sibling_documents:
        sibling.is_actual = False


async def fetch_contact_type_options(
    session: AsyncSession,
) -> list[OrganizationCardReferenceOption]:
    result = await session.execute(
        select(DetailnameContactData.id, DetailnameContactData.name).order_by(
            DetailnameContactData.display_priority.asc(),
            DetailnameContactData.id.asc(),
        )
    )
    return [
        OrganizationCardReferenceOption(id=row.id, label=row.name or f"Тип #{row.id}")
        for row in result
    ]


async def fetch_contract_type_options(
    session: AsyncSession,
) -> list[OrganizationCardReferenceOption]:
    result = await session.execute(
        select(ContractDatatype.id, ContractDatatype.name).order_by(
            ContractDatatype.name.asc(),
            ContractDatatype.id.asc(),
        )
    )
    return [
        OrganizationCardReferenceOption(id=row.id, label=row.name or f"Тип #{row.id}")
        for row in result
    ]


async def fetch_requisite_type_options(
    session: AsyncSession,
) -> list[OrganizationCardReferenceOption]:
    result = await session.execute(
        select(DetailnameLegalInformation.id, DetailnameLegalInformation.name).order_by(
            DetailnameLegalInformation.priority.asc(),
            DetailnameLegalInformation.id.asc(),
        )
    )
    return [
        OrganizationCardReferenceOption(id=row.id, label=row.name or f"Реквизит #{row.id}")
        for row in result
    ]


async def fetch_settlement_options(
    session: AsyncSession,
) -> list[OrganizationCardReferenceOption]:
    result = await session.execute(
        select(DetailnameSettlement.id, DetailnameSettlement.name)
        .where(DetailnameSettlement.name.is_not(None))
        .order_by(DetailnameSettlement.name.asc(), DetailnameSettlement.id.asc())
    )
    return [
        OrganizationCardReferenceOption(id=row.id, label=row.name) for row in result if row.name
    ]


def _build_study_field_option_label(code: str | None, name: str | None) -> str:
    code = (code or "").strip()
    name = (name or "").strip()
    if code and name:
        return f"{code} {name}"
    return code or name


async def fetch_study_field_options(
    session: AsyncSession,
) -> list[OrganizationCardReferenceOption]:
    result = await session.execute(
        select(
            UniversityStudyField.id, UniversityStudyField.code, UniversityStudyField.name
        ).order_by(UniversityStudyField.code.asc(), UniversityStudyField.name.asc())
    )
    return [
        OrganizationCardReferenceOption(
            id=row.id,
            label=_build_study_field_option_label(row.code, row.name),
        )
        for row in result
        if _build_study_field_option_label(row.code, row.name)
    ]


async def _get_organization_for_update(
    session: AsyncSession,
    organization_id: int,
) -> OrganizationOrm:
    organization = await session.get(OrganizationOrm, organization_id)
    if organization is None:
        raise OrganizationCardNotFoundError("Организация не найдена.")
    return organization


async def _resolve_settlement_id(
    session: AsyncSession,
    settlement_name: str | None,
) -> int | None:
    prepared_name = _normalize_limited_text(
        settlement_name,
        field_name="Населённый пункт",
        max_length=255,
    )
    if prepared_name is None:
        return None

    existing = await session.execute(
        select(DetailnameSettlement).where(
            func.lower(DetailnameSettlement.name) == prepared_name.lower()
        )
    )
    settlement = existing.scalar_one_or_none()
    if settlement is not None:
        return settlement.id

    settlement = DetailnameSettlement(name=prepared_name)
    session.add(settlement)
    await session.flush()
    return settlement.id


async def _load_contact_type_ids(session: AsyncSession) -> set[int]:
    result = await session.execute(select(DetailnameContactData.id))
    return {value for value in result.scalars().all()}


async def _find_requisite_type_id_by_name(
    session: AsyncSession,
    *,
    requisite_name: str,
) -> int | None:
    return await session.scalar(
        select(DetailnameLegalInformation.id).where(
            func.lower(DetailnameLegalInformation.name) == requisite_name.lower()
        )
    )


async def _delete_orphan_logotype(
    session: AsyncSession,
    *,
    logotype_id: int | None,
    skip_organization_id: int | None = None,
) -> None:
    if not logotype_id:
        return

    statement = (
        select(func.count())
        .select_from(OrganizationOrm)
        .where(OrganizationOrm.logotype_id == logotype_id)
    )
    if skip_organization_id is not None:
        statement = statement.where(OrganizationOrm.id != skip_organization_id)

    references_count = await session.scalar(statement)
    if references_count:
        return

    logotype = await session.get(OrganizationDetailLogotype, logotype_id)
    if logotype is not None:
        await session.delete(logotype)


def _prepare_contacts(
    contacts: list[OrganizationCardContactInput],
) -> list[_PreparedContact]:
    prepared_contacts: list[_PreparedContact] = []
    for index, contact in enumerate(contacts, start=1):
        contact_name = _normalize_limited_text(
            contact.contact_name,
            field_name=f"Контакт #{index}: контактное лицо",
            max_length=255,
        )
        contact_post = _normalize_limited_text(
            contact.contact_post,
            field_name=f"Контакт #{index}: должность",
            max_length=1024,
        )
        contact_value = _normalize_limited_text(
            contact.contact_value,
            field_name=f"Контакт #{index}: контактные данные",
            max_length=255,
        )
        client_entity_key = _normalize_limited_text(
            contact.client_entity_key,
            field_name=f"Контакт #{index}: технический ключ",
            max_length=128,
        )
        has_any_value = any(
            [
                contact_name,
                contact_post,
                contact_value,
                contact.contact_type_id,
                contact.entity_id,
                contact.data_id,
            ]
        )
        if not has_any_value:
            continue
        if contact.contact_type_id is None:
            raise OrganizationCardValidationError(f"Для контакта #{index} не выбран тип контакта.")
        if contact_value is None:
            raise OrganizationCardValidationError(
                f"Для контакта #{index} не заполнены контактные данные."
            )

        prepared_contacts.append(
            _PreparedContact(
                entity_id=contact.entity_id,
                data_id=contact.data_id,
                client_entity_key=client_entity_key,
                contact_name=contact_name,
                contact_post=contact_post,
                contact_type_id=contact.contact_type_id,
                contact_value=contact_value,
            )
        )
    return prepared_contacts


async def _sync_contacts(
    session: AsyncSession,
    *,
    organization_id: int,
    contacts: list[OrganizationCardContactInput],
) -> None:
    valid_contact_type_ids = await _load_contact_type_ids(session)
    prepared_contacts = _prepare_contacts(contacts)
    for index, contact in enumerate(prepared_contacts, start=1):
        if contact.contact_type_id not in valid_contact_type_ids:
            raise OrganizationCardValidationError(
                f"Для контакта #{index} выбран неизвестный тип контакта."
            )

    existing_entities = {
        entity.id: entity
        for entity in (
            await session.execute(
                select(OrganizationDetailContactEntity).where(
                    OrganizationDetailContactEntity.organization_id == organization_id
                )
            )
        ).scalars()
    }
    existing_data_rows = {
        row.id: row
        for row in (
            await session.execute(
                select(OrganizationDetailContactData)
                .join(
                    OrganizationDetailContactEntity,
                    OrganizationDetailContactEntity.id == OrganizationDetailContactData.entity_id,
                )
                .where(OrganizationDetailContactEntity.organization_id == organization_id)
            )
        ).scalars()
    }

    retained_data_ids: set[int] = set()
    created_entities_by_client_key: dict[str, OrganizationDetailContactEntity] = {}

    for contact in prepared_contacts:
        entity: OrganizationDetailContactEntity | None
        if contact.data_id is not None:
            data_row = existing_data_rows.get(contact.data_id)
            if data_row is None:
                raise OrganizationCardValidationError(
                    "Один из контактов больше не существует. Обновите страницу."
                )
            if contact.entity_id and contact.entity_id != data_row.entity_id:
                raise OrganizationCardValidationError(
                    "Получены конфликтующие идентификаторы контакта."
                )
            entity = existing_entities[data_row.entity_id]
        else:
            if contact.entity_id is not None:
                entity = existing_entities.get(contact.entity_id)
                if entity is None:
                    raise OrganizationCardValidationError(
                        "Одна из контактных записей больше не существует."
                    )
            elif contact.client_entity_key:
                entity = created_entities_by_client_key.get(contact.client_entity_key)
                if entity is None:
                    entity = OrganizationDetailContactEntity(organization_id=organization_id)
                    session.add(entity)
                    await session.flush()
                    existing_entities[entity.id] = entity
                    created_entities_by_client_key[contact.client_entity_key] = entity
            else:
                entity = OrganizationDetailContactEntity(organization_id=organization_id)
                session.add(entity)
                await session.flush()
                existing_entities[entity.id] = entity

            data_row = OrganizationDetailContactData(
                entity_id=entity.id,
                type_id=contact.contact_type_id,
                data=contact.contact_value,
            )
            session.add(data_row)
            await session.flush()
            existing_data_rows[data_row.id] = data_row

        entity.name = contact.contact_name
        entity.post = contact.contact_post
        data_row.type_id = contact.contact_type_id
        data_row.data = contact.contact_value
        retained_data_ids.add(data_row.id)

    for data_id, data_row in list(existing_data_rows.items()):
        if data_id in retained_data_ids:
            continue
        await session.delete(data_row)

    await session.flush()

    orphan_entities = (
        await session.execute(
            select(OrganizationDetailContactEntity)
            .outerjoin(
                OrganizationDetailContactData,
                OrganizationDetailContactData.entity_id == OrganizationDetailContactEntity.id,
            )
            .where(OrganizationDetailContactEntity.organization_id == organization_id)
            .where(OrganizationDetailContactData.id.is_(None))
        )
    ).scalars()
    for entity in orphan_entities:
        await session.delete(entity)


async def _sync_requisites(
    session: AsyncSession,
    *,
    organization_id: int,
    requisites: list[OrganizationCardRequisiteInput],
) -> None:
    existing_rows = {
        row.id: row
        for row in (
            await session.execute(
                select(OrganizationDetailLegalInformation).where(
                    OrganizationDetailLegalInformation.organization_id == organization_id
                )
            )
        ).scalars()
    }

    for index, requisite in enumerate(requisites, start=1):
        value = _normalize_limited_text(
            requisite.value,
            field_name=f"Реквизит #{index}",
            max_length=4096,
        )

        if requisite.id is not None:
            record = existing_rows.get(requisite.id)
            if record is None:
                raise OrganizationCardValidationError(
                    "Один из реквизитов больше не существует. Обновите страницу."
                )
            if value is None:
                await session.delete(record)
                continue
            record.data = value
            if requisite.type_id is not None:
                record.type_id = requisite.type_id
            continue

        if value is None:
            continue
        if requisite.type_id is None:
            raise OrganizationCardValidationError(f"Для реквизита #{index} не указан тип.")

        session.add(
            OrganizationDetailLegalInformation(
                organization_id=organization_id,
                type_id=requisite.type_id,
                data=value,
            )
        )


async def _sync_study_fields(
    session: AsyncSession,
    *,
    organization_id: int,
    study_field_ids: list[int],
) -> None:
    prepared_ids: list[int] = []
    seen_ids: set[int] = set()
    for raw_id in study_field_ids:
        if raw_id in seen_ids:
            continue
        seen_ids.add(raw_id)
        prepared_ids.append(raw_id)

    if prepared_ids:
        existing_ids = set(
            (
                await session.execute(
                    select(UniversityStudyField.id).where(UniversityStudyField.id.in_(prepared_ids))
                )
            ).scalars()
        )
        missing_ids = [field_id for field_id in prepared_ids if field_id not in existing_ids]
        if missing_ids:
            raise OrganizationCardValidationError("Выбрано неизвестное профильное направление.")

    current_rows = (
        (
            await session.execute(
                select(OrganizationDetailStudyField).where(
                    OrganizationDetailStudyField.organization_id == organization_id
                )
            )
        )
        .scalars()
        .all()
    )
    current_by_field_id = {row.study_field_id: row for row in current_rows}
    retained_ids = set(prepared_ids)

    for field_id in prepared_ids:
        if field_id in current_by_field_id:
            continue
        session.add(
            OrganizationDetailStudyField(
                organization_id=organization_id,
                study_field_id=field_id,
            )
        )

    for field_id, row in current_by_field_id.items():
        if field_id not in retained_ids:
            await session.delete(row)


async def _validate_create_required_requisites(
    session: AsyncSession,
    *,
    requisites: list[OrganizationCardRequisiteInput],
) -> None:
    inn_type_id = await _find_requisite_type_id_by_name(
        session,
        requisite_name="ИНН",
    )
    if inn_type_id is None:
        raise OrganizationCardValidationError("В справочнике реквизитов не найден тип «ИНН».")

    has_inn = any(
        requisite.type_id == inn_type_id and _normalize_text(requisite.value)
        for requisite in requisites
    )
    if not has_inn:
        raise OrganizationCardValidationError("Поле «ИНН» обязательно при создании организации.")


async def save_organization_card(
    session: AsyncSession,
    *,
    payload: OrganizationCardSavePayload,
    organization_id: int | None = None,
) -> int:
    if organization_id is None:
        await _validate_create_required_requisites(
            session,
            requisites=payload.requisites,
        )
        organization = OrganizationOrm()
        session.add(organization)
    else:
        organization = await _get_organization_for_update(session, organization_id)

    organization.name_short = _require_limited_text(
        payload.name_short,
        field_name="Краткое наименование",
        max_length=1024,
    )
    organization.name_long = _require_limited_text(
        payload.name_long,
        field_name="Полное наименование",
        max_length=1024,
    )
    organization.chief_name = _normalize_limited_text(
        payload.chief_name,
        field_name="ФИО руководителя",
        max_length=255,
    )
    organization.chief_post = _normalize_limited_text(
        payload.chief_post,
        field_name="Должность руководителя",
        max_length=255,
    )
    organization.notes = _normalize_limited_text(
        payload.notes,
        field_name="Заметки",
        max_length=4096,
    )
    organization.website = _normalize_limited_text(
        payload.website,
        field_name="Официальный сайт",
        max_length=255,
    )
    organization.settlement_id = await _resolve_settlement_id(
        session,
        _require_limited_text(
            payload.settlement_name,
            field_name="Населённый пункт",
            max_length=255,
        ),
    )
    organization.is_active = int(bool(payload.is_active))
    organization.is_university_department = int(bool(payload.is_university_department))
    organization.data_is_filled = 1

    await session.flush()

    await _sync_contacts(
        session,
        organization_id=organization.id,
        contacts=payload.contacts,
    )
    await _sync_requisites(
        session,
        organization_id=organization.id,
        requisites=payload.requisites,
    )
    await _sync_study_fields(
        session,
        organization_id=organization.id,
        study_field_ids=payload.study_field_ids,
    )

    await session.commit()
    return organization.id


async def save_organization_logo(
    session: AsyncSession,
    *,
    organization_id: int,
    logo_bytes: bytes,
) -> int:
    organization = await _get_organization_for_update(session, organization_id)
    validated_logo = _validate_logo_bytes(logo_bytes)
    try:
        compressed_logo = build_logo_preview_bytes(
            validated_logo,
            max_bytes=_MAX_LOGO_PREVIEW_BYTES,
        )
    except ValueError as error:
        raise OrganizationCardValidationError(
            "Не удалось подготовить логотип для сохранения. Попробуйте изображение меньшего размера."
        ) from error
    previous_logotype_id = organization.logotype_id

    logotype = OrganizationDetailLogotype(
        original=validated_logo,
        compressed=compressed_logo,
    )
    session.add(logotype)
    await session.flush()

    organization.logotype_id = logotype.id
    await session.flush()
    await _delete_orphan_logotype(
        session,
        logotype_id=previous_logotype_id,
        skip_organization_id=organization_id,
    )
    await session.commit()
    await cache_logotype_data(
        logotype_id=logotype.id,
        raw_data=compressed_logo,
    )
    await invalidate_logotype_cache(logotype_ids=[previous_logotype_id or 0])
    return logotype.id


async def delete_organization_logo(
    session: AsyncSession,
    *,
    organization_id: int,
) -> None:
    organization = await _get_organization_for_update(session, organization_id)
    previous_logotype_id = organization.logotype_id
    organization.logotype_id = None
    await session.flush()
    await _delete_orphan_logotype(
        session,
        logotype_id=previous_logotype_id,
        skip_organization_id=organization_id,
    )
    await session.commit()
    await invalidate_logotype_cache(logotype_ids=[previous_logotype_id or 0])


async def add_organization_document(
    session: AsyncSession,
    *,
    organization_id: int,
    payload: OrganizationDocumentCreatePayload,
) -> int:
    await _get_organization_for_update(session, organization_id)

    datatype = await session.get(ContractDatatype, payload.datatype_id)
    if datatype is None:
        raise OrganizationCardValidationError("Выбран неизвестный тип документа.")

    name_primary, name_secondary, chief_name, chief_post = _prepare_document_fields(
        name_primary=payload.name_primary,
        name_secondary=payload.name_secondary,
        chief_name=payload.chief_name,
        chief_post=payload.chief_post,
        require_primary=True,
    )

    contract = ContractOrm(
        name_primary=name_primary,
        name_secondary=name_secondary,
        chief_name=chief_name,
        chief_post=chief_post,
        signing_date=payload.signing_date,
        organization_id=organization_id,
        datatype_id=payload.datatype_id,
        is_actual=True,
    )
    session.add(contract)
    await session.flush()
    await _sync_actual_document_with_type(
        session,
        organization_id=organization_id,
        datatype_id=payload.datatype_id,
        current_document_id=contract.id,
    )
    await session.commit()
    return contract.id


async def update_organization_document(
    session: AsyncSession,
    *,
    organization_id: int,
    document_id: int,
    payload: OrganizationDocumentUpdatePayload,
    pdf_bytes: bytes | None = None,
    pdf_filename: str | None = None,
) -> None:
    result = await session.execute(
        select(ContractOrm).where(
            ContractOrm.id == document_id,
            ContractOrm.organization_id == organization_id,
        )
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise OrganizationCardNotFoundError("Документ не найден.")

    name_primary, name_secondary, chief_name, chief_post = _prepare_document_fields(
        name_primary=payload.name_primary,
        name_secondary=payload.name_secondary,
        chief_name=payload.chief_name,
        chief_post=payload.chief_post,
    )

    contract.name_primary = name_primary
    contract.name_secondary = name_secondary
    contract.signing_date = payload.signing_date
    contract.chief_name = chief_name
    contract.chief_post = chief_post
    contract.is_actual = bool(payload.is_actual)

    if pdf_bytes is not None:
        validated_pdf = _validate_document_pdf_bytes(pdf_bytes)
        await _replace_document_pdf_blob(
            session,
            contract_id=document_id,
            pdf_bytes=validated_pdf,
        )
        contract.website = None
        contract.meta_creator_name = _normalize_document_pdf_filename(
            pdf_filename,
            document_id=document_id,
        )

    if contract.is_actual:
        await _sync_actual_document_with_type(
            session,
            organization_id=organization_id,
            datatype_id=contract.datatype_id,
            current_document_id=contract.id,
        )

    await session.commit()


async def get_organization_document_pdf(
    session: AsyncSession,
    *,
    organization_id: int,
    document_id: int,
) -> tuple[bytes, str]:
    result = await session.execute(
        select(ContractOrm).where(
            ContractOrm.id == document_id,
            ContractOrm.organization_id == organization_id,
        )
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise OrganizationCardNotFoundError("Документ не найден.")

    pdf_bytes = await _fetch_document_pdf_blob(
        session,
        contract_id=document_id,
    )
    if pdf_bytes is None:
        raise OrganizationCardNotFoundError("PDF-файл документа не найден.")
    return (
        pdf_bytes,
        _normalize_document_pdf_filename(
            contract.meta_creator_name,
            document_id=document_id,
        ),
    )


async def delete_organization_document_pdf(
    session: AsyncSession,
    *,
    organization_id: int,
    document_id: int,
) -> None:
    result = await session.execute(
        select(ContractOrm).where(
            ContractOrm.id == document_id,
            ContractOrm.organization_id == organization_id,
        )
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise OrganizationCardNotFoundError("Документ не найден.")

    existing_pdf = await _fetch_document_pdf_blob(
        session,
        contract_id=document_id,
    )
    if existing_pdf is None:
        raise OrganizationCardNotFoundError("PDF-файл документа не найден.")

    await session.execute(
        delete(ContractPdfDocument).where(ContractPdfDocument.contract_id == document_id)
    )
    contract.website = None
    contract.meta_creator_name = None
    await session.commit()


async def archive_organization_document(
    session: AsyncSession,
    *,
    organization_id: int,
    document_id: int,
) -> None:
    result = await session.execute(
        select(ContractOrm).where(
            ContractOrm.id == document_id,
            ContractOrm.organization_id == organization_id,
        )
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise OrganizationCardNotFoundError("Документ не найден.")

    contract.is_actual = False
    await session.commit()


async def delete_organization_safely(
    session: AsyncSession,
    *,
    organization_id: int,
) -> None:
    organization = await _get_organization_for_update(session, organization_id)
    previous_logotype_id = organization.logotype_id

    blocking_checks = [
        (ContractOrm, "связанные договоры"),
        (OrganizationDistributionStatistic, "статистика распределения"),
        (PracticeDistributionOrderBlock, "блоки распределения"),
        (UniversityAcademicDepartment, "связанные кафедры"),
    ]
    blocking_reasons: list[str] = []
    for model, label in blocking_checks:
        organization_id_column = getattr(model, "organization_id")
        count = await session.scalar(
            select(func.count()).select_from(model).where(organization_id_column == organization_id)
        )
        if count:
            blocking_reasons.append(f"{label}: {count}")

    if blocking_reasons:
        raise OrganizationDeleteBlockedError(blocking_reasons)

    contact_entity_ids = select(OrganizationDetailContactEntity.id).where(
        OrganizationDetailContactEntity.organization_id == organization_id
    )
    local_contact_entity_ids = select(OrganizationDetailContactEntityLocal.id).where(
        OrganizationDetailContactEntityLocal.organization_id == organization_id
    )

    await session.execute(
        delete(OrganizationDetailContactData).where(
            OrganizationDetailContactData.entity_id.in_(contact_entity_ids)
        )
    )
    await session.execute(
        delete(OrganizationDetailContactEntity).where(
            OrganizationDetailContactEntity.organization_id == organization_id
        )
    )
    await session.execute(
        delete(OrganizationDetailContactDataLocal).where(
            OrganizationDetailContactDataLocal.entity_id.in_(local_contact_entity_ids)
        )
    )
    await session.execute(
        delete(OrganizationDetailContactEntityLocal).where(
            OrganizationDetailContactEntityLocal.organization_id == organization_id
        )
    )
    await session.execute(
        delete(OrganizationDetailLegalInformation).where(
            OrganizationDetailLegalInformation.organization_id == organization_id
        )
    )
    await session.execute(
        delete(OrganizationDetailStudyField).where(
            OrganizationDetailStudyField.organization_id == organization_id
        )
    )
    await session.execute(
        delete(OrganizationPreviousName).where(
            OrganizationPreviousName.organization_id == organization_id
        )
    )
    await session.delete(organization)
    await session.flush()
    await _delete_orphan_logotype(
        session,
        logotype_id=previous_logotype_id,
        skip_organization_id=organization_id,
    )
    await session.commit()
    await invalidate_logotype_cache(logotype_ids=[previous_logotype_id or 0])

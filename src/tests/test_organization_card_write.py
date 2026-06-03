import os
import time
import unittest
from datetime import date
from io import BytesIO

from PIL import Image
from sqlalchemy import delete, select

from src.app.database import async_session_maker, engine
from src.app.models.contract import ContractOrm
from src.app.models.contract_datatype import ContractDatatype
from src.app.models.contract_pdfdocument import ContractPdfDocument
from src.app.models.detailname_contactdata import DetailnameContactData
from src.app.models.detailname_legalinformation import DetailnameLegalInformation
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
    OrganizationCardRequisiteInput,
    OrganizationCardSavePayload,
    OrganizationDocumentCreatePayload,
    OrganizationDocumentUpdatePayload,
)
from src.app.services.logotypes_batch import close_logo_cache
from src.app.services.organization_card import fetch_organization_card_page
from src.app.services.organization_card_write import (
    OrganizationCardValidationError,
    OrganizationDeleteBlockedError,
    add_organization_document,
    archive_organization_document,
    delete_organization_logo,
    delete_organization_safely,
    get_organization_document_pdf,
    save_organization_card,
    save_organization_logo,
    update_organization_document,
)

TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)

TEST_GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
    b"\x00\x02\x02D\x01\x00;"
)


def build_large_png_bytes() -> bytes:
    image = Image.frombytes("RGB", (400, 400), os.urandom(400 * 400 * 3))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    payload = buffer.getvalue()
    assert len(payload) > 65535
    return payload


def build_oversized_logo_bytes() -> bytes:
    payload = TEST_PNG_BYTES + (b"0" * (1024 * 1024))
    assert len(payload) > 1024 * 1024
    return payload


def build_test_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def build_valid_payload(*, suffix: str) -> OrganizationCardSavePayload:
    return OrganizationCardSavePayload(
        name_short=f"Test Org {suffix}",
        name_long=f"Full Test Org {suffix}",
        settlement_name="г. Санкт-Петербург",
        chief_name="Иванов Иван Иванович",
        chief_post="Генеральный директор",
        notes=None,
        website=None,
        is_active=True,
        is_university_department=False,
        contacts=[],
        requisites=[],
    )


class OrganizationCardWriteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.created_organization_ids: list[int] = []
        self._suffix_counter = 0

    async def asyncTearDown(self):
        for organization_id in reversed(self.created_organization_ids):
            await self._purge_organization(organization_id)
        await close_logo_cache()
        await engine.dispose()

    def _unique_suffix(self, prefix: str) -> str:
        self._suffix_counter += 1
        return f"{prefix}-{time.time_ns()}-{self._suffix_counter}"

    async def _create_organization(
        self,
        payload: OrganizationCardSavePayload | None = None,
    ) -> int:
        if payload is None:
            payload = build_valid_payload(suffix=self._unique_suffix("create"))
        payload = await self._with_create_required_requisites(payload)

        async with async_session_maker() as session:
            organization_id = await save_organization_card(session, payload=payload)

        self.created_organization_ids.append(organization_id)
        return organization_id

    async def _fetch_card(self, organization_id: int):
        async with async_session_maker() as session:
            return await fetch_organization_card_page(session, organization_id)

    async def _fetch_first_contact_type_id(self) -> int:
        async with async_session_maker() as session:
            contact_type_id = await session.scalar(
                select(DetailnameContactData.id).order_by(
                    DetailnameContactData.display_priority.asc(),
                    DetailnameContactData.id.asc(),
                )
            )
        self.assertIsNotNone(contact_type_id)
        return int(contact_type_id)

    async def _fetch_contract_datatype_id(self) -> int:
        async with async_session_maker() as session:
            datatype_id = await session.scalar(
                select(ContractDatatype.id).order_by(
                    ContractDatatype.name.asc(),
                    ContractDatatype.id.asc(),
                )
            )
        self.assertIsNotNone(datatype_id)
        return int(datatype_id)

    async def _fetch_requisite_type_id(self, label: str) -> int:
        async with async_session_maker() as session:
            requisite_type_id = await session.scalar(
                select(DetailnameLegalInformation.id).where(
                    DetailnameLegalInformation.name == label
                )
            )
        self.assertIsNotNone(requisite_type_id, label)
        return int(requisite_type_id)

    async def _fetch_study_field_ids(self, limit: int = 2) -> list[int]:
        async with async_session_maker() as session:
            study_field_ids = list(
                (
                    await session.execute(
                        select(UniversityStudyField.id)
                        .order_by(UniversityStudyField.id.asc())
                        .limit(limit)
                    )
                ).scalars()
            )
        self.assertGreaterEqual(len(study_field_ids), limit)
        return [int(value) for value in study_field_ids]

    async def _with_create_required_requisites(
        self,
        payload: OrganizationCardSavePayload,
    ) -> OrganizationCardSavePayload:
        inn_type_id = await self._fetch_requisite_type_id("ИНН")
        prepared_payload = payload.model_copy(deep=True)
        has_inn = any(
            requisite.type_id == inn_type_id and (requisite.value or "").strip()
            for requisite in prepared_payload.requisites
        )
        if not has_inn:
            prepared_payload.requisites.append(
                OrganizationCardRequisiteInput(
                    type_id=inn_type_id,
                    value="7812345678",
                )
            )
        return prepared_payload

    async def _purge_organization(self, organization_id: int) -> None:
        async with async_session_maker() as session:
            contract_ids = list(
                (
                    await session.execute(
                        select(ContractOrm.id).where(ContractOrm.organization_id == organization_id)
                    )
                ).scalars()
            )
            contact_entity_ids = list(
                (
                    await session.execute(
                        select(OrganizationDetailContactEntity.id).where(
                            OrganizationDetailContactEntity.organization_id == organization_id
                        )
                    )
                ).scalars()
            )
            local_contact_entity_ids = list(
                (
                    await session.execute(
                        select(OrganizationDetailContactEntityLocal.id).where(
                            OrganizationDetailContactEntityLocal.organization_id == organization_id
                        )
                    )
                ).scalars()
            )

            if contract_ids:
                await session.execute(
                    delete(ContractPdfDocument).where(
                        ContractPdfDocument.contract_id.in_(contract_ids)
                    )
                )
            await session.execute(
                delete(ContractOrm).where(ContractOrm.organization_id == organization_id)
            )
            await session.execute(
                delete(OrganizationDistributionStatistic).where(
                    OrganizationDistributionStatistic.organization_id == organization_id
                )
            )
            await session.execute(
                delete(PracticeDistributionOrderBlock).where(
                    PracticeDistributionOrderBlock.organization_id == organization_id
                )
            )
            await session.execute(
                delete(UniversityAcademicDepartment).where(
                    UniversityAcademicDepartment.organization_id == organization_id
                )
            )

            if contact_entity_ids:
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

            if local_contact_entity_ids:
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
            await session.execute(
                delete(OrganizationOrm).where(OrganizationOrm.id == organization_id)
            )
            await session.commit()

    def _remove_from_cleanup(self, organization_id: int) -> None:
        if organization_id in self.created_organization_ids:
            self.created_organization_ids.remove(organization_id)

    async def test_create_requires_short_name(self):
        payload = build_valid_payload(suffix=self._unique_suffix("short"))
        payload.name_short = "   "
        payload = await self._with_create_required_requisites(payload)

        async with async_session_maker() as session:
            with self.assertRaisesRegex(
                OrganizationCardValidationError,
                "Краткое наименование",
            ):
                await save_organization_card(session, payload=payload)
            await session.rollback()

    async def test_create_requires_full_name(self):
        payload = build_valid_payload(suffix=self._unique_suffix("long"))
        payload.name_long = ""
        payload = await self._with_create_required_requisites(payload)

        async with async_session_maker() as session:
            with self.assertRaisesRegex(
                OrganizationCardValidationError,
                "Полное наименование",
            ):
                await save_organization_card(session, payload=payload)
            await session.rollback()

    async def test_create_requires_settlement_name(self):
        payload = build_valid_payload(suffix=self._unique_suffix("settlement"))
        payload.settlement_name = None
        payload = await self._with_create_required_requisites(payload)

        async with async_session_maker() as session:
            with self.assertRaisesRegex(
                OrganizationCardValidationError,
                "Населённый пункт",
            ):
                await save_organization_card(session, payload=payload)
            await session.rollback()

    async def test_create_allows_empty_chief_fields(self):
        payload = build_valid_payload(suffix=self._unique_suffix("no-chief"))
        payload.chief_name = " "
        payload.chief_post = None
        organization_id = await self._create_organization(payload)

        card = await self._fetch_card(organization_id)
        self.assertIsNone(card.chief_name)
        self.assertIsNone(card.chief_post)

    async def test_create_requires_inn_requisite(self):
        payload = build_valid_payload(suffix=self._unique_suffix("no-inn"))

        async with async_session_maker() as session:
            with self.assertRaisesRegex(
                OrganizationCardValidationError,
                "ИНН",
            ):
                await save_organization_card(session, payload=payload)
            await session.rollback()

    async def test_create_does_not_require_other_requisites_when_inn_present(self):
        inn_type_id = await self._fetch_requisite_type_id("ИНН")
        payload = build_valid_payload(suffix=self._unique_suffix("only-inn"))
        payload.requisites = [
            OrganizationCardRequisiteInput(
                type_id=inn_type_id,
                value="7812345678",
            )
        ]
        organization_id = await self._create_organization(payload)

        card = await self._fetch_card(organization_id)
        self.assertIsNotNone(card)
        requisites = {requisite.label: requisite.value for requisite in card.requisites}
        self.assertEqual(requisites, {"ИНН": "7812345678"})
        self.assertEqual(card.map_query, "г. Санкт-Петербург")

    async def test_create_succeeds_with_required_fields(self):
        payload = await self._with_create_required_requisites(
            build_valid_payload(suffix=self._unique_suffix("success"))
        )
        organization_id = await self._create_organization(payload)

        card = await self._fetch_card(organization_id)
        self.assertIsNotNone(card)
        self.assertEqual(card.name_short, payload.name_short)
        self.assertEqual(card.name_long, payload.name_long)
        self.assertEqual(card.settlement_name, payload.settlement_name)
        self.assertEqual(card.chief_name, payload.chief_name)
        self.assertEqual(card.chief_post, payload.chief_post)
        requisites = {requisite.label: requisite.value for requisite in card.requisites}
        self.assertEqual(requisites["ИНН"], "7812345678")

    async def test_update_saves_base_fields(self):
        organization_id = await self._create_organization()
        payload = build_valid_payload(suffix=self._unique_suffix("update-base"))
        payload.name_short = "Обновленная организация"
        payload.name_long = "Обновленное полное наименование организации"
        payload.settlement_name = "г. Москва"
        payload.chief_name = "Петров Петр Петрович"
        payload.chief_post = "Исполнительный директор"
        payload.notes = "Тестовое обновление заметок"
        payload.website = "https://example.org"
        payload.is_active = False
        payload.is_university_department = True

        async with async_session_maker() as session:
            await save_organization_card(
                session,
                payload=payload,
                organization_id=organization_id,
            )

        card = await self._fetch_card(organization_id)
        self.assertIsNotNone(card)
        self.assertEqual(card.name_short, payload.name_short)
        self.assertEqual(card.name_long, payload.name_long)
        self.assertEqual(card.settlement_name, payload.settlement_name)
        self.assertEqual(card.chief_name, payload.chief_name)
        self.assertEqual(card.chief_post, payload.chief_post)
        self.assertEqual(card.notes, payload.notes)
        self.assertEqual(card.website, payload.website)
        self.assertFalse(card.is_active)
        self.assertTrue(card.is_university_department)

    async def test_update_saves_study_fields(self):
        organization_id = await self._create_organization()
        first_field_id, second_field_id = await self._fetch_study_field_ids(limit=2)

        payload = build_valid_payload(suffix=self._unique_suffix("study-fields"))
        payload.study_field_ids = [first_field_id, second_field_id, first_field_id]

        async with async_session_maker() as session:
            await save_organization_card(
                session,
                payload=payload,
                organization_id=organization_id,
            )

        card = await self._fetch_card(organization_id)
        self.assertEqual(
            sorted(study_field.id for study_field in card.study_fields),
            sorted([first_field_id, second_field_id]),
        )

        update_payload = build_valid_payload(suffix=self._unique_suffix("study-fields-clear"))
        update_payload.study_field_ids = [second_field_id]

        async with async_session_maker() as session:
            await save_organization_card(
                session,
                payload=update_payload,
                organization_id=organization_id,
            )

        updated_card = await self._fetch_card(organization_id)
        self.assertEqual(
            [study_field.id for study_field in updated_card.study_fields],
            [second_field_id],
        )

    async def test_contact_requires_type_when_value_present(self):
        payload = build_valid_payload(suffix=self._unique_suffix("contact-type"))
        payload.contacts = [
            OrganizationCardContactInput(
                contact_name="Сидоров Сидор Сидорович",
                contact_post="Менеджер",
                contact_value="+7 (999) 111-22-33",
            )
        ]
        payload = await self._with_create_required_requisites(payload)

        async with async_session_maker() as session:
            with self.assertRaisesRegex(
                OrganizationCardValidationError,
                "не выбран тип контакта",
            ):
                await save_organization_card(session, payload=payload)
            await session.rollback()

    async def test_contact_requires_value_when_type_present(self):
        contact_type_id = await self._fetch_first_contact_type_id()
        payload = build_valid_payload(suffix=self._unique_suffix("contact-value"))
        payload.contacts = [
            OrganizationCardContactInput(
                contact_name="Сидоров Сидор Сидорович",
                contact_post="Менеджер",
                contact_type_id=contact_type_id,
            )
        ]
        payload = await self._with_create_required_requisites(payload)

        async with async_session_maker() as session:
            with self.assertRaisesRegex(
                OrganizationCardValidationError,
                "не заполнены контактные данные",
            ):
                await save_organization_card(session, payload=payload)
            await session.rollback()

    async def test_update_saves_existing_contact(self):
        contact_type_id = await self._fetch_first_contact_type_id()
        payload = build_valid_payload(suffix=self._unique_suffix("contact-create"))
        payload.contacts = [
            OrganizationCardContactInput(
                contact_name="Сидоров Сидор Сидорович",
                contact_post="Менеджер",
                contact_type_id=contact_type_id,
                contact_value="+7 (812) 000-00-00",
            )
        ]
        organization_id = await self._create_organization(payload)

        original_card = await self._fetch_card(organization_id)
        self.assertEqual(len(original_card.organization_contacts), 1)
        original_contact = original_card.organization_contacts[0]

        update_payload = build_valid_payload(suffix=self._unique_suffix("contact-update"))
        update_payload.contacts = [
            OrganizationCardContactInput(
                entity_id=original_contact.entity_id,
                data_id=original_contact.data_id,
                contact_name="Павлов Павел Павлович",
                contact_post="Руководитель отдела практики",
                contact_type_id=contact_type_id,
                contact_value="practice@example.org",
            )
        ]

        async with async_session_maker() as session:
            await save_organization_card(
                session,
                payload=update_payload,
                organization_id=organization_id,
            )

        updated_card = await self._fetch_card(organization_id)
        self.assertEqual(len(updated_card.organization_contacts), 1)
        updated_contact = updated_card.organization_contacts[0]
        self.assertEqual(updated_contact.entity_id, original_contact.entity_id)
        self.assertEqual(updated_contact.data_id, original_contact.data_id)
        self.assertEqual(updated_contact.contact_name, "Павлов Павел Павлович")
        self.assertEqual(
            updated_contact.contact_post,
            "Руководитель отдела практики",
        )
        self.assertEqual(updated_contact.contact_value, "practice@example.org")

    async def test_update_adds_new_contact(self):
        organization_id = await self._create_organization()
        contact_type_id = await self._fetch_first_contact_type_id()

        payload = build_valid_payload(suffix=self._unique_suffix("contact-add"))
        payload.contacts = [
            OrganizationCardContactInput(
                contact_name="Орлов Олег Олегович",
                contact_post="Куратор",
                contact_type_id=contact_type_id,
                contact_value="curator@example.org",
            )
        ]

        async with async_session_maker() as session:
            await save_organization_card(
                session,
                payload=payload,
                organization_id=organization_id,
            )

        card = await self._fetch_card(organization_id)
        self.assertEqual(len(card.organization_contacts), 1)
        contact = card.organization_contacts[0]
        self.assertIsNotNone(contact.entity_id)
        self.assertIsNotNone(contact.data_id)
        self.assertEqual(contact.contact_name, "Орлов Олег Олегович")
        self.assertEqual(contact.contact_post, "Куратор")
        self.assertEqual(contact.contact_value, "curator@example.org")

    async def test_update_adds_multiple_contact_values_to_same_new_person(self):
        organization_id = await self._create_organization()
        contact_type_id = await self._fetch_first_contact_type_id()

        payload = build_valid_payload(suffix=self._unique_suffix("contact-add-multiple"))
        payload.contacts = [
            OrganizationCardContactInput(
                client_entity_key="new-contact-1",
                contact_name="Орлов Олег Олегович",
                contact_post="Куратор",
                contact_type_id=contact_type_id,
                contact_value="curator@example.org",
            ),
            OrganizationCardContactInput(
                client_entity_key="new-contact-1",
                contact_name="Орлов Олег Олегович",
                contact_post="Куратор",
                contact_type_id=contact_type_id,
                contact_value="+7 (812) 123-45-67",
            ),
        ]

        async with async_session_maker() as session:
            await save_organization_card(
                session,
                payload=payload,
                organization_id=organization_id,
            )

        card = await self._fetch_card(organization_id)
        self.assertEqual(len(card.organization_contacts), 2)
        entity_ids = {contact.entity_id for contact in card.organization_contacts}
        self.assertEqual(len(entity_ids), 1)
        self.assertEqual(len(card.organization_contact_groups), 1)
        self.assertEqual(len(card.organization_contact_groups[0].contacts), 2)

    async def test_update_removes_contact_omitted_from_payload(self):
        contact_type_id = await self._fetch_first_contact_type_id()
        payload = build_valid_payload(suffix=self._unique_suffix("contact-remove"))
        payload.contacts = [
            OrganizationCardContactInput(
                contact_name="Удаляемый контакт",
                contact_post="Специалист",
                contact_type_id=contact_type_id,
                contact_value="+7 (812) 555-55-55",
            )
        ]
        organization_id = await self._create_organization(payload)

        update_payload = build_valid_payload(suffix=self._unique_suffix("contact-remove-update"))
        update_payload.contacts = []

        async with async_session_maker() as session:
            await save_organization_card(
                session,
                payload=update_payload,
                organization_id=organization_id,
            )

        card = await self._fetch_card(organization_id)
        self.assertEqual(card.organization_contacts, [])

    async def test_save_requisites_create_update_delete(self):
        legal_type_id = await self._fetch_requisite_type_id("Юридический адрес")
        factual_type_id = await self._fetch_requisite_type_id("Фактический адрес")
        inn_type_id = await self._fetch_requisite_type_id("ИНН")

        payload = build_valid_payload(suffix=self._unique_suffix("requisites-create"))
        payload.requisites = [
            OrganizationCardRequisiteInput(
                type_id=legal_type_id,
                value="190000, г. Санкт-Петербург, Невский пр., д. 1",
            ),
            OrganizationCardRequisiteInput(
                type_id=factual_type_id,
                value="190000, г. Санкт-Петербург, Лиговский пр., д. 10",
            ),
        ]
        organization_id = await self._create_organization(payload)

        original_card = await self._fetch_card(organization_id)
        original_requisites = {requisite.label: requisite for requisite in original_card.requisites}
        self.assertEqual(
            original_requisites["Юридический адрес"].value,
            "190000, г. Санкт-Петербург, Невский пр., д. 1",
        )
        self.assertEqual(
            original_requisites["Фактический адрес"].value,
            "190000, г. Санкт-Петербург, Лиговский пр., д. 10",
        )
        self.assertEqual(
            original_card.map_query,
            "190000, г. Санкт-Петербург, Лиговский пр., д. 10",
        )

        update_payload = build_valid_payload(suffix=self._unique_suffix("requisites-update"))
        update_payload.requisites = [
            OrganizationCardRequisiteInput(
                id=original_requisites["Юридический адрес"].id,
                type_id=legal_type_id,
                value="",
            ),
            OrganizationCardRequisiteInput(
                id=original_requisites["Фактический адрес"].id,
                type_id=factual_type_id,
                value="101000, г. Москва, ул. Тверская, д. 5",
            ),
            OrganizationCardRequisiteInput(
                type_id=inn_type_id,
                value="7812345678",
            ),
        ]

        async with async_session_maker() as session:
            await save_organization_card(
                session,
                payload=update_payload,
                organization_id=organization_id,
            )

        updated_card = await self._fetch_card(organization_id)
        updated_requisites = {
            requisite.label: requisite.value for requisite in updated_card.requisites
        }
        self.assertNotIn("Юридический адрес", updated_requisites)
        self.assertEqual(
            updated_requisites["Фактический адрес"],
            "101000, г. Москва, ул. Тверская, д. 5",
        )
        self.assertEqual(updated_requisites["ИНН"], "7812345678")
        self.assertEqual(
            updated_card.map_query,
            "101000, г. Москва, ул. Тверская, д. 5",
        )

    async def test_add_document_requires_internal_number(self):
        organization_id = await self._create_organization()
        datatype_id = await self._fetch_contract_datatype_id()

        async with async_session_maker() as session:
            with self.assertRaisesRegex(
                OrganizationCardValidationError,
                "Номер договора \\(внутренний\\)",
            ):
                await add_organization_document(
                    session,
                    organization_id=organization_id,
                    payload=OrganizationDocumentCreatePayload(
                        name_primary=" ",
                        name_secondary="EXT-ONLY",
                        datatype_id=datatype_id,
                    ),
                )
            await session.rollback()

    async def test_add_document_requires_only_type_and_internal_number(self):
        organization_id = await self._create_organization()
        datatype_id = await self._fetch_contract_datatype_id()

        async with async_session_maker() as session:
            document_id = await add_organization_document(
                session,
                organization_id=organization_id,
                payload=OrganizationDocumentCreatePayload(
                    name_primary="ONLY-PRIMARY",
                    datatype_id=datatype_id,
                ),
            )

        card = await self._fetch_card(organization_id)
        self.assertEqual(card.documents[0].id, document_id)
        self.assertEqual(card.documents[0].title, "ONLY-PRIMARY")

    async def test_upload_and_delete_logo(self):
        organization_id = await self._create_organization()

        async with async_session_maker() as session:
            logotype_id = await save_organization_logo(
                session,
                organization_id=organization_id,
                logo_bytes=TEST_PNG_BYTES,
            )

        card_with_logo = await self._fetch_card(organization_id)
        self.assertIsNotNone(card_with_logo.logo_data_url)
        self.assertTrue(card_with_logo.logo_data_url.startswith("data:image/png;base64,"))

        async with async_session_maker() as session:
            organization = await session.get(OrganizationOrm, organization_id)
            self.assertEqual(organization.logotype_id, logotype_id)
            self.assertIsNotNone(await session.get(OrganizationDetailLogotype, logotype_id))

        async with async_session_maker() as session:
            await delete_organization_logo(
                session,
                organization_id=organization_id,
            )

        card_without_logo = await self._fetch_card(organization_id)
        self.assertIsNone(card_without_logo.logo_data_url)

        async with async_session_maker() as session:
            organization = await session.get(OrganizationOrm, organization_id)
            self.assertIsNone(organization.logotype_id)
            self.assertIsNone(await session.get(OrganizationDetailLogotype, logotype_id))

    async def test_upload_large_logo_stores_resized_preview(self):
        organization_id = await self._create_organization()
        large_logo_bytes = build_large_png_bytes()

        async with async_session_maker() as session:
            logotype_id = await save_organization_logo(
                session,
                organization_id=organization_id,
                logo_bytes=large_logo_bytes,
            )

        async with async_session_maker() as session:
            logotype = await session.get(OrganizationDetailLogotype, logotype_id)
            self.assertIsNotNone(logotype)
            self.assertEqual(logotype.original, large_logo_bytes)
            self.assertLessEqual(len(logotype.compressed or b""), 32 * 1024)

        card = await self._fetch_card(organization_id)
        self.assertIsNotNone(card.logo_data_url)
        self.assertTrue(
            card.logo_data_url.startswith(("data:image/png;base64,", "data:image/jpeg;base64,"))
        )

    async def test_upload_logo_rejects_oversized_source_file(self):
        organization_id = await self._create_organization()

        async with async_session_maker() as session:
            with self.assertRaisesRegex(
                OrganizationCardValidationError,
                "1 МБ",
            ):
                await save_organization_logo(
                    session,
                    organization_id=organization_id,
                    logo_bytes=build_oversized_logo_bytes(),
                )
            await session.rollback()

    async def test_replace_logo_removes_previous_logotype_row(self):
        organization_id = await self._create_organization()

        async with async_session_maker() as session:
            first_logotype_id = await save_organization_logo(
                session,
                organization_id=organization_id,
                logo_bytes=TEST_PNG_BYTES,
            )

        async with async_session_maker() as session:
            second_logotype_id = await save_organization_logo(
                session,
                organization_id=organization_id,
                logo_bytes=TEST_GIF_BYTES,
            )

        self.assertNotEqual(first_logotype_id, second_logotype_id)

        async with async_session_maker() as session:
            organization = await session.get(OrganizationOrm, organization_id)
            self.assertEqual(organization.logotype_id, second_logotype_id)
            self.assertIsNone(await session.get(OrganizationDetailLogotype, first_logotype_id))
            self.assertIsNotNone(await session.get(OrganizationDetailLogotype, second_logotype_id))

        card = await self._fetch_card(organization_id)
        self.assertIsNotNone(card.logo_data_url)
        self.assertTrue(card.logo_data_url.startswith("data:image/gif;base64,"))

    async def test_add_document_and_archive_document(self):
        organization_id = await self._create_organization()
        datatype_id = await self._fetch_contract_datatype_id()

        async with async_session_maker() as session:
            document_id = await add_organization_document(
                session,
                organization_id=organization_id,
                payload=OrganizationDocumentCreatePayload(
                    name_primary="123/Р-1",
                    name_secondary="Основной договор",
                    datatype_id=datatype_id,
                    signing_date=date(2026, 4, 20),
                    chief_name="Сидоров Сидор Сидорович",
                    chief_post="Исполняющий обязанности директора",
                ),
            )

        card = await self._fetch_card(organization_id)
        self.assertEqual(len(card.documents), 1)
        self.assertEqual(card.documents[0].id, document_id)
        self.assertEqual(card.documents[0].title, "123/Р-1")
        self.assertFalse(card.documents[0].is_archived)
        self.assertEqual(card.documents[0].chief_name, "Сидоров Сидор Сидорович")
        self.assertEqual(card.documents[0].chief_post, "Исполняющий обязанности директора")

        async with async_session_maker() as session:
            await archive_organization_document(
                session,
                organization_id=organization_id,
                document_id=document_id,
            )

        updated_card = await self._fetch_card(organization_id)
        self.assertEqual(len(updated_card.documents), 0)
        self.assertEqual(len(updated_card.document_groups), 1)
        self.assertIsNone(updated_card.document_groups[0].actual_document)
        self.assertEqual(len(updated_card.document_groups[0].archived_documents), 1)
        self.assertTrue(updated_card.document_groups[0].archived_documents[0].is_archived)

    async def test_add_document_of_same_type_archives_previous_actual(self):
        organization_id = await self._create_organization()
        datatype_id = await self._fetch_contract_datatype_id()

        async with async_session_maker() as session:
            first_document_id = await add_organization_document(
                session,
                organization_id=organization_id,
                payload=OrganizationDocumentCreatePayload(
                    name_primary="DOC-1",
                    datatype_id=datatype_id,
                    signing_date=date(2026, 4, 1),
                ),
            )

        async with async_session_maker() as session:
            second_document_id = await add_organization_document(
                session,
                organization_id=organization_id,
                payload=OrganizationDocumentCreatePayload(
                    name_primary="DOC-2",
                    datatype_id=datatype_id,
                    signing_date=date(2026, 4, 2),
                ),
            )

        card = await self._fetch_card(organization_id)
        self.assertEqual(len(card.documents), 1)
        self.assertEqual(card.documents[0].id, second_document_id)
        self.assertEqual(len(card.document_groups), 1)
        self.assertEqual(card.document_groups[0].actual_document.id, second_document_id)
        self.assertEqual(len(card.document_groups[0].archived_documents), 1)
        self.assertEqual(card.document_groups[0].archived_documents[0].id, first_document_id)

    async def test_update_document_can_restore_actual_and_store_pdf(self):
        organization_id = await self._create_organization()
        datatype_id = await self._fetch_contract_datatype_id()

        async with async_session_maker() as session:
            first_document_id = await add_organization_document(
                session,
                organization_id=organization_id,
                payload=OrganizationDocumentCreatePayload(
                    name_primary="ACTUAL-1",
                    datatype_id=datatype_id,
                    signing_date=date(2026, 4, 10),
                ),
            )

        async with async_session_maker() as session:
            second_document_id = await add_organization_document(
                session,
                organization_id=organization_id,
                payload=OrganizationDocumentCreatePayload(
                    name_primary="ACTUAL-2",
                    datatype_id=datatype_id,
                    signing_date=date(2026, 4, 11),
                ),
            )

        async with async_session_maker() as session:
            await update_organization_document(
                session,
                organization_id=organization_id,
                document_id=first_document_id,
                payload=OrganizationDocumentUpdatePayload(
                    name_primary="ACTUAL-1-UPDATED",
                    name_secondary="EXT-44",
                    signing_date=date(2026, 4, 12),
                    chief_name="Петров Петр Петрович",
                    chief_post="Директор по договорам",
                    is_actual=True,
                ),
                pdf_bytes=build_test_pdf_bytes(),
                pdf_filename="agreement.pdf",
            )

        card = await self._fetch_card(organization_id)
        self.assertEqual(len(card.documents), 1)
        self.assertEqual(card.documents[0].id, first_document_id)
        self.assertTrue(card.documents[0].has_pdf)
        self.assertIsNotNone(card.documents[0].pdf_url)
        self.assertEqual(card.documents[0].name_secondary, "EXT-44")
        self.assertEqual(card.documents[0].chief_name, "Петров Петр Петрович")

        archived_ids = [row.id for row in card.document_groups[0].archived_documents]
        self.assertIn(second_document_id, archived_ids)

        async with async_session_maker() as session:
            file_bytes, filename = await get_organization_document_pdf(
                session,
                organization_id=organization_id,
                document_id=first_document_id,
            )
            stored_blob = await session.scalar(
                select(ContractPdfDocument.file).where(
                    ContractPdfDocument.contract_id == first_document_id
                )
            )

        self.assertEqual(file_bytes, build_test_pdf_bytes())
        self.assertEqual(stored_blob, build_test_pdf_bytes())
        self.assertEqual(filename, "agreement.pdf")

    async def test_delete_empty_organization_succeeds(self):
        organization_id = await self._create_organization()

        async with async_session_maker() as session:
            await delete_organization_safely(session, organization_id=organization_id)

        self._remove_from_cleanup(organization_id)

        async with async_session_maker() as session:
            deleted_organization = await session.get(OrganizationOrm, organization_id)
        self.assertIsNone(deleted_organization)

    async def test_delete_is_blocked_when_contract_exists(self):
        organization_id = await self._create_organization()
        datatype_id = await self._fetch_contract_datatype_id()

        async with async_session_maker() as session:
            await add_organization_document(
                session,
                organization_id=organization_id,
                payload=OrganizationDocumentCreatePayload(
                    name_primary="BLOCK-1",
                    datatype_id=datatype_id,
                ),
            )

        async with async_session_maker() as session:
            with self.assertRaises(OrganizationDeleteBlockedError) as caught:
                await delete_organization_safely(session, organization_id=organization_id)
            await session.rollback()

        self.assertTrue(caught.exception.reasons)
        self.assertTrue(any(reason.endswith(": 1") for reason in caught.exception.reasons))

    async def test_delete_is_blocked_when_distribution_statistic_exists(self):
        organization_id = await self._create_organization()

        async with async_session_maker() as session:
            session.add(
                OrganizationDistributionStatistic(
                    id=int(time.time_ns() % 1_000_000_000),
                    organization_id=organization_id,
                    year=2026,
                    stat_number=1,
                )
            )
            await session.commit()

        async with async_session_maker() as session:
            with self.assertRaises(OrganizationDeleteBlockedError) as caught:
                await delete_organization_safely(session, organization_id=organization_id)
            await session.rollback()

        self.assertTrue(caught.exception.reasons)
        self.assertTrue(any(reason.endswith(": 1") for reason in caught.exception.reasons))


if __name__ == "__main__":
    unittest.main()

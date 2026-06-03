import time
import unittest

from sqlalchemy import select

from src.app.database import async_session_maker, engine
from src.app.models.detailname_legalinformation import DetailnameLegalInformation
from src.app.schemas.organizations import (
    OrganizationCardRequisiteInput,
    OrganizationCardSavePayload,
)
from src.app.services.organization_card_write import (
    delete_organization_safely,
    save_organization_card,
)
from src.app.services.organization_search import search_organizations_for_header


class OrganizationHeaderSearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.created_organization_ids: list[int] = []

    async def asyncTearDown(self):
        for organization_id in reversed(self.created_organization_ids):
            async with async_session_maker() as session:
                await delete_organization_safely(session, organization_id=organization_id)
        await engine.dispose()

    async def _fetch_inn_type_id(self) -> int:
        async with async_session_maker() as session:
            inn_type_id = await session.scalar(
                select(DetailnameLegalInformation.id).where(
                    DetailnameLegalInformation.name == "ИНН"
                )
            )
        self.assertIsNotNone(inn_type_id)
        return int(inn_type_id)

    async def _create_searchable_organization(self) -> tuple[int, str, str, str]:
        suffix = str(time.time_ns())
        short_name = f"SearchShort {suffix}"
        long_name = f"Search Long Name {suffix}"
        inn_value = suffix[-10:]

        payload = OrganizationCardSavePayload(
            name_short=short_name,
            name_long=long_name,
            settlement_name="г. Санкт-Петербург",
            chief_name="Иванов Иван Иванович",
            chief_post="Генеральный директор",
            is_active=True,
            is_university_department=False,
            contacts=[],
            requisites=[
                OrganizationCardRequisiteInput(
                    type_id=await self._fetch_inn_type_id(),
                    value=inn_value,
                )
            ],
        )

        async with async_session_maker() as session:
            organization_id = await save_organization_card(session, payload=payload)

        self.created_organization_ids.append(organization_id)
        return organization_id, short_name, long_name, inn_value

    async def test_search_finds_organization_by_short_name(self):
        organization_id, short_name, _, _ = await self._create_searchable_organization()

        async with async_session_maker() as session:
            items = await search_organizations_for_header(
                session,
                query=short_name,
            )

        self.assertTrue(any(item.organization_id == organization_id for item in items))

    async def test_search_finds_organization_by_long_name_fragment(self):
        organization_id, _, long_name, _ = await self._create_searchable_organization()
        query = long_name.split()[-1]

        async with async_session_maker() as session:
            items = await search_organizations_for_header(
                session,
                query=query,
            )

        self.assertTrue(any(item.organization_id == organization_id for item in items))

    async def test_search_finds_organization_by_inn(self):
        organization_id, _, _, inn_value = await self._create_searchable_organization()

        async with async_session_maker() as session:
            items = await search_organizations_for_header(
                session,
                query=inn_value,
            )

        matched_item = next(
            (item for item in items if item.organization_id == organization_id),
            None,
        )
        self.assertIsNotNone(matched_item)
        self.assertEqual(matched_item.inn, inn_value)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import ANY, AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from src.app.schemas.organizations import ActiveOrganizationsFilters
from src.app.services.auth import AuthenticatedUser
from src.main import app
from src.tests.http_test_utils import attach_csrf


class DummySessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def build_session_maker(session):
    def _session_maker():
        return DummySessionContext(session)

    return _session_maker


def build_user(*, role: str = "viewer") -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1,
        username="route-tester",
        role=role,  # type: ignore[arg-type]
        is_active=True,
    )


def build_sort_links() -> dict:
    return {
        "organization_name": {
            "is_active": True,
            "current_direction": "asc",
            "next_direction": "desc",
        },
        "contract_number": {
            "is_active": False,
            "current_direction": None,
            "next_direction": "asc",
        },
        "signing_date": {
            "is_active": False,
            "current_direction": None,
            "next_direction": "asc",
        },
    }


def build_page_context(
    request,
    *,
    rows: list[dict] | None = None,
    result_count: int = 0,
    has_more: bool = False,
    next_offset: int | None = None,
) -> dict:
    return {
        "request": request,
        "can_edit": False,
        "filters": ActiveOrganizationsFilters(),
        "custom_sort_requested": False,
        "rows": rows or [],
        "result_count": result_count,
        "has_more": has_more,
        "next_offset": next_offset,
        "sort_links": build_sort_links(),
    }


class ActiveOrganizationsRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_active_page_route_renders_rows_and_result_count(self):
        rows = [
            {
                "organization_id": 11,
                "contract_number": "A-100",
                "signing_date": "20.04.2026",
                "logotype_id": None,
                "organization_name": "Acme University",
                "settlement_name": "Москва",
                "study_fields": ["Информатика", "Дизайн"],
                "phones": ["+7 (800) 555-35-35"],
                "digitals": ["mail@example.org"],
            }
        ]
        async_context = AsyncMock(
            side_effect=lambda request, filters, custom_sort_requested: build_page_context(
                request,
                rows=rows,
                result_count=1,
            )
        )

        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user()),
            ),
            patch(
                "src.app.api.organizations_pages.build_active_organizations_page_context",
                new=async_context,
            ),
        ):
            response = self.client.get("/organizations/active")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Результаты подбора (1 записей)", response.text)
        self.assertIn("Acme University", response.text)
        self.assertIn('data-organization-url="/organizations/11"', response.text)
        self.assertIn('data-export-url="/api/organizations/active/export"', response.text)

        args = async_context.await_args.args
        self.assertIsInstance(args[1], ActiveOrganizationsFilters)
        self.assertFalse(async_context.await_args.kwargs["custom_sort_requested"])

    def test_active_filter_options_route_returns_mocked_payload(self):
        fake_session = object()
        fake_options = {
            "organizations": [{"value": "Acme University", "label": "Acme University"}],
            "contract_numbers": [{"value": "A-100", "label": "A-100"}],
            "settlements": [{"value": "Москва", "label": "Москва"}],
        }
        fetch_options = AsyncMock(return_value=fake_options)

        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user()),
            ),
            patch(
                "src.app.api.organizations_api.async_session_maker",
                new=build_session_maker(fake_session),
            ),
            patch(
                "src.app.api.organizations_api.fetch_active_organizations_filter_options",
                new=fetch_options,
            ),
        ):
            response = self.client.post(
                "/api/organizations/active/filter-options",
                json={"organization_names": ["Acme University"]},
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), fake_options)
        fetch_options.assert_awaited_once()
        called_filters = fetch_options.await_args.args[1]
        self.assertIs(fetch_options.await_args.args[0], fake_session)
        self.assertIsInstance(called_filters, ActiveOrganizationsFilters)
        self.assertEqual(called_filters.organization_names, ["Acme University"])

    def test_active_table_route_renders_html_fragment_for_next_page(self):
        rows = [
            {
                "organization_id": 21,
                "contract_number": "B-200",
                "signing_date": "21.04.2026",
                "logotype_id": 99,
                "organization_name": "Beta Labs",
                "settlement_name": "Казань",
                "study_fields": ["Экономика"],
                "phones": [],
                "digitals": ["beta@example.org"],
            }
        ]
        async_context = AsyncMock(
            side_effect=lambda request, filters, custom_sort_requested: {
                **build_page_context(
                    request,
                    rows=rows,
                    result_count=5,
                    has_more=True,
                    next_offset=3,
                ),
                "filters": filters,
                "custom_sort_requested": custom_sort_requested,
            }
        )

        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user()),
            ),
            patch(
                "src.app.api.organizations_api.build_active_organizations_page_context",
                new=async_context,
            ),
        ):
            response = self.client.post(
                "/api/organizations/active/table",
                json={
                    "filters": {
                        "organization_names": ["Beta Labs"],
                        "offset": 2,
                    },
                    "custom_sort_requested": True,
                },
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Beta Labs", response.text)
        self.assertIn('data-load-more data-next-offset="3"', response.text)
        self.assertIn("Результаты подбора (5 записей)", response.text)

        args = async_context.await_args.args
        self.assertIsInstance(args[1], ActiveOrganizationsFilters)
        self.assertEqual(args[1].organization_names, ["Beta Labs"])
        self.assertEqual(args[1].offset, 2)
        self.assertTrue(async_context.await_args.kwargs["custom_sort_requested"])

    def test_active_export_route_returns_xlsx_attachment(self):
        fake_session = object()
        fetch_rows = AsyncMock(return_value=["row-1", "row-2"])
        serialize_row = Mock(
            side_effect=[
                {
                    "contract_number": "A-100",
                    "signing_date": "20.04.2026",
                    "organization_name": "Acme University",
                    "settlement_name": "Москва",
                    "study_fields": ["Информатика", "Дизайн"],
                    "phones": ["+7 (800) 555-35-35"],
                    "digitals": ["mail@example.org"],
                },
                {
                    "contract_number": None,
                    "signing_date": None,
                    "organization_name": "Beta Labs",
                    "settlement_name": "Казань",
                    "study_fields": [],
                    "phones": [],
                    "digitals": ["beta@example.org"],
                },
            ]
        )
        workbook_bytes = b"fake-xlsx-binary"
        build_workbook = Mock(return_value=workbook_bytes)

        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user()),
            ),
            patch(
                "src.app.api.organizations_api.async_session_maker",
                new=build_session_maker(fake_session),
            ),
            patch(
                "src.app.api.organizations_api.fetch_all_active_organizations",
                new=fetch_rows,
            ),
            patch(
                "src.app.api.organizations_api.serialize_active_row",
                new=serialize_row,
            ),
            patch(
                "src.app.api.organizations_api.build_xlsx_bytes",
                new=build_workbook,
            ),
        ):
            response = self.client.post(
                "/api/organizations/active/export",
                json={
                    "filters": {
                        "organization_names": ["Acme University"],
                    },
                    "custom_sort_requested": True,
                },
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, workbook_bytes)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn(
            "attachment; filename*=UTF-8''",
            response.headers["content-disposition"],
        )
        self.assertIn(".xlsx", response.headers["content-disposition"])

        fetch_rows.assert_awaited_once_with(
            fake_session,
            ANY,
            custom_sort_requested=True,
        )
        called_filters = fetch_rows.await_args.args[1]
        self.assertIsInstance(called_filters, ActiveOrganizationsFilters)
        self.assertEqual(called_filters.organization_names, ["Acme University"])

        self.assertEqual(serialize_row.call_count, 2)
        build_workbook.assert_called_once_with(
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
            rows=[
                [
                    "A-100",
                    "20.04.2026",
                    "Acme University",
                    "Москва",
                    "Информатика\nДизайн",
                    "+7 (800) 555-35-35",
                    "mail@example.org",
                ],
                [
                    "",
                    "",
                    "Beta Labs",
                    "Казань",
                    "",
                    "",
                    "beta@example.org",
                ],
            ],
        )


if __name__ == "__main__":
    unittest.main()

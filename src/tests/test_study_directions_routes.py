import unittest
from unittest.mock import ANY, AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from src.app.schemas.organizations import StudyDirectionsFilters
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
        "faculty_name": {
            "is_active": False,
            "current_direction": None,
            "next_direction": "asc",
        },
        "department_name": {
            "is_active": False,
            "current_direction": None,
            "next_direction": "asc",
        },
        "study_direction_name": {
            "is_active": False,
            "current_direction": None,
            "next_direction": "asc",
        },
        "study_direction_code": {
            "is_active": False,
            "current_direction": None,
            "next_direction": "asc",
        },
        "organization_name": {
            "is_active": True,
            "current_direction": "asc",
            "next_direction": "desc",
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
        "filters": StudyDirectionsFilters(),
        "custom_sort_requested": False,
        "rows": rows or [],
        "result_count": result_count,
        "has_more": has_more,
        "next_offset": next_offset,
        "sort_links": build_sort_links(),
    }


class StudyDirectionsRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_study_directions_page_route_renders_rows_and_filters(self):
        rows = [
            {
                "organization_id": 7,
                "logotype_id": 12,
                "faculty_name": "Ф1",
                "department_name": "И-1",
                "study_direction_name": "Прикладная информатика",
                "study_direction_code": "09.03.03",
                "organization_name": "Acme University",
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
                "src.app.api.organizations_pages.build_study_directions_page_context",
                new=async_context,
            ),
        ):
            response = self.client.get("/organizations/study-directions")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Результаты подбора (1 записей)", response.text)
        self.assertIn("Прикладная информатика", response.text)
        self.assertIn('data-table-url="/api/organizations/study-directions/table"', response.text)
        self.assertIn('data-organization-url="/organizations/7"', response.text)

        args = async_context.await_args.args
        self.assertIsInstance(args[1], StudyDirectionsFilters)
        self.assertFalse(async_context.await_args.kwargs["custom_sort_requested"])

    def test_study_directions_filter_options_route_returns_mocked_payload(self):
        fake_session = object()
        fake_options = {
            "faculties": [{"value": "Ф1", "label": "Ф1"}],
            "departments": [{"value": "И-1", "label": "И-1"}],
            "study_direction_names": [
                {"value": "Прикладная информатика", "label": "Прикладная информатика"}
            ],
            "study_direction_codes": [{"value": "09.03.03", "label": "09.03.03"}],
            "organizations": [{"value": "Acme University", "label": "Acme University"}],
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
                "src.app.api.organizations_api.fetch_study_directions_filter_options",
                new=fetch_options,
            ),
        ):
            response = self.client.post(
                "/api/organizations/study-directions/filter-options",
                json={"faculty_names": ["Ф1"]},
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), fake_options)
        called_filters = fetch_options.await_args.args[1]
        self.assertIs(fetch_options.await_args.args[0], fake_session)
        self.assertIsInstance(called_filters, StudyDirectionsFilters)
        self.assertEqual(called_filters.faculty_names, ["Ф1"])

    def test_study_directions_table_route_renders_html_fragment(self):
        rows = [
            {
                "organization_id": 8,
                "logotype_id": 15,
                "faculty_name": "Ф2",
                "department_name": "И-2",
                "study_direction_name": "Мехатроника",
                "study_direction_code": "15.03.06",
                "organization_name": "Beta Labs",
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
                "src.app.api.organizations_api.build_study_directions_page_context",
                new=async_context,
            ),
        ):
            response = self.client.post(
                "/api/organizations/study-directions/table",
                json={
                    "filters": {
                        "faculty_names": ["Ф2"],
                        "offset": 2,
                    },
                    "custom_sort_requested": True,
                },
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Мехатроника", response.text)
        self.assertIn('data-load-more data-next-offset="3"', response.text)
        self.assertIn("Результаты подбора (5 записей)", response.text)

        args = async_context.await_args.args
        self.assertIsInstance(args[1], StudyDirectionsFilters)
        self.assertEqual(args[1].faculty_names, ["Ф2"])
        self.assertEqual(args[1].offset, 2)
        self.assertTrue(async_context.await_args.kwargs["custom_sort_requested"])

    def test_study_directions_export_route_returns_xlsx_attachment(self):
        fake_session = object()
        fetch_rows = AsyncMock(return_value=["row-1", "row-2"])
        serialize_row = Mock(
            side_effect=[
                {
                    "faculty_name": "Ф1",
                    "department_name": "И-1",
                    "study_direction_name": "Прикладная информатика",
                    "study_direction_code": "09.03.03",
                    "logotype_id": 12,
                    "organization_name": "Acme University",
                    "phones": ["+7 (800) 555-35-35"],
                    "digitals": ["mail@example.org"],
                },
                {
                    "faculty_name": "Ф2",
                    "department_name": "И-2",
                    "study_direction_name": "Мехатроника",
                    "study_direction_code": "15.03.06",
                    "logotype_id": None,
                    "organization_name": "Beta Labs",
                    "phones": [],
                    "digitals": ["beta@example.org"],
                },
            ]
        )
        workbook_bytes = b"fake-study-directions-xlsx"
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
                "src.app.api.organizations_api.fetch_all_study_directions",
                new=fetch_rows,
            ),
            patch(
                "src.app.api.organizations_api.serialize_study_direction_row",
                new=serialize_row,
            ),
            patch(
                "src.app.api.organizations_api.build_xlsx_bytes",
                new=build_workbook,
            ),
        ):
            response = self.client.post(
                "/api/organizations/study-directions/export",
                json={
                    "filters": {
                        "faculty_names": ["Ф1"],
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
        self.assertIn(
            "%D0%9D%D0%B0%D0%BF%D1%80%D0%B0%D0%B2%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F_",
            response.headers["content-disposition"],
        )

        fetch_rows.assert_awaited_once_with(
            fake_session,
            ANY,
            custom_sort_requested=True,
        )
        called_filters = fetch_rows.await_args.args[1]
        self.assertIsInstance(called_filters, StudyDirectionsFilters)
        self.assertEqual(called_filters.faculty_names, ["Ф1"])

        self.assertEqual(serialize_row.call_count, 2)
        build_workbook.assert_called_once_with(
            sheet_name="Направления подготовки",
            headers=[
                "Факультет",
                "Кафедра",
                "Наименование направления",
                "Шифры направления",
                "Логотип",
                "Наименование организации",
                "Телефонные контакты",
                "Цифровые контакты",
            ],
            rows=[
                [
                    "Ф1",
                    "И-1",
                    "Прикладная информатика",
                    "09.03.03",
                    "Да",
                    "Acme University",
                    "+7 (800) 555-35-35",
                    "mail@example.org",
                ],
                [
                    "Ф2",
                    "И-2",
                    "Мехатроника",
                    "15.03.06",
                    "",
                    "Beta Labs",
                    "",
                    "beta@example.org",
                ],
            ],
        )


if __name__ == "__main__":
    unittest.main()

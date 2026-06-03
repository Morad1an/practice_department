import unittest
from unittest.mock import ANY, AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from src.app.schemas.organizations import GroupDistributionFilters
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
        key: {
            "is_active": key == "department_name",
            "current_direction": "asc" if key == "department_name" else None,
            "next_direction": "desc" if key == "department_name" else "asc",
        }
        for key in [
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
    }


def build_page_context(
    request,
    *,
    rows: list[dict] | None = None,
    result_count: int = 0,
    has_more: bool = False,
    next_offset: int | None = None,
    selected_semester_label: str = "2024/2025 | Осенний семестр",
) -> dict:
    return {
        "request": request,
        "can_edit": False,
        "filters": GroupDistributionFilters(semester_id=1),
        "custom_sort_requested": False,
        "rows": rows or [],
        "result_count": result_count,
        "has_more": has_more,
        "next_offset": next_offset,
        "sort_links": build_sort_links(),
        "semester_options": [
            {
                "value": 1,
                "label": "2024/2025 | Осенний семестр",
                "record_count": 305,
            },
            {
                "value": 2,
                "label": "2024/2025 | Весенний семестр",
                "record_count": 0,
            },
        ],
        "selected_semester_label": selected_semester_label,
    }


class GroupsRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_groups_page_route_renders_rows_and_semester_filter(self):
        rows = [
            {
                "organization_id": 7,
                "department_name": "А9",
                "study_direction_code": "13.03.01",
                "study_direction_name": "Теплоэнергетика и теплотехника",
                "study_profile_name": "Энергетика теплотехнологий",
                "group_name": "А912Б",
                "course": 4,
                "distributed_quantity": 14,
                "organization_name": "Acme University",
                "order_name": "339-С(О)",
                "signing_date": "29.08.2024",
                "practice_name": "Практика",
                "practice_date_begin": "02.09.2024",
                "practice_date_end": "29.12.2024",
                "practice_chief_name": "Савелова К.Э.",
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
                "src.app.api.organizations_pages.build_group_distribution_page_context",
                new=async_context,
            ),
        ):
            response = self.client.get("/organizations/groups")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Результаты распределения (1 записей)", response.text)
        self.assertIn("Теплоэнергетика и теплотехника", response.text)
        self.assertIn('data-table-url="/api/organizations/groups/table"', response.text)
        self.assertIn("2024/2025 | Осенний семестр", response.text)
        self.assertIn('data-organization-url="/organizations/7"', response.text)

        args = async_context.await_args.args
        self.assertIsInstance(args[1], GroupDistributionFilters)
        self.assertFalse(async_context.await_args.kwargs["custom_sort_requested"])

    def test_groups_filter_options_route_returns_mocked_payload(self):
        fake_session = object()
        fake_options = {
            "semesters": [
                {
                    "value": 1,
                    "label": "2024/2025 | Осенний семестр",
                    "record_count": 305,
                }
            ]
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
                "src.app.api.organizations_api.fetch_group_distribution_filter_options",
                new=fetch_options,
            ),
        ):
            response = self.client.post(
                "/api/organizations/groups/filter-options",
                json={"semester_id": 1},
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), fake_options)
        fetch_options.assert_awaited_once_with(fake_session)

    def test_groups_table_route_renders_html_fragment(self):
        rows = [
            {
                "organization_id": 8,
                "department_name": "И5",
                "study_direction_code": "09.03.04",
                "study_direction_name": "Программная инженерия",
                "study_profile_name": "Разработка ПО",
                "group_name": "И512",
                "course": 3,
                "distributed_quantity": 18,
                "organization_name": "Beta Labs",
                "order_name": "225-С(О)",
                "signing_date": "10.06.2024",
                "practice_name": "Технологическая практика",
                "practice_date_begin": "24.06.2024",
                "practice_date_end": "21.07.2024",
                "practice_chief_name": "Иванов И.И.",
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
                "src.app.api.organizations_api.build_group_distribution_page_context",
                new=async_context,
            ),
        ):
            response = self.client.post(
                "/api/organizations/groups/table",
                json={
                    "filters": {
                        "semester_id": 1,
                        "offset": 2,
                    },
                    "custom_sort_requested": True,
                },
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Программная инженерия", response.text)
        self.assertIn('data-load-more data-next-offset="3"', response.text)
        self.assertIn("Результаты распределения (5 записей)", response.text)

        args = async_context.await_args.args
        self.assertIsInstance(args[1], GroupDistributionFilters)
        self.assertEqual(args[1].semester_id, 1)
        self.assertEqual(args[1].offset, 2)
        self.assertTrue(async_context.await_args.kwargs["custom_sort_requested"])

    def test_groups_export_route_returns_xlsx_attachment(self):
        fake_session = object()
        fetch_rows = AsyncMock(return_value=["row-1", "row-2"])
        serialize_row = Mock(
            side_effect=[
                {
                    "department_name": "А9",
                    "study_direction_code": "13.03.01",
                    "study_direction_name": "Теплоэнергетика и теплотехника",
                    "study_profile_name": "Энергетика теплотехнологий",
                    "group_name": "А912Б",
                    "course": 4,
                    "distributed_quantity": 14,
                    "organization_name": "Acme University",
                    "order_name": "339-С(О)",
                    "signing_date": "29.08.2024",
                    "practice_name": "Практика",
                    "practice_date_begin": "02.09.2024",
                    "practice_date_end": "29.12.2024",
                    "practice_chief_name": "Савелова К.Э.",
                },
                {
                    "department_name": "И5",
                    "study_direction_code": "09.03.04",
                    "study_direction_name": "Программная инженерия",
                    "study_profile_name": "Разработка ПО",
                    "group_name": "И512",
                    "course": 3,
                    "distributed_quantity": 18,
                    "organization_name": "Beta Labs",
                    "order_name": "225-С(О)",
                    "signing_date": "10.06.2024",
                    "practice_name": "Технологическая практика",
                    "practice_date_begin": "24.06.2024",
                    "practice_date_end": "21.07.2024",
                    "practice_chief_name": "Иванов И.И.",
                },
            ]
        )
        workbook_bytes = b"fake-groups-xlsx"
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
                "src.app.api.organizations_api.fetch_all_group_distribution",
                new=fetch_rows,
            ),
            patch(
                "src.app.api.organizations_api.serialize_group_distribution_row",
                new=serialize_row,
            ),
            patch(
                "src.app.api.organizations_api.build_xlsx_bytes",
                new=build_workbook,
            ),
        ):
            response = self.client.post(
                "/api/organizations/groups/export",
                json={
                    "filters": {
                        "semester_id": 1,
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
            "%D0%97%D0%B0%D1%8F%D0%B2%D0%BA%D0%B0_",
            response.headers["content-disposition"],
        )

        fetch_rows.assert_awaited_once_with(
            fake_session,
            ANY,
            custom_sort_requested=True,
        )
        called_filters = fetch_rows.await_args.args[1]
        self.assertIsInstance(called_filters, GroupDistributionFilters)
        self.assertEqual(called_filters.semester_id, 1)

        self.assertEqual(serialize_row.call_count, 2)
        build_workbook.assert_called_once_with(
            sheet_name="Распределение по группам",
            headers=[
                "Кафедра",
                "Шифр направления",
                "Направление подготовки",
                "Профиль обучения",
                "Группа",
                "Курс",
                "Кол-во распределённых",
                "Наименование организации",
                "Номер приказа",
                "Дата подписания",
                "Наименование практики",
                "Дата начала",
                "Дата окончания",
                "Фамилия ИО руководителя",
            ],
            rows=[
                [
                    "А9",
                    "13.03.01",
                    "Теплоэнергетика и теплотехника",
                    "Энергетика теплотехнологий",
                    "А912Б",
                    4,
                    14,
                    "Acme University",
                    "339-С(О)",
                    "29.08.2024",
                    "Практика",
                    "02.09.2024",
                    "29.12.2024",
                    "Савелова К.Э.",
                ],
                [
                    "И5",
                    "09.03.04",
                    "Программная инженерия",
                    "Разработка ПО",
                    "И512",
                    3,
                    18,
                    "Beta Labs",
                    "225-С(О)",
                    "10.06.2024",
                    "Технологическая практика",
                    "24.06.2024",
                    "21.07.2024",
                    "Иванов И.И.",
                ],
            ],
        )


if __name__ == "__main__":
    unittest.main()

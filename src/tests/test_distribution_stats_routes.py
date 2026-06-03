import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.app.schemas.organizations import DistributionStatsFilters
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


def build_table_payload() -> dict:
    return {
        "available_years": [2022, 2023, 2024, 2025],
        "selected_year_from": 2022,
        "selected_year_to": 2025,
        "organization_status": "all",
        "actual_contract_status": "all",
        "years": [2022, 2023, 2024, 2025],
        "columns": [
            {"key": "contract_number", "label": "Номер договора", "kind": "text", "year": None},
            {"key": "year_2022", "label": "2022", "kind": "year", "year": 2022},
            {"key": "total_for_period", "label": "За все время", "kind": "total", "year": None},
        ],
        "rows": [
            {
                "organization_id": 7,
                "contract_id": 17,
                "contract_number": "ПР-7/22",
                "signing_date": "14.03.2022",
                "logotype_id": 12,
                "organization_name": "Acme University",
                "year_values": [
                    {"year": 2022, "value": 5},
                    {"year": 2023, "value": 7},
                    {"year": 2024, "value": 8},
                    {"year": 2025, "value": 6},
                ],
                "total_for_period": 26,
            }
        ],
        "total_rows": 1,
    }


def build_chart_payload() -> dict:
    return {
        "available_years": [2022, 2023, 2024, 2025],
        "selected_year_from": 2022,
        "selected_year_to": 2025,
        "organization_status": "all",
        "actual_contract_status": "all",
        "years": [2022, 2023, 2024, 2025],
        "items": [
            {
                "organization_id": 7,
                "contract_id": 17,
                "contract_number": "ПР-7/22",
                "organization_name": "Acme University",
                "logotype_id": 12,
                "year_values": [
                    {"year": 2022, "value": 5},
                    {"year": 2023, "value": 7},
                    {"year": 2024, "value": 8},
                    {"year": 2025, "value": 6},
                ],
                "total_for_period": 26,
            }
        ],
        "total_items": 1,
    }


class DistributionStatsRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_distribution_stats_page_route_renders_shell(self):
        async_context = AsyncMock(
            side_effect=lambda request, filters: {
                "request": request,
                "can_edit": False,
                "filters": filters,
                "years_payload": {
                    "available_years": [2022, 2023, 2024, 2025],
                    "default_year_from": 2022,
                    "default_year_to": 2025,
                },
                "table_payload": build_table_payload(),
            }
        )

        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user()),
            ),
            patch(
                "src.app.api.organizations_pages.build_distribution_stats_page_context",
                new=async_context,
            ),
        ):
            response = self.client.get("/organizations/distribution-stats")

        self.assertEqual(response.status_code, 200)
        self.assertIn('data-table-url="/api/organizations/distribution-stats/table"', response.text)
        self.assertIn("data-organization-status-select", response.text)
        self.assertIn("data-actual-contract-status-select", response.text)

        args = async_context.await_args.args
        self.assertIsInstance(args[1], DistributionStatsFilters)

    def test_timeline_stats_page_route_renders_shell(self):
        async_context = AsyncMock(
            side_effect=lambda request, filters: {
                "request": request,
                "can_edit": False,
                "filters": filters,
                "years_payload": {
                    "available_years": [2022, 2023, 2024, 2025],
                    "default_year_from": 2022,
                    "default_year_to": 2025,
                },
                "chart_payload": build_chart_payload(),
            }
        )

        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user()),
            ),
            patch(
                "src.app.api.organizations_pages.build_timeline_stats_page_context",
                new=async_context,
            ),
        ):
            response = self.client.get("/organizations/timeline-stats")

        self.assertEqual(response.status_code, 200)
        self.assertIn('data-chart-url="/api/organizations/distribution-stats/chart"', response.text)
        self.assertIn("data-organization-status-select", response.text)
        self.assertIn("data-actual-contract-status-select", response.text)

        args = async_context.await_args.args
        self.assertIsInstance(args[1], DistributionStatsFilters)

    def test_distribution_stats_years_route_returns_payload(self):
        fake_session = object()
        fetch_years = AsyncMock(
            return_value={
                "available_years": [2022, 2023, 2024, 2025],
                "default_year_from": 2022,
                "default_year_to": 2025,
            }
        )

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
                "src.app.api.organizations_api.fetch_distribution_stats_years",
                new=fetch_years,
            ),
        ):
            response = self.client.get("/api/organizations/distribution-stats/years")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["available_years"], [2022, 2023, 2024, 2025])
        fetch_years.assert_awaited_once_with(fake_session)

    def test_distribution_stats_table_route_returns_payload(self):
        fake_session = object()
        fetch_table = AsyncMock(return_value=build_table_payload())

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
                "src.app.api.organizations_api.fetch_distribution_stats_table",
                new=fetch_table,
            ),
        ):
            response = self.client.post(
                "/api/organizations/distribution-stats/table",
                json={
                    "year_from": 2022,
                    "year_to": 2025,
                    "organization_status": "inactive",
                    "actual_contract_status": "without_actual_contract",
                },
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_rows"], 1)
        called_filters = fetch_table.await_args.args[1]
        self.assertIsInstance(called_filters, DistributionStatsFilters)
        self.assertEqual(called_filters.year_from, 2022)
        self.assertEqual(called_filters.year_to, 2025)
        self.assertEqual(called_filters.organization_status, "inactive")
        self.assertEqual(called_filters.actual_contract_status, "without_actual_contract")

    def test_distribution_stats_chart_route_returns_payload(self):
        fake_session = object()
        fetch_chart = AsyncMock(return_value=build_chart_payload())

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
                "src.app.api.organizations_api.fetch_distribution_stats_chart",
                new=fetch_chart,
            ),
        ):
            response = self.client.post(
                "/api/organizations/distribution-stats/chart",
                json={
                    "year_from": 2023,
                    "year_to": 2025,
                    "organization_status": "active",
                    "actual_contract_status": "with_actual_contract",
                },
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_items"], 1)
        called_filters = fetch_chart.await_args.args[1]
        self.assertIsInstance(called_filters, DistributionStatsFilters)
        self.assertEqual(called_filters.year_from, 2023)
        self.assertEqual(called_filters.year_to, 2025)
        self.assertEqual(called_filters.organization_status, "active")
        self.assertEqual(called_filters.actual_contract_status, "with_actual_contract")


if __name__ == "__main__":
    unittest.main()

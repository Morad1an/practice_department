import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.app.config import settings
from src.app.schemas.organizations import ActiveOrganizationsFilters
from src.app.services.auth import AuthenticatedUser
from src.main import app
from src.tests.http_test_utils import attach_csrf, build_form_with_csrf


def build_user(*, role: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1,
        username="tester",
        role=role,  # type: ignore[arg-type]
        is_active=True,
    )


def build_active_page_context(request) -> dict:
    return {
        "request": request,
        "filters": ActiveOrganizationsFilters(),
        "custom_sort_requested": False,
        "rows": [],
        "result_count": 0,
        "has_more": False,
        "next_offset": None,
        "sort_links": {
            "organization_name": {
                "is_active": True,
                "current_direction": "asc",
                "next_direction": "desc",
            },
            "contract_number": {
                "is_active": False,
                "current_direction": "asc",
                "next_direction": "asc",
            },
            "signing_date": {
                "is_active": False,
                "current_direction": "asc",
                "next_direction": "asc",
            },
            "settlement_name": {
                "is_active": False,
                "current_direction": "asc",
                "next_direction": "asc",
            },
        },
    }


class AuthAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_unauthenticated_page_redirects_to_login(self):
        response = self.client.get("/organizations/active", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/login?next=%2Forganizations%2Factive", response.headers["location"])

    def test_unauthenticated_mutation_api_returns_401(self):
        response = self.client.post(
            "/api/organizations",
            json={"contacts": [], "requisites": []},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Требуется авторизация."})

    def test_login_success_sets_cookie_and_redirects(self):
        with patch(
            "src.app.api.auth_pages.authenticate_user",
            new=AsyncMock(return_value=build_user(role="editor")),
        ):
            response = self.client.post(
                "/login",
                data=build_form_with_csrf(
                    self.client,
                    {
                        "username": "editor",
                        "password": "password123",
                        "next": "/organizations/active",
                    },
                ),
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/organizations/active")
        self.assertIn(settings.AUTH_COOKIE_NAME, response.headers.get("set-cookie", ""))

    def test_logout_clears_cookie(self):
        with patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="editor")),
        ):
            response = self.client.post(
                "/logout",
                data=build_form_with_csrf(self.client, {}),
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")
        self.assertIn("Max-Age=0", response.headers.get("set-cookie", ""))

    def test_viewer_cannot_open_new_organization_page(self):
        with patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="viewer")),
        ):
            response = self.client.get("/organizations/new", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/organizations/active")

    def test_viewer_cannot_create_organization(self):
        with patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="viewer")),
        ):
            response = self.client.post(
                "/api/organizations",
                json={"contacts": [], "requisites": []},
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "Недостаточно прав для изменения данных."},
        )

    def test_editor_can_create_organization(self):
        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user(role="editor")),
            ),
            patch(
                "src.app.api.organizations_api.save_organization_card",
                new=AsyncMock(return_value=77),
            ),
        ):
            response = self.client.post(
                "/api/organizations",
                json={"contacts": [], "requisites": []},
                headers=attach_csrf(self.client),
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(),
            {
                "organization_id": 77,
                "message": "Организация сохранена.",
                "redirect_url": "/organizations/77",
            },
        )

    def test_viewer_active_page_hides_add_organization_link(self):
        async_context = AsyncMock(
            side_effect=lambda request, filters, custom_sort_requested: build_active_page_context(
                request
            )
        )
        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user(role="viewer")),
            ),
            patch(
                "src.app.api.organizations_pages.build_active_organizations_page_context",
                new=async_context,
            ),
        ):
            response = self.client.get("/organizations/active")

        self.assertEqual(response.status_code, 200)
        self.assertIn("tester", response.text)
        self.assertIn("Просмотр", response.text)
        self.assertNotIn('href="/organizations/new"', response.text)
        self.assertIn('action="/logout"', response.text)

    def test_editor_active_page_shows_add_organization_link(self):
        async_context = AsyncMock(
            side_effect=lambda request, filters, custom_sort_requested: build_active_page_context(
                request
            )
        )
        with (
            patch(
                "src.main.resolve_auth_user_from_session_cookie",
                new=AsyncMock(return_value=build_user(role="editor")),
            ),
            patch(
                "src.app.api.organizations_pages.build_active_organizations_page_context",
                new=async_context,
            ),
        ):
            response = self.client.get("/organizations/active")

        self.assertEqual(response.status_code, 200)
        self.assertIn("tester", response.text)
        self.assertIn("Редактор", response.text)
        self.assertIn('href="/organizations/new"', response.text)
        self.assertIn('action="/logout"', response.text)


if __name__ == "__main__":
    unittest.main()

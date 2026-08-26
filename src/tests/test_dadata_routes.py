from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.app.schemas.organizations import OrganizationCardPage
from src.app.services.auth import AuthenticatedUser
from src.app.services.dadata.runtime import DadataRuntimeError
from src.app.services.dadata.schemas import (
    DadataLookupResponse,
    DadataRefreshAllResponse,
    DadataRefreshResponse,
)
from src.main import app
from src.tests.http_test_utils import attach_csrf


def build_user(*, role: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1,
        username="tester",
        role=role,  # type: ignore[arg-type]
        is_active=True,
    )


async def build_detail_context(request, organization_id: int):
    return {
        "request": request,
        "can_edit": bool(request.state.can_edit),
        "can_admin": bool(request.state.can_admin),
        "active_tab": None,
        "create_mode": False,
        "organization": OrganizationCardPage(
            id=organization_id,
            name_short="Тестовая организация",
            is_active=True,
        ).model_dump(),
        "contact_type_options": [],
        "document_type_options": [],
        "requisite_type_options": [],
        "settlement_options": [],
        "study_field_options": [],
        "page_title": "Тестовая организация",
        "page_heading": "Тестовая организация",
    }


def test_dadata_lookup_requires_authentication():
    client = TestClient(app)

    response = client.post(
        "/api/dadata/party/lookup",
        json={"inn": "7719402047"},
    )

    assert response.status_code == 401


def test_dadata_lookup_requires_editor_role():
    client = TestClient(app)

    with patch(
        "src.main.resolve_auth_user_from_session_cookie",
        new=AsyncMock(return_value=build_user(role="viewer")),
    ):
        response = client.post(
            "/api/dadata/party/lookup",
            json={"inn": "7719402047"},
            headers=attach_csrf(client),
        )

    assert response.status_code == 403


def test_dadata_lookup_returns_service_response_for_editor():
    client = TestClient(app)
    service_response = DadataLookupResponse(
        status="queued",
        job_id="job-1",
        message="Поиск данных поставлен в очередь.",
    )

    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="editor")),
        ),
        patch(
            "src.app.api.dadata.queue_lookup_organization_by_inn",
            new=AsyncMock(return_value=service_response),
        ) as lookup_mock,
    ):
        response = client.post(
            "/api/dadata/party/lookup",
            json={"inn": "7719402047"},
            headers=attach_csrf(client),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["job_id"] == "job-1"
    assert response.json()["message"] == "Поиск данных поставлен в очередь."
    lookup_mock.assert_awaited_once()


def test_dadata_refresh_all_requires_admin_role():
    client = TestClient(app)
    with patch(
        "src.main.resolve_auth_user_from_session_cookie",
        new=AsyncMock(return_value=build_user(role="editor")),
    ):
        response = client.post(
            "/api/dadata/refresh-all",
            headers=attach_csrf(client),
        )

    assert response.status_code == 403


def test_viewer_cannot_queue_refresh_for_one_organization():
    client = TestClient(app)
    queued = DadataRefreshResponse(
        status="queued",
        job_id="one-job",
        organization_id=7,
    )
    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="viewer")),
        ),
        patch(
            "src.app.api.dadata.queue_organization_refresh",
            new=AsyncMock(return_value=queued),
        ) as queue_mock,
    ):
        response = client.post(
            "/api/organizations/7/dadata-refresh",
            headers=attach_csrf(client),
        )

    assert response.status_code == 403
    queue_mock.assert_not_awaited()


@pytest.mark.parametrize(("role", "expect_refresh"), [("viewer", False), ("admin", True)])
def test_detail_page_exposes_sync_button_by_role(role: str, expect_refresh: bool):
    client = TestClient(app)
    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role=role)),
        ),
        patch(
            "src.app.api.organizations_pages.build_organization_detail_page_context",
            side_effect=build_detail_context,
        ),
    ):
        response = client.get("/organizations/7")

    assert response.status_code == 200
    assert (
        "data-dadata-refresh>Синхронизация данных с ЕГРЮЛ</button>" in response.text
    ) is expect_refresh
    assert "data-dadata-refresh-all>" not in response.text


def test_dadata_refresh_all_queues_job_for_admin():
    client = TestClient(app)
    queued = DadataRefreshAllResponse(status="queued", job_id="full-job")
    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="admin")),
        ),
        patch(
            "src.app.api.dadata.queue_full_refresh",
            new=AsyncMock(return_value=queued),
        ) as queue_mock,
        patch("src.app.api.dadata.require_redis_client", new=AsyncMock()),
    ):
        response = client.post(
            "/api/dadata/refresh-all",
            headers=attach_csrf(client),
        )

    assert response.status_code == 200
    assert response.json()["job_id"] == "full-job"
    queue_mock.assert_awaited_once_with(manual=True)


def test_full_refresh_returns_503_when_redis_is_unavailable():
    client = TestClient(app)
    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="admin")),
        ),
        patch(
            "src.app.api.dadata.require_redis_client",
            new=AsyncMock(side_effect=DadataRuntimeError("Redis недоступен")),
        ),
    ):
        response = client.post("/api/dadata/refresh-all", headers=attach_csrf(client))

    assert response.status_code == 503


def test_dadata_job_status_returns_persisted_result():
    client = TestClient(app)
    job = {
        "job_id": "job-1",
        "kind": "lookup",
        "status": "success",
        "result": {"status": "ready", "data": {"inn": "7719402047"}},
        "message": "Готово",
        "created_at": 1.0,
        "updated_at": 2.0,
        "payload": {"created_by_user_id": 1},
    }
    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="editor")),
        ),
        patch("src.app.api.dadata.get_job", new=AsyncMock(return_value=job)),
    ):
        response = client.get("/api/dadata/jobs/job-1")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["result"]["data"]["inn"] == "7719402047"


def test_dadata_job_status_is_hidden_from_another_editor():
    client = TestClient(app)
    job = {
        "job_id": "job-1",
        "kind": "lookup",
        "status": "success",
        "result": None,
        "message": None,
        "created_at": 1.0,
        "updated_at": 2.0,
        "payload": {"created_by_user_id": 2},
    }
    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="editor")),
        ),
        patch("src.app.api.dadata.get_job", new=AsyncMock(return_value=job)),
    ):
        response = client.get("/api/dadata/jobs/job-1")

    assert response.status_code == 403


def test_admin_can_read_another_users_dadata_job():
    client = TestClient(app)
    job = {
        "job_id": "job-1",
        "kind": "refresh_one",
        "status": "success",
        "result": None,
        "message": None,
        "created_at": 1.0,
        "updated_at": 2.0,
        "payload": {"created_by_user_id": 2},
    }
    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="admin")),
        ),
        patch("src.app.api.dadata.get_job", new=AsyncMock(return_value=job)),
    ):
        response = client.get("/api/dadata/jobs/job-1")

    assert response.status_code == 200


def test_full_refresh_job_status_includes_nonblocking_progress():
    client = TestClient(app)
    job = {
        "job_id": "full-job",
        "kind": "refresh_all",
        "status": "running",
        "result": None,
        "message": None,
        "created_at": 1.0,
        "updated_at": 2.0,
        "payload": {},
    }
    with (
        patch(
            "src.main.resolve_auth_user_from_session_cookie",
            new=AsyncMock(return_value=build_user(role="admin")),
        ),
        patch("src.app.api.dadata.get_job", new=AsyncMock(return_value=job)),
        patch(
            "src.app.api.dadata.get_full_refresh_progress",
            new=AsyncMock(return_value={"total": 20, "processed": 7, "status:success": 6}),
        ),
    ):
        response = client.get("/api/dadata/jobs/full-job")

    assert response.status_code == 200
    assert response.json()["result"]["processed"] == 7
    assert response.json()["result"]["total_candidates"] == 20

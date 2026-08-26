from pathlib import Path

DETAIL_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "organization_detail.js"
ACTIVE_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "active_organizations.js"


def test_save_rollback_and_single_sync_reload_the_card_from_server_state():
    source = DETAIL_JS.read_text(encoding="utf-8")

    assert 'persistToastForRedirect(successMessage, "success")' in source
    assert 'operation.result.message || "Данные организации синхронизированы."' in source
    assert source.count("window.location.reload()") >= 3
    assert "formChanged" in source


def test_create_lookup_redirects_after_refreshing_existing_card_and_scrolls_new_form_up():
    source = DETAIL_JS.read_text(encoding="utf-8")

    assert "window.location.assign(payload.existing_organization_url)" in source
    assert 'new Set(["ready", "updated"]).has(result?.status)' in source
    assert 'window.scrollTo({top: 0, behavior: "smooth"})' in source


def test_dadata_actions_support_queued_jobs_and_direct_fallback_responses():
    source = DETAIL_JS.read_text(encoding="utf-8")

    assert "const resolveDadataOperation = async (payload) =>" in source
    assert 'if (payload.status === "queued")' in source
    assert "const operation = await resolveDadataOperation(payload);" in source


def test_organization_detail_has_no_user_facing_dadata_text():
    source = DETAIL_JS.read_text(encoding="utf-8")

    assert "Задача Dadata" not in source
    assert "адрес проверки задачи Dadata" not in source


def test_full_refresh_status_monitor_is_nonblocking_and_survives_page_reload():
    source = ACTIVE_JS.read_text(encoding="utf-8")

    assert "fullRefreshJobStorageKey" in source
    assert "window.setInterval" in source
    assert "10_000" in source
    assert "sessionStorage.setItem(fullRefreshJobStorageKey, jobId)" in source

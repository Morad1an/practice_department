from pathlib import Path

DETAIL_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "organization_detail.js"
ACTIVE_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "active_organizations.js"
DETAIL_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "app" / "templates" / "organizations" / "detail.html"
)


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


def test_card_action_buttons_follow_the_actual_form_snapshot():
    source = DETAIL_JS.read_text(encoding="utf-8")

    assert "initialFormSnapshot" in source
    assert "JSON.stringify(collectPayload()) !== initialFormSnapshot" in source
    assert "saveButton.disabled = isBusy || !formChanged" in source
    assert "rollbackButton.disabled = !formChanged" in source
    assert "new MutationObserver(syncFormChangedState)" in source


def test_delete_confirmation_uses_the_server_preview_and_redirect_notification():
    source = DETAIL_JS.read_text(encoding="utf-8")

    assert "fetchDeletionPreview" in source
    assert "buildDeletionConfirmationMessage(preview)" in source
    assert "organization-confirm-list" in source
    assert "confirmMessageNode.replaceChildren()" in source
    assert "persistDeletionToast(payload.message" in source
    assert 'window.location.assign("/organizations/active")' in source


def test_document_rows_show_contract_type_and_only_labeled_populated_metadata():
    source = DETAIL_TEMPLATE.read_text(encoding="utf-8")

    assert source.count("{{ actual_document.datatype_label or group.datatype_label }}") >= 2
    assert source.count("{{ document.datatype_label or group.datatype_label }}") >= 2
    assert source.count("Внутренний номер:") == 2
    assert source.count("Внешний номер:") == 2
    assert source.count("Дата подписания:") == 2

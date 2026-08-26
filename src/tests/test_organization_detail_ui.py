from pathlib import Path

DETAIL_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "organization_detail.js"
ACTIVE_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "active_organizations.js"
TABLE_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "active_organizations_table.js"
STATS_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "distribution_stats.js"
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


def test_dadata_populates_existing_primary_okved_requisite():
    source = DETAIL_JS.read_text(encoding="utf-8")

    assert 'ensureRequisiteValue(["ОКВЭД (ОСНОВНОЙ)", "ОКВЭД"], data.okved)' in source


def test_organization_rows_open_on_double_click_even_when_text_is_selected():
    table_source = TABLE_JS.read_text(encoding="utf-8")
    stats_source = STATS_JS.read_text(encoding="utf-8")

    assert table_source.count('addEventListener("dblclick"') == 1
    assert 'querySelectorAll("[data-organization-row]")' in table_source
    assert "window.getSelection" not in table_source
    assert 'addEventListener("dblclick"' in stats_source
    assert 'querySelectorAll("[data-organization-row]")' in stats_source
    assert "window.getSelection" not in stats_source
    assert 'closest("button, a, input, textarea, select, label")' in table_source
    assert 'closest("button, a, input, textarea, select, label")' in stats_source


def test_organization_rows_do_not_show_double_click_tooltip():
    template_paths = [
        Path(__file__).resolve().parents[1] / "app" / "templates" / "organizations" / name
        for name in ("active.html", "study_directions.html", "groups.html")
    ]
    template_sources = [path.read_text(encoding="utf-8") for path in template_paths]
    stats_source = STATS_JS.read_text(encoding="utf-8")

    tooltip = "Двойной щелчок откроет карточку организации"
    assert all(tooltip not in source for source in template_sources)
    assert tooltip not in stats_source


def test_document_rows_show_contract_type_and_only_labeled_populated_metadata():
    source = DETAIL_TEMPLATE.read_text(encoding="utf-8")

    assert source.count("{{ actual_document.datatype_label or group.datatype_label }}") >= 2
    assert source.count("{{ document.datatype_label or group.datatype_label }}") >= 2
    assert source.count("Внутренний номер:") == 2
    assert source.count("Внешний номер:") == 2
    assert source.count("Дата подписания:") == 2

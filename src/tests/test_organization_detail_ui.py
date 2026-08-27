from pathlib import Path

DETAIL_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "organization_detail.js"
ACTIVE_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "active_organizations.js"
TABLE_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "active_organizations_table.js"
STATS_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "distribution_stats.js"
STICKY_HEADERS_JS = (
    Path(__file__).resolve().parents[1] / "app" / "static" / "sticky_table_headers.js"
)
BASE_TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "templates" / "base.html"
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


def test_table_refresh_preserves_horizontal_scroll_position():
    table_source = TABLE_JS.read_text(encoding="utf-8")

    assert (
        "const previousHorizontalScrollLeft = currentTableScroll?.scrollLeft ?? null;"
        in table_source
    )
    assert "nextTableScroll.scrollLeft = previousHorizontalScrollLeft;" in table_source
    assert 'nextTableScroll.dispatchEvent(new Event("scroll"));' in table_source


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


def test_sorted_tables_keep_a_shared_fixed_column_model_with_sticky_headers():
    base_source = BASE_TEMPLATE.read_text(encoding="utf-8")
    sticky_source = STICKY_HEADERS_JS.read_text(encoding="utf-8")
    stats_source = STATS_JS.read_text(encoding="utf-8")

    assert "table-layout: fixed" in base_source
    assert 'querySelector(":scope > colgroup")?.cloneNode(true)' in sticky_source
    assert 'querySelectorAll(":scope > colgroup > col")' in sticky_source
    assert "window.requestAnimationFrame(() => this.tick())" in sticky_source
    assert "const columnsHtml" in stats_source
    assert "<colgroup>" in stats_source
    assert 'style="min-width: ${tableMinWidth}px"' in stats_source


def test_table_headers_stay_on_one_line_inside_their_wider_columns():
    base_source = BASE_TEMPLATE.read_text(encoding="utf-8")
    groups_template = (
        Path(__file__).resolve().parents[1] / "app" / "templates" / "organizations" / "groups.html"
    ).read_text(encoding="utf-8")
    stats_css = (
        Path(__file__).resolve().parents[1] / "app" / "static" / "distribution_stats.css"
    ).read_text(encoding="utf-8")
    stats_source = STATS_JS.read_text(encoding="utf-8")

    assert ".data-table th {" in base_source
    assert "white-space: nowrap;" in base_source
    assert "overflow-wrap: normal;" in base_source
    assert ".groups-page .study-direction-name-col { width: 290px; }" in groups_template
    assert "width: 380px;" in stats_css
    assert "210 + 180 + 88 + 380" in stats_source


def test_distribution_contract_headers_stay_on_one_line_and_names_match_regular_cells():
    stats_css = (
        Path(__file__).resolve().parents[1] / "app" / "static" / "distribution_stats.css"
    ).read_text(encoding="utf-8")

    assert ".distribution-data-table th.contract-number-col .sort-link" in stats_css
    assert ".distribution-data-table th.signing-date-col .sort-link" in stats_css
    assert "white-space: nowrap;" in stats_css
    assert ".distribution-data-table .organization-name" in stats_css
    assert "font-weight: 400;" in stats_css


def test_active_table_gives_space_from_study_fields_to_contacts():
    active_template = (
        Path(__file__).resolve().parents[1] / "app" / "templates" / "organizations" / "active.html"
    ).read_text(encoding="utf-8")

    assert "col:nth-child(5)" in active_template
    assert "width: 180px;" in active_template
    assert "col:nth-child(6)" in active_template
    assert "width: 280px;" in active_template


def test_study_directions_has_a_floating_horizontal_scrollbar():
    study_template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "organizations"
        / "study_directions.html"
    ).read_text(encoding="utf-8")
    study_source = (
        Path(__file__).resolve().parents[1] / "app" / "static" / "study_directions.js"
    ).read_text(encoding="utf-8")

    assert "data-floating-x-scroll" in study_template
    assert "data-floating-x-scroll-inner" in study_template
    assert "syncFloatingScrollbarVisibility" in study_source
    assert "handleFloatingHorizontalScroll" in study_source
    assert "bindHorizontalScrollbar" in study_source


def test_study_directions_organization_names_match_direction_cell_text_style():
    study_template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "organizations"
        / "study_directions.html"
    ).read_text(encoding="utf-8")

    assert ".study-directions-page .data-table td.organization-col {" in study_template
    assert "font-size: inherit;" in study_template
    assert "color: var(--text-main);" in study_template
    assert (
        ".study-directions-page .data-table td.organization-col .organization-name {"
        in study_template
    )
    assert "font-weight: 400;" in study_template


def test_active_sort_header_remains_contrasted_against_the_table_header():
    base_source = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert ".data-table th .sort-link.active {" in base_source
    assert ".data-table th .sort-link.active.direction-asc::after" in base_source
    assert ".data-table th .sort-link.active.direction-desc::after" in base_source
    assert base_source.count("color: #fff;") >= 3


def test_document_rows_show_contract_type_and_only_labeled_populated_metadata():
    source = DETAIL_TEMPLATE.read_text(encoding="utf-8")

    assert source.count("{{ actual_document.datatype_label or group.datatype_label }}") >= 2
    assert source.count("{{ document.datatype_label or group.datatype_label }}") >= 2
    assert source.count("Внутренний номер:") == 2
    assert source.count("Внешний номер:") == 2
    assert source.count("Дата подписания:") == 2

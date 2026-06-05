(() => {
    const pageRoot = document.querySelector("[data-page-root]");
    if (!pageRoot || pageRoot.dataset.pageUrl !== "/organizations/distribution-stats") {
        return;
    }

    const bootstrapYearsNode = document.getElementById("distribution-stats-years-bootstrap");
    const bootstrapTableNode = document.getElementById("distribution-stats-table-bootstrap");
    const namespace = window.DistributionStatsPage || {};
    const logosNamespace = window.ActiveOrganizationsPage || {};
    if (
        !bootstrapYearsNode
        || !bootstrapTableNode
        || typeof namespace.normalizeYearsPayload !== "function"
        || typeof namespace.resolveRange !== "function"
        || typeof namespace.renderYearOptions !== "function"
        || typeof namespace.fetchJson !== "function"
        || typeof namespace.escapeHtml !== "function"
        || typeof namespace.writeStoredRange !== "function"
        || typeof namespace.readStoredRange !== "function"
        || typeof namespace.buildPeriodLabel !== "function"
        || typeof logosNamespace.createLogosController !== "function"
    ) {
        return;
    }

    const yearsUrl = pageRoot.dataset.yearsUrl;
    const tableUrl = pageRoot.dataset.tableUrl;
    const logotypesUrl = pageRoot.dataset.logotypesUrl;
    const yearFromSelect = pageRoot.querySelector("[data-year-from-select]");
    const yearToSelect = pageRoot.querySelector("[data-year-to-select]");
    const organizationStatusSelect = pageRoot.querySelector("[data-organization-status-select]");
    const actualContractStatusSelect = pageRoot.querySelector("[data-actual-contract-status-select]");
    const applyButton = pageRoot.querySelector("[data-apply-range]");
    const resetButton = pageRoot.querySelector("[data-reset-range]");
    const tableSection = pageRoot.querySelector("[data-table-section]");
    const tableContent = pageRoot.querySelector("[data-table-content]");
    const summaryTitle = pageRoot.querySelector("[data-range-summary-title]");
    const summaryText = pageRoot.querySelector("[data-range-summary-text]");
    const scrollTopButton = document.querySelector("[data-scroll-top]");

    const normalizeYearsPayload = namespace.normalizeYearsPayload;
    const resolveRange = namespace.resolveRange;
    const renderYearOptions = namespace.renderYearOptions;
    const fetchJson = namespace.fetchJson;
    const escapeHtml = namespace.escapeHtml;
    const writeStoredRange = namespace.writeStoredRange;
    const readStoredRange = namespace.readStoredRange;
    const buildPeriodLabel = namespace.buildPeriodLabel;

    const organizationStatusLabels = {
        all: "все организации",
        active: "только действующие",
        inactive: "только недействующие",
    };
    const actualContractStatusLabels = {
        all: "все",
        with_actual_contract: "с актуальным договором",
        without_actual_contract: "без актуального договора",
    };

    const normalizeOrganizationStatus = (value) => (
        value === "active" || value === "inactive" ? value : "all"
    );

    const normalizeActualContractStatus = (value) => (
        value === "with_actual_contract" || value === "without_actual_contract"
            ? value
            : "all"
    );

    const normalizeTablePayload = (payload) => ({
        available_years: Array.isArray(payload?.available_years) ? payload.available_years : [],
        selected_year_from: namespace.normalizeYear(payload?.selected_year_from),
        selected_year_to: namespace.normalizeYear(payload?.selected_year_to),
        organization_status: normalizeOrganizationStatus(payload?.organization_status),
        actual_contract_status: normalizeActualContractStatus(payload?.actual_contract_status),
        sort_by: typeof payload?.sort_by === "string" && payload.sort_by ? payload.sort_by : null,
        sort_dir: payload?.sort_dir === "desc" ? "desc" : "asc",
        years: Array.isArray(payload?.years) ? payload.years : [],
        columns: Array.isArray(payload?.columns) ? payload.columns : [],
        rows: Array.isArray(payload?.rows) ? payload.rows : [],
        total_rows: Number.isInteger(payload?.total_rows) ? payload.total_rows : 0,
    });

    let yearsPayload = normalizeYearsPayload(JSON.parse(bootstrapYearsNode.textContent));
    let currentPayload = normalizeTablePayload(JSON.parse(bootstrapTableNode.textContent));
    let currentRange = resolveRange(
        {
            year_from: currentPayload.selected_year_from,
            year_to: currentPayload.selected_year_to,
        },
        yearsPayload,
    );
    const storedRange = readStoredRange();
    if (storedRange) {
        currentRange = resolveRange(storedRange, yearsPayload);
    }
    let currentFilters = {
        organization_status: currentPayload.organization_status,
        actual_contract_status: currentPayload.actual_contract_status,
    };
    let currentSort = {
        sort_by: currentPayload.sort_by,
        sort_dir: currentPayload.sort_dir,
    };

    const sortableColumns = new Set(["signing_date", "organization_name", "total_for_period"]);

    const logosController = logosNamespace.createLogosController({
        getTableSection: () => tableSection,
        logoApiUrl: logotypesUrl,
    });

    const handleScrollButton = () => {
        if (!scrollTopButton) {
            return;
        }
        if (window.scrollY > 400) {
            scrollTopButton.classList.add("visible");
        } else {
            scrollTopButton.classList.remove("visible");
        }
    };

    const setBusy = (busy) => {
        tableSection?.classList.toggle("table-section-loading", busy);
        applyButton?.toggleAttribute("disabled", busy);
        resetButton?.toggleAttribute("disabled", busy);
        organizationStatusSelect?.toggleAttribute("disabled", busy);
        actualContractStatusSelect?.toggleAttribute("disabled", busy);
    };

    const syncRangeControls = () => {
        renderYearOptions(yearFromSelect, yearsPayload.available_years, currentRange.year_from);
        renderYearOptions(yearToSelect, yearsPayload.available_years, currentRange.year_to);
        if (organizationStatusSelect instanceof HTMLSelectElement) {
            organizationStatusSelect.value = currentFilters.organization_status;
        }
        if (actualContractStatusSelect instanceof HTMLSelectElement) {
            actualContractStatusSelect.value = currentFilters.actual_contract_status;
        }
        if (summaryTitle) {
            summaryTitle.textContent = "";
        }
        if (summaryText) {
            summaryText.textContent = "";
        }
    };

    const isColumnSortable = (column) => (
        Boolean(column)
        && (sortableColumns.has(column.key) || column.kind === "year")
    );

    const buildSortControl = (column) => {
        const isActive = currentSort.sort_by === column.key;
        const nextSortDir = !isActive ? "asc" : currentSort.sort_dir === "asc" ? "desc" : "";
        const directionClass = isActive ? ` direction-${currentSort.sort_dir}` : "";
        return `
            <button
                type="button"
                class="sort-link${isActive ? ` active${directionClass}` : ""}"
                data-sort-button
                data-sort-by="${escapeHtml(column.key)}"
                data-next-sort-dir="${escapeHtml(nextSortDir)}"
            >
                ${escapeHtml(column.label)}
            </button>
        `;
    };

    const buildLogoCell = (row) => `
        <div class="avatar">
            <img
                src="/static/logo_placeholder.png"
                alt="Логотип организации"
                class="logo-placeholder"
                data-logo-img="true"
                ${row.logotype_id ? `data-logo-id="${escapeHtml(row.logotype_id)}"` : ""}
                loading="lazy"
            >
        </div>
    `;

    const bindTableInteractions = () => {
        tableContent?.querySelectorAll("[data-organization-row]").forEach((row) => {
            row.addEventListener("dblclick", (event) => {
                const interactiveTarget = event.target instanceof Element
                    ? event.target.closest("button, a, input, textarea, select, label")
                    : null;
                if (interactiveTarget) {
                    return;
                }
                const organizationUrl = row.dataset.organizationUrl;
                if (organizationUrl) {
                    window.open(organizationUrl, "_blank", "noopener");
                }
            });
        });

        tableContent?.querySelectorAll("[data-sort-button]").forEach((button) => {
            button.addEventListener("click", () => {
                const sortBy = button.dataset.sortBy || null;
                const nextSortDir = button.dataset.nextSortDir || "";
                if (!sortBy) {
                    return;
                }
                if (!nextSortDir) {
                    currentSort = {sort_by: null, sort_dir: "asc"};
                } else {
                    currentSort = {
                        sort_by: sortBy,
                        sort_dir: nextSortDir === "desc" ? "desc" : "asc",
                    };
                }
                loadTable();
            });
        });

        logosController.setup();
    };

    const renderTable = (payload) => {
        if (!tableContent) {
            return;
        }

        if (!payload.years.length) {
            tableContent.innerHTML = `
                <div class="empty-state">
                    <h3 class="empty-state-title">Данные по годам не найдены</h3>
                    <p>Когда появятся записи распределения, диапазон лет подхватится автоматически.</p>
                </div>
            `;
            return;
        }

        if (!payload.rows.length) {
            tableContent.innerHTML = `
                <div class="empty-state">
                    <h3 class="empty-state-title">Нет данных за выбранный период</h3>
                    <p>Измените диапазон лет или фильтры и повторите запрос.</p>
                </div>
            `;
            return;
        }

        const headersHtml = payload.columns.map((column) => {
            const classes = [
                `${column.key}-col`,
                column.kind === "year" ? "year-col" : "",
                column.kind === "total" ? "total-col" : "",
                column.kind === "logo" ? "logo-col" : "",
                column.key === "organization_name" ? "organization-col" : "",
                column.key === "signing_date" ? "signing-date-col" : "",
                column.key === "contract_number" ? "contract-number-col" : "",
            ].filter(Boolean).join(" ");
            return `
                <th class="${classes}">
                    ${isColumnSortable(column) ? buildSortControl(column) : escapeHtml(column.label)}
                </th>
            `;
        }).join("");

        const rowsHtml = payload.rows.map((row) => {
            const yearValues = Object.fromEntries(
                (Array.isArray(row.year_values) ? row.year_values : [])
                    .map((item) => [item.year, item.value]),
            );
            return `
                <tr ${row.organization_id ? `data-organization-row data-organization-url="/organizations/${escapeHtml(row.organization_id)}" title="Двойной щелчок откроет карточку организации в новой вкладке"` : ""}>
                    <td class="contract-number-col">${escapeHtml(row.contract_number || "—")}</td>
                    <td class="signing-date-col">${escapeHtml(row.signing_date || "—")}</td>
                    <td class="logo-cell logo-col">${buildLogoCell(row)}</td>
                    <td class="organization-col"><div class="organization-name">${escapeHtml(row.organization_name || "—")}</div></td>
                    ${payload.years.map((year) => `
                        <td class="year-cell year-col">
                            <span class="distribution-year-pill">${escapeHtml(yearValues[year] ?? 0)}</span>
                        </td>
                    `).join("")}
                    <td class="total-cell total-col">
                        <span class="distribution-year-pill distribution-total-pill">${escapeHtml(row.total_for_period ?? 0)}</span>
                    </td>
                </tr>
            `;
        }).join("");

        tableContent.innerHTML = `
            <div class="distribution-meta">
                <span class="distribution-meta-badge">Период: ${escapeHtml(buildPeriodLabel(currentRange))}</span>
                <span class="distribution-meta-badge">Записей: ${escapeHtml(payload.total_rows)}</span>
                <span class="distribution-meta-badge">Организации: ${escapeHtml(organizationStatusLabels[currentFilters.organization_status])}</span>
                <span class="distribution-meta-badge">Договор: ${escapeHtml(actualContractStatusLabels[currentFilters.actual_contract_status])}</span>
            </div>
            <div class="distribution-table-scroll">
                <table class="data-table distribution-data-table">
                    <thead>
                        <tr>${headersHtml}</tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>
        `;

        bindTableInteractions();
        window.StickyTableHeaders?.rescan?.(tableSection);
    };

    const renderError = () => {
        if (!tableContent) {
            return;
        }
        tableContent.innerHTML = `
            <div class="distribution-error">
                <strong>Не удалось загрузить статистику распределения.</strong>
                <span>Проверьте диапазон лет и фильтры, затем повторите попытку.</span>
            </div>
        `;
    };

    const loadTable = async ({refreshYears = false} = {}) => {
        setBusy(true);
        try {
            if (refreshYears && yearsUrl) {
                yearsPayload = normalizeYearsPayload(await fetchJson(yearsUrl));
                currentRange = resolveRange(currentRange, yearsPayload);
            }
            const payload = await fetchJson(tableUrl, {
                method: "POST",
                body: {
                    year_from: currentRange.year_from,
                    year_to: currentRange.year_to,
                    organization_status: currentFilters.organization_status,
                    actual_contract_status: currentFilters.actual_contract_status,
                    sort_by: currentSort.sort_by,
                    sort_dir: currentSort.sort_dir,
                },
            });
            currentPayload = normalizeTablePayload(payload);
            currentFilters = {
                organization_status: currentPayload.organization_status,
                actual_contract_status: currentPayload.actual_contract_status,
            };
            currentSort = {
                sort_by: currentPayload.sort_by,
                sort_dir: currentPayload.sort_dir,
            };
            currentRange = resolveRange(
                {
                    year_from: currentPayload.selected_year_from,
                    year_to: currentPayload.selected_year_to,
                },
                yearsPayload,
            );
            writeStoredRange({
                year_from: currentRange.year_from,
                year_to: currentRange.year_to,
            });
            syncRangeControls();
            renderTable(currentPayload);
            handleScrollButton();
        } catch (error) {
            console.error(error);
            renderError();
        } finally {
            setBusy(false);
        }
    };

    applyButton?.addEventListener("click", () => {
        currentRange = resolveRange({
            year_from: yearFromSelect?.value,
            year_to: yearToSelect?.value,
        }, yearsPayload);
        currentFilters = {
            organization_status: normalizeOrganizationStatus(organizationStatusSelect?.value),
            actual_contract_status: normalizeActualContractStatus(actualContractStatusSelect?.value),
        };
        loadTable();
    });

    resetButton?.addEventListener("click", () => {
        currentRange = resolveRange({
            year_from: yearsPayload.default_year_from,
            year_to: yearsPayload.default_year_to,
        }, yearsPayload);
        currentFilters = {
            organization_status: "all",
            actual_contract_status: "all",
        };
        currentSort = {sort_by: null, sort_dir: "asc"};
        loadTable();
    });

    scrollTopButton?.addEventListener("click", () => {
        window.scrollTo({top: 0, behavior: "smooth"});
    });

    syncRangeControls();
    renderTable(currentPayload);
    handleScrollButton();
    window.addEventListener("scroll", handleScrollButton);

    const bootstrapRange = resolveRange(
        {
            year_from: currentPayload.selected_year_from,
            year_to: currentPayload.selected_year_to,
        },
        yearsPayload,
    );
    if (
        bootstrapRange.year_from !== currentRange.year_from
        || bootstrapRange.year_to !== currentRange.year_to
    ) {
        loadTable();
    } else {
        writeStoredRange({
            year_from: currentRange.year_from,
            year_to: currentRange.year_to,
        });
    }
})();

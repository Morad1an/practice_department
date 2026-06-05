(() => {
    const pageRoot = document.querySelector("[data-page-root]");
    if (!pageRoot || pageRoot.dataset.pageUrl !== "/organizations/timeline-stats") {
        return;
    }

    const bootstrapYearsNode = document.getElementById("timeline-stats-years-bootstrap");
    const bootstrapChartNode = document.getElementById("timeline-stats-chart-bootstrap");
    const namespace = window.DistributionStatsPage || {};
    if (
        !bootstrapYearsNode
        || !bootstrapChartNode
        || typeof namespace.normalizeYearsPayload !== "function"
        || typeof namespace.resolveRange !== "function"
        || typeof namespace.renderYearOptions !== "function"
        || typeof namespace.fetchJson !== "function"
        || typeof namespace.escapeHtml !== "function"
        || typeof namespace.writeStoredRange !== "function"
        || typeof namespace.readStoredRange !== "function"
        || typeof namespace.buildPeriodLabel !== "function"
        || typeof namespace.buildYearPalette !== "function"
    ) {
        return;
    }

    const chartUrl = pageRoot.dataset.chartUrl;
    const yearsUrl = pageRoot.dataset.yearsUrl;
    const yearFromSelect = pageRoot.querySelector("[data-year-from-select]");
    const yearToSelect = pageRoot.querySelector("[data-year-to-select]");
    const organizationStatusSelect = pageRoot.querySelector("[data-organization-status-select]");
    const actualContractStatusSelect = pageRoot.querySelector("[data-actual-contract-status-select]");
    const pageSizeSelect = pageRoot.querySelector("[data-page-size-select]");
    const applyButton = pageRoot.querySelector("[data-apply-range]");
    const resetButton = pageRoot.querySelector("[data-reset-range]");
    const prevButton = pageRoot.querySelector("[data-chart-prev]");
    const nextButton = pageRoot.querySelector("[data-chart-next]");
    const chartSection = pageRoot.querySelector("[data-chart-section]");
    const chartContent = pageRoot.querySelector("[data-chart-content]");
    const summaryTitle = pageRoot.querySelector("[data-range-summary-title]");
    const summaryText = pageRoot.querySelector("[data-range-summary-text]");
    const windowMeta = pageRoot.querySelector("[data-chart-window-meta]");
    const scrollTopButton = document.querySelector("[data-scroll-top]");

    const normalizeYearsPayload = namespace.normalizeYearsPayload;
    const resolveRange = namespace.resolveRange;
    const renderYearOptions = namespace.renderYearOptions;
    const fetchJson = namespace.fetchJson;
    const escapeHtml = namespace.escapeHtml;
    const writeStoredRange = namespace.writeStoredRange;
    const readStoredRange = namespace.readStoredRange;
    const buildPeriodLabel = namespace.buildPeriodLabel;
    const buildYearPalette = namespace.buildYearPalette;

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

    const normalizeChartPayload = (payload) => ({
        available_years: Array.isArray(payload?.available_years) ? payload.available_years : [],
        selected_year_from: namespace.normalizeYear(payload?.selected_year_from),
        selected_year_to: namespace.normalizeYear(payload?.selected_year_to),
        organization_status: normalizeOrganizationStatus(payload?.organization_status),
        actual_contract_status: normalizeActualContractStatus(payload?.actual_contract_status),
        years: Array.isArray(payload?.years) ? payload.years : [],
        items: Array.isArray(payload?.items) ? payload.items : [],
        total_items: Number.isInteger(payload?.total_items) ? payload.total_items : 0,
    });

    const pageSizeStorageKey = "timeline-stats:page-size:v2";
    const readPageSize = () => {
        try {
            const stored = Number(window.sessionStorage.getItem(pageSizeStorageKey));
            return Number.isInteger(stored) && stored > 0 ? stored : 10;
        } catch {
            return 10;
        }
    };
    const writePageSize = (value) => {
        try {
            window.sessionStorage.setItem(pageSizeStorageKey, String(value));
        } catch {
            // ignore disabled session storage
        }
    };

    let yearsPayload = normalizeYearsPayload(JSON.parse(bootstrapYearsNode.textContent));
    let currentPayload = normalizeChartPayload(JSON.parse(bootstrapChartNode.textContent));
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
    let pageSize = readPageSize();
    let pageOffset = 0;
    let isBusy = false;

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

    const syncWindowControls = () => {
        if (prevButton) {
            prevButton.disabled = (
                isBusy
                || currentPayload.total_items <= 0
                || pageOffset <= 0
            );
        }
        if (nextButton) {
            nextButton.disabled = (
                isBusy
                || currentPayload.total_items <= 0
                || pageOffset + pageSize >= currentPayload.total_items
            );
        }
    };

    const setBusy = (busy) => {
        isBusy = busy;
        chartSection?.classList.toggle("table-section-loading", busy);
        applyButton?.toggleAttribute("disabled", busy);
        resetButton?.toggleAttribute("disabled", busy);
        pageSizeSelect?.toggleAttribute("disabled", busy);
        organizationStatusSelect?.toggleAttribute("disabled", busy);
        actualContractStatusSelect?.toggleAttribute("disabled", busy);
        syncWindowControls();
    };

    const syncControls = () => {
        renderYearOptions(yearFromSelect, yearsPayload.available_years, currentRange.year_from);
        renderYearOptions(yearToSelect, yearsPayload.available_years, currentRange.year_to);
        if (organizationStatusSelect instanceof HTMLSelectElement) {
            organizationStatusSelect.value = currentFilters.organization_status;
        }
        if (actualContractStatusSelect instanceof HTMLSelectElement) {
            actualContractStatusSelect.value = currentFilters.actual_contract_status;
        }
        if (pageSizeSelect) {
            pageSizeSelect.value = String(pageSize);
        }
        if (summaryTitle) {
            summaryTitle.textContent = "";
        }
        if (summaryText) {
            summaryText.textContent = "";
        }
    };

    const renderError = () => {
        if (!chartContent) {
            return;
        }
        chartContent.innerHTML = `
            <div class="distribution-error">
                <strong>Не удалось загрузить график-статистику.</strong>
                <span>Повторите запрос или смените диапазон лет и фильтры.</span>
            </div>
        `;
    };

    const renderChart = (payload) => {
        if (!chartContent) {
            return;
        }

        if (!payload.years.length) {
            chartContent.innerHTML = `
                <div class="empty-state">
                    <h3 class="empty-state-title">Нет доступных лет</h3>
                    <p>Когда появится статистика распределения, диаграмма построится автоматически.</p>
                </div>
            `;
            if (windowMeta) {
                windowMeta.textContent = "";
            }
            syncWindowControls();
            return;
        }

        if (!payload.items.length) {
            chartContent.innerHTML = `
                <div class="empty-state">
                    <h3 class="empty-state-title">Нет данных за выбранный период</h3>
                    <p>Измените диапазон лет или фильтры и попробуйте снова.</p>
                </div>
            `;
            if (windowMeta) {
                windowMeta.textContent = "";
            }
            syncWindowControls();
            return;
        }

        const visibleItems = payload.items.slice(pageOffset, pageOffset + pageSize);
        const maxTotal = Math.max(...visibleItems.map((item) => item.total_for_period || 0), 1);
        const palette = buildYearPalette(payload.years);
        const legendHtml = payload.years.map((year) => `
            <span class="chart-legend-item">
                <span class="chart-legend-swatch" style="background:${escapeHtml(palette[year])};"></span>
                ${escapeHtml(year)}
            </span>
        `).join("");

        const ticks = [0, Math.round(maxTotal / 2), maxTotal];
        const scaleHtml = ticks.map((value, index) => `
            <span class="chart-scale-tick" style="left:${index === 0 ? 0 : index === 1 ? 50 : 100}%;">${escapeHtml(value)}</span>
        `).join("");

        const itemsHtml = visibleItems.map((item) => {
            const segments = (Array.isArray(item.year_values) ? item.year_values : [])
                .filter((segment) => Number(segment?.value) > 0)
                .map((segment) => {
                    const width = (Number(segment.value) / maxTotal) * 100;
                    const tightClass = width < 10 ? " is-tight" : "";
                    return `
                        <div class="chart-segment${tightClass}" style="width:${width.toFixed(4)}%;background:${escapeHtml(palette[segment.year])};">
                            <span class="chart-segment-label">${escapeHtml(segment.value)}</span>
                        </div>
                    `;
                }).join("");

            return `
                <div class="chart-row">
                    <div class="chart-row-label">
                        <div class="chart-row-title">${escapeHtml(item.organization_name || "—")}</div>
                        <div class="chart-row-meta">
                            Договор: ${escapeHtml(item.contract_number || "—")} · Всего: ${escapeHtml(item.total_for_period || 0)}
                        </div>
                    </div>
                    <div class="chart-track">
                        <div class="chart-track-inner">${segments}</div>
                        <span class="chart-total-badge">${escapeHtml(item.total_for_period || 0)}</span>
                    </div>
                </div>
            `;
        }).join("");

        chartContent.innerHTML = `
            <div class="chart-shell">
                <div class="distribution-meta">
                    <span class="distribution-meta-badge">Период: ${escapeHtml(buildPeriodLabel(currentRange))}</span>
                    <span class="distribution-meta-badge">Организаций: ${escapeHtml(payload.total_items)}</span>
                    <span class="distribution-meta-badge">Организации: ${escapeHtml(organizationStatusLabels[currentFilters.organization_status])}</span>
                    <span class="distribution-meta-badge">Договор: ${escapeHtml(actualContractStatusLabels[currentFilters.actual_contract_status])}</span>
                </div>
                <div class="chart-legend">${legendHtml}</div>
                <div class="chart-scale">
                    <div class="muted">Шкала по текущему окну</div>
                    <div class="chart-scale-ruler">${scaleHtml}</div>
                </div>
                <div class="chart-items">${itemsHtml}</div>
            </div>
        `;

        const from = payload.total_items ? pageOffset + 1 : 0;
        const to = Math.min(pageOffset + pageSize, payload.total_items);
        if (windowMeta) {
            windowMeta.textContent = payload.total_items
                ? `${from}–${to} из ${payload.total_items}`
                : "";
        }
        syncWindowControls();
    };

    const loadChart = async ({refreshYears = false} = {}) => {
        setBusy(true);
        try {
            if (refreshYears && yearsUrl) {
                yearsPayload = normalizeYearsPayload(await fetchJson(yearsUrl));
                currentRange = resolveRange(currentRange, yearsPayload);
            }
            const payload = await fetchJson(chartUrl, {
                method: "POST",
                body: {
                    year_from: currentRange.year_from,
                    year_to: currentRange.year_to,
                    organization_status: currentFilters.organization_status,
                    actual_contract_status: currentFilters.actual_contract_status,
                },
            });
            currentPayload = normalizeChartPayload(payload);
            currentFilters = {
                organization_status: currentPayload.organization_status,
                actual_contract_status: currentPayload.actual_contract_status,
            };
            currentRange = resolveRange(
                {
                    year_from: currentPayload.selected_year_from,
                    year_to: currentPayload.selected_year_to,
                },
                yearsPayload,
            );
            pageOffset = 0;
            writeStoredRange({
                year_from: currentRange.year_from,
                year_to: currentRange.year_to,
            });
            syncControls();
            renderChart(currentPayload);
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
        loadChart();
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
        loadChart();
    });

    prevButton?.addEventListener("click", () => {
        pageOffset = Math.max(pageOffset - pageSize, 0);
        renderChart(currentPayload);
    });

    nextButton?.addEventListener("click", () => {
        if (pageOffset + pageSize >= currentPayload.total_items) {
            return;
        }
        pageOffset += pageSize;
        renderChart(currentPayload);
    });

    pageSizeSelect?.addEventListener("change", () => {
        const nextSize = Number(pageSizeSelect.value);
        if (!Number.isInteger(nextSize) || nextSize <= 0) {
            return;
        }
        pageSize = nextSize;
        pageOffset = 0;
        writePageSize(pageSize);
        renderChart(currentPayload);
    });

    scrollTopButton?.addEventListener("click", () => {
        window.scrollTo({top: 0, behavior: "smooth"});
    });

    syncControls();
    renderChart(currentPayload);
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
        loadChart();
    } else {
        writeStoredRange({
            year_from: currentRange.year_from,
            year_to: currentRange.year_to,
        });
        writePageSize(pageSize);
    }
})();

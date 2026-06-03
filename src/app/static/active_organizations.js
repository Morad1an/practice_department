(() => {
    const pageRoot = document.querySelector("[data-page-root]");
    if (!pageRoot) {
        return;
    }

    const bootstrapNode = document.getElementById("active-organizations-bootstrap");
    if (!bootstrapNode) {
        return;
    }

    const namespace = window.ActiveOrganizationsPage || {};
    if (
        typeof namespace.createFiltersController !== "function"
        || typeof namespace.createTableController !== "function"
        || typeof namespace.createExportController !== "function"
        || typeof namespace.createLogosController !== "function"
        || typeof namespace.createStudyFieldsController !== "function"
    ) {
        console.error("active organizations modules are not loaded");
        return;
    }

    const defaultContractDatatypeNames = ["Договор о практической подготовке обучающихся"];
    const storageKey = "active-organizations:filter-state:v3";
    const dropdownFilterKeys = ["organization_names", "contract_numbers", "settlement_names"];
    const staticBooleanFilterKeys = [
        "only_active_organizations",
        "only_actual_contracts",
        "only_university_departments",
    ];
    const multiCheckboxFilterKeys = ["contract_datatype_names"];
    const selectionArrayKeys = [...dropdownFilterKeys, ...multiCheckboxFilterKeys];
    const selectAllValue = "__select_all__";
    const selectAllLabel = "Выбрать всё";
    const filterLabels = {
        organization_names: "Организации",
        contract_numbers: "Договоры",
        settlement_names: "Города",
    };
    const sortFields = new Set(["organization_name", "contract_number", "signing_date", "settlement_name"]);
    const sortDirections = new Set(["asc", "desc"]);
    const pageLimit = 200;
    const triggerTextMaxLength = 28;

    const filterOptionsUrl = pageRoot.dataset.filterOptionsUrl;
    const tableUrl = pageRoot.dataset.tableUrl;
    const exportUrl = pageRoot.dataset.exportUrl;
    const logotypesUrl = pageRoot.dataset.logotypesUrl;
    const pageUrl = pageRoot.dataset.pageUrl || window.location.pathname;
    const scrollTopButton = document.querySelector("[data-scroll-top]");
    const dropdowns = Array.from(pageRoot.querySelectorAll("[data-filter-dropdown]"));
    const summaryRoot = pageRoot.querySelector("[data-filter-summary]");
    const summaryTitle = pageRoot.querySelector("[data-filter-summary-title]");
    const summaryText = pageRoot.querySelector("[data-filter-summary-text]");
    const pendingNote = pageRoot.querySelector("[data-filter-pending-note]");
    const applyButton = pageRoot.querySelector("[data-apply-filters]");
    const exportButton = pageRoot.querySelector("[data-export-table]");
    const resetButton = pageRoot.querySelector("[data-reset-filters]");
    const staticFilterCheckboxes = Array.from(pageRoot.querySelectorAll("[data-static-filter-checkbox]"));
    const datatypeFilterCheckboxes = Array.from(pageRoot.querySelectorAll("[data-datatype-filter-checkbox]"));
    const checkboxFiltersDisclosure = pageRoot.querySelector("[data-checkbox-filters-disclosure]");
    const tableSelector = "[data-table-root]";
    let tableSection = pageRoot.querySelector(tableSelector);

    const fetchHeaders = {
        Accept: "text/html",
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
    };

    const escapeHtml = (value) => String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

    const normalizeArray = (values) => {
        if (!Array.isArray(values)) {
            return [];
        }
        const seen = new Set();
        const normalized = [];
        values.forEach((value) => {
            if (typeof value !== "string") {
                return;
            }
            const trimmed = value.trim();
            if (!trimmed || seen.has(trimmed)) {
                return;
            }
            seen.add(trimmed);
            normalized.push(trimmed);
        });
        return normalized;
    };

    const buildDefaultSelection = () => ({
        organization_names: [],
        contract_numbers: [],
        settlement_names: [],
        contract_datatype_names: [...defaultContractDatatypeNames],
        only_active_organizations: true,
        only_actual_contracts: true,
        only_university_departments: false,
    });

    const cloneSelection = (selection) => ({
        organization_names: normalizeArray(selection?.organization_names),
        contract_numbers: normalizeArray(selection?.contract_numbers),
        settlement_names: normalizeArray(selection?.settlement_names),
        contract_datatype_names: selection?.contract_datatype_names === undefined
            ? [...defaultContractDatatypeNames]
            : normalizeArray(selection?.contract_datatype_names),
        only_active_organizations: selection?.only_active_organizations !== false,
        only_actual_contracts: selection?.only_actual_contracts !== false,
        only_university_departments: Boolean(selection?.only_university_departments),
    });

    const normalizeTableState = (table) => {
        const sortBy = sortFields.has(table?.sort_by) ? table.sort_by : "organization_name";
        const sortDir = sortDirections.has(table?.sort_dir) ? table.sort_dir : "asc";
        return {
            sort_by: sortBy,
            sort_dir: sortDir,
            custom_sort_requested: Boolean(table?.custom_sort_requested),
        };
    };

    const normalizeState = (raw) => ({
        draft: cloneSelection(raw?.draft || raw?.applied || {}),
        applied: cloneSelection(raw?.applied || raw?.draft || {}),
        table: normalizeTableState(raw?.table || {}),
    });

    const bootstrapState = normalizeState(JSON.parse(bootstrapNode.textContent));

    const readStoredState = () => {
        try {
            const raw = window.sessionStorage.getItem(storageKey);
            return raw ? normalizeState(JSON.parse(raw)) : null;
        } catch {
            return null;
        }
    };

    let state = readStoredState() || bootstrapState;

    const getState = () => state;
    const setState = (nextState) => {
        state = nextState;
    };

    const persistState = () => {
        try {
            window.sessionStorage.setItem(storageKey, JSON.stringify(state));
        } catch {
            // ignore disabled session storage
        }
    };

    const selectionsEqual = (left, right) => (
        selectionArrayKeys.every((key) => {
            const leftValues = normalizeArray(left?.[key]);
            const rightValues = normalizeArray(right?.[key]);
            return leftValues.length === rightValues.length
                && leftValues.every((value, index) => value === rightValues[index]);
        })
        && staticBooleanFilterKeys.every(
            (key) => Boolean(left?.[key]) === Boolean(right?.[key]),
        )
    );

    const statesEqual = (left, right) => (
        selectionsEqual(left?.draft, right?.draft)
        && selectionsEqual(left?.applied, right?.applied)
        && left?.table?.sort_by === right?.table?.sort_by
        && left?.table?.sort_dir === right?.table?.sort_dir
        && Boolean(left?.table?.custom_sort_requested) === Boolean(right?.table?.custom_sort_requested)
    );

    const buildHistoryState = () => ({
        activeOrganizations: {
            draft: cloneSelection(state.draft),
            applied: cloneSelection(state.applied),
            table: {...state.table},
        },
    });

    const updateHistory = (mode) => {
        const nextState = buildHistoryState();
        if (mode === "push") {
            window.history.pushState(nextState, "", pageUrl);
            return;
        }
        window.history.replaceState(nextState, "", pageUrl);
    };

    const serializeFilterOptionsPayload = () => ({
        organization_names: [...state.draft.organization_names],
        contract_numbers: [...state.draft.contract_numbers],
        settlement_names: [...state.draft.settlement_names],
        contract_datatype_names: [...state.draft.contract_datatype_names],
        only_active_organizations: state.draft.only_active_organizations,
        only_actual_contracts: state.draft.only_actual_contracts,
        only_university_departments: state.draft.only_university_departments,
    });

    const serializeTablePayload = (offset = 0) => ({
        filters: {
            organization_names: [...state.applied.organization_names],
            contract_numbers: [...state.applied.contract_numbers],
            settlement_names: [...state.applied.settlement_names],
            contract_datatype_names: [...state.applied.contract_datatype_names],
            only_active_organizations: state.applied.only_active_organizations,
            only_actual_contracts: state.applied.only_actual_contracts,
            only_university_departments: state.applied.only_university_departments,
            sort_by: state.table.sort_by,
            sort_dir: state.table.sort_dir,
            limit: pageLimit,
            offset,
        },
        custom_sort_requested: state.table.custom_sort_requested,
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

    const syncStaticFilterControls = () => {
        staticFilterCheckboxes.forEach((checkbox) => {
            const key = checkbox.dataset.filterKey;
            checkbox.checked = Boolean(state.draft[key]);
        });
        const selectedDatatypes = new Set(normalizeArray(state.draft.contract_datatype_names));
        datatypeFilterCheckboxes.forEach((checkbox) => {
            checkbox.checked = selectedDatatypes.has(checkbox.value);
        });
    };

    const normalizeExclusiveStatusFilters = () => {
        if (state.draft.only_university_departments) {
            state.draft.only_active_organizations = false;
            state.draft.only_actual_contracts = false;
            state.draft.contract_datatype_names = [];
        }
    };

    const closeCheckboxFiltersDisclosure = () => {
        const disclosures = [
            checkboxFiltersDisclosure,
            ...pageRoot.querySelectorAll("[data-checkbox-filters-disclosure]"),
        ].filter(Boolean);
        disclosures.forEach((disclosure) => {
            disclosure.open = false;
            disclosure.removeAttribute("open");
        });
    };

    const studyFieldsController = namespace.createStudyFieldsController({
        getTableSection: () => tableSection,
    });

    const logosController = namespace.createLogosController({
        getTableSection: () => tableSection,
        logoApiUrl: logotypesUrl,
    });

    const tableController = namespace.createTableController({
        pageRoot,
        tableSelector,
        getTableSection: () => tableSection,
        setTableSection: (nextSection) => {
            tableSection = nextSection;
        },
        tableUrl,
        fetchHeaders,
        serializeTablePayload,
        applyButton,
        exportButton,
        resetButton,
        handleScrollButton,
        persistState,
        updateHistory,
        getState,
        sortFields,
        sortDirections,
        defaultSortBy: "organization_name",
        defaultSortDir: "asc",
        onTableChanged: () => {
            studyFieldsController.bind();
            logosController.setup();
        },
    });

    const filtersController = namespace.createFiltersController({
        pageRoot,
        dropdowns,
        summaryRoot,
        summaryTitle,
        summaryText,
        pendingNote,
        fetchHeaders,
        filterOptionsUrl,
        getState,
        normalizeArray,
        persistState,
        selectionsEqual,
        serializeFilterOptionsPayload,
        escapeHtml,
        dropdownFilterKeys,
        filterLabels,
        selectAllValue,
        selectAllLabel,
        triggerTextMaxLength,
    });

    const exportController = namespace.createExportController({
        exportUrl,
        exportButton,
        serializeTablePayload,
    });

    const applyDraftFilters = async () => {
        normalizeExclusiveStatusFilters();
        syncStaticFilterControls();
        state.applied = cloneSelection(state.draft);
        filtersController.closeAllDropdowns();
        closeCheckboxFiltersDisclosure();
        window.requestAnimationFrame(closeCheckboxFiltersDisclosure);
        await tableController.refreshTable({historyMode: "push"});
        await filtersController.refreshFilterOptions();
        closeCheckboxFiltersDisclosure();
    };

    const resetAllFilters = async () => {
        setState(normalizeState({
            draft: buildDefaultSelection(),
            applied: buildDefaultSelection(),
            table: {
                sort_by: "organization_name",
                sort_dir: "asc",
                custom_sort_requested: false,
            },
        }));
        syncStaticFilterControls();
        filtersController.syncTriggerStates();
        filtersController.syncSummary();
        filtersController.closeAllDropdowns();
        closeCheckboxFiltersDisclosure();
        await tableController.refreshTable({historyMode: "push"});
        await filtersController.refreshFilterOptions();
    };

    filtersController.bindEvents();

    staticFilterCheckboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", async () => {
            const key = checkbox.dataset.filterKey;
            state.draft[key] = checkbox.checked;
            if (key === "only_university_departments" && checkbox.checked) {
                state.draft.only_active_organizations = false;
                state.draft.only_actual_contracts = false;
                state.draft.contract_datatype_names = [];
            }
            if (
                (key === "only_active_organizations" || key === "only_actual_contracts")
                && checkbox.checked
            ) {
                state.draft.only_university_departments = false;
            }
            persistState();
            syncStaticFilterControls();
            filtersController.syncSummary();
            await filtersController.refreshFilterOptions();
        });
    });

    datatypeFilterCheckboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", async () => {
            const current = new Set(normalizeArray(state.draft.contract_datatype_names));
            if (checkbox.checked) {
                current.add(checkbox.value);
            } else {
                current.delete(checkbox.value);
            }
            state.draft.contract_datatype_names = Array.from(current);
            persistState();
            filtersController.syncSummary();
            await filtersController.refreshFilterOptions();
        });
    });

    applyButton?.addEventListener("click", () => {
        applyDraftFilters();
    });

    exportButton?.addEventListener("click", () => {
        exportController.exportTable();
    });

    resetButton?.addEventListener("click", () => {
        resetAllFilters();
    });

    window.addEventListener("popstate", (event) => {
        const nextState = event.state?.activeOrganizations;
        setState(normalizeState(nextState || bootstrapState));
        persistState();
        syncStaticFilterControls();
        filtersController.syncTriggerStates();
        filtersController.syncSummary();
        filtersController.closeAllDropdowns();
        filtersController.refreshFilterOptions();
        tableController.refreshTable({historyMode: "replace"});
    });

    scrollTopButton?.addEventListener("click", () => {
        window.scrollTo({top: 0, behavior: "smooth"});
    });

    filtersController.syncTriggerStates();
    syncStaticFilterControls();
    filtersController.syncSummary();
    tableController.rebindTableInteractions();
    persistState();
    updateHistory("replace");
    filtersController.refreshFilterOptions();

    if (!statesEqual(state, bootstrapState)) {
        tableController.refreshTable({historyMode: "replace"});
    }

    handleScrollButton();
    window.addEventListener("scroll", handleScrollButton);
})();

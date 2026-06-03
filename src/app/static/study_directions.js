(() => {
    const pageRoot = document.querySelector("[data-page-root]");
    if (!pageRoot || pageRoot.dataset.pageUrl !== "/organizations/study-directions") {
        return;
    }

    const bootstrapNode = document.getElementById("study-directions-bootstrap");
    if (!bootstrapNode) {
        return;
    }

    const namespace = window.ActiveOrganizationsPage || {};
    if (
        typeof namespace.createFiltersController !== "function"
        || typeof namespace.createTableController !== "function"
        || typeof namespace.createExportController !== "function"
        || typeof namespace.createLogosController !== "function"
    ) {
        console.error("study directions modules are not loaded");
        return;
    }

    const storageKey = "study-directions:filter-state:v1";
    const dropdownFilterKeys = [
        "faculty_names",
        "department_names",
        "study_direction_names",
        "study_direction_codes",
        "organization_names",
    ];
    const selectionArrayKeys = [...dropdownFilterKeys];
    const selectAllValue = "__select_all__";
    const selectAllLabel = "Выбрать всё";
    const filterLabels = {
        faculty_names: "Факультеты",
        department_names: "Кафедры",
        study_direction_names: "Направления",
        study_direction_codes: "Шифры",
        organization_names: "Организации",
    };
    const sortFields = new Set([
        "faculty_name",
        "department_name",
        "study_direction_name",
        "study_direction_code",
        "organization_name",
    ]);
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
        faculty_names: [],
        department_names: [],
        study_direction_names: [],
        study_direction_codes: [],
        organization_names: [],
    });

    const cloneSelection = (selection) => ({
        faculty_names: normalizeArray(selection?.faculty_names),
        department_names: normalizeArray(selection?.department_names),
        study_direction_names: normalizeArray(selection?.study_direction_names),
        study_direction_codes: normalizeArray(selection?.study_direction_codes),
        organization_names: normalizeArray(selection?.organization_names),
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
    );

    const statesEqual = (left, right) => (
        selectionsEqual(left?.draft, right?.draft)
        && selectionsEqual(left?.applied, right?.applied)
        && left?.table?.sort_by === right?.table?.sort_by
        && left?.table?.sort_dir === right?.table?.sort_dir
        && Boolean(left?.table?.custom_sort_requested) === Boolean(right?.table?.custom_sort_requested)
    );

    const buildHistoryState = () => ({
        studyDirections: {
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
        faculty_names: [...state.draft.faculty_names],
        department_names: [...state.draft.department_names],
        study_direction_names: [...state.draft.study_direction_names],
        study_direction_codes: [...state.draft.study_direction_codes],
        organization_names: [...state.draft.organization_names],
    });

    const serializeTablePayload = (offset = 0) => ({
        filters: {
            faculty_names: [...state.applied.faculty_names],
            department_names: [...state.applied.department_names],
            study_direction_names: [...state.applied.study_direction_names],
            study_direction_codes: [...state.applied.study_direction_codes],
            organization_names: [...state.applied.organization_names],
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
        state.applied = cloneSelection(state.draft);
        await tableController.refreshTable({historyMode: "push"});
        await filtersController.refreshFilterOptions();
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
        filtersController.syncTriggerStates();
        filtersController.syncSummary();
        filtersController.closeAllDropdowns();
        await tableController.refreshTable({historyMode: "push"});
        await filtersController.refreshFilterOptions();
    };

    filtersController.bindEvents();

    applyButton?.addEventListener("click", () => {
        applyDraftFilters();
    });

    resetButton?.addEventListener("click", () => {
        resetAllFilters();
    });

    exportButton?.addEventListener("click", () => {
        exportController.exportTable();
    });

    window.addEventListener("popstate", (event) => {
        const nextState = event.state?.studyDirections;
        setState(normalizeState(nextState || bootstrapState));
        persistState();
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
    filtersController.syncSummary();
    tableController.rebindTableInteractions();
    logosController.setup();
    persistState();
    updateHistory("replace");
    filtersController.refreshFilterOptions();

    if (!statesEqual(state, bootstrapState)) {
        tableController.refreshTable({historyMode: "replace"});
    }

    handleScrollButton();
    window.addEventListener("scroll", handleScrollButton);
})();

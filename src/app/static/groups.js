(() => {
    const pageRoot = document.querySelector("[data-page-root]");
    if (!pageRoot || pageRoot.dataset.pageUrl !== "/organizations/groups") {
        return;
    }

    const bootstrapNode = document.getElementById("groups-bootstrap");
    if (!bootstrapNode) {
        return;
    }

    const namespace = window.ActiveOrganizationsPage || {};
    if (
        typeof namespace.createTableController !== "function"
        || typeof namespace.createExportController !== "function"
    ) {
        console.error("groups modules are not loaded");
        return;
    }

    const bootstrapState = JSON.parse(bootstrapNode.textContent);
    const storageKey = "groups:filter-state:v1";
    const pageUrl = pageRoot.dataset.pageUrl || window.location.pathname;
    const tableUrl = pageRoot.dataset.tableUrl;
    const exportUrl = pageRoot.dataset.exportUrl;
    const pageLimit = 200;
    const sortFields = new Set([
        "department_name",
        "study_direction_code",
        "study_direction_name",
        "study_profile_name",
        "group_name",
        "course",
        "distributed_quantity",
        "organization_name",
        "order_name",
        "signing_date",
        "practice_name",
        "practice_date_begin",
        "practice_date_end",
        "practice_chief_name",
    ]);
    const sortDirections = new Set(["asc", "desc"]);

    const semesterTrigger = pageRoot.querySelector("[data-semester-trigger]");
    const semesterTriggerText = pageRoot.querySelector("[data-semester-trigger-text]");
    const semesterMenu = pageRoot.querySelector("[data-semester-menu]");
    const semesterOptionsRoot = pageRoot.querySelector("[data-semester-options]");
    const exportButton = pageRoot.querySelector("[data-export-table]");
    const scrollTopButton = document.querySelector("[data-scroll-top]");
    const floatingScrollbar = document.querySelector("[data-floating-x-scroll]");
    const floatingScrollbarInner = document.querySelector("[data-floating-x-scroll-inner]");
    const tableSelector = "[data-table-root]";
    let tableSection = pageRoot.querySelector(tableSelector);
    let tableScroll = tableSection?.querySelector(".table-scroll") || null;
    let userIsScrollingFloating = false;

    const semesterOptions = Array.isArray(bootstrapState?.semester_options)
        ? bootstrapState.semester_options
        : [];
    const defaultSemesterId = Number.isInteger(Number(bootstrapState?.default_semester_id))
        ? Number(bootstrapState.default_semester_id)
        : null;

    const fetchHeaders = {
        Accept: "text/html",
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
    };

    const normalizeSemesterId = (value) => {
        const numeric = Number(value);
        return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
    };

    const hasSemesterOption = (semesterId) => semesterOptions.some((item) => item.value === semesterId);

    const normalizeSemesterSelection = (value) => {
        const normalized = normalizeSemesterId(value);
        if (normalized && hasSemesterOption(normalized)) {
            return normalized;
        }
        if (defaultSemesterId && hasSemesterOption(defaultSemesterId)) {
            return defaultSemesterId;
        }
        return normalizeSemesterId(semesterOptions[0]?.value);
    };

    const normalizeTableState = (table) => {
        const sortBy = sortFields.has(table?.sort_by) ? table.sort_by : "department_name";
        const sortDir = sortDirections.has(table?.sort_dir) ? table.sort_dir : "asc";
        return {
            sort_by: sortBy,
            sort_dir: sortDir,
            custom_sort_requested: Boolean(table?.custom_sort_requested),
        };
    };

    const normalizeState = (raw) => ({
        draft: {
            semester_id: normalizeSemesterSelection(
                raw?.draft?.semester_id ?? raw?.applied?.semester_id,
            ),
        },
        applied: {
            semester_id: normalizeSemesterSelection(
                raw?.applied?.semester_id ?? raw?.draft?.semester_id,
            ),
        },
        table: normalizeTableState(raw?.table || {}),
    });

    const readStoredState = () => {
        try {
            const raw = window.sessionStorage.getItem(storageKey);
            return raw ? normalizeState(JSON.parse(raw)) : null;
        } catch {
            return null;
        }
    };

    let state = readStoredState() || normalizeState(bootstrapState);

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

    const resolveSemesterLabel = (semesterId) => {
        const option = semesterOptions.find((item) => item.value === semesterId);
        return option?.label || "";
    };

    const renderTriggerState = () => {
        const label = resolveSemesterLabel(state.draft.semester_id);
        if (semesterTriggerText) {
            semesterTriggerText.textContent = label ? `Семестр: ${label}` : "Выберите семестр";
        }
        semesterTrigger?.classList.toggle("has-value", Boolean(label));
    };

    const renderSemesterOptions = () => {
        if (!semesterOptionsRoot) {
            return;
        }
        const currentSemesterId = state.draft.semester_id;
        const radioButtons = semesterOptionsRoot.querySelectorAll('input[type="radio"][name="groups-semester"]');
        radioButtons.forEach((radio) => {
            radio.checked = normalizeSemesterId(radio.value) === currentSemesterId;
        });
    };

    const closeSemesterMenu = () => {
        semesterTrigger?.classList.remove("is-open");
        semesterTrigger?.setAttribute("aria-expanded", "false");
        if (semesterMenu) {
            semesterMenu.hidden = true;
        }
    };

    const openSemesterMenu = () => {
        semesterTrigger?.classList.add("is-open");
        semesterTrigger?.setAttribute("aria-expanded", "true");
        if (semesterMenu) {
            semesterMenu.hidden = false;
        }
    };

    const buildHistoryState = () => ({
        groups: {
            draft: {semester_id: state.draft.semester_id},
            applied: {semester_id: state.applied.semester_id},
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

    const serializeTablePayload = (offset = 0) => ({
        filters: {
            semester_id: state.applied.semester_id,
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

    const syncFloatingScrollFromTable = () => {
        if (!floatingScrollbar || !tableScroll) {
            return;
        }
        const tableMaxScrollLeft = Math.max(
            tableScroll.scrollWidth - tableScroll.clientWidth,
            0,
        );
        const floatingMaxScrollLeft = Math.max(
            floatingScrollbar.scrollWidth - floatingScrollbar.clientWidth,
            0,
        );
        const nextFloatingScrollLeft = tableMaxScrollLeft <= 0 || floatingMaxScrollLeft <= 0
            ? tableScroll.scrollLeft
            : (tableScroll.scrollLeft / tableMaxScrollLeft) * floatingMaxScrollLeft;
        if (Math.abs(floatingScrollbar.scrollLeft - nextFloatingScrollLeft) > 1) {
            floatingScrollbar.scrollLeft = nextFloatingScrollLeft;
        }
    };

    const syncFloatingScrollbarVisibility = () => {
        if (!floatingScrollbar || !floatingScrollbarInner) {
            return;
        }

        tableScroll = tableSection?.querySelector(".table-scroll") || null;
        if (!tableScroll) {
            floatingScrollbar.hidden = true;
            floatingScrollbar.scrollLeft = 0;
            floatingScrollbarInner.style.width = "0px";
            return;
        }

        const hasHorizontalOverflow = tableScroll.scrollWidth > tableScroll.clientWidth + 1;
        floatingScrollbar.hidden = !hasHorizontalOverflow;
        floatingScrollbarInner.style.width = `${tableScroll.scrollWidth}px`;
        if (!hasHorizontalOverflow) {
            floatingScrollbar.scrollLeft = 0;
            return;
        }
        syncFloatingScrollFromTable();
    };

    const handleTableHorizontalScroll = () => {
        if (!floatingScrollbar || !tableScroll) {
            return;
        }
        syncFloatingScrollFromTable();
    };

    const handleFloatingHorizontalScroll = () => {
        if (!floatingScrollbar || !tableScroll || !userIsScrollingFloating) {
            return;
        }
        const floatingMaxScrollLeft = Math.max(
            floatingScrollbar.scrollWidth - floatingScrollbar.clientWidth,
            0,
        );
        const tableMaxScrollLeft = Math.max(
            tableScroll.scrollWidth - tableScroll.clientWidth,
            0,
        );
        if (floatingMaxScrollLeft <= 0 || tableMaxScrollLeft <= 0) {
            tableScroll.scrollLeft = floatingScrollbar.scrollLeft;
            return;
        }
        const progress = floatingScrollbar.scrollLeft / floatingMaxScrollLeft;
        tableScroll.scrollLeft = progress * tableMaxScrollLeft;
    };

    const bindHorizontalScrollbar = () => {
        tableScroll = tableSection?.querySelector(".table-scroll") || null;
        if (tableScroll && tableScroll.dataset.horizontalScrollBound !== "1") {
            tableScroll.dataset.horizontalScrollBound = "1";
            tableScroll.addEventListener("scroll", handleTableHorizontalScroll, {passive: true});
        }
        syncFloatingScrollbarVisibility();
    };

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
        exportButton,
        handleScrollButton,
        persistState,
        updateHistory,
        getState,
        sortFields,
        sortDirections,
        defaultSortBy: "department_name",
        defaultSortDir: "asc",
        onTableChanged: () => {
            bindHorizontalScrollbar();
        },
    });

    const exportController = namespace.createExportController({
        exportUrl,
        exportButton,
        serializeTablePayload,
    });

    semesterTrigger?.addEventListener("click", () => {
        const isOpen = semesterTrigger.getAttribute("aria-expanded") === "true";
        if (isOpen) {
            closeSemesterMenu();
        } else {
            openSemesterMenu();
        }
    });

    semesterOptionsRoot?.addEventListener("change", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLInputElement) || target.type !== "radio") {
            return;
        }
        const nextSemesterId = normalizeSemesterId(target.value);
        const changed = nextSemesterId !== state.applied.semester_id;
        state.draft.semester_id = nextSemesterId;
        state.applied.semester_id = nextSemesterId;
        persistState();
        renderTriggerState();
        closeSemesterMenu();
        if (changed) {
            tableController.refreshTable({historyMode: "push"});
        }
    });

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Node)) {
            return;
        }
        if (semesterMenu?.hidden === false) {
            const filterRoot = pageRoot.querySelector("[data-semester-filter]");
            if (filterRoot && !filterRoot.contains(event.target)) {
                closeSemesterMenu();
            }
        }
    });

    exportButton?.addEventListener("click", () => {
        exportController.exportTable();
    });

    floatingScrollbar?.addEventListener("pointerdown", () => {
        userIsScrollingFloating = true;
    });
    floatingScrollbar?.addEventListener("pointerup", () => {
        userIsScrollingFloating = false;
    });
    floatingScrollbar?.addEventListener("pointercancel", () => {
        userIsScrollingFloating = false;
    });
    window.addEventListener("pointerup", () => {
        userIsScrollingFloating = false;
    });
    floatingScrollbar?.addEventListener("scroll", handleFloatingHorizontalScroll, {passive: true});

    window.addEventListener("popstate", (event) => {
        const nextState = event.state?.groups;
        setState(normalizeState(nextState || bootstrapState));
        persistState();
        renderTriggerState();
        renderSemesterOptions();
        closeSemesterMenu();
        tableController.refreshTable({historyMode: "replace"});
    });

    scrollTopButton?.addEventListener("click", () => {
        window.scrollTo({top: 0, behavior: "smooth"});
    });

    renderTriggerState();
    renderSemesterOptions();
    tableController.rebindTableInteractions();
    bindHorizontalScrollbar();
    persistState();
    updateHistory("replace");

    handleScrollButton();
    window.addEventListener("scroll", handleScrollButton);
    window.addEventListener("resize", syncFloatingScrollbarVisibility);
})();

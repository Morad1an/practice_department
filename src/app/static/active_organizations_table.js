(() => {
    const namespace = window.ActiveOrganizationsPage || (window.ActiveOrganizationsPage = {});

    namespace.createTableController = function createTableController(config) {
        const {
            pageRoot,
            tableSelector,
            getTableSection,
            setTableSection,
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
            defaultSortBy,
            defaultSortDir,
            onTableChanged,
        } = config;

        let tableRequestId = 0;

        const setTableBusy = (busy) => {
            getTableSection()?.classList.toggle("table-section-loading", busy);
            applyButton?.toggleAttribute("disabled", busy);
            exportButton?.toggleAttribute("disabled", busy);
            resetButton?.toggleAttribute("disabled", busy);
        };

        const requestTableSection = async (offset = 0) => {
            const response = await fetch(tableUrl, {
                method: "POST",
                headers: fetchHeaders,
                body: JSON.stringify(serializeTablePayload(offset)),
            });
            if (!response.ok) {
                throw new Error("table-request-failed");
            }
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, "text/html");
            const freshSection = doc.querySelector(tableSelector);
            if (!freshSection) {
                throw new Error("missing-table-root");
            }
            return freshSection;
        };

        const replaceTable = (freshSection) => {
            const currentSection = getTableSection();
            if (!currentSection) {
                pageRoot.appendChild(freshSection);
            } else {
                currentSection.replaceWith(freshSection);
            }
            setTableSection(freshSection);
            rebindTableInteractions();
        };

        const appendRows = (freshSection) => {
            const targetBody = getTableSection()?.querySelector("tbody");
            const freshBody = freshSection.querySelector("tbody");
            if (!targetBody || !freshBody) {
                return;
            }
            freshBody.querySelectorAll("tr").forEach((row) => {
                targetBody.appendChild(row);
            });
        };

        const updateLoadMoreState = (freshSection) => {
            const currentWrapper = getTableSection()?.querySelector(".load-more-wrapper");
            const incomingWrapper = freshSection.querySelector(".load-more-wrapper");

            if (!currentWrapper && incomingWrapper) {
                const tableScroll = getTableSection()?.querySelector(".table-scroll");
                if (tableScroll) {
                    tableScroll.insertAdjacentElement("afterend", incomingWrapper);
                }
                return;
            }

            if (!currentWrapper) {
                return;
            }

            if (incomingWrapper) {
                currentWrapper.replaceWith(incomingWrapper);
            } else {
                currentWrapper.remove();
            }
        };

        const handleSort = async (button) => {
            const sortBy = button.dataset.sortBy;
            if (!sortFields.has(sortBy)) {
                return;
            }

            const isActive = button.classList.contains("active");
            const isDescending = button.classList.contains("direction-desc");
            const nextSortDir = button.dataset.sortDir;
            if (!isActive && !sortDirections.has(nextSortDir)) {
                return;
            }

            const state = getState();
            if (isActive && isDescending) {
                state.table.sort_by = defaultSortBy;
                state.table.sort_dir = defaultSortDir;
                state.table.custom_sort_requested = false;
            } else {
                state.table.sort_by = sortBy;
                state.table.sort_dir = isActive ? "desc" : nextSortDir;
                state.table.custom_sort_requested = true;
            }
            await refreshTable({historyMode: "push"});
        };

        const attachSortHandlers = () => {
            const tableSection = getTableSection();
            if (!tableSection) {
                return;
            }
            tableSection.querySelectorAll("[data-sort-button]").forEach((button) => {
                if (button.dataset.bound === "1") {
                    return;
                }
                button.dataset.bound = "1";
                button.addEventListener("click", () => {
                    handleSort(button);
                });
            });
        };

        const attachLoadMoreHandler = () => {
            const tableSection = getTableSection();
            if (!tableSection) {
                return;
            }
            const button = tableSection.querySelector("[data-load-more]");
            if (!button || button.dataset.bound === "1") {
                return;
            }
            button.dataset.bound = "1";
            button.addEventListener("click", () => {
                loadMoreRows(button.dataset.nextOffset);
            });
        };

        const attachOrganizationOpenHandlers = () => {
            const tableSection = getTableSection();
            if (!tableSection) {
                return;
            }
            tableSection.querySelectorAll("[data-organization-row]").forEach((row) => {
                if (row.dataset.dblclickBound === "1") {
                    return;
                }
                row.dataset.dblclickBound = "1";
                row.addEventListener("dblclick", (event) => {
                    const selection = window.getSelection?.();
                    if (selection && String(selection).trim()) {
                        return;
                    }

                    const interactiveTarget = event.target instanceof Element
                        ? event.target.closest("button, a, input, textarea, select, label")
                        : null;
                    if (interactiveTarget) {
                        return;
                    }

                    const organizationUrl = row.dataset.organizationUrl;
                    if (!organizationUrl) {
                        return;
                    }
                    window.open(organizationUrl, "_blank", "noopener");
                });
            });
        };

        const rebindTableInteractions = () => {
            attachSortHandlers();
            attachLoadMoreHandler();
            attachOrganizationOpenHandlers();
            onTableChanged?.();
        };

        const refreshTable = async ({historyMode = "replace"} = {}) => {
            const requestId = ++tableRequestId;
            setTableBusy(true);
            try {
                const freshSection = await requestTableSection(0);
                if (requestId !== tableRequestId) {
                    return;
                }
                replaceTable(freshSection);
                persistState();
                updateHistory(historyMode);
                handleScrollButton();
            } catch (error) {
                console.error(error);
            } finally {
                if (requestId === tableRequestId) {
                    setTableBusy(false);
                }
            }
        };

        const loadMoreRows = async (offset) => {
            const numericOffset = Number(offset);
            if (!Number.isInteger(numericOffset) || numericOffset < 0) {
                return;
            }

            const button = getTableSection()?.querySelector("[data-load-more]");
            button?.toggleAttribute("disabled", true);

            try {
                const freshSection = await requestTableSection(numericOffset);
                appendRows(freshSection);
                updateLoadMoreState(freshSection);
                rebindTableInteractions();
                handleScrollButton();
            } catch (error) {
                console.error(error);
            } finally {
                button?.toggleAttribute("disabled", false);
            }
        };

        return {
            rebindTableInteractions,
            refreshTable,
        };
    };
})();

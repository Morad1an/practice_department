(() => {
    const namespace = window.ActiveOrganizationsPage || (window.ActiveOrganizationsPage = {});

    namespace.createFiltersController = function createFiltersController(config) {
        const {
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
        } = config;

        let filterOptions = {};
        let filterOptionsRequestId = 0;

        const truncateTriggerLabel = (value) => {
            const text = String(value || "").trim();
            if (text.length <= triggerTextMaxLength) {
                return text;
            }
            return `${text.slice(0, triggerTextMaxLength - 1).trimEnd()}…`;
        };

        const formatTriggerText = (dropdown) => {
            const state = getState();
            const key = dropdown.dataset.filterKey;
            const emptyText = dropdown.dataset.emptyText || "Не выбрано";
            const selected = normalizeArray(state.draft[key]);
            if (!selected.length) {
                return emptyText;
            }
            if (selected.length === 1) {
                return truncateTriggerLabel(selected[0]);
            }
            return `${truncateTriggerLabel(selected[0])} +${selected.length - 1}`;
        };

        const describeAppliedFilters = () => {
            const state = getState();
            const parts = dropdownFilterKeys
                .map((key) => {
                    const count = normalizeArray(state.applied[key]).length;
                    if (!count) {
                        return null;
                    }
                    return `${filterLabels[key]}: ${count}`;
                })
                .filter(Boolean);

            return {
                title: parts.join(" · "),
                text: "",
            };
        };

        const syncSummary = () => {
            const state = getState();
            const summary = describeAppliedFilters();
            const hasSummaryTitle = Boolean(summary.title);
            const hasPendingChanges = !selectionsEqual(state.draft, state.applied);

            if (summaryRoot) {
                summaryRoot.hidden = !hasSummaryTitle && !hasPendingChanges;
            }
            if (summaryTitle) {
                summaryTitle.textContent = summary.title;
                summaryTitle.hidden = !hasSummaryTitle;
            }
            if (summaryText) {
                summaryText.textContent = "";
                summaryText.hidden = true;
            }
            if (pendingNote) {
                pendingNote.hidden = !hasPendingChanges;
            }
        };

        const syncTriggerStates = () => {
            const state = getState();
            dropdowns.forEach((dropdown) => {
                const trigger = dropdown.querySelector("[data-filter-trigger]");
                const triggerText = dropdown.querySelector("[data-filter-trigger-text]");
                const selected = normalizeArray(state.draft[dropdown.dataset.filterKey]);
                if (triggerText) {
                    triggerText.textContent = formatTriggerText(dropdown);
                }
                trigger?.classList.toggle("has-value", selected.length > 0);
            });
        };

        const compareOptions = (left, right) => String(left.label).localeCompare(
            String(right.label),
            "ru",
            {sensitivity: "base"},
        );

        const buildSelectableOptions = (dropdown) => {
            const state = getState();
            const key = dropdown.dataset.filterKey;
            const optionsKey = dropdown.dataset.optionsKey;
            const selectedValues = normalizeArray(state.draft[key]);
            const availableOptions = Array.isArray(filterOptions[optionsKey]) ? filterOptions[optionsKey] : [];
            const optionsMap = new Map();

            availableOptions.forEach((option) => {
                if (!option || typeof option.value !== "string") {
                    return;
                }
                const value = option.value.trim();
                if (!value) {
                    return;
                }
                optionsMap.set(value, {
                    value,
                    label: typeof option.label === "string" && option.label.trim() ? option.label.trim() : value,
                });
            });

            selectedValues.forEach((value) => {
                if (!optionsMap.has(value)) {
                    optionsMap.set(value, {value, label: value});
                }
            });

            return Array.from(optionsMap.values()).sort(compareOptions);
        };

        const renderDropdownOptions = (dropdown) => {
            const state = getState();
            const key = dropdown.dataset.filterKey;
            const searchInput = dropdown.querySelector("[data-filter-search]");
            const container = dropdown.querySelector("[data-filter-options]");
            if (!container) {
                return;
            }

            const searchTerm = (searchInput?.value || "").trim().toLowerCase();
            const selectedValues = normalizeArray(state.draft[key]);
            const selectableOptions = buildSelectableOptions(dropdown);
            const allSelectableValues = selectableOptions.map((option) => option.value);
            const isSelectAllChecked = allSelectableValues.length > 0
                && allSelectableValues.every((value) => selectedValues.includes(value));
            const visibleOptions = selectableOptions.filter((option) => {
                const label = String(option?.label || "");
                return !searchTerm || label.toLowerCase().includes(searchTerm);
            });

            if (!allSelectableValues.length) {
                container.innerHTML = '<div class="filter-empty">Ничего не найдено.</div>';
                return;
            }

            const optionsHtml = [
                {
                    value: selectAllValue,
                    label: selectAllLabel,
                    checked: isSelectAllChecked,
                },
                ...visibleOptions.map((option) => ({
                    value: option.value,
                    label: option.label,
                    checked: selectedValues.includes(option.value),
                })),
            ];

            container.innerHTML = optionsHtml.map((option) => {
                const resolvedChecked = option.checked ? "checked" : "";
                return `
                    <label class="filter-option">
                        <input type="checkbox" value="${escapeHtml(option.value)}" ${resolvedChecked}>
                        <span class="filter-option-text">
                            <span class="filter-option-title">${escapeHtml(option.label)}</span>
                        </span>
                    </label>
                `;
            }).join("");
        };

        const renderAllDropdownOptions = () => {
            dropdowns.forEach((dropdown) => renderDropdownOptions(dropdown));
        };

        const closeDropdown = (dropdown) => {
            const trigger = dropdown.querySelector("[data-filter-trigger]");
            const menu = dropdown.querySelector("[data-filter-menu]");
            trigger?.classList.remove("is-open");
            trigger?.setAttribute("aria-expanded", "false");
            if (menu) {
                menu.hidden = true;
            }
        };

        const closeAllDropdowns = (except = null) => {
            dropdowns.forEach((dropdown) => {
                if (dropdown !== except) {
                    closeDropdown(dropdown);
                }
            });
        };

        const openDropdown = (dropdown) => {
            closeAllDropdowns(dropdown);
            const trigger = dropdown.querySelector("[data-filter-trigger]");
            const menu = dropdown.querySelector("[data-filter-menu]");
            trigger?.classList.add("is-open");
            trigger?.setAttribute("aria-expanded", "true");
            if (menu) {
                menu.hidden = false;
            }
        };

        const refreshFilterOptions = async () => {
            const requestId = ++filterOptionsRequestId;
            try {
                const response = await fetch(filterOptionsUrl, {
                    method: "POST",
                    headers: fetchHeaders,
                    body: JSON.stringify(serializeFilterOptionsPayload()),
                });
                if (!response.ok) {
                    throw new Error("filter-options-request-failed");
                }
                const payload = await response.json();
                if (requestId !== filterOptionsRequestId) {
                    return;
                }
                filterOptions = Object.fromEntries(
                    Object.entries(payload || {}).map(([key, value]) => [
                        key,
                        Array.isArray(value) ? value : [],
                    ]),
                );
                renderAllDropdownOptions();
                syncTriggerStates();
                syncSummary();
            } catch (error) {
                if (requestId === filterOptionsRequestId) {
                    console.error(error);
                }
            }
        };

        const bindEvents = () => {
            dropdowns.forEach((dropdown) => {
                const key = dropdown.dataset.filterKey;
                const trigger = dropdown.querySelector("[data-filter-trigger]");
                const searchInput = dropdown.querySelector("[data-filter-search]");
                const clearButton = dropdown.querySelector("[data-filter-clear]");
                const optionsContainer = dropdown.querySelector("[data-filter-options]");

                trigger?.addEventListener("click", () => {
                    const isOpen = trigger.getAttribute("aria-expanded") === "true";
                    if (isOpen) {
                        closeDropdown(dropdown);
                    } else {
                        openDropdown(dropdown);
                        searchInput?.focus();
                    }
                });

                searchInput?.addEventListener("input", () => {
                    renderDropdownOptions(dropdown);
                });

                clearButton?.addEventListener("click", async () => {
                    const state = getState();
                    state.draft[key] = [];
                    persistState();
                    syncTriggerStates();
                    syncSummary();
                    await refreshFilterOptions();
                });

                optionsContainer?.addEventListener("change", async (event) => {
                    const target = event.target;
                    if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") {
                        return;
                    }

                    const state = getState();
                    if (target.value === selectAllValue) {
                        const mergedOptions = buildSelectableOptions(dropdown);
                        state.draft[key] = target.checked
                            ? mergedOptions.map((option) => option.value)
                            : [];
                        persistState();
                        syncTriggerStates();
                        syncSummary();
                        await refreshFilterOptions();
                        return;
                    }

                    const current = new Set(normalizeArray(state.draft[key]));
                    if (target.checked) {
                        current.add(target.value);
                    } else {
                        current.delete(target.value);
                    }
                    state.draft[key] = Array.from(current);
                    persistState();
                    syncTriggerStates();
                    syncSummary();
                    await refreshFilterOptions();
                });
            });

            document.addEventListener("click", (event) => {
                const target = event.target;
                if (!(target instanceof Node)) {
                    return;
                }
                if (!pageRoot.contains(target)) {
                    closeAllDropdowns();
                    return;
                }
                const dropdown = target instanceof Element ? target.closest("[data-filter-dropdown]") : null;
                if (!dropdown) {
                    closeAllDropdowns();
                }
            });

            document.addEventListener("keydown", (event) => {
                if (event.key === "Escape") {
                    closeAllDropdowns();
                }
            });
        };

        return {
            bindEvents,
            closeAllDropdowns,
            refreshFilterOptions,
            syncSummary,
            syncTriggerStates,
        };
    };
})();

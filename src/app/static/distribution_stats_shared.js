(() => {
    const namespace = window.DistributionStatsPage || (window.DistributionStatsPage = {});
    const storageKey = "distribution-stats:year-range:v2";
    const palette = [
        "#1d4ed8",
        "#0f766e",
        "#d97706",
        "#9333ea",
        "#dc2626",
        "#0891b2",
        "#4f46e5",
        "#65a30d",
    ];

    const normalizeYear = (value) => {
        const numeric = Number(value);
        return Number.isInteger(numeric) ? numeric : null;
    };

    const uniqueSortedYears = (values) => Array.from(
        new Set((Array.isArray(values) ? values : [])
            .map((item) => normalizeYear(item))
            .filter((item) => item !== null)),
    ).sort((left, right) => left - right);

    const normalizeYearsPayload = (payload) => {
        const availableYears = uniqueSortedYears(payload?.available_years);
        if (!availableYears.length) {
            return {
                available_years: [],
                default_year_from: null,
                default_year_to: null,
            };
        }

        const defaultYearFrom = availableYears.includes(normalizeYear(payload?.default_year_from))
            ? normalizeYear(payload.default_year_from)
            : availableYears[0];
        const defaultYearTo = availableYears.includes(normalizeYear(payload?.default_year_to))
            ? normalizeYear(payload.default_year_to)
            : availableYears[availableYears.length - 1];

        return {
            available_years: availableYears,
            default_year_from: defaultYearFrom,
            default_year_to: defaultYearTo,
        };
    };

    const resolveRange = (rawRange, payload) => {
        const yearsPayload = normalizeYearsPayload(payload);
        const availableYears = yearsPayload.available_years;
        if (!availableYears.length) {
            return {year_from: null, year_to: null, years: []};
        }

        let yearFrom = normalizeYear(rawRange?.year_from);
        let yearTo = normalizeYear(rawRange?.year_to);
        if (!availableYears.includes(yearFrom)) {
            yearFrom = yearsPayload.default_year_from;
        }
        if (!availableYears.includes(yearTo)) {
            yearTo = yearsPayload.default_year_to;
        }
        if (yearFrom > yearTo) {
            const tmp = yearFrom;
            yearFrom = yearTo;
            yearTo = tmp;
        }

        const years = availableYears.filter((year) => year >= yearFrom && year <= yearTo);
        return {
            year_from: yearFrom,
            year_to: yearTo,
            years,
        };
    };

    const readStoredRange = () => {
        try {
            const raw = window.sessionStorage.getItem(storageKey);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    };

    const writeStoredRange = (range) => {
        try {
            window.sessionStorage.setItem(storageKey, JSON.stringify(range));
        } catch {
            // ignore disabled session storage
        }
    };

    const renderYearOptions = (select, availableYears, selectedYear) => {
        if (!(select instanceof HTMLSelectElement)) {
            return;
        }
        select.innerHTML = "";
        availableYears.forEach((year) => {
            const option = document.createElement("option");
            option.value = String(year);
            option.textContent = String(year);
            option.selected = year === selectedYear;
            select.appendChild(option);
        });
        select.disabled = !availableYears.length;
    };

    const buildPeriodLabel = (range) => {
        if (!range?.years?.length) {
            return "Нет доступных лет";
        }
        return `${range.year_from}–${range.year_to}`;
    };

    const fetchJson = async (url, {method = "GET", body} = {}) => {
        const response = await fetch(url, {
            method,
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
                "X-Requested-With": "fetch",
            },
            body: body ? JSON.stringify(body) : undefined,
        });
        if (!response.ok) {
            throw new Error("json-request-failed");
        }
        return response.json();
    };

    const escapeHtml = (value) => String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

    const buildYearPalette = (years) => {
        const mapping = {};
        uniqueSortedYears(years).forEach((year, index) => {
            mapping[year] = palette[index % palette.length];
        });
        return mapping;
    };

    const closeSelectDropdown = (dropdown) => {
        const menu = dropdown.querySelector("[data-select-menu]");
        const trigger = dropdown.querySelector("[data-select-trigger]");
        if (menu) {
            menu.hidden = true;
        }
        trigger?.classList.remove("is-open");
        trigger?.setAttribute("aria-expanded", "false");
    };

    const closeSelectDropdownMenus = (root, exceptDropdown = null) => {
        const scope = root instanceof Element ? root : document;
        scope.querySelectorAll("[data-select-dropdown]").forEach((dropdown) => {
            if (dropdown === exceptDropdown) {
                return;
            }
            closeSelectDropdown(dropdown);
        });
    };

    const openSelectDropdown = (dropdown) => {
        const scope = dropdown.closest("[data-page-root]") || document;
        closeSelectDropdownMenus(scope, dropdown);
        const menu = dropdown.querySelector("[data-select-menu]");
        const trigger = dropdown.querySelector("[data-select-trigger]");
        if (menu) {
            menu.hidden = false;
        }
        trigger?.classList.add("is-open");
        trigger?.setAttribute("aria-expanded", "true");
    };

    const refreshSelectDropdown = (dropdown) => {
        const select = dropdown.querySelector("select");
        const trigger = dropdown.querySelector("[data-select-trigger]");
        const triggerText = dropdown.querySelector("[data-select-trigger-text]");
        const optionsContainer = dropdown.querySelector("[data-select-options]");
        if (
            !(select instanceof HTMLSelectElement)
            || !(trigger instanceof HTMLButtonElement)
            || !(triggerText instanceof HTMLElement)
            || !(optionsContainer instanceof HTMLElement)
        ) {
            return;
        }

        const selectedOption = select.selectedOptions[0];
        triggerText.textContent = selectedOption?.textContent?.trim() || "—";
        trigger.classList.toggle("has-value", Boolean(select.value));
        trigger.toggleAttribute("disabled", select.disabled);

        optionsContainer.innerHTML = "";
        if (!select.options.length) {
            optionsContainer.innerHTML = '<div class="filter-empty">Нет доступных значений</div>';
            return;
        }

        Array.from(select.options).forEach((option) => {
            const optionButton = document.createElement("button");
            optionButton.type = "button";
            optionButton.className = `filter-option filter-option-static select-dropdown-option${
                option.selected ? " is-selected" : ""
            }`;
            optionButton.dataset.value = option.value;
            optionButton.innerHTML = `
                <span class="filter-option-text">
                    <span class="filter-option-title">${escapeHtml(option.textContent || "")}</span>
                </span>
            `;
            optionButton.addEventListener("click", (event) => {
                event.stopPropagation();
                select.value = option.value;
                select.dispatchEvent(new Event("change", {bubbles: true}));
                refreshSelectDropdown(dropdown);
                closeSelectDropdown(dropdown);
            });
            optionsContainer.appendChild(optionButton);
        });
    };

    const initSelectDropdowns = (root = document) => {
        const scope = root instanceof Element ? root : document;
        scope.querySelectorAll("[data-select-dropdown]").forEach((dropdown) => {
            if (dropdown.dataset.selectDropdownReady === "true") {
                refreshSelectDropdown(dropdown);
                return;
            }

            const select = dropdown.querySelector("select");
            const trigger = dropdown.querySelector("[data-select-trigger]");
            const menu = dropdown.querySelector("[data-select-menu]");
            if (
                !(select instanceof HTMLSelectElement)
                || !(trigger instanceof HTMLButtonElement)
                || !(menu instanceof HTMLElement)
            ) {
                return;
            }

            trigger.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (trigger.hasAttribute("disabled")) {
                    return;
                }
                const isOpen = trigger.getAttribute("aria-expanded") === "true";
                if (isOpen) {
                    closeSelectDropdown(dropdown);
                } else {
                    openSelectDropdown(dropdown);
                }
            });

            select.addEventListener("change", () => {
                refreshSelectDropdown(dropdown);
            });

            dropdown.dataset.selectDropdownReady = "true";
            refreshSelectDropdown(dropdown);
        });

        if (!document.documentElement.dataset.selectDropdownOutsideBound) {
            document.addEventListener("click", (event) => {
                const target = event.target;
                if (!(target instanceof Element)) {
                    return;
                }
                const dropdown = target.closest("[data-select-dropdown]");
                if (!dropdown) {
                    closeSelectDropdownMenus(document);
                }
            });

            document.addEventListener("keydown", (event) => {
                if (event.key === "Escape") {
                    closeSelectDropdownMenus(document);
                }
            });

            document.documentElement.dataset.selectDropdownOutsideBound = "true";
        }
    };

    const refreshSelectDropdowns = (root = document) => {
        const scope = root instanceof Element ? root : document;
        scope.querySelectorAll("[data-select-dropdown]").forEach((dropdown) => {
            refreshSelectDropdown(dropdown);
        });
    };

    namespace.storageKey = storageKey;
    namespace.normalizeYear = normalizeYear;
    namespace.normalizeYearsPayload = normalizeYearsPayload;
    namespace.resolveRange = resolveRange;
    namespace.readStoredRange = readStoredRange;
    namespace.writeStoredRange = writeStoredRange;
    namespace.renderYearOptions = renderYearOptions;
    namespace.buildPeriodLabel = buildPeriodLabel;
    namespace.fetchJson = fetchJson;
    namespace.escapeHtml = escapeHtml;
    namespace.buildYearPalette = buildYearPalette;
    namespace.initSelectDropdowns = initSelectDropdowns;
    namespace.refreshSelectDropdowns = refreshSelectDropdowns;

    const bootSelectDropdowns = () => {
        document.querySelectorAll("[data-page-root]").forEach((pageRoot) => {
            if (pageRoot.querySelector("[data-select-dropdown]")) {
                initSelectDropdowns(pageRoot);
            }
        });
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootSelectDropdowns);
    } else {
        bootSelectDropdowns();
    }
})();

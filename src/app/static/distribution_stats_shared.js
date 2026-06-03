(() => {
    const namespace = window.DistributionStatsPage || (window.DistributionStatsPage = {});
    const storageKey = "distribution-stats:year-range:v1";
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

        const fallbackYears = availableYears.length > 4
            ? availableYears.slice(-4)
            : availableYears;
        const defaultYearFrom = availableYears.includes(normalizeYear(payload?.default_year_from))
            ? normalizeYear(payload.default_year_from)
            : fallbackYears[0];
        const defaultYearTo = availableYears.includes(normalizeYear(payload?.default_year_to))
            ? normalizeYear(payload.default_year_to)
            : fallbackYears[fallbackYears.length - 1];

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
})();

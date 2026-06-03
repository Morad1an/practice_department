(() => {
    const root = document.querySelector("[data-organization-header-search]");
    if (!(root instanceof HTMLElement)) {
        return;
    }

    const input = root.querySelector("[data-organization-search-input]");
    const panel = root.querySelector("[data-organization-search-panel]");
    const statusNode = root.querySelector("[data-organization-search-status]");
    const resultsNode = root.querySelector("[data-organization-search-results]");
    const searchUrl = root.dataset.searchUrl || "";

    if (
        !(input instanceof HTMLInputElement) ||
        !(panel instanceof HTMLElement) ||
        !(statusNode instanceof HTMLElement) ||
        !(resultsNode instanceof HTMLElement) ||
        !searchUrl
    ) {
        return;
    }

    let debounceTimerId = null;
    let abortController = null;
    let latestRequestId = 0;
    let latestItems = [];

    const escapeHtml = (value) =>
        String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;");

    const hidePanel = () => {
        panel.hidden = true;
    };

    const showPanel = () => {
        panel.hidden = false;
    };

    const setStatus = (message) => {
        statusNode.textContent = message || "";
        statusNode.hidden = !message;
    };

    const renderResults = (items, query) => {
        latestItems = items;

        if (!items.length) {
            resultsNode.innerHTML = `<div class="hero-search-empty">По запросу «${escapeHtml(query)}» ничего не найдено.</div>`;
            showPanel();
            return;
        }

        const markup = items
            .map((item) => {
                const title = item.name_short || item.name_long || `Организация #${item.organization_id}`;
                const metaParts = [];

                if (item.name_long && item.name_long !== title) {
                    metaParts.push(item.name_long);
                }
                if (item.inn) {
                    metaParts.push(`ИНН: ${item.inn}`);
                }
                if (item.settlement_name) {
                    metaParts.push(item.settlement_name);
                }

                return `
                    <a class="hero-search-result" href="${escapeHtml(item.organization_url)}">
                        <span class="hero-search-result-title">${escapeHtml(title)}</span>
                        <span class="hero-search-result-meta">${escapeHtml(metaParts.join(" • "))}</span>
                    </a>
                `;
            })
            .join("");

        resultsNode.innerHTML = `<div class="hero-search-list">${markup}</div>`;
        showPanel();
    };

    const runSearch = async (rawQuery) => {
        const query = rawQuery.trim();
        if (query.length < 2) {
            latestItems = [];
            resultsNode.innerHTML = "";
            setStatus("");
            hidePanel();
            return;
        }

        if (abortController) {
            abortController.abort();
        }
        abortController = new AbortController();
        const requestId = ++latestRequestId;

        setStatus("Ищем организации...");
        resultsNode.innerHTML = "";
        showPanel();

        try {
            const url = new URL(searchUrl, window.location.origin);
            url.searchParams.set("q", query);

            const response = await fetch(url, {
                method: "GET",
                headers: {
                    Accept: "application/json",
                },
                signal: abortController.signal,
            });
            if (!response.ok) {
                throw new Error(`Ошибка ${response.status}`);
            }

            const payload = await response.json();
            if (requestId !== latestRequestId) {
                return;
            }

            setStatus("");
            renderResults(Array.isArray(payload?.items) ? payload.items : [], query);
        } catch (error) {
            if (error instanceof DOMException && error.name === "AbortError") {
                return;
            }
            if (requestId !== latestRequestId) {
                return;
            }
            latestItems = [];
            resultsNode.innerHTML = "";
            setStatus("Не удалось загрузить результаты поиска.");
            showPanel();
        }
    };

    input.addEventListener("input", () => {
        if (debounceTimerId) {
            window.clearTimeout(debounceTimerId);
        }
        debounceTimerId = window.setTimeout(() => {
            runSearch(input.value);
        }, 250);
    });

    input.addEventListener("focus", () => {
        if (input.value.trim().length >= 2 && (latestItems.length || statusNode.textContent)) {
            showPanel();
        }
    });

    input.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            hidePanel();
            return;
        }
        if (event.key === "Enter" && latestItems.length > 0) {
            event.preventDefault();
            window.location.assign(latestItems[0].organization_url);
            return;
        }
        if (event.key === "ArrowDown") {
            const firstLink = resultsNode.querySelector(".hero-search-result");
            if (firstLink instanceof HTMLAnchorElement) {
                event.preventDefault();
                firstLink.focus();
            }
        }
    });

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Node)) {
            return;
        }
        if (!root.contains(event.target)) {
            hidePanel();
        }
    });
})();

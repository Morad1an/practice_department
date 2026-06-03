(() => {
    const namespace = window.ActiveOrganizationsPage || (window.ActiveOrganizationsPage = {});

    namespace.createLogosController = function createLogosController(config) {
        const {
            getTableSection,
            logoApiUrl,
        } = config;

        const logoBatchSize = 60;
        const logoEstimatedRowHeightPx = 96;
        const logoPreloadRowsAbove = 2;
        const logoPreloadRowsBelow = 5;
        const logoBatchCoalesceMs = 50;
        const logoCachePrefix = "active-org-logo:v1:";
        const logoCacheTtlMs = 24 * 60 * 60 * 1000;
        const logoMemoryCache = new Map();
        const logoPendingIds = new Set();
        let logoBatchInFlight = false;
        let logoFlushTimer = null;
        let logoObserver = null;

        const readLogoFromStorage = (logoId) => {
            try {
                const raw = window.localStorage.getItem(`${logoCachePrefix}${logoId}`);
                if (!raw) {
                    return undefined;
                }
                const payload = JSON.parse(raw);
                if (!payload || typeof payload.ts !== "number") {
                    window.localStorage.removeItem(`${logoCachePrefix}${logoId}`);
                    return undefined;
                }
                if (Date.now() - payload.ts > logoCacheTtlMs) {
                    window.localStorage.removeItem(`${logoCachePrefix}${logoId}`);
                    return undefined;
                }
                return payload.data ?? null;
            } catch {
                return undefined;
            }
        };

        const writeLogoToStorage = (logoId, dataUrl) => {
            try {
                const payload = JSON.stringify({ts: Date.now(), data: dataUrl});
                window.localStorage.setItem(`${logoCachePrefix}${logoId}`, payload);
            } catch {
                // ignore storage quota / disabled storage
            }
        };

        const getCachedLogo = (logoId) => {
            if (logoMemoryCache.has(logoId)) {
                return logoMemoryCache.get(logoId);
            }
            const fromStorage = readLogoFromStorage(logoId);
            if (fromStorage !== undefined) {
                logoMemoryCache.set(logoId, fromStorage);
                return fromStorage;
            }
            return undefined;
        };

        const applyLogoToImage = (img, dataUrl) => {
            if (dataUrl) {
                img.src = dataUrl;
                img.classList.remove("logo-placeholder");
            }
            img.dataset.logoLoaded = "1";
        };

        const applyLogoToCurrentTable = (logoId, dataUrl) => {
            const tableSection = getTableSection();
            if (!tableSection) {
                return;
            }
            const images = tableSection.querySelectorAll(`[data-logo-img="true"][data-logo-id="${logoId}"]`);
            images.forEach((img) => applyLogoToImage(img, dataUrl));
        };

        const fetchLogoBatch = (ids) => {
            if (!ids.length || !logoApiUrl) {
                return Promise.resolve();
            }

            const url = new URL(logoApiUrl, window.location.origin);
            ids.forEach((id) => url.searchParams.append("ids", String(id)));

            return fetch(url, {headers: {"X-Requested-With": "fetch", Accept: "application/json"}})
                .then((response) => {
                    if (!response.ok) {
                        throw new Error("logo-batch-failed");
                    }
                    return response.json();
                })
                .then((payload) => {
                    const logos = payload?.logos || {};
                    ids.forEach((logoId) => {
                        const key = String(logoId);
                        const dataUrl = Object.prototype.hasOwnProperty.call(logos, key) ? logos[key] : null;
                        logoMemoryCache.set(logoId, dataUrl);
                        writeLogoToStorage(logoId, dataUrl);
                        applyLogoToCurrentTable(logoId, dataUrl);
                    });
                });
        };

        const flushLogoQueue = () => {
            if (logoBatchInFlight || !logoPendingIds.size) {
                return;
            }

            logoBatchInFlight = true;
            const ids = Array.from(logoPendingIds).slice(0, logoBatchSize);
            ids.forEach((id) => logoPendingIds.delete(id));

            fetchLogoBatch(ids)
                .catch(() => {
                    // keep placeholders if batch request fails
                })
                .finally(() => {
                    logoBatchInFlight = false;
                    if (logoPendingIds.size) {
                        scheduleLogoFlush();
                    }
                });
        };

        const scheduleLogoFlush = () => {
            if (logoFlushTimer !== null) {
                return;
            }
            logoFlushTimer = window.setTimeout(() => {
                logoFlushTimer = null;
                flushLogoQueue();
            }, logoBatchCoalesceMs);
        };

        const queueLogoLoad = (logoId) => {
            if (!logoId || logoMemoryCache.has(logoId)) {
                return;
            }
            logoPendingIds.add(logoId);
            scheduleLogoFlush();
        };

        const prepareLogoImage = (img) => {
            if (!img || img.dataset.logoLoaded === "1") {
                return;
            }

            const rawId = img.getAttribute("data-logo-id");
            if (!rawId) {
                img.dataset.logoLoaded = "1";
                return;
            }

            const logoId = Number(rawId);
            if (!Number.isInteger(logoId) || logoId <= 0) {
                img.dataset.logoLoaded = "1";
                return;
            }

            const cached = getCachedLogo(logoId);
            if (cached !== undefined) {
                applyLogoToImage(img, cached);
                return;
            }

            if (logoObserver) {
                logoObserver.observe(img);
                return;
            }

            queueLogoLoad(logoId);
        };

        const observeLogosInSection = (root) => {
            if (!root) {
                return;
            }
            root.querySelectorAll("[data-logo-img='true']").forEach((img) => prepareLogoImage(img));
        };

        const setup = () => {
            if (logoFlushTimer !== null) {
                window.clearTimeout(logoFlushTimer);
                logoFlushTimer = null;
            }
            if (logoObserver) {
                logoObserver.disconnect();
                logoObserver = null;
            }

            const tableSection = getTableSection();
            if (!("IntersectionObserver" in window)) {
                observeLogosInSection(tableSection);
                return;
            }

            logoObserver = new IntersectionObserver((entries) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) {
                        return;
                    }
                    const img = entry.target;
                    logoObserver.unobserve(img);
                    const rawId = img.getAttribute("data-logo-id");
                    const logoId = Number(rawId);
                    if (Number.isInteger(logoId) && logoId > 0) {
                        queueLogoLoad(logoId);
                    } else {
                        img.dataset.logoLoaded = "1";
                    }
                });
            }, {
                root: null,
                rootMargin: `${logoPreloadRowsAbove * logoEstimatedRowHeightPx}px 0px ${logoPreloadRowsBelow * logoEstimatedRowHeightPx}px 0px`,
            });

            observeLogosInSection(tableSection);
        };

        return {
            setup,
        };
    };
})();

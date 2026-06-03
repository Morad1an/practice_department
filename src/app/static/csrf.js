(() => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = meta?.getAttribute("content") || "";
    const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
    const originalFetch = window.fetch.bind(window);

    const isSameOrigin = (input) => {
        try {
            if (input instanceof Request) {
                return new URL(input.url, window.location.href).origin === window.location.origin;
            }
            return new URL(String(input), window.location.href).origin === window.location.origin;
        } catch {
            return false;
        }
    };

    const buildHeaders = (existingHeaders) => {
        const headers = new Headers(existingHeaders || {});
        if (csrfToken && !headers.has("X-CSRF-Token")) {
            headers.set("X-CSRF-Token", csrfToken);
        }
        if (!headers.has("X-Requested-With")) {
            headers.set("X-Requested-With", "fetch");
        }
        return headers;
    };

    window.AppCsrf = {
        token: csrfToken,
        buildHeaders,
    };

    window.fetch = (input, init = {}) => {
        const method = (
            init.method
            || (input instanceof Request ? input.method : "GET")
        ).toUpperCase();

        if (!unsafeMethods.has(method) || !isSameOrigin(input)) {
            return originalFetch(input, init);
        }

        return originalFetch(input, {
            ...init,
            headers: buildHeaders(
                init.headers || (input instanceof Request ? input.headers : undefined),
            ),
        });
    };
})();

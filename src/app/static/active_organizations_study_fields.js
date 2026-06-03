(() => {
    const namespace = window.ActiveOrganizationsPage || (window.ActiveOrganizationsPage = {});

    namespace.createStudyFieldsController = function createStudyFieldsController(config) {
        const {getTableSection} = config;

        const bind = () => {
            const tableSection = getTableSection();
            if (!tableSection) {
                return;
            }

            tableSection.querySelectorAll("[data-study-more]").forEach((button) => {
                if (button.dataset.bound === "1") {
                    return;
                }
                button.dataset.bound = "1";
                button.addEventListener("click", () => {
                    const container = button.closest("[data-study-fields]");
                    if (!container) {
                        return;
                    }
                    const preview = container.querySelector("[data-study-preview]");
                    const expanded = container.querySelector("[data-study-expanded]");
                    if (preview) {
                        preview.hidden = true;
                    }
                    if (expanded) {
                        expanded.hidden = false;
                    }
                });
            });

            tableSection.querySelectorAll("[data-study-collapse]").forEach((button) => {
                if (button.dataset.bound === "1") {
                    return;
                }
                button.dataset.bound = "1";
                button.addEventListener("click", () => {
                    const container = button.closest("[data-study-fields]");
                    if (!container) {
                        return;
                    }
                    const preview = container.querySelector("[data-study-preview]");
                    const expanded = container.querySelector("[data-study-expanded]");
                    if (expanded) {
                        expanded.hidden = true;
                    }
                    if (preview) {
                        preview.hidden = false;
                    }
                });
            });
        };

        return {
            bind,
        };
    };
})();

(() => {
    const namespace = window.ActiveOrganizationsPage || (window.ActiveOrganizationsPage = {});

    namespace.createExportController = function createExportController(config) {
        const {
            exportUrl,
            exportButton,
            serializeTablePayload,
        } = config;

        const resolveDownloadFilename = (response) => {
            const fallback = "Контакты.xlsx";
            const disposition = response.headers.get("Content-Disposition");
            if (!disposition) {
                return fallback;
            }

            const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
            if (utf8Match?.[1]) {
                try {
                    return decodeURIComponent(utf8Match[1]);
                } catch {
                    return utf8Match[1];
                }
            }

            const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
            return plainMatch?.[1] || fallback;
        };

        const exportTable = async () => {
            if (!exportUrl) {
                return;
            }

            exportButton?.toggleAttribute("disabled", true);
            try {
                const response = await fetch(exportUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Requested-With": "fetch",
                    },
                    body: JSON.stringify(serializeTablePayload(0)),
                });
                if (!response.ok) {
                    throw new Error("export-request-failed");
                }

                const blob = await response.blob();
                const downloadUrl = window.URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = downloadUrl;
                link.download = resolveDownloadFilename(response);
                document.body.appendChild(link);
                link.click();
                link.remove();
                window.URL.revokeObjectURL(downloadUrl);
            } catch (error) {
                console.error(error);
            } finally {
                exportButton?.toggleAttribute("disabled", false);
            }
        };

        return {
            exportTable,
        };
    };
})();

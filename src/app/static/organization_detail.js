(() => {
    const form = document.querySelector("[data-organization-card-form]");
    if (!form) {
        return;
    }

    const contactsTableBody = form.querySelector("[data-contacts-list], [data-contacts-table-body]");
    const addContactButton = form.querySelector("[data-add-contact]");
    const emptyContactsNote = form.querySelector("[data-empty-contacts-note]");
    const mapButton = form.querySelector("[data-show-on-map]");
    const saveButton = form.querySelector("[data-save-organization]");
    const deleteButton = form.querySelector("[data-delete-organization]");
    const logoFileInput = form.querySelector("[data-logo-file-input]");
    const uploadLogoTrigger = form.querySelector("[data-upload-logo-trigger]");
    const deleteLogoButton = form.querySelector("[data-delete-logo]");
    const logoFrame = form.querySelector("[data-logo-frame]");
    const logoActions = form.querySelector(".organization-logo-actions");
    const statusNode = form.querySelector("[data-form-status]");
    const toastNode = form.querySelector("[data-organization-toast]");
    const confirmModal = form.querySelector("[data-confirm-modal]");
    const confirmTitleNode = form.querySelector("[data-confirm-title]");
    const confirmMessageNode = form.querySelector("[data-confirm-message]");
    const confirmCancelButton = form.querySelector("[data-confirm-cancel]");
    const confirmSubmitButton = form.querySelector("[data-confirm-submit]");
    const documentEditor = form.querySelector("[data-document-editor]");
    const addDocumentButton = form.querySelector("[data-add-document]");
    const cancelDocumentButton = form.querySelector("[data-cancel-document]");
    const submitDocumentButton = form.querySelector("[data-submit-document]");
    const documentModal = form.querySelector("[data-document-modal]");
    const closeDocumentModalButtons = form.querySelectorAll("[data-close-document-modal]");
    const saveDocumentModalButton = form.querySelector("[data-save-document-modal]");
    const documentModalTitle = form.querySelector("[data-document-modal-title]");
    const documentModalOrgName = form.querySelector("[data-document-modal-org-name]");
    const documentModalOrgAddress = form.querySelector("[data-document-modal-org-address]");
    const documentModalDatatype = form.querySelector("[data-document-modal-datatype]");
    const documentModalPdfInput = form.querySelector("[data-document-modal-pdf-input]");
    const documentModalPdfLink = form.querySelector("[data-document-modal-pdf-link]");
    const documentModalPdfUpload = form.querySelector("[data-document-modal-pdf-upload]");
    const documentModalDeletePdfButton = form.querySelector("[data-document-modal-delete-pdf]");
    const documentModalPdfTrigger = form.querySelector("[data-document-modal-pdf-trigger]");
    const documentModalPdfName = form.querySelector("[data-document-modal-pdf-name]");
    const createMode = form.dataset.createMode === "true";
    const canEdit = form.dataset.canEdit === "true";
    const logoMaxBytes = Number.parseInt(form.dataset.logoMaxBytes || "0", 10) || 0;
    const toastStorageKey = "organization-card-toast";
    let toastTimerId = null;
    let confirmResolver = null;
    let documentModalState = null;
    let contactClientKeyCounter = 0;
    const contactTypeOptions = (() => {
        try {
            return JSON.parse(form.dataset.contactTypeOptions || "[]");
        } catch {
            return [];
        }
    })();
    const studyFieldOptions = (() => {
        try {
            return JSON.parse(form.querySelector("[data-study-field-options-json]")?.textContent || "[]");
        } catch {
            return [];
        }
    })();
    const requisiteTypeOptions = (() => {
        try {
            return JSON.parse(form.querySelector("[data-requisite-type-options-json]")?.textContent || "[]");
        } catch {
            return [];
        }
    })();
    const studyFieldList = form.querySelector("[data-study-field-list]");
    const studyFieldSearch = form.querySelector("[data-study-field-search]");
    const studyFieldOptionsList = form.querySelector("#organization-study-field-options");
    const addStudyFieldButton = form.querySelector("[data-add-study-field]");
    const emptyStudyFieldsNote = form.querySelector("[data-empty-study-fields-note]");
    const requisitesList = form.querySelector("[data-requisites-list]");
    const requisiteTypeSelect = form.querySelector("[data-requisite-type-select]");
    const addRequisiteButton = form.querySelector("[data-add-requisite]");

    const escapeHtml = (value) =>
        String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;");

    const setStatus = (message, type = "info") => {
        if (!(statusNode instanceof HTMLElement)) {
            return;
        }
        if (!message) {
            statusNode.hidden = true;
            statusNode.textContent = "";
            statusNode.dataset.statusType = "";
            return;
        }
        statusNode.hidden = false;
        statusNode.textContent = message;
        statusNode.dataset.statusType = type;
    };

    const showToast = (message, type = "success") => {
        if (!(toastNode instanceof HTMLElement) || !message) {
            return;
        }
        if (toastTimerId) {
            window.clearTimeout(toastTimerId);
        }
        toastNode.hidden = false;
        toastNode.textContent = message;
        toastNode.dataset.toastType = type;
        toastTimerId = window.setTimeout(() => {
            toastNode.hidden = true;
            toastNode.textContent = "";
            toastNode.dataset.toastType = "";
            toastTimerId = null;
        }, 2000);
    };

    const persistToastForRedirect = (message, type = "success") => {
        try {
            window.sessionStorage.setItem(
                toastStorageKey,
                JSON.stringify({ message, type }),
            );
        } catch {
            // Ignore storage failures and continue redirect flow.
        }
    };

    const restoreToastFromRedirect = () => {
        try {
            const rawValue = window.sessionStorage.getItem(toastStorageKey);
            if (!rawValue) {
                return;
            }
            window.sessionStorage.removeItem(toastStorageKey);
            const payload = JSON.parse(rawValue);
            if (payload?.message) {
                showToast(payload.message, payload.type || "success");
            }
        } catch {
            window.sessionStorage.removeItem(toastStorageKey);
        }
    };

    const applyReadOnlyMode = () => {
        if (canEdit) {
            return;
        }

        [
            "[data-upload-logo-trigger]",
            "[data-delete-logo]",
            "[data-add-document]",
            "[data-document-editor]",
            "[data-document-modal-delete-pdf]",
            "[data-document-modal-pdf-upload]",
            "[data-save-document-modal]",
            "[data-add-contact]",
            "[data-remove-contact-row]",
            "[data-delete-organization]",
        ].forEach((selector) => {
            form.querySelectorAll(selector).forEach((node) => {
                if (node instanceof HTMLElement) {
                    node.hidden = true;
                }
            });
        });

        form.querySelectorAll(".organization-form-actions-right").forEach((node) => {
            if (node instanceof HTMLElement) {
                node.hidden = true;
            }
        });

        form.querySelectorAll(".organization-actions-column, .organization-actions-cell").forEach((node) => {
            if (node instanceof HTMLElement) {
                node.hidden = true;
            }
        });

        form.querySelectorAll("input, textarea, select").forEach((element) => {
            if (!(element instanceof HTMLElement)) {
                return;
            }
            if (element instanceof HTMLInputElement && element.type === "hidden") {
                return;
            }
            if (element.closest("[data-confirm-modal]")) {
                return;
            }
            if (element instanceof HTMLInputElement && ["text", "url", "date"].includes(element.type)) {
                element.readOnly = true;
                return;
            }
            if (element instanceof HTMLTextAreaElement) {
                element.readOnly = true;
                return;
            }
            element.setAttribute("disabled", "disabled");
        });
    };

    if (confirmTitleNode instanceof HTMLElement) {
        confirmTitleNode.textContent = "Подтверждение";
    }
    if (confirmCancelButton instanceof HTMLButtonElement) {
        confirmCancelButton.textContent = "Отмена";
    }
    if (confirmSubmitButton instanceof HTMLButtonElement) {
        confirmSubmitButton.textContent = "Подтвердить";
    }

    applyReadOnlyMode();

    const closeConfirmModal = (confirmed) => {
        if (!(confirmModal instanceof HTMLElement)) {
            return;
        }
        confirmModal.hidden = true;
        const resolver = confirmResolver;
        confirmResolver = null;
        if (resolver) {
            resolver(Boolean(confirmed));
        }
    };

    const ensureLogoPlaceholder = () => {
        if (!(logoFrame instanceof HTMLElement)) {
            return;
        }
        const currentImage = logoFrame.querySelector("[data-logo-image]");
        currentImage?.remove();

        let placeholder = logoFrame.querySelector("[data-logo-placeholder]");
        if (!(placeholder instanceof HTMLElement)) {
            placeholder = document.createElement("div");
            placeholder.className = "organization-logo-placeholder";
            placeholder.setAttribute("data-logo-placeholder", "");
            logoFrame.appendChild(placeholder);
        }
        placeholder.innerHTML = "Логотип<br>не загружен";
    };

    const renderUploadLogoButton = () => {
        if (!(logoActions instanceof HTMLElement)) {
            return;
        }

        const existingDeleteButton = logoActions.querySelector("[data-delete-logo]");
        existingDeleteButton?.remove();

        let uploadButton = logoActions.querySelector("[data-upload-logo-trigger]");
        if (!(uploadButton instanceof HTMLButtonElement)) {
            uploadButton = document.createElement("button");
            uploadButton.type = "button";
            uploadButton.className = "btn btn-outline";
            uploadButton.setAttribute("data-upload-logo-trigger", "");
            uploadButton.textContent = "Загрузить логотип";

            const hint = logoActions.querySelector(".organization-logo-hint");
            if (hint instanceof HTMLElement) {
                logoActions.insertBefore(uploadButton, hint);
            } else {
                logoActions.appendChild(uploadButton);
            }
        } else {
            uploadButton.hidden = false;
            uploadButton.disabled = false;
            uploadButton.textContent = "Загрузить логотип";
        }
    };

    const confirmAction = ({
        title = "Подтверждение",
        message = "",
        confirmLabel = "Подтвердить",
        tone = "primary",
    }) => {
        if (
            !(confirmModal instanceof HTMLElement) ||
            !(confirmTitleNode instanceof HTMLElement) ||
            !(confirmMessageNode instanceof HTMLElement) ||
            !(confirmSubmitButton instanceof HTMLButtonElement)
        ) {
            return Promise.resolve(window.confirm(message || title));
        }

        if (confirmResolver) {
            const pendingResolver = confirmResolver;
            confirmResolver = null;
            pendingResolver(false);
        }

        confirmTitleNode.textContent = title;
        confirmMessageNode.textContent = message;
        confirmSubmitButton.textContent = confirmLabel;
        confirmSubmitButton.classList.add("organization-confirm-submit");
        confirmSubmitButton.classList.toggle("is-danger", tone === "danger");
        confirmModal.hidden = false;

        return new Promise((resolve) => {
            confirmResolver = resolve;
            window.requestAnimationFrame(() => {
                confirmSubmitButton.focus();
            });
        });
    };

    const syncContactsEmptyState = () => {
        if (!(contactsTableBody instanceof HTMLElement) || !(emptyContactsNote instanceof HTMLElement)) {
            return;
        }
        emptyContactsNote.hidden = contactsTableBody.querySelectorAll("[data-contact-card]").length > 0;
    };

    const buildContactTypeOptionsMarkup = (selectedId = "") => {
        const normalizedSelectedId = String(selectedId || "");
        const options = ['<option value="">Выберите тип</option>'];
        contactTypeOptions.forEach((option) => {
            const optionId = String(option.id ?? "");
            const selected = optionId === normalizedSelectedId ? " selected" : "";
            options.push(
                `<option value="${escapeHtml(optionId)}"${selected}>${escapeHtml(option.label || "")}</option>`,
            );
        });
        return options.join("");
    };

    const nextContactClientKey = () => {
        contactClientKeyCounter += 1;
        return `new-${Date.now()}-${contactClientKeyCounter}`;
    };

    const buildContactMethodRow = ({
        dataId = "",
        typeId = "",
        value = "",
    } = {}) => {
        const row = document.createElement("div");
        row.className = "organization-contact-method-row";
        row.setAttribute("data-contact-method-row", "");
        row.innerHTML = `
            <input type="hidden" name="contact_data_id" value="${escapeHtml(dataId)}">
            <select name="contact_type_id">
                ${buildContactTypeOptionsMarkup(typeId)}
            </select>
            <input type="text" name="contact_value" value="${escapeHtml(value)}" placeholder="Контактные данные">
            <button type="button" class="organization-contact-method-remove" data-remove-contact-row aria-label="Удалить контакт">×</button>
        `;
        return row;
    };

    const buildContactCard = ({
        entityId = "",
        clientEntityKey = "",
        name = "",
        post = "",
        methods = [{}],
    } = {}) => {
        const card = document.createElement("div");
        card.className = "organization-contact-card";
        card.setAttribute("data-contact-card", "");
        card.dataset.clientEntityKey = clientEntityKey || nextContactClientKey();
        card.innerHTML = `
            <input type="hidden" name="contact_entity_id" value="${escapeHtml(entityId)}">
            <div class="organization-contact-card-header">
                <div class="organization-contact-person-fields">
                    <input type="text" name="contact_name" value="${escapeHtml(name)}" placeholder="Контактное лицо">
                    <input type="text" name="contact_post" value="${escapeHtml(post)}" placeholder="Должность">
                </div>
                <button type="button" class="btn organization-contact-delete-person" data-remove-contact-card>Удалить контактное лицо</button>
            </div>
            <div class="organization-contact-methods" data-contact-methods></div>
            <button type="button" class="btn btn-outline organization-contact-add-method" data-add-contact-method>Добавить контактные данные</button>
        `;
        const methodsContainer = card.querySelector("[data-contact-methods]");
        if (methodsContainer instanceof HTMLElement) {
            methods.forEach((method) => {
                methodsContainer.appendChild(buildContactMethodRow(method));
            });
        }
        return card;
    };

    const normalizeOptionLabel = (value) => String(value || "").trim().toLowerCase();
    const isOtherRequisiteLabel = (value) => normalizeOptionLabel(value) === "другое";
    const isInnRequisiteLabel = (value) => normalizeOptionLabel(value) === "инн";

    const getRequisiteBaseLabel = (item) => {
        if (!(item instanceof HTMLElement)) {
            return "";
        }
        return item.dataset.requisiteBaseLabel
            || item.querySelector("[data-requisite-value-input]")?.dataset.requisiteLabel
            || item.querySelector("[data-requisite-label-text]")?.textContent
            || "";
    };

    const findStudyFieldOptionByLabel = (label) => {
        const normalizedLabel = normalizeOptionLabel(label);
        if (!normalizedLabel) {
            return null;
        }
        return studyFieldOptions.find((option) => (
            normalizeOptionLabel(option?.label) === normalizedLabel
        )) || null;
    };

    const getSelectedStudyFieldIds = () => {
        if (!(studyFieldList instanceof HTMLElement)) {
            return new Set();
        }
        return new Set(
            Array.from(studyFieldList.querySelectorAll('input[name="study_field_id"]'))
                .map((input) => parseInteger(input.value))
                .filter((value) => value !== null),
        );
    };

    const syncStudyFieldsEmptyState = () => {
        if (!(studyFieldList instanceof HTMLElement) || !(emptyStudyFieldsNote instanceof HTMLElement)) {
            return;
        }
        emptyStudyFieldsNote.hidden = studyFieldList.querySelectorAll("[data-study-field-chip]").length > 0;
    };

    const syncStudyFieldOptionsList = () => {
        if (!(studyFieldOptionsList instanceof HTMLDataListElement)) {
            return;
        }
        const selectedIds = getSelectedStudyFieldIds();
        studyFieldOptionsList.innerHTML = "";
        studyFieldOptions.forEach((option) => {
            const optionId = parseInteger(option?.id);
            const label = String(option?.label || "").trim();
            if (optionId === null || selectedIds.has(optionId) || !label) {
                return;
            }
            const node = document.createElement("option");
            node.value = label;
            studyFieldOptionsList.appendChild(node);
        });
    };

    const buildStudyFieldChip = (option) => {
        const chip = document.createElement("span");
        chip.className = "organization-study-pill organization-study-pill-editable";
        chip.setAttribute("data-study-field-chip", "");
        chip.innerHTML = `
            <input type="hidden" name="study_field_id" value="${escapeHtml(option.id)}">
            <span>${escapeHtml(option.label)}</span>
            <button type="button" class="organization-chip-remove" data-remove-study-field aria-label="Убрать направление">×</button>
        `;
        return chip;
    };

    const addStudyFieldFromSearch = () => {
        if (!(studyFieldSearch instanceof HTMLInputElement) || !(studyFieldList instanceof HTMLElement)) {
            return;
        }
        const option = findStudyFieldOptionByLabel(studyFieldSearch.value);
        if (!option) {
            studyFieldSearch.setCustomValidity("Выберите направление из списка.");
            studyFieldSearch.reportValidity();
            return;
        }
        studyFieldSearch.setCustomValidity("");
        const optionId = parseInteger(option.id);
        if (optionId === null || getSelectedStudyFieldIds().has(optionId)) {
            studyFieldSearch.value = "";
            return;
        }
        studyFieldList.appendChild(buildStudyFieldChip(option));
        studyFieldSearch.value = "";
        syncStudyFieldsEmptyState();
        syncStudyFieldOptionsList();
    };

    const getUsedNonRepeatableRequisiteTypeIds = () => {
        if (!(requisitesList instanceof HTMLElement)) {
            return new Set();
        }
        return new Set(
            Array.from(requisitesList.querySelectorAll(".organization-requisite-item"))
                .map((item) => ({
                    id: parseInteger(item.querySelector('input[name="requisite_type_id"]')?.value),
                    label: getRequisiteBaseLabel(item),
                }))
                .filter((item) => item.id !== null && !isOtherRequisiteLabel(item.label))
                .map((item) => item.id),
        );
    };

    const syncRequisiteTypeSelectOptions = () => {
        if (!(requisiteTypeSelect instanceof HTMLSelectElement)) {
            return;
        }
        const usedIds = getUsedNonRepeatableRequisiteTypeIds();
        const currentValue = requisiteTypeSelect.value;
        requisiteTypeSelect.innerHTML = '<option value="">Выберите реквизит</option>';
        requisiteTypeOptions.forEach((option) => {
            const optionId = parseInteger(option.id);
            if (optionId === null) {
                return;
            }
            const isRepeatable = isOtherRequisiteLabel(option.label);
            if (!isRepeatable && usedIds.has(optionId)) {
                return;
            }
            const node = document.createElement("option");
            node.value = String(optionId);
            node.textContent = option.label || `Реквизит #${optionId}`;
            node.selected = currentValue === node.value;
            requisiteTypeSelect.appendChild(node);
        });
    };

    const buildRequisiteItem = ({
        id = "",
        typeId,
        label,
        value = "",
        requiredInn = false,
        customLabel = "",
    }) => {
        const isOther = isOtherRequisiteLabel(label);
        const isInn = isInnRequisiteLabel(label);
        const displayLabel = isOther && customLabel ? `${label} (${customLabel})` : label;
        const item = document.createElement("div");
        item.className = "organization-requisite-item";
        item.dataset.requisiteBaseLabel = label || "";
        item.dataset.requisiteCustomLabel = customLabel || "";
        item.innerHTML = `
            <input type="hidden" name="requisite_id" value="${escapeHtml(id)}">
            <input type="hidden" name="requisite_type_id" value="${escapeHtml(typeId)}">
            ${isInn ? "" : '<button type="button" class="organization-icon-remove" data-remove-requisite aria-label="Удалить реквизит">×</button>'}
            <span class="organization-requisite-label" data-requisite-label-text>
                ${escapeHtml(displayLabel)}${requiredInn ? ' <span class="organization-required-mark">*</span>' : ""}
            </span>
            <div class="organization-requisite-input-row">
                ${isOther ? `
                    <input
                        type="text"
                        class="organization-requisite-other-title"
                        value="${escapeHtml(customLabel)}"
                        placeholder="Подпись, например ИНН"
                        data-requisite-other-title
                    >
                ` : ""}
                <input
                    type="text"
                    class="organization-requisite-value-input"
                    name="requisite_value"
                    value="${escapeHtml(value)}"
                    placeholder="Не заполнено"
                    data-requisite-value-input
                    data-requisite-label="${escapeHtml(String(label || "").toLowerCase())}"
                    ${requiredInn ? 'data-create-required-inn="true"' : ""}
                >
            </div>
        `;
        return item;
    };

    const addSelectedRequisite = () => {
        if (!(requisiteTypeSelect instanceof HTMLSelectElement) || !(requisitesList instanceof HTMLElement)) {
            return;
        }
        const typeId = parseInteger(requisiteTypeSelect.value);
        if (typeId === null) {
            return;
        }
        const option = requisiteTypeOptions.find((item) => parseInteger(item.id) === typeId);
        if (!option) {
            return;
        }
        const label = option.label || `Реквизит #${typeId}`;
        const requiredInn = createMode && label === "ИНН" && !form.querySelector("[data-create-required-inn]");
        requisitesList.appendChild(buildRequisiteItem({typeId, label, requiredInn}));
        requisiteTypeSelect.value = "";
        syncRequisiteTypeSelectOptions();
        updateMapButtonState();
    };

    const parseInteger = (value) => {
        const trimmed = String(value ?? "").trim();
        if (!trimmed) {
            return null;
        }
        const parsed = Number.parseInt(trimmed, 10);
        return Number.isNaN(parsed) ? null : parsed;
    };

    const getActualAddressValue = () => {
        const requisiteInputs = form.querySelectorAll("[data-requisite-value-input]");
        for (const input of requisiteInputs) {
            if (!(input instanceof HTMLInputElement)) {
                continue;
            }
            const label = (input.dataset.requisiteLabel || "").toLowerCase();
            if (label.includes("фактичес") && label.includes("адрес")) {
                return input.value.trim();
            }
        }
        return "";
    };

    const getCurrentMapQuery = () => {
        const actualAddress = getActualAddressValue();
        if (actualAddress) {
            return actualAddress;
        }
        const settlementInput = form.querySelector('input[name="settlement_name"]');
        if (settlementInput instanceof HTMLInputElement && settlementInput.value.trim()) {
            return settlementInput.value.trim();
        }
        return form.dataset.mapQuery?.trim() || "";
    };

    const updateMapButtonState = () => {
        if (!(mapButton instanceof HTMLButtonElement)) {
            return;
        }
        mapButton.disabled = !getCurrentMapQuery();
    };

    const getOrganizationDisplayName = () => {
        const shortName = form.querySelector('input[name="name_short"]')?.value?.trim() || "";
        const longName = form.querySelector('textarea[name="name_long"]')?.value?.trim() || "";
        return shortName || longName || "Организация не указана";
    };

    const getOrganizationDisplayAddress = () => {
        return getCurrentMapQuery() || "Фактический адрес не указан";
    };

    const resetDocumentEditorFields = () => {
        if (!(documentEditor instanceof HTMLElement)) {
            return;
        }
        documentEditor.querySelectorAll("[data-document-field]").forEach((field) => {
            if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) {
                if (field.type === "checkbox") {
                    field.checked = false;
                } else {
                    field.value = "";
                }
            }
        });
    };

    const syncDocumentEditorFieldsState = () => {
        if (!(documentEditor instanceof HTMLElement)) {
            return;
        }
        const visible = !documentEditor.hidden;
        documentEditor.querySelectorAll("[data-document-field]").forEach((field) => {
            if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) {
                field.disabled = !visible;
            }
        });
    };

    const resetDocumentModalPdfPicker = () => {
        if (documentModalPdfInput instanceof HTMLInputElement) {
            documentModalPdfInput.value = "";
        }
        if (documentModalPdfName instanceof HTMLElement) {
            documentModalPdfName.textContent = "Файл не выбран";
        }
    };

    const readDocumentRowState = (row) => {
        if (!(row instanceof HTMLElement)) {
            return null;
        }
        return {
            id: parseInteger(row.dataset.documentId),
            updateUrl: row.dataset.updateUrl || "",
            title: row.dataset.documentTitle || "Документ",
            datatypeLabel: row.dataset.documentDatatypeLabel || "Документ",
            namePrimary: row.dataset.documentNamePrimary || "",
            nameSecondary: row.dataset.documentNameSecondary || "",
            chiefName: row.dataset.documentChiefName || "",
            chiefPost: row.dataset.documentChiefPost || "",
            signingDate: row.dataset.documentSigningDate || "",
            isActual: row.dataset.documentIsActual === "true",
            pdfUrl: row.dataset.documentPdfUrl || "",
            pdfFilename: row.dataset.documentPdfFilename || "",
            deletePdfUrl: row.dataset.deletePdfUrl || "",
        };
    };

    const expandSectionForElement = (element) => {
        const section = element?.closest("[data-collapsible-section]");
        if (!(section instanceof HTMLElement)) {
            return;
        }
        const toggle = section.querySelector("[data-section-toggle]");
        if (!(toggle instanceof HTMLElement)) {
            return;
        }
        toggle.setAttribute("aria-expanded", "true");
        syncCollapsibleSection(section);
    };

    const validateCreateInn = () => {
        if (!createMode) {
            return true;
        }
        const innInput = form.querySelector("[data-create-required-inn]");
        if (!(innInput instanceof HTMLInputElement)) {
            setStatus("Поле «ИНН» обязательно при создании организации.", "error");
            return false;
        }

        const validationMessage = "Поле «ИНН» обязательно при создании организации.";
        const hasValue = Boolean(innInput.value.trim());
        innInput.setCustomValidity(hasValue ? "" : validationMessage);

        if (hasValue) {
            return true;
        }

        expandSectionForElement(innInput);
        if (typeof innInput.reportValidity === "function") {
            innInput.reportValidity();
        }
        setStatus(validationMessage, "error");
        return false;
    };

    const validateInnRequisites = () => {
        const innInputs = Array.from(form.querySelectorAll(".organization-requisite-item"))
            .filter((item) => isInnRequisiteLabel(getRequisiteBaseLabel(item)))
            .map((item) => item.querySelector("[data-requisite-value-input]"))
            .filter((input) => input instanceof HTMLInputElement);

        for (const input of innInputs) {
            const validationMessage = "Поле «ИНН» нельзя оставлять пустым.";
            const hasValue = Boolean(input.value.trim());
            input.setCustomValidity(hasValue ? "" : validationMessage);
            if (hasValue) {
                continue;
            }
            expandSectionForElement(input);
            if (typeof input.reportValidity === "function") {
                input.reportValidity();
            }
            setStatus(validationMessage, "error");
            return false;
        }
        return true;
    };

    const gatherContacts = () => {
        if (!(contactsTableBody instanceof HTMLElement)) {
            return [];
        }

        const rows = [];
        contactsTableBody.querySelectorAll("[data-contact-card]").forEach((card) => {
            if (!(card instanceof HTMLElement)) {
                return;
            }
            const entityId = parseInteger(card.querySelector('input[name="contact_entity_id"]')?.value);
            const clientEntityKey = card.dataset.clientEntityKey || null;
            const name = card.querySelector('input[name="contact_name"]')?.value?.trim() || "";
            const post = card.querySelector('input[name="contact_post"]')?.value?.trim() || "";
            card.querySelectorAll("[data-contact-method-row]").forEach((methodRow) => {
                if (!(methodRow instanceof HTMLElement)) {
                    return;
                }
                const dataId = parseInteger(methodRow.querySelector('input[name="contact_data_id"]')?.value);
                const typeId = parseInteger(methodRow.querySelector('select[name="contact_type_id"]')?.value);
                const value = methodRow.querySelector('input[name="contact_value"]')?.value?.trim() || "";
                const methodHasAnyValue = Boolean(dataId || typeId || value);
                const hasAnyValue = Boolean(entityId || dataId || name || post || typeId || value);

                if (!methodHasAnyValue && !hasAnyValue) {
                    return;
                }
                if (!methodHasAnyValue) {
                    return;
                }

                rows.push({
                    entity_id: entityId,
                    data_id: dataId,
                    client_entity_key: clientEntityKey,
                    contact_name: name || null,
                    contact_post: post || null,
                    contact_type_id: typeId,
                    contact_value: value || null,
                });
            });
        });
        return rows;
    };

    const gatherStudyFieldIds = () => Array.from(getSelectedStudyFieldIds());

    const gatherRequisites = () => {
        const requisites = [];
        form.querySelectorAll(".organization-requisite-item").forEach((item) => {
            if (!(item instanceof HTMLElement)) {
                return;
            }
            const baseLabel = getRequisiteBaseLabel(item);
            const valueInput = item.querySelector('input[name="requisite_value"]');
            const rawValue = valueInput?.value?.trim() || "";
            const customLabel = item.querySelector("[data-requisite-other-title]")?.value?.trim() || "";
            const value = isOtherRequisiteLabel(baseLabel) && customLabel && rawValue
                ? `${customLabel}: ${rawValue}`
                : rawValue;
            requisites.push({
                id: parseInteger(item.querySelector('input[name="requisite_id"]')?.value),
                type_id: parseInteger(item.querySelector('input[name="requisite_type_id"]')?.value),
                value: value || null,
            });
        });
        return requisites;
    };

    const collectPayload = () => ({
        name_short: form.querySelector('input[name="name_short"]')?.value?.trim() || null,
        name_long: form.querySelector('textarea[name="name_long"]')?.value?.trim() || null,
        settlement_name: form.querySelector('input[name="settlement_name"]')?.value?.trim() || null,
        chief_name: form.querySelector('input[name="chief_name"]')?.value?.trim() || null,
        chief_post: form.querySelector('input[name="chief_post"]')?.value?.trim() || null,
        notes: form.querySelector('textarea[name="notes"]')?.value?.trim() || null,
        website: form.querySelector('input[name="website"]')?.value?.trim() || null,
        is_active: Boolean(form.querySelector('input[name="is_active"]')?.checked),
        is_university_department: Boolean(form.querySelector('input[name="is_university_department"]')?.checked),
        study_field_ids: gatherStudyFieldIds(),
        contacts: gatherContacts(),
        requisites: gatherRequisites(),
    });

    const readErrorMessage = async (response) => {
        try {
            const payload = await response.json();
            if (typeof payload?.detail === "string") {
                return payload.detail;
            }
            if (payload?.detail?.message) {
                const reasons = Array.isArray(payload.detail.reasons) ? payload.detail.reasons : [];
                return [payload.detail.message, ...reasons].join("\n");
            }
        } catch {
            return `Ошибка ${response.status}`;
        }
        return `Ошибка ${response.status}`;
    };

    const uploadLogoFile = async (file) => {
        const uploadUrl = form.dataset.uploadLogoUrl;
        if (!uploadUrl || !(file instanceof File)) {
            return;
        }
        if (logoMaxBytes > 0 && file.size > logoMaxBytes) {
            setStatus("Логотип превышает допустимый размер 1 МБ.", "error");
            if (logoFileInput instanceof HTMLInputElement) {
                logoFileInput.value = "";
            }
            return;
        }

        const formData = new FormData();
        formData.append("logo_file", file);

        if (uploadLogoTrigger instanceof HTMLButtonElement) {
            uploadLogoTrigger.disabled = true;
        }
        if (deleteLogoButton instanceof HTMLButtonElement) {
            deleteLogoButton.disabled = true;
        }
        setStatus("Загрузка логотипа...", "info");

        try {
            const response = await fetch(uploadUrl, {
                method: "POST",
                body: formData,
            });
            if (!response.ok) {
                throw new Error(await readErrorMessage(response));
            }

            const payload = await response.json();
            showToast(payload.message || "Логотип сохранён.", "success");
            window.location.reload();
        } catch (error) {
            setStatus(
                error instanceof Error ? error.message : "Не удалось сохранить логотип.",
                "error",
            );
        } finally {
            if (uploadLogoTrigger instanceof HTMLButtonElement) {
                uploadLogoTrigger.disabled = false;
            }
            if (deleteLogoButton instanceof HTMLButtonElement) {
                deleteLogoButton.disabled = false;
            }
            if (logoFileInput instanceof HTMLInputElement) {
                logoFileInput.value = "";
            }
        }
    };

    const toggleDocumentEditor = (visible) => {
        if (!(documentEditor instanceof HTMLElement)) {
            return;
        }
        documentEditor.hidden = !visible;
        syncDocumentEditorFieldsState();
        if (!visible) {
            resetDocumentEditorFields();
        }
    };

    const closeDocumentModal = () => {
        if (!(documentModal instanceof HTMLElement)) {
            return;
        }
        documentModal.hidden = true;
        documentModalState = null;
        if (documentModalPdfInput instanceof HTMLInputElement) {
            documentModalPdfInput.value = "";
        }
        resetDocumentModalPdfPicker();
        if (documentModalPdfUpload instanceof HTMLElement) {
            documentModalPdfUpload.hidden = false;
        }
        if (documentModalDeletePdfButton instanceof HTMLButtonElement) {
            documentModalDeletePdfButton.hidden = true;
            documentModalDeletePdfButton.disabled = false;
        }
        if (documentModalPdfLink instanceof HTMLAnchorElement) {
            documentModalPdfLink.hidden = true;
            documentModalPdfLink.href = "#";
            documentModalPdfLink.textContent = "Открыть текущий PDF";
        }
    };

    const openDocumentModal = (row) => {
        if (!(documentModal instanceof HTMLElement)) {
            return;
        }
        const state = readDocumentRowState(row);
        if (!state?.id || !state.updateUrl) {
            return;
        }
        documentModalState = state;

        if (documentModalTitle instanceof HTMLElement) {
            documentModalTitle.textContent = state.title || "Документ";
        }
        if (documentModalOrgName instanceof HTMLElement) {
            documentModalOrgName.textContent = getOrganizationDisplayName();
        }
        if (documentModalOrgAddress instanceof HTMLElement) {
            documentModalOrgAddress.textContent = getOrganizationDisplayAddress();
        }
        if (documentModalDatatype instanceof HTMLElement) {
            documentModalDatatype.textContent = state.datatypeLabel || "Не указан";
        }

        const primaryInput = form.querySelector('input[name="modal_document_name_primary"]');
        const secondaryInput = form.querySelector('input[name="modal_document_name_secondary"]');
        const signingDateInput = form.querySelector('input[name="modal_document_signing_date"]');
        const chiefNameInput = form.querySelector('input[name="modal_document_chief_name"]');
        const chiefPostInput = form.querySelector('input[name="modal_document_chief_post"]');
        const actualInput = form.querySelector('input[name="modal_document_is_actual"]');

        if (primaryInput instanceof HTMLInputElement) {
            primaryInput.value = state.namePrimary;
        }
        if (secondaryInput instanceof HTMLInputElement) {
            secondaryInput.value = state.nameSecondary;
        }
        if (signingDateInput instanceof HTMLInputElement) {
            signingDateInput.value = state.signingDate;
        }
        if (chiefNameInput instanceof HTMLInputElement) {
            chiefNameInput.value = state.chiefName;
        }
        if (chiefPostInput instanceof HTMLInputElement) {
            chiefPostInput.value = state.chiefPost;
        }
        if (actualInput instanceof HTMLInputElement) {
            actualInput.checked = Boolean(state.isActual);
        }
        resetDocumentModalPdfPicker();
        if (documentModalPdfUpload instanceof HTMLElement) {
            documentModalPdfUpload.hidden = Boolean(state.pdfUrl);
        }
        if (documentModalPdfLink instanceof HTMLAnchorElement) {
            documentModalPdfLink.hidden = !state.pdfUrl;
            documentModalPdfLink.href = state.pdfUrl || "#";
            documentModalPdfLink.textContent = state.pdfUrl
                ? `Открыть текущий PDF${state.pdfFilename ? ` (${state.pdfFilename})` : ""}`
                : "Открыть текущий PDF";
        }
        if (documentModalDeletePdfButton instanceof HTMLButtonElement) {
            documentModalDeletePdfButton.hidden = !state.pdfUrl;
            documentModalDeletePdfButton.disabled = false;
        }

        documentModal.hidden = false;
    };

    const syncCollapsibleSection = (section) => {
        const toggle = section.querySelector("[data-section-toggle]");
        const panel = section.querySelector("[data-section-panel]");
        const icon = toggle?.querySelector(".organization-section-toggle-icon");
        if (!toggle || !panel || !icon) {
            return;
        }
        const isExpanded = toggle.getAttribute("aria-expanded") === "true";
        panel.hidden = !isExpanded;
        icon.textContent = isExpanded ? "-" : "+";
    };

    document.querySelectorAll("[data-collapsible-section]").forEach((section) => {
        const toggle = section.querySelector("[data-section-toggle]");
        const panel = section.querySelector("[data-section-panel]");
        const icon = toggle?.querySelector(".organization-section-toggle-icon");
        if (!toggle || !panel || !icon) {
            return;
        }

        syncCollapsibleSection(section);

        toggle.addEventListener("click", () => {
            const isExpanded = toggle.getAttribute("aria-expanded") === "true";
            toggle.setAttribute("aria-expanded", String(!isExpanded));
            syncCollapsibleSection(section);
        });
    });

    mapButton?.addEventListener("click", () => {
        const mapQuery = getCurrentMapQuery();
        if (!mapQuery) {
            return;
        }
        const mapUrl = `https://yandex.ru/maps/?text=${encodeURIComponent(mapQuery)}`;
        window.open(mapUrl, "_blank", "noopener");
    });

    form.addEventListener("input", (event) => {
        if (!(event.target instanceof HTMLElement)) {
            return;
        }
        if (
            event.target.matches('input[name="settlement_name"]') ||
            event.target.matches("[data-requisite-value-input]")
        ) {
            updateMapButtonState();
        }
        if (event.target.matches("[data-create-required-inn]")) {
            validateCreateInn();
            if (event.target.value.trim()) {
                setStatus("");
            }
        }
        if (
            event.target.matches("[data-requisite-value-input]") &&
            event.target instanceof HTMLInputElement &&
            isInnRequisiteLabel(getRequisiteBaseLabel(event.target.closest(".organization-requisite-item"))) &&
            event.target.value.trim()
        ) {
            event.target.setCustomValidity("");
            setStatus("");
        }
    });

    form.addEventListener("reset", (event) => {
        event.preventDefault();
        window.location.reload();
    });

    logoFileInput?.addEventListener("change", async () => {
        if (!(logoFileInput instanceof HTMLInputElement)) {
            return;
        }
        const [file] = Array.from(logoFileInput.files || []);
        if (!file) {
            return;
        }
        await uploadLogoFile(file);
    });

    confirmModal?.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        if (target === confirmModal || target.closest("[data-confirm-cancel]")) {
            closeConfirmModal(false);
            return;
        }
        if (target.closest("[data-confirm-submit]")) {
            closeConfirmModal(true);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }
        if (documentModal instanceof HTMLElement && !documentModal.hidden) {
            event.preventDefault();
            closeDocumentModal();
            return;
        }
        if (!(confirmModal instanceof HTMLElement) || confirmModal.hidden) {
            return;
        }
        event.preventDefault();
        closeConfirmModal(false);
    });

    addContactButton?.addEventListener("click", () => {
        if (!(contactsTableBody instanceof HTMLElement)) {
            return;
        }
        const card = buildContactCard();
        contactsTableBody.appendChild(card);
        syncContactsEmptyState();
        card.querySelector('input[name="contact_name"]')?.focus();
    });

    contactsTableBody?.addEventListener("click", async (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        const addMethodButton = target.closest("[data-add-contact-method]");
        if (addMethodButton) {
            const card = addMethodButton.closest("[data-contact-card]");
            const methods = card?.querySelector("[data-contact-methods]");
            if (methods instanceof HTMLElement) {
                const row = buildContactMethodRow();
                methods.appendChild(row);
                row.querySelector("select")?.focus();
            }
            return;
        }

        const removeCardButton = target.closest("[data-remove-contact-card]");
        if (removeCardButton) {
            const card = removeCardButton.closest("[data-contact-card]");
            const shouldRemoveContact = await confirmAction({
                title: "Удалить контактное лицо?",
                message: "Контактное лицо и все его контактные данные будут удалены после сохранения изменений.",
                confirmLabel: "Удалить",
                tone: "danger",
            });
            if (!shouldRemoveContact) {
                return;
            }
            card?.remove();
            syncContactsEmptyState();
            return;
        }

        const removeButton = target.closest("[data-remove-contact-row]");
        if (!removeButton) {
            return;
        }
        const row = removeButton.closest("[data-contact-method-row]");
        const shouldRemoveContact = await confirmAction({
            title: "Удалить поле контакта?",
            message: "Поле контакта будет удалено после сохранения изменений.",
            confirmLabel: "Удалить",
            tone: "danger",
        });
        if (!shouldRemoveContact) {
            return;
        }
        row?.remove();
    });

    addStudyFieldButton?.addEventListener("click", () => {
        addStudyFieldFromSearch();
    });

    studyFieldSearch?.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") {
            return;
        }
        event.preventDefault();
        addStudyFieldFromSearch();
    });

    studyFieldSearch?.addEventListener("input", () => {
        if (studyFieldSearch instanceof HTMLInputElement) {
            studyFieldSearch.setCustomValidity("");
        }
    });

    studyFieldList?.addEventListener("click", async (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        const removeButton = target.closest("[data-remove-study-field]");
        if (!removeButton) {
            return;
        }
        const shouldRemove = await confirmAction({
            title: "Удалить направление?",
            message: "Направление будет удалено из карточки после сохранения изменений.",
            confirmLabel: "Удалить",
            tone: "danger",
        });
        if (!shouldRemove) {
            return;
        }
        removeButton.closest("[data-study-field-chip]")?.remove();
        syncStudyFieldsEmptyState();
        syncStudyFieldOptionsList();
    });

    addRequisiteButton?.addEventListener("click", () => {
        addSelectedRequisite();
    });

    requisiteTypeSelect?.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") {
            return;
        }
        event.preventDefault();
        addSelectedRequisite();
    });

    requisitesList?.addEventListener("click", async (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        const removeButton = target.closest("[data-remove-requisite]");
        if (!removeButton) {
            return;
        }
        const item = removeButton.closest(".organization-requisite-item");
        if (isInnRequisiteLabel(getRequisiteBaseLabel(item))) {
            return;
        }
        const shouldRemove = await confirmAction({
            title: "Удалить реквизит?",
            message: "Реквизит будет удалён из карточки после сохранения изменений.",
            confirmLabel: "Удалить",
            tone: "danger",
        });
        if (!shouldRemove) {
            return;
        }
        item?.remove();
        syncRequisiteTypeSelectOptions();
        updateMapButtonState();
    });

    requisitesList?.addEventListener("input", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLInputElement) || !target.matches("[data-requisite-other-title]")) {
            return;
        }
        const item = target.closest(".organization-requisite-item");
        if (!(item instanceof HTMLElement)) {
            return;
        }
        const labelNode = item.querySelector("[data-requisite-label-text]");
        if (!(labelNode instanceof HTMLElement)) {
            return;
        }
        const baseLabel = getRequisiteBaseLabel(item) || "Другое";
        const customLabel = target.value.trim();
        item.dataset.requisiteCustomLabel = customLabel;
        labelNode.textContent = customLabel ? `${baseLabel} (${customLabel})` : baseLabel;
    });

    syncStudyFieldsEmptyState();
    syncStudyFieldOptionsList();
    syncRequisiteTypeSelectOptions();
    syncDocumentEditorFieldsState();

    saveButton?.addEventListener("click", async () => {
        if (!form.dataset.saveUrl) {
            return;
        }
        if (typeof form.reportValidity === "function" && !form.reportValidity()) {
            return;
        }
        if (!validateCreateInn()) {
            return;
        }
        if (!validateInnRequisites()) {
            return;
        }
        saveButton.disabled = true;
        setStatus("");

        try {
            const response = await fetch(form.dataset.saveUrl, {
                method: createMode ? "POST" : "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(collectPayload()),
            });

            if (!response.ok) {
                throw new Error(await readErrorMessage(response));
            }

            const payload = await response.json();
            const successMessage = payload.message || "Изменения сохранены.";
            setStatus("");

            if (payload.redirect_url) {
                persistToastForRedirect(successMessage, "success");
                window.location.assign(payload.redirect_url);
                return;
            }
            showToast(successMessage, "success");
        } catch (error) {
            setStatus(error instanceof Error ? error.message : "Не удалось сохранить изменения.", "error");
        } finally {
            saveButton.disabled = false;
        }
    });

    addDocumentButton?.addEventListener("click", () => {
        if (createMode) {
            return;
        }
        const currentlyHidden = documentEditor instanceof HTMLElement ? documentEditor.hidden : true;
        toggleDocumentEditor(currentlyHidden);
    });

    cancelDocumentButton?.addEventListener("click", () => {
        toggleDocumentEditor(false);
    });

    closeDocumentModalButtons.forEach((button) => {
        button.addEventListener("click", () => {
            closeDocumentModal();
        });
    });

    documentModalPdfTrigger?.addEventListener("click", () => {
        if (documentModalPdfInput instanceof HTMLInputElement) {
            documentModalPdfInput.click();
        }
    });

    documentModalPdfInput?.addEventListener("change", () => {
        if (!(documentModalPdfInput instanceof HTMLInputElement) || !(documentModalPdfName instanceof HTMLElement)) {
            return;
        }
        const [file] = Array.from(documentModalPdfInput.files || []);
        documentModalPdfName.textContent = file?.name || "Файл не выбран";
    });

    submitDocumentButton?.addEventListener("click", async () => {
        if (!(submitDocumentButton instanceof HTMLButtonElement) || !form.dataset.addDocumentUrl) {
            return;
        }

        if (
            documentEditor instanceof HTMLElement
            && typeof documentEditor.querySelector("[data-document-required]")?.reportValidity === "function"
        ) {
            const invalidField = Array.from(
                documentEditor.querySelectorAll("[data-document-required]"),
            ).find((field) => (
                (field instanceof HTMLInputElement || field instanceof HTMLSelectElement)
                && !field.checkValidity()
            ));
            if (invalidField instanceof HTMLInputElement || invalidField instanceof HTMLSelectElement) {
                invalidField.reportValidity();
                return;
            }
        }

        const datatypeId = parseInteger(form.querySelector('select[name="document_datatype_id"]')?.value);
        const namePrimary = form.querySelector('input[name="document_name_primary"]')?.value?.trim() || null;
        const nameSecondary = form.querySelector('input[name="document_name_secondary"]')?.value?.trim() || null;
        const signingDate = form.querySelector('input[name="document_signing_date"]')?.value || null;
        const chiefName = form.querySelector('input[name="document_chief_name"]')?.value?.trim() || null;
        const chiefPost = form.querySelector('input[name="document_chief_post"]')?.value?.trim() || null;

        submitDocumentButton.disabled = true;
        setStatus("Сохранение документа...", "info");

        try {
            const response = await fetch(form.dataset.addDocumentUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    datatype_id: datatypeId,
                    name_primary: namePrimary,
                    name_secondary: nameSecondary,
                    signing_date: signingDate,
                    chief_name: chiefName,
                    chief_post: chiefPost,
                }),
            });

            if (!response.ok) {
                throw new Error(await readErrorMessage(response));
            }

            window.location.reload();
        } catch (error) {
            setStatus(error instanceof Error ? error.message : "Не удалось сохранить документ.", "error");
        } finally {
            submitDocumentButton.disabled = false;
        }
    });

    saveDocumentModalButton?.addEventListener("click", async () => {
        if (!(saveDocumentModalButton instanceof HTMLButtonElement) || !documentModalState?.updateUrl) {
            return;
        }

        const primaryInput = form.querySelector('input[name="modal_document_name_primary"]');
        const secondaryInput = form.querySelector('input[name="modal_document_name_secondary"]');
        const signingDateInput = form.querySelector('input[name="modal_document_signing_date"]');
        const chiefNameInput = form.querySelector('input[name="modal_document_chief_name"]');
        const chiefPostInput = form.querySelector('input[name="modal_document_chief_post"]');
        const actualInput = form.querySelector('input[name="modal_document_is_actual"]');
        const pdfFile =
            documentModalPdfInput instanceof HTMLInputElement
                ? Array.from(documentModalPdfInput.files || [])[0]
                : null;

        const formData = new FormData();
        formData.append("name_primary", primaryInput instanceof HTMLInputElement ? primaryInput.value.trim() : "");
        formData.append("name_secondary", secondaryInput instanceof HTMLInputElement ? secondaryInput.value.trim() : "");
        formData.append("chief_name", chiefNameInput instanceof HTMLInputElement ? chiefNameInput.value.trim() : "");
        formData.append("chief_post", chiefPostInput instanceof HTMLInputElement ? chiefPostInput.value.trim() : "");
        if (signingDateInput instanceof HTMLInputElement && signingDateInput.value) {
            formData.append("signing_date", signingDateInput.value);
        }
        formData.append(
            "is_actual",
            actualInput instanceof HTMLInputElement && actualInput.checked ? "true" : "false",
        );
        if (pdfFile instanceof File) {
            formData.append("pdf_file", pdfFile);
        }

        saveDocumentModalButton.disabled = true;
        setStatus("Сохранение документа...", "info");

        try {
            const response = await fetch(documentModalState.updateUrl, {
                method: "PUT",
                body: formData,
            });
            if (!response.ok) {
                throw new Error(await readErrorMessage(response));
            }
            window.location.reload();
        } catch (error) {
            setStatus(error instanceof Error ? error.message : "Не удалось сохранить документ.", "error");
        } finally {
            saveDocumentModalButton.disabled = false;
        }
    });

    documentModalDeletePdfButton?.addEventListener("click", async () => {
        if (
            !(documentModalDeletePdfButton instanceof HTMLButtonElement) ||
            !documentModalState?.deletePdfUrl
        ) {
            return;
        }

        const shouldDeletePdf = await confirmAction({
            title: "Удалить PDF",
            message: "PDF-файл будет удалён из документа.",
            confirmLabel: "Удалить",
            tone: "danger",
        });
        if (!shouldDeletePdf) {
            return;
        }

        documentModalDeletePdfButton.disabled = true;
        setStatus("Удаление PDF...", "info");

        try {
            const response = await fetch(documentModalState.deletePdfUrl, {
                method: "DELETE",
            });
            if (!response.ok) {
                throw new Error(await readErrorMessage(response));
            }
            window.location.reload();
        } catch (error) {
            setStatus(error instanceof Error ? error.message : "Не удалось удалить PDF.", "error");
            documentModalDeletePdfButton.disabled = false;
        }
    });

    form.addEventListener("click", async (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }

        if (target === documentModal) {
            closeDocumentModal();
            return;
        }

        const uploadLogoButton = target.closest("[data-upload-logo-trigger]");
        if (uploadLogoButton instanceof HTMLButtonElement) {
            if (logoFileInput instanceof HTMLInputElement) {
                logoFileInput.click();
            }
            return;
        }

        const archiveToggleButton = target.closest("[data-toggle-document-archive]");
        if (archiveToggleButton instanceof HTMLButtonElement) {
            const group = archiveToggleButton.closest("[data-document-group]");
            const archivePanel = group?.querySelector("[data-document-archive-panel]");
            if (!(archivePanel instanceof HTMLElement)) {
                return;
            }
            const isExpanded = archiveToggleButton.getAttribute("aria-expanded") === "true";
            archiveToggleButton.setAttribute("aria-expanded", String(!isExpanded));
            archivePanel.hidden = isExpanded;
            return;
        }

        const deleteLogoTrigger = target.closest("[data-delete-logo]");
        if (deleteLogoTrigger instanceof HTMLButtonElement) {
            const deleteLogoUrl = form.dataset.deleteLogoUrl;
            if (!deleteLogoUrl) {
                return;
            }
            const shouldDeleteLogo = await confirmAction({
                title: "Удалить логотип",
                message: "Логотип будет удалён из карточки организации.",
                confirmLabel: "Удалить",
                tone: "danger",
            });
            if (!shouldDeleteLogo) {
                return;
            }

            deleteLogoTrigger.disabled = true;
            if (uploadLogoTrigger instanceof HTMLButtonElement) {
                uploadLogoTrigger.disabled = true;
            }
            setStatus("Удаление логотипа...", "info");

            try {
                const response = await fetch(deleteLogoUrl, { method: "DELETE" });
                if (!response.ok) {
                    throw new Error(await readErrorMessage(response));
                }
                const payload = await response.json();
                ensureLogoPlaceholder();
                renderUploadLogoButton();
                deleteLogoTrigger.remove();
                setStatus("");
                showToast(payload.message || "Логотип удалён.", "success");
            } catch (error) {
                setStatus(
                    error instanceof Error ? error.message : "Не удалось удалить логотип.",
                    "error",
                );
                deleteLogoTrigger.disabled = false;
                if (uploadLogoTrigger instanceof HTMLButtonElement) {
                    uploadLogoTrigger.disabled = false;
                }
            }
            return;
        }

        if (deleteButton && target.closest("[data-delete-organization]")) {
            const deleteUrl = form.dataset.deleteUrl;
            if (!deleteUrl) {
                return;
            }
            const shouldDeleteOrganization = await confirmAction({
                title: "Удалить организацию",
                message: "Организация будет удалена без возможности восстановления, если её не блокируют связанные данные.",
                confirmLabel: "Удалить",
                tone: "danger",
            });
            if (!shouldDeleteOrganization) {
                return;
            }

            deleteButton.disabled = true;
            setStatus("Удаление организации...", "info");

            try {
                const response = await fetch(deleteUrl, { method: "DELETE" });
                if (!response.ok) {
                    throw new Error(await readErrorMessage(response));
                }
                window.location.assign("/organizations/active");
            } catch (error) {
                setStatus(error instanceof Error ? error.message : "Не удалось удалить организацию.", "error");
                deleteButton.disabled = false;
            }
        }
    });

    form.addEventListener("dblclick", (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        if (
            target.closest("[data-toggle-document-archive]") ||
            target.closest("button") ||
            target.closest("a") ||
            target.closest("input") ||
            target.closest("select") ||
            target.closest("textarea")
        ) {
            return;
        }
        const documentRow = target.closest("[data-document-row]");
        if (!(documentRow instanceof HTMLElement)) {
            return;
        }
        event.preventDefault();
        openDocumentModal(documentRow);
    });

    syncContactsEmptyState();
    updateMapButtonState();
    restoreToastFromRedirect();
})();

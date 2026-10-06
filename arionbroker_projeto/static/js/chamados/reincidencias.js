/* ==========================================================================
 * 1. INICIALIZAÇÃO
 * ========================================================================== */
(function () {
    "use strict";

    const rootElement = document.getElementById("rreipWrapper") || document.getElementById("rreipDetailsPage");
    if (!rootElement) return;

    if (rootElement.dataset.rreipGlobalInicializado === "true") return;
    rootElement.dataset.rreipGlobalInicializado = "true";

    window.RREIP = window.RREIP || {};

    /* ==========================================================================
     * 2. CONFIGURAÇÃO GLOBAL
     * ========================================================================== */
    function getRootElement() {
        return rootElement;
    }

    function getApiBase() {
        let base = rootElement.dataset.urlCriar || rootElement.dataset.urlDetalhes || "";
        if (base) {
            return base.replace(/\/(?:criar|\d+\/detalhes)\/?$/, "/");
        }
        return "/projetos/reincidencias/api/";
    }

    function isValidId(id) {
        const num = Number(id);
        return Number.isInteger(num) && num > 0;
    }

    function buildEndpoint(id, action) {
        if (!isValidId(id)) return "";
        const base = getApiBase();
        const actionNorm = String(action || "").replace(/^\/+|\/+$/g, "");
        const baseNorm = base.endsWith("/") ? base : `${base}/`;
        return `${baseNorm}${id}/${actionNorm}/`;
    }

    /* ==========================================================================
     * 3. CSRF
     * ========================================================================== */
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== "") {
            const cookies = document.cookie.split(";");
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + "=")) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function getCsrfToken() {
        if (window.ArionBroker && typeof window.ArionBroker.getCsrf === "function") {
            return window.ArionBroker.getCsrf();
        }
        const inputGlobal = document.getElementById("global-csrf");
        if (inputGlobal) return inputGlobal.value;

        const inputForm = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (inputForm) return inputForm.value;

        return getCookie("csrftoken");
    }

    /* ==========================================================================
     * 4. ERRO DE API
     * ========================================================================== */
    class ApiError extends Error {
        constructor(message, status = 0, data = null) {
            super(message);
            this.name = "ApiError";
            this.status = status;
            this.data = data;
        }
    }

    function getFriendlyErrorMessage(status) {
        switch (status) {
            case 400: return "Dados inválidos ou operação não permitida.";
            case 401: return "Sessão expirada. Por favor, faça login novamente.";
            case 403: return "Você não tem permissão para executar esta ação.";
            case 404: return "Registro não encontrado.";
            case 405: return "Método não permitido.";
            case 409: return "Conflito de dados. O registro pode ter sido alterado.";
            case 422: return "Erro de validação nos dados fornecidos.";
            case 500: return "Erro interno do servidor. Tente novamente mais tarde.";
            case 0: return "Falha de comunicação com o servidor. Verifique sua conexão.";
            default: return "Ocorreu um erro inesperado.";
        }
    }

    /* ==========================================================================
     * 5. REQUEST API
     * ========================================================================== */
    async function requestApi(url, options = {}) {
        const method = (options.method || "GET").toUpperCase();
        const expectJson = options.expectJson !== false;

        const fetchOptions = {
            method,
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                ...options.headers
            },
            signal: options.signal
        };

        if (method !== "GET" && method !== "HEAD") {
            const csrf = getCsrfToken();
            if (csrf) fetchOptions.headers["X-CSRFToken"] = csrf;
        }

        if (options.body) {
            if (typeof options.body === "object" && !(options.body instanceof FormData)) {
                if (fetchOptions.headers["Content-Type"] === "application/json") {
                    fetchOptions.body = JSON.stringify(options.body);
                } else {
                    const formData = new FormData();
                    for (const key in options.body) {
                        if (Object.prototype.hasOwnProperty.call(options.body, key)) {
                            formData.append(key, options.body[key]);
                        }
                    }
                    fetchOptions.body = formData;
                }
            } else {
                fetchOptions.body = options.body;
            }
        }

        let response;
        try {
            response = await fetch(url, fetchOptions);
        } catch (error) {
            throw new ApiError(getFriendlyErrorMessage(0), 0);
        }

        if (!expectJson && response.ok) {
            return response;
        }

        let data;
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
            try {
                data = await response.json();
            } catch (error) {
                throw new ApiError("A resposta do servidor não é válida.", response.status);
            }
        } else if (!response.ok) {
            data = {};
        } else {
            return null;
        }

        if (!response.ok || data.ok === false) {
            const errorMsg = data.erro || data.mensagem || data.detail || getFriendlyErrorMessage(response.status);
            throw new ApiError(errorMsg, response.status, data);
        }

        return data;
    }

    /* ==========================================================================
     * 6. TOASTS
     * ========================================================================== */
    let toastContainer = document.getElementById("rreipToastContainer");

    function ensureToastContainer() {
        if (!toastContainer) {
            toastContainer = document.createElement("div");
            toastContainer.id = "rreipToastContainer";
            toastContainer.className = "rreip-toast-container";
            toastContainer.setAttribute("aria-live", "polite");
            document.body.appendChild(toastContainer);
        }
        return toastContainer;
    }

    function showToast(message, type = "info", options = {}) {
        const container = ensureToastContainer();
        const duration = options.duration || 5000;
        const persistent = options.persistent || false;

        const toast = document.createElement("div");
        toast.className = `rreip-toast rreip-toast--${type}`;
        toast.setAttribute("role", type === "error" ? "alert" : "status");

        const textSpan = document.createElement("span");
        textSpan.textContent = message;
        toast.appendChild(textSpan);

        if (persistent) {
            const closeBtn = document.createElement("button");
            closeBtn.innerHTML = "&times;";
            closeBtn.style.background = "none";
            closeBtn.style.border = "none";
            closeBtn.style.color = "inherit";
            closeBtn.style.cursor = "pointer";
            closeBtn.style.marginLeft = "10px";
            closeBtn.style.fontSize = "16px";
            closeBtn.addEventListener("click", () => removeToast(toast));
            toast.appendChild(closeBtn);
        }

        container.appendChild(toast);

        // Reflow para a animação
        void toast.offsetWidth;
        toast.classList.add("rreip-toast--show");

        if (!persistent) {
            setTimeout(() => removeToast(toast), duration);
        }
    }

    function removeToast(toast) {
        toast.classList.remove("rreip-toast--show");
        toast.addEventListener("transitionend", () => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        });
    }

    /* ==========================================================================
     * 7. LOADING
     * ========================================================================== */
    function setLoading(button, loading, loadingText = "Processando...") {
        if (!button) return;
        if (loading) {
            if (!button.dataset.originalContent) {
                button.dataset.originalContent = button.innerHTML;
            }
            const wasDisabled = button.hasAttribute("disabled");
            if (wasDisabled && !button.dataset.disabledBeforeLoading) {
                button.dataset.disabledBeforeLoading = "true";
            }
            button.disabled = true;
            button.classList.add("is-loading");
            button.innerHTML = `<span class="rreip-btn-spinner"></span> ${loadingText}`;
        } else {
            button.classList.remove("is-loading");
            if (button.dataset.originalContent) {
                button.innerHTML = button.dataset.originalContent;
                delete button.dataset.originalContent;
            }
            if (button.dataset.disabledBeforeLoading === "true") {
                button.disabled = true;
                delete button.dataset.disabledBeforeLoading;
            } else {
                button.disabled = false;
            }
        }
    }

    function setFormLoading(form, loading, loadingText = "Salvando...") {
        if (!form) return;
        const submitBtn = form.querySelector('button[type="submit"]');
        setLoading(submitBtn, loading, loadingText);

        const inputs = form.querySelectorAll('input, select, textarea, button');
        inputs.forEach(el => {
            if (el !== submitBtn) {
                if (loading) {
                    if (el.disabled) el.dataset.disabledBeforeLoading = "true";
                    el.disabled = true;
                } else {
                    if (!el.dataset.disabledBeforeLoading) el.disabled = false;
                    delete el.dataset.disabledBeforeLoading;
                }
            }
        });
    }

    function setContainerLoading(container, loading) {
        if (!container) return;
        if (loading) {
            container.classList.add("is-loading");
            container.style.opacity = "0.5";
            container.style.pointerEvents = "none";
        } else {
            container.classList.remove("is-loading");
            container.style.opacity = "";
            container.style.pointerEvents = "";
        }
    }

    /* ==========================================================================
     * 8. MODAIS
     * ========================================================================== */
    let openModalElement = null;
    let elementThatOpenedModal = null;

    function openModal(id) {
        const modal = document.getElementById(id);
        if (!modal) return;

        elementThatOpenedModal = document.activeElement;
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
        openModalElement = modal;

        const focusable = modal.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (focusable) focusable.focus();

        emit("rreip:modal-opened", { id });
    }

    function closeModal(id) {
        const modal = document.getElementById(id);
        if (!modal) return;

        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");

        const stillOpen = document.querySelector(".rreip-modal-overlay.is-open");
        if (!stillOpen) {
            document.body.style.overflow = "";
            openModalElement = null;
        } else {
            openModalElement = stillOpen;
        }

        if (elementThatOpenedModal && !stillOpen) {
            elementThatOpenedModal.focus();
            elementThatOpenedModal = null;
        }

        emit("rreip:modal-closed", { id });
    }

    function closeAllModals() {
        document.querySelectorAll(".rreip-modal-overlay.is-open").forEach(modal => {
            closeModal(modal.id);
        });
    }

    function getOpenModal() {
        return openModalElement;
    }

    // Delegação de fechamento no overlay ou click no botão data-close-modal
    document.addEventListener("click", (event) => {
        const closeButton = event.target.closest("[data-close-modal]");
        if (closeButton) {
            closeModal(closeButton.dataset.closeModal);
            return;
        }
        if (event.target.classList.contains("rreip-modal-overlay")) {
            closeModal(event.target.id);
        }
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && openModalElement) {
            closeModal(openModalElement.id);
        }
    });

    /* ==========================================================================
     * 9. CONFIRMAÇÃO
     * ========================================================================== */
    function showConfirm(message, options = {}) {
        return new Promise((resolve) => {
            const modal = document.getElementById("rreipConfirmModal");
            if (!modal) {
                // Fallback de segurança 
                resolve(window.confirm(message));
                return;
            }

            const titleEl = document.getElementById("rreipConfirmTitle");
            const msgEl = document.getElementById("rreipConfirmMessage");
            const btnAccept = document.getElementById("rreipConfirmAccept");
            const btnCancel = document.getElementById("rreipConfirmCancel");

            titleEl.textContent = options.title || "Confirmar ação";
            msgEl.textContent = message;
            btnAccept.textContent = options.confirmText || "Confirmar";
            btnCancel.textContent = options.cancelText || "Cancelar";

            if (options.danger) {
                btnAccept.className = "rreip-btn rreip-btn--danger";
            } else {
                btnAccept.className = "rreip-btn rreip-btn--primary";
            }

            const cleanup = (result) => {
                closeModal("rreipConfirmModal");
                btnAccept.removeEventListener("click", onAccept);
                btnCancel.removeEventListener("click", onCancel);
                resolve(result);
            };

            const onAccept = () => cleanup(true);
            const onCancel = () => cleanup(false);

            btnAccept.addEventListener("click", onAccept);
            btnCancel.addEventListener("click", onCancel);

            openModal("rreipConfirmModal");
        });
    }

    /* ==========================================================================
     * 10. FORMULÁRIOS E ERROS
     * ========================================================================== */
    function getField(form, name) {
        return form.querySelector(`[name="${name}"]`);
    }

    function getValue(form, name) {
        const field = getField(form, name);
        if (!field) return null;
        if (field.type === "checkbox" || field.type === "radio") return field.checked ? field.value : null;
        return field.value;
    }

    function setValue(elementOrId, value) {
        let el = typeof elementOrId === "string" ? document.getElementById(elementOrId) : elementOrId;
        if (!el) return;
        if (el.type === "checkbox" || el.type === "radio") {
            el.checked = !!value;
        } else {
            el.value = value || "";
        }
    }

    function resetFormErrors(form) {
        form.querySelectorAll(".rreip-form-error").forEach(el => el.remove());
        form.querySelectorAll('[aria-invalid="true"]').forEach(el => el.removeAttribute("aria-invalid"));
        const summary = form.querySelector("[data-form-error-summary]");
        if (summary) {
            summary.hidden = true;
            summary.textContent = "";
        }
    }

    function showFieldError(field, message) {
        if (!field) return;
        field.setAttribute("aria-invalid", "true");
        let errorEl = field.parentNode.querySelector(".rreip-form-error");
        if (!errorEl) {
            errorEl = document.createElement("div");
            errorEl.className = "rreip-form-error";
            field.parentNode.appendChild(errorEl);
        }
        errorEl.textContent = message;
    }

    function applyApiErrors(form, error) {
        resetFormErrors(form);
        if (!error || !error.data) return;

        const fields = error.data.campos || error.data.errors || (error.data.dados && error.data.dados.campos);

        if (fields && typeof fields === "object") {
            let firstInvalid = null;
            for (const [fieldName, messages] of Object.entries(fields)) {
                const field = getField(form, fieldName);
                if (field) {
                    const msgText = Array.isArray(messages) ? messages[0] : messages;
                    showFieldError(field, msgText);
                    if (!firstInvalid) firstInvalid = field;
                }
            }
            if (firstInvalid) firstInvalid.focus();
        }

        const summary = form.querySelector("[data-form-error-summary]");
        if (summary && error.message) {
            summary.textContent = error.message;
            summary.hidden = false;
        }
    }

    function serializeForm(form) {
        const formData = new FormData(form);
        const data = {};
        formData.forEach((value, key) => {
            data[key] = value;
        });
        return data;
    }

    /* ==========================================================================
     * 11. DATAS
     * ========================================================================== */
    function toDatetimeLocal(value) {
        if (!value) return "";
        const d = new Date(value);
        if (isNaN(d.getTime())) return "";
        d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
        return d.toISOString().slice(0, 16);
    }

    function formatDateTime(value) {
        if (!value) return "";
        const d = new Date(value);
        if (isNaN(d.getTime())) return "";
        return d.toLocaleString("pt-BR", {
            day: "2-digit", month: "2-digit", year: "numeric",
            hour: "2-digit", minute: "2-digit"
        });
    }

    function formatDate(value) {
        if (!value) return "";
        const d = new Date(value);
        if (isNaN(d.getTime())) return "";
        return d.toLocaleDateString("pt-BR");
    }

    /* ==========================================================================
     * 12. CLIPBOARD
     * ========================================================================== */
    function copyText(text, successMessage = "Texto copiado com sucesso.") {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text)
                .then(() => showToast(successMessage, "success"))
                .catch(() => fallbackCopyText(text, successMessage));
        } else {
            fallbackCopyText(text, successMessage);
        }
    }

    function fallbackCopyText(text, successMessage) {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.style.position = "fixed";
        textArea.style.top = "-9999px";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            document.execCommand("copy");
            showToast(successMessage, "success");
        } catch (err) {
            showToast("Erro ao copiar o texto para a área de transferência.", "error");
        }
        document.body.removeChild(textArea);
    }

    /* ==========================================================================
     * 13. RESUMO
     * ========================================================================== */
    function updateSummary(summaryObj) {
        if (!summaryObj) return;
        const elements = document.querySelectorAll("[data-summary-key]");
        elements.forEach(el => {
            const key = el.dataset.summaryKey;
            if (summaryObj[key] !== undefined) {
                el.textContent = summaryObj[key];
            }
        });
        emit("rreip:summary-updated", { summary: summaryObj });
    }

    async function refreshSummary() {
        const url = rootElement.dataset.urlResumo;
        if (!url) return;
        try {
            const response = await requestApi(url);
            if (response && response.dados) {
                updateSummary(response.dados);
            }
        } catch (error) {
            console.error("RREIP: Erro ao recarregar os dados do resumo numérico.", error);
        }
    }

    /* ==========================================================================
     * 14. CHECKBOXES (SELEÇÃO DA TABELA)
     * ========================================================================== */
    function initRowSelection() {
        const selectAll = document.getElementById("rreipSelectAll");
        if (selectAll) {
            selectAll.addEventListener("change", (e) => {
                document.querySelectorAll(".rreip-row-checkbox").forEach(cb => {
                    cb.checked = e.target.checked;
                    updateRowClass(cb);
                });
                updateSelectedCount();
            });
        }

        document.addEventListener("change", (e) => {
            if (e.target.classList.contains("rreip-row-checkbox")) {
                updateRowClass(e.target);
                updateSelectedCount();
            }
        });
    }

    function updateRowClass(checkbox) {
        const tr = checkbox.closest("tr");
        if (tr) {
            if (checkbox.checked) tr.classList.add("is-selected");
            else tr.classList.remove("is-selected");
        }
    }

    function updateSelectedCount() {
        const checkboxes = document.querySelectorAll(".rreip-row-checkbox");
        const checked = document.querySelectorAll(".rreip-row-checkbox:checked");
        const selectAll = document.getElementById("rreipSelectAll");
        const counter = document.getElementById("rreipSelectedCount");

        if (selectAll && checkboxes.length > 0) {
            selectAll.checked = (checked.length === checkboxes.length);
            selectAll.indeterminate = (checked.length > 0 && checked.length < checkboxes.length);
        }

        if (counter) {
            if (checked.length > 0) {
                counter.textContent = `${checked.length} selecionado(s)`;
                counter.hidden = false;
            } else {
                counter.hidden = true;
            }
        }
        emit("rreip:selection-changed", { count: checked.length });
    }

    function getSelectedIds() {
        const checked = document.querySelectorAll(".rreip-row-checkbox:checked");
        return Array.from(checked).map(cb => cb.value || cb.dataset.id);
    }

    function clearSelection() {
        document.querySelectorAll(".rreip-row-checkbox:checked").forEach(cb => {
            cb.checked = false;
            updateRowClass(cb);
        });
        updateSelectedCount();
    }

    /* ==========================================================================
     * 15. FILTROS MOBILE
     * ========================================================================== */
    function initFilterToggle() {
        const btn = document.getElementById("btnToggleFiltros");
        const body = document.getElementById("rreipFiltersBody");

        if (btn && body) {
            btn.addEventListener("click", () => {
                const isExpanded = btn.getAttribute("aria-expanded") === "true";
                btn.setAttribute("aria-expanded", !isExpanded);
                if (!isExpanded) {
                    body.classList.remove("is-collapsed");
                } else {
                    body.classList.add("is-collapsed");
                }
            });
        }
    }

    /* ==========================================================================
     * 16. BOTÃO ATUALIZAR
     * ========================================================================== */
    function initRefreshButton() {
        const btn = document.getElementById("btnAtualizarLista");
        if (btn) {
            btn.addEventListener("click", () => {
                setLoading(btn, true, "Atualizando...");
                window.location.reload();
            });
        }
    }

    /* ==========================================================================
     * 17. UTILITÁRIOS DE DADOS E FORMATAÇÃO
     * ========================================================================== */
    function unwrapResponse(response) {
        if (!response) return {};
        let payload = response;
        if (response.dados) payload = response.dados;
        if (payload.reincidencia) payload = payload.reincidencia;
        return payload;
    }

    function escapeText(value) {
        const div = document.createElement("div");
        div.textContent = value;
        return div.innerHTML;
    }

    function textOrDash(value) {
        if (value === null || value === undefined || String(value).trim() === "") {
            return "—";
        }
        return value;
    }

    function normalizeString(value) {
        return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
    }

    /* ==========================================================================
     * 18. DETALHES COMPARTILHADOS
     * ========================================================================== */
    async function loadDetails(id) {
        const url = buildEndpoint(id, "detalhes");
        const res = await requestApi(url);
        return unwrapResponse(res);
    }

    async function loadHistory(id) {
        const url = buildEndpoint(id, "historico");
        const res = await requestApi(url);
        return res.dados ? res.dados.historico || [] : [];
    }

    /* ==========================================================================
     * 19. USUÁRIOS
     * ========================================================================== */
    let usersCache = null;

    async function loadUsers(force = false) {
        if (usersCache && !force) return usersCache;
        const url = rootElement.dataset.urlUsuarios;
        if (!url) return [];

        try {
            const res = await requestApi(url);
            usersCache = res.dados || [];
            return usersCache;
        } catch (error) {
            console.error("RREIP: Falha ao carregar a lista de usuários responsáveis.", error);
            return [];
        }
    }

    /* ==========================================================================
     * 20. PROJETOS POR OPERADORA E IDENTIFICADORES
     * ========================================================================== */

    const PROJETOS_POR_OPERADORA = {
        Claro: [
            "Bradesco",
            "Banco do Brasil",
            "Caixa Econômica",
            "Correios",
            "Carrefour",
            "Diversos"
        ],
        Vivo: [
            "Bradesco",
            "McDonald's",
            "L2L",
            "Diversos"
        ],
        Algar: [
            "Escolas Conectadas"
        ],
        Outros: [
            "Diversos"
        ]
    };

    /*
     * Mantém compatibilidade caso algum outro arquivo específico já tenha
     * acrescentado projetos ao objeto global antes do carregamento deste core.
     */
    window.RREIP.PROJETOS_POR_OPERADORA = {
        ...PROJETOS_POR_OPERADORA,
        ...(window.RREIP.PROJETOS_POR_OPERADORA || {})
    };

    function getProjectsByOperator(operator) {
        const operatorValue = String(operator || "").trim();

        if (!operatorValue) {
            return [];
        }

        return (
            window.RREIP.PROJETOS_POR_OPERADORA[operatorValue] ||
            window.RREIP.PROJETOS_POR_OPERADORA.Outros ||
            []
        );
    }

    function fillProjectSelect(select, operator, selectedValue = "") {
        if (!select) return;

        const currentValue = selectedValue || select.value || "";
        const projects = getProjectsByOperator(operator);

        select.innerHTML = "";

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = operator
            ? "Selecione o projeto"
            : "Selecione a operadora primeiro";
        select.appendChild(placeholder);

        projects.forEach(project => {
            const option = document.createElement("option");
            option.value = project;
            option.textContent = project;
            option.selected = project === currentValue;
            select.appendChild(option);
        });

        /*
         * Em uma edição, preserva um projeto antigo que ainda não esteja
         * cadastrado na relação atual.
         */
        if (
            currentValue &&
            !projects.includes(currentValue)
        ) {
            const legacyOption = document.createElement("option");
            legacyOption.value = currentValue;
            legacyOption.textContent = currentValue;
            legacyOption.selected = true;
            select.appendChild(legacyOption);
        }

        select.disabled = !operator;
    }

    function updateIdentifierLabel(project, operator) {
        const projectNormalized = normalizeString(project);
        const operatorNormalized = normalizeString(operator);

        if (projectNormalized.includes("bradesco")) {
            return "BRAD";
        }

        if (
            projectNormalized.includes("mcdonald") ||
            projectNormalized.includes("arcos dourado") ||
            projectNormalized.includes("arcosdourado")
        ) {
            return "SIGLA";
        }

        if (
            projectNormalized.includes("banco do brasil") ||
            projectNormalized === "bb"
        ) {
            return "CI";
        }

        if (
            projectNormalized.includes("correios") ||
            projectNormalized.includes("caixa") ||
            projectNormalized.includes("carrefour") ||
            projectNormalized.includes("escolas conectadas") ||
            projectNormalized.includes("l2l") ||
            operatorNormalized.includes("claro") ||
            operatorNormalized.includes("vivo") ||
            operatorNormalized.includes("algar")
        ) {
            return "CI";
        }

        return "CI";
    }

    function updateProjectIdentifierElements(prefix) {
        const operatorSelect = document.getElementById(`${prefix}Operadora`);
        const projectSelect = document.getElementById(`${prefix}Projeto`);
        const identifierLabel = document.getElementById(`${prefix}IdentificadorLabel`);
        const identifierInput = document.getElementById(`${prefix}Identificador`);

        if (!projectSelect) return;

        const label = updateIdentifierLabel(
            projectSelect.value,
            operatorSelect ? operatorSelect.value : ""
        );

        if (identifierLabel) {
            identifierLabel.textContent = label;
        }

        if (identifierInput) {
            identifierInput.placeholder = `Informe a(o) ${label}`;
        }
    }

    function bindProjectDependency(prefix) {
        const operatorSelect = document.getElementById(`${prefix}Operadora`);
        const projectSelect = document.getElementById(`${prefix}Projeto`);

        if (!operatorSelect || !projectSelect) {
            return;
        }

        /*
         * Evita registrar duas vezes os eventos quando a página ou algum JS
         * específico também chama esta inicialização.
         */
        if (operatorSelect.dataset.rreipProjectsBound !== "true") {
            operatorSelect.dataset.rreipProjectsBound = "true";

            operatorSelect.addEventListener("change", () => {
                fillProjectSelect(projectSelect, operatorSelect.value, "");
                updateProjectIdentifierElements(prefix);
            });
        }

        if (projectSelect.dataset.rreipIdentifierBound !== "true") {
            projectSelect.dataset.rreipIdentifierBound = "true";

            projectSelect.addEventListener("change", () => {
                updateProjectIdentifierElements(prefix);
            });
        }

        fillProjectSelect(
            projectSelect,
            operatorSelect.value,
            projectSelect.value
        );

        updateProjectIdentifierElements(prefix);
    }

    function initProjectDependencies() {
        /*
         * IDs usados pelos templates atuais.
         */
        [
            "rreipNovo",
            "rreipEditar"
        ].forEach(bindProjectDependency);

        /*
         * Compatibilidade com a versão anterior do formulário.
         */
        const oldOperatorSelect = document.getElementById("rreipFormOperadora");
        const oldProjectSelect = document.getElementById("rreipFormProjeto");

        if (oldOperatorSelect && oldProjectSelect) {
            if (oldOperatorSelect.dataset.rreipProjectsBound !== "true") {
                oldOperatorSelect.dataset.rreipProjectsBound = "true";

                oldOperatorSelect.addEventListener("change", () => {
                    fillProjectSelect(
                        oldProjectSelect,
                        oldOperatorSelect.value,
                        ""
                    );

                    const oldLabel = document.getElementById(
                        "rreipFormIdentificadorLabel"
                    );

                    const oldInput = document.getElementById(
                        "rreipFormIdentificador"
                    );

                    const label = updateIdentifierLabel(
                        oldProjectSelect.value,
                        oldOperatorSelect.value
                    );

                    if (oldLabel) oldLabel.textContent = label;
                    if (oldInput) {
                        oldInput.placeholder = `Informe a(o) ${label}`;
                    }
                });
            }

            if (oldProjectSelect.dataset.rreipIdentifierBound !== "true") {
                oldProjectSelect.dataset.rreipIdentifierBound = "true";

                oldProjectSelect.addEventListener("change", () => {
                    const oldLabel = document.getElementById(
                        "rreipFormIdentificadorLabel"
                    );

                    const oldInput = document.getElementById(
                        "rreipFormIdentificador"
                    );

                    const label = updateIdentifierLabel(
                        oldProjectSelect.value,
                        oldOperatorSelect.value
                    );

                    if (oldLabel) oldLabel.textContent = label;
                    if (oldInput) {
                        oldInput.placeholder = `Informe a(o) ${label}`;
                    }
                });
            }

            fillProjectSelect(
                oldProjectSelect,
                oldOperatorSelect.value,
                oldProjectSelect.value
            );
        }
    }

    /* ==========================================================================
     * 21. EVENTOS CUSTOMIZADOS
     * ========================================================================== */
    function getActionData(event) {
        const btn = event.target.closest("[data-action]");
        if (!btn) return null;
        return {
            action: btn.dataset.action,
            id: btn.dataset.id,
            button: btn
        };
    }

    function emit(name, detail = {}) {
        document.dispatchEvent(new CustomEvent(name, { detail }));
    }

    /* ==========================================================================
     * 23. API PÚBLICA
     * ========================================================================== */
    Object.assign(window.RREIP, {
        // Classes e Requisições
        ApiError,
        requestApi,

        // Componentes UI
        showToast,
        setLoading,
        setFormLoading,
        setContainerLoading,
        openModal,
        closeModal,
        closeAllModals,
        showConfirm,

        // Utilitários de Formulários
        getField,
        getValue,
        setValue,
        resetFormErrors,
        showFieldError,
        applyApiErrors,
        serializeForm,

        // Formatação
        toDatetimeLocal,
        formatDateTime,
        formatDate,
        copyText,
        unwrapResponse,
        textOrDash,
        normalizeString,

        // Funções de Resumo
        updateSummary,
        refreshSummary,

        // Tabelas
        getSelectedIds,
        clearSelection,

        // Requisições Específicas
        loadDetails,
        loadHistory,
        loadUsers,

        // Utilitários Internos
        buildEndpoint,
        isValidId,
        getRootElement,
        getApiBase,
        PROJETOS_POR_OPERADORA: window.RREIP.PROJETOS_POR_OPERADORA,
        getProjectsByOperator,
        fillProjectSelect,
        updateIdentifierLabel,
        updateProjectIdentifierElements,
        bindProjectDependency,
        initProjectDependencies,

        // Eventos
        emit,
        getActionData
    });

    /* ==========================================================================
     * 26. INICIALIZAÇÃO FINAL
     * ========================================================================== */
    initRowSelection();
    initFilterToggle();
    initRefreshButton();
    initProjectDependencies();

    // Tenta carregar o resumo de forma silenciosa apenas se houver endpoint
    if (rootElement.dataset.urlResumo) {
        refreshSummary();
    }

})();
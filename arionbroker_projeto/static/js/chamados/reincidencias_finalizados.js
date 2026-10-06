/* ==========================================================================
 * reincidencias_finalizados.js
 * Fila de Finalizados — Módulo RREIP
 *
 * Responsabilidades:
 * - reabrir registro finalizado para Tratamento;
 * - transferir responsável;
 * - excluir definitivamente registros criados por engano;
 * - controlar carregamento, validações, confirmações e mensagens;
 * - preservar compatibilidade com o core window.RREIP.
 * ========================================================================== */

(function () {
    "use strict";

    /* ==========================================================================
     * 1. Inicialização
     * ========================================================================== */

    const wrapper = document.getElementById("rreipWrapper");

    if (!wrapper) {
        return;
    }

    if (wrapper.dataset.filaAtual !== "FINALIZADO") {
        return;
    }

    if (!window.RREIP) {
        console.error("Core RREIP não carregado.");
        return;
    }

    if (wrapper.dataset.finalizadosJsInicializado === "true") {
        return;
    }

    wrapper.dataset.finalizadosJsInicializado = "true";


    /* ==========================================================================
     * 2. Referências
     * ========================================================================== */

    const formReabrir = document.getElementById("rreipFormReabrirFinalizado");
    const formTransferir = document.getElementById("rreipFormTransferir");

    const modalReabrir = document.getElementById("rreipModalReabrirFinalizado");
    const modalTransferir = document.getElementById("rreipModalTransferir");

    const campoReabrirId = document.getElementById("rreipReabrirFinalizadoId");
    const campoReabrirMotivo = document.getElementById("rreipReabrirFinalizadoMotivo");

    const campoTransferirId = document.getElementById("rreipTransferirId");
    const campoTransferirUsuario = document.getElementById("rreipTransferirUsuario");


    /* ==========================================================================
     * 3. Atalhos seguros para o core
     * ========================================================================== */

    const requestApi = window.RREIP.requestApi;
    const showToast = window.RREIP.showToast;
    const showConfirm = window.RREIP.showConfirm;
    const openModal = window.RREIP.openModal;
    const closeModal = window.RREIP.closeModal;

    function buildEndpoint(id, action) {
        if (typeof window.RREIP.buildEndpoint === "function") {
            return window.RREIP.buildEndpoint(id, action);
        }

        const urlCriar = wrapper.dataset.urlCriar || "";
        const apiBase = urlCriar
            ? urlCriar.replace(/criar\/?$/, "")
            : "/chamados/reincidencias/api/";

        return `${apiBase}${id}/${action}/`;
    }

    function setValue(elementOrId, value) {
        const element = typeof elementOrId === "string"
            ? document.getElementById(elementOrId)
            : elementOrId;

        if (!element) {
            return;
        }

        element.value = value === null || value === undefined ? "" : String(value);
    }

    function getValue(form, name) {
        if (!form) {
            return "";
        }

        const field = form.querySelector(`[name="${name}"]`);

        if (!field) {
            return "";
        }

        if (field.type === "checkbox") {
            return field.checked;
        }

        return typeof field.value === "string"
            ? field.value.trim()
            : field.value;
    }

    function resetFormErrors(form) {
        if (!form) {
            return;
        }

        if (typeof window.RREIP.resetFormErrors === "function") {
            window.RREIP.resetFormErrors(form);
            return;
        }

        form.querySelectorAll("[aria-invalid]").forEach((field) => {
            field.removeAttribute("aria-invalid");
        });

        form.querySelectorAll(".rreip-form-error").forEach((error) => {
            error.remove();
        });

        const summary = form.querySelector("[data-form-error-summary]");

        if (summary) {
            summary.hidden = true;
            summary.textContent = "";
        }
    }

    function applyApiErrors(form, error) {
        if (typeof window.RREIP.applyApiErrors === "function") {
            window.RREIP.applyApiErrors(form, error);
            return;
        }

        resetFormErrors(form);

        const responseData = error?.data || {};
        const fieldErrors = responseData.campos || responseData.errors || null;
        let firstInvalidField = null;

        if (fieldErrors && typeof fieldErrors === "object") {
            Object.entries(fieldErrors).forEach(([name, messages]) => {
                const field = form?.querySelector(`[name="${name}"]`);

                if (!field) {
                    return;
                }

                const message = Array.isArray(messages)
                    ? messages[0]
                    : messages;

                field.setAttribute("aria-invalid", "true");

                const errorElement = document.createElement("div");
                errorElement.className = "rreip-form-error";
                errorElement.textContent = String(message || "Valor inválido.");

                field.insertAdjacentElement("afterend", errorElement);

                if (!firstInvalidField) {
                    firstInvalidField = field;
                }
            });
        }

        if (firstInvalidField) {
            firstInvalidField.focus();
            return;
        }

        const summary = form?.querySelector("[data-form-error-summary]");
        const message = error?.message || "Não foi possível concluir a operação.";

        if (summary) {
            summary.textContent = message;
            summary.hidden = false;
        } else {
            showToast(message, "error");
        }
    }

    function setFormLoading(form, loading, loadingText) {
        if (!form) {
            return;
        }

        if (typeof window.RREIP.setFormLoading === "function") {
            window.RREIP.setFormLoading(form, loading, loadingText);
            return;
        }

        const submitButton = form.querySelector('button[type="submit"]');

        form.querySelectorAll("input, select, textarea, button").forEach((element) => {
            if (element === submitButton) {
                return;
            }

            element.disabled = loading;
        });

        if (!submitButton) {
            return;
        }

        if (loading) {
            if (!submitButton.dataset.originalHtml) {
                submitButton.dataset.originalHtml = submitButton.innerHTML;
            }

            submitButton.disabled = true;
            submitButton.classList.add("is-loading");
            submitButton.innerHTML = `
                <span class="rreip-btn-spinner" aria-hidden="true"></span>
                ${loadingText || "Processando..."}
            `;
        } else {
            submitButton.disabled = false;
            submitButton.classList.remove("is-loading");

            if (submitButton.dataset.originalHtml) {
                submitButton.innerHTML = submitButton.dataset.originalHtml;
                delete submitButton.dataset.originalHtml;
            }
        }
    }

    function setButtonLoading(button, loading, loadingText) {
        if (!button) {
            return;
        }

        if (typeof window.RREIP.setLoading === "function") {
            window.RREIP.setLoading(button, loading, loadingText);
            return;
        }

        if (loading) {
            if (!button.dataset.originalHtml) {
                button.dataset.originalHtml = button.innerHTML;
            }

            button.disabled = true;
            button.classList.add("is-loading");

            if (loadingText) {
                button.innerHTML = `
                    <span class="rreip-btn-spinner" aria-hidden="true"></span>
                    ${loadingText}
                `;
            }
        } else {
            button.disabled = false;
            button.classList.remove("is-loading");

            if (button.dataset.originalHtml) {
                button.innerHTML = button.dataset.originalHtml;
                delete button.dataset.originalHtml;
            }
        }
    }

    function setModalLoading(modal, loading) {
        if (!modal) {
            return;
        }

        modal.classList.toggle("is-loading", Boolean(loading));
    }

    async function loadUsers() {
        if (typeof window.RREIP.loadUsers === "function") {
            return await window.RREIP.loadUsers();
        }

        if (typeof window.RREIP.carregarUsuarios === "function") {
            return await window.RREIP.carregarUsuarios();
        }

        const url = wrapper.dataset.urlUsuarios;

        if (!url) {
            throw new Error("Endpoint de usuários não configurado.");
        }

        const response = await requestApi(url);

        if (Array.isArray(response)) {
            return response;
        }

        if (Array.isArray(response?.dados)) {
            return response.dados;
        }

        if (Array.isArray(response?.usuarios)) {
            return response.usuarios;
        }

        if (Array.isArray(response?.dados?.usuarios)) {
            return response.dados.usuarios;
        }

        return [];
    }

    function refreshSummary() {
        if (typeof window.RREIP.refreshSummary === "function") {
            window.RREIP.refreshSummary();
            return;
        }

        if (typeof window.RREIP.atualizarResumo === "function") {
            window.RREIP.atualizarResumo();
        }
    }

    function getActionData(event) {
        if (typeof window.RREIP.getActionData === "function") {
            return window.RREIP.getActionData(event);
        }

        const button = event.target.closest("[data-action]");

        if (!button || !wrapper.contains(button)) {
            return null;
        }

        return {
            action: button.dataset.action || "",
            id: button.dataset.id || "",
            button
        };
    }


    /* ==========================================================================
     * 4. Utilitários de linha
     * ========================================================================== */

    function getRow(id) {
        return wrapper.querySelector(`.rreip-row[data-id="${CSS.escape(String(id))}"]`);
    }

    function setRowLoading(id, loading) {
        const row = getRow(id);

        if (!row) {
            return;
        }

        row.classList.toggle("is-loading", Boolean(loading));
    }

    function closeActionsMenus() {
        wrapper.querySelectorAll(".rreip-actions-menu[open]").forEach((menu) => {
            menu.removeAttribute("open");
        });
    }

    function redirectToTreatment() {
        const treatmentUrl = wrapper.dataset.urlTratamento;
        const treatmentLink = wrapper.querySelector(
            '.rreip-tab[href*="tratamento"]'
        );

        window.location.href =
            treatmentUrl ||
            treatmentLink?.href ||
            window.location.href;
    }


    /* ==========================================================================
     * 5. Reabrir registro finalizado
     * ========================================================================== */

    function openReopenModal(id) {
        if (!id || !formReabrir) {
            showToast("Não foi possível identificar o registro.", "error");
            return;
        }

        formReabrir.reset();
        resetFormErrors(formReabrir);
        setValue(campoReabrirId, id);

        openModal("rreipModalReabrirFinalizado");

        window.setTimeout(() => {
            campoReabrirMotivo?.focus();
        }, 100);
    }

    async function submitReopen(event) {
        event.preventDefault();
        resetFormErrors(formReabrir);

        const id = getValue(formReabrir, "id");
        const motivo = getValue(formReabrir, "motivo");

        if (!id) {
            showToast("Registro finalizado não identificado.", "error");
            return;
        }

        if (!motivo) {
            campoReabrirMotivo?.setAttribute("aria-invalid", "true");

            const errorElement = document.createElement("div");
            errorElement.className = "rreip-form-error";
            errorElement.textContent = "Informe o motivo da reabertura.";

            campoReabrirMotivo?.insertAdjacentElement("afterend", errorElement);
            campoReabrirMotivo?.focus();
            return;
        }

        const confirmed = await showConfirm(
            "O registro retornará para Tratamento e todo o histórico será preservado. Confirma a reabertura?",
            {
                title: "Reabrir registro",
                confirmText: "Reabrir para análise",
                danger: false
            }
        );

        if (!confirmed) {
            return;
        }

        setFormLoading(formReabrir, true, "Reabrindo...");
        setModalLoading(modalReabrir, true);
        setRowLoading(id, true);

        try {
            const response = await requestApi(
                buildEndpoint(id, "reabrir-finalizado"),
                {
                    method: "POST",
                    body: {
                        motivo
                    }
                }
            );

            showToast(
                response?.mensagem ||
                "Registro reaberto e enviado para Tratamento.",
                "success"
            );

            closeModal("rreipModalReabrirFinalizado");
            refreshSummary();

            window.setTimeout(redirectToTreatment, 650);
        } catch (error) {
            applyApiErrors(formReabrir, error);
            setRowLoading(id, false);
        } finally {
            setModalLoading(modalReabrir, false);
            setFormLoading(formReabrir, false);
        }
    }


    /* ==========================================================================
     * 6. Transferir responsável
     * ========================================================================== */

    async function openTransferModal(id) {
        if (!id || !formTransferir) {
            showToast("Não foi possível identificar o registro.", "error");
            return;
        }

        formTransferir.reset();
        resetFormErrors(formTransferir);
        setValue(campoTransferirId, id);

        if (campoTransferirUsuario) {
            campoTransferirUsuario.innerHTML =
                '<option value="">Carregando usuários...</option>';
            campoTransferirUsuario.disabled = true;
        }

        openModal("rreipModalTransferir");
        setModalLoading(modalTransferir, true);

        try {
            const users = await loadUsers();

            if (!campoTransferirUsuario) {
                return;
            }

            campoTransferirUsuario.innerHTML =
                '<option value="">Selecione um responsável</option>';

            users.forEach((user) => {
                const option = document.createElement("option");

                option.value = user.id;
                option.textContent =
                    user.nome ||
                    user.full_name ||
                    user.get_full_name ||
                    user.username ||
                    `Usuário ${user.id}`;

                campoTransferirUsuario.appendChild(option);
            });

            campoTransferirUsuario.disabled = false;
            campoTransferirUsuario.focus();
        } catch (error) {
            showToast(
                error?.message || "Não foi possível carregar os responsáveis.",
                "error"
            );

            closeModal("rreipModalTransferir");
        } finally {
            setModalLoading(modalTransferir, false);
        }
    }

    async function submitTransfer(event) {
        event.preventDefault();
        resetFormErrors(formTransferir);

        const id = getValue(formTransferir, "id");
        const responsavelId = getValue(formTransferir, "responsavel_id");

        if (!id) {
            showToast("Registro finalizado não identificado.", "error");
            return;
        }

        if (!responsavelId) {
            campoTransferirUsuario?.setAttribute("aria-invalid", "true");

            const errorElement = document.createElement("div");
            errorElement.className = "rreip-form-error";
            errorElement.textContent = "Selecione o novo responsável.";

            campoTransferirUsuario?.insertAdjacentElement(
                "afterend",
                errorElement
            );

            campoTransferirUsuario?.focus();
            return;
        }

        const confirmed = await showConfirm(
            "Confirma a transferência deste registro para o responsável selecionado?",
            {
                title: "Transferir responsável",
                confirmText: "Transferir"
            }
        );

        if (!confirmed) {
            return;
        }

        setFormLoading(formTransferir, true, "Transferindo...");
        setModalLoading(modalTransferir, true);
        setRowLoading(id, true);

        try {
            const response = await requestApi(
                buildEndpoint(id, "transferir"),
                {
                    method: "POST",
                    body: {
                        responsavel_id: responsavelId
                    }
                }
            );

            showToast(
                response?.mensagem ||
                "Responsável transferido com sucesso.",
                "success"
            );

            closeModal("rreipModalTransferir");

            window.setTimeout(() => {
                window.location.reload();
            }, 450);
        } catch (error) {
            applyApiErrors(formTransferir, error);
            setRowLoading(id, false);
        } finally {
            setModalLoading(modalTransferir, false);
            setFormLoading(formTransferir, false);
        }
    }


    /* ==========================================================================
     * 7. Exclusão definitiva
     * ========================================================================== */

    async function deleteRecord(id, button) {
        if (!id) {
            showToast("Não foi possível identificar o registro.", "error");
            return;
        }

        const confirmed = await showConfirm(
            "ATENÇÃO: esta exclusão é definitiva. Use somente para registros criados por engano ou teste. Deseja continuar?",
            {
                title: "Excluir definitivamente",
                confirmText: "Excluir registro",
                danger: true
            }
        );

        if (!confirmed) {
            return;
        }

        closeActionsMenus();
        setButtonLoading(button, true, "Excluindo...");
        setRowLoading(id, true);

        try {
            const response = await requestApi(
                buildEndpoint(id, "excluir"),
                {
                    method: "POST"
                }
            );

            showToast(
                response?.mensagem ||
                "Registro excluído definitivamente.",
                "success"
            );

            refreshSummary();

            const row = getRow(id);

            if (row) {
                row.style.transition =
                    "opacity 0.2s ease, transform 0.2s ease";
                row.style.opacity = "0";
                row.style.transform = "translateX(8px)";

                window.setTimeout(() => {
                    row.remove();
                    updateVisibleRecordCount();
                    showEmptyStateIfNecessary();
                }, 220);
            } else {
                window.setTimeout(() => {
                    window.location.reload();
                }, 400);
            }
        } catch (error) {
            showToast(
                error?.message ||
                "Não foi possível excluir o registro.",
                "error"
            );

            setRowLoading(id, false);
            setButtonLoading(button, false);
        }
    }


    /* ==========================================================================
     * 8. Atualização visual após exclusão
     * ========================================================================== */

    function getVisibleRows() {
        return Array.from(
            wrapper.querySelectorAll(".rreip-row[data-id]")
        ).filter((row) => row.isConnected);
    }

    function updateVisibleRecordCount() {
        const countElement = wrapper.querySelector(".rreip-record-count");

        if (!countElement) {
            return;
        }

        const total = getVisibleRows().length;
        countElement.textContent = `${total} registro(s)`;
    }

    function showEmptyStateIfNecessary() {
        if (getVisibleRows().length > 0) {
            return;
        }

        const tableWrapper = wrapper.querySelector(".rreip-table-wrapper");

        if (tableWrapper) {
            tableWrapper.hidden = true;
        }

        const existingEmptyState = wrapper.querySelector(".rreip-empty-state");

        if (existingEmptyState) {
            existingEmptyState.hidden = false;
            return;
        }

        window.location.reload();
    }


    /* ==========================================================================
     * 9. Eventos dos formulários
     * ========================================================================== */

    if (formReabrir) {
        formReabrir.addEventListener("submit", submitReopen);
    }

    if (formTransferir) {
        formTransferir.addEventListener("submit", submitTransfer);
    }


    /* ==========================================================================
     * 10. Delegação central das ações
     * ========================================================================== */

    wrapper.addEventListener("click", (event) => {
        const actionData = getActionData(event);

        if (!actionData) {
            return;
        }

        const { action, id, button } = actionData;

        switch (action) {
            case "reabrir-finalizado":
                event.preventDefault();
                closeActionsMenus();
                openReopenModal(id);
                break;

            case "transferir":
                event.preventDefault();
                closeActionsMenus();
                openTransferModal(id);
                break;

            case "excluir":
                event.preventDefault();
                deleteRecord(id, button);
                break;

            default:
                break;
        }
    });


    /* ==========================================================================
     * 11. Fechamento dos menus de ações
     * ========================================================================== */

    document.addEventListener("click", (event) => {
        if (event.target.closest(".rreip-actions-menu")) {
            return;
        }

        closeActionsMenus();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeActionsMenus();
        }
    });


    /* ==========================================================================
     * 12. Inicialização visual
     * ========================================================================== */

    function initialize() {
        updateVisibleRecordCount();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialize, {
            once: true
        });
    } else {
        initialize();
    }


    /* ==========================================================================
     * 13. API pública opcional
     * ========================================================================== */

    window.RREIPFinalizados = {
        openReopenModal,
        openTransferModal,
        deleteRecord
    };

})();

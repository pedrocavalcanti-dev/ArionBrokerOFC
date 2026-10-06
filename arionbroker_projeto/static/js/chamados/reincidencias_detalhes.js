/* ==========================================================================
 * reincidencias_detalhes.js
 * Página de Detalhes — Módulo RREIP | Arion Broker
 * Fonte de verdade: detalhes.html atualizado
 * ========================================================================== */
(function () {
    "use strict";

    /* ---------------------------------------------------------------------- *
     * 1. INICIALIZAÇÃO E REFERÊNCIAS
     * ---------------------------------------------------------------------- */
    const page = document.getElementById("rreipDetailsPage");

    if (!page || !window.RREIP) return;
    if (page.dataset.detailsJsInicializado === "true") return;
    page.dataset.detailsJsInicializado = "true";

    const reincidenciaId = Number(page.dataset.reincidenciaId);
    if (!Number.isInteger(reincidenciaId) || reincidenciaId <= 0) {
        window.RREIP.showToast("Não foi possível identificar a reincidência.", "error");
        return;
    }

    /* ---------------------------------------------------------------------- *
     * 2. URLS — lidas do dataset de #rreipDetailsPage
     * ---------------------------------------------------------------------- */
    function getPageUrl(datasetKey, fallbackAction) {
        const url = page.dataset[datasetKey];
        if (url) return url;
        if (typeof window.RREIP.buildEndpoint === "function") {
            return window.RREIP.buildEndpoint(reincidenciaId, fallbackAction);
        }
        return `/chamados/reincidencias/api/${reincidenciaId}/${fallbackAction}/`;
    }

    const URLS = {
        detalhes:           () => getPageUrl("urlDetalhes",           "detalhes"),
        historico:          () => getPageUrl("urlHistorico",          "historico"),
        editar:             () => getPageUrl("urlEditar",             "editar"),
        apropriar:          () => getPageUrl("urlApropriar",          "apropriar"),
        liberar:            () => getPageUrl("urlLiberar",            "liberar"),
        transferir:         () => getPageUrl("urlTransferir",         "transferir"),
        classificar:        () => getPageUrl("urlClassificar",        "classificar"),
        salvarAnalise:      () => getPageUrl("urlSalvarAnalise",      "salvar-analise"),
        textoOtrs:          () => getPageUrl("urlTextoOtrs",          "texto-otrs"),
        previaEmail:        () => getPageUrl("urlPreviaEmail",        "previa-email-monitoramento"),
        enviarEmail:        () => getPageUrl("urlEnviarEmail",        "enviar-email-monitoramento"),
        registrarTicket:    () => getPageUrl("urlRegistrarTicket",    "registrar-ticket-monitoramento"),
        iniciarMonitoramento: () => getPageUrl("urlIniciarMonitoramento", "mover-monitoramento"),
        reabrir:            () => getPageUrl("urlReabrir",            "reabrir"),
        reabrirFinalizado:  () => getPageUrl("urlReabrirFinalizado",  "reabrir-finalizado"),
        concluir:           () => getPageUrl("urlConcluir",           "concluir"),
        excluir:            () => getPageUrl("urlExcluir",            "excluir"),
    };

    /* ---------------------------------------------------------------------- *
     * 3. HELPERS GERAIS
     * ---------------------------------------------------------------------- */
    function criarEl(tag, className, text) {
        const el = document.createElement(tag);
        if (className) el.className = className;
        if (text !== undefined && text !== null) el.textContent = String(text);
        return el;
    }

    function setVal(id, value) {
        const el = typeof id === "string" ? document.getElementById(id) : id;
        if (!el) return;
        el.value = (value !== null && value !== undefined) ? value : "";
    }

    function getVal(form, name) {
        const el = form ? form.querySelector(`[name="${name}"]`) : null;
        if (!el) return "";
        return typeof el.value === "string" ? el.value.trim() : String(el.value || "");
    }

    function toDatetimeLocal(value) {
        if (!value) return "";
        if (typeof window.RREIP.toDatetimeLocal === "function") {
            return window.RREIP.toDatetimeLocal(value);
        }
        try {
            const s = String(value);
            if (s.includes("T") && s.length >= 16) return s.substring(0, 16);
            return "";
        } catch (_) {
            return "";
        }
    }

    function unwrap(response) {
        if (!response) return {};
        if (response.reincidencia) return response.reincidencia;
        if (response.dados && response.dados.reincidencia) return response.dados.reincidencia;
        if (response.dados && typeof response.dados === "object") return response.dados;
        return response;
    }

    function resetErrors(form) {
        if (!form) return;
        form.querySelectorAll("[aria-invalid]").forEach(el => el.removeAttribute("aria-invalid"));
        form.querySelectorAll(".rreip-form-error").forEach(el => el.remove());
        const summary = form.querySelector("[data-form-error-summary]");
        if (summary) summary.hidden = true;
    }

    function applyApiErrors(form, error) {
        resetErrors(form);
        const campos = error?.data?.campos || error?.data?.errors || null;
        if (campos && typeof campos === "object") {
            let focou = false;
            for (const [name, msgs] of Object.entries(campos)) {
                const campo = form ? form.querySelector(`[name="${name}"]`) : null;
                if (campo) {
                    campo.setAttribute("aria-invalid", "true");
                    const msg = Array.isArray(msgs) ? msgs[0] : msgs;
                    const errEl = criarEl("div", "rreip-form-error", msg);
                    campo.parentNode.appendChild(errEl);
                    if (!focou) { campo.focus(); focou = true; }
                }
            }
            if (focou) return;
        }
        const msg = error?.message || "Ocorreu um erro ao concluir a operação.";
        window.RREIP.showToast(msg, "error");
    }

    function setFormLoading(form, loading, text) {
        if (typeof window.RREIP.setFormLoading === "function") {
            window.RREIP.setFormLoading(form, loading, text);
            return;
        }
        const btn = form ? form.querySelector('button[type="submit"]') : null;
        if (!btn) return;
        if (loading) {
            btn.dataset.orig = btn.textContent;
            btn.disabled = true;
            btn.textContent = text || "Salvando...";
        } else {
            btn.disabled = false;
            btn.textContent = btn.dataset.orig || "Salvar";
            delete btn.dataset.orig;
        }
    }

    function lockBtn(btn) {
        if (!btn) return;
        btn.dataset.processing = "true";
        btn.disabled = true;
    }

    function unlockBtn(btn) {
        if (!btn) return;
        delete btn.dataset.processing;
        btn.disabled = false;
    }

    /* ---------------------------------------------------------------------- *
     * 4. CARREGAR DADOS ATUAIS
     * ---------------------------------------------------------------------- */
    async function carregarDadosAtuais() {
        const response = await window.RREIP.requestApi(URLS.detalhes());
        return unwrap(response);
    }

    function atualizarCamposDaPagina(dados) {
        // campos simples [data-detail-field]
        document.querySelectorAll("[data-detail-field]").forEach(el => {
            const key = el.dataset.detailField;
            if (dados[key] === undefined || dados[key] === null) return;
            el.textContent = dados[key];
        });

        // links [data-detail-link-field]
        document.querySelectorAll("[data-detail-link-field]").forEach(el => {
            const key = el.dataset.detailLinkField;
            const urlKey = el.dataset.detailLinkUrl;
            if (dados[key] !== undefined && dados[key] !== null) {
                el.textContent = dados[key];
            }
            if (urlKey && dados[urlKey]) {
                el.href = dados[urlKey];
            }
        });

        // campos de análise [data-analysis-field]
        document.querySelectorAll("[data-analysis-field]").forEach(el => {
            const key = el.dataset.analysisField;
            const val = dados[key];
            const container = el.closest(".rreip-analysis-item__content") || el;
            container.textContent = val ? val : "Não informado.";
        });
    }

    /* ---------------------------------------------------------------------- *
     * 5. HISTÓRICO
     * ---------------------------------------------------------------------- */
    const historyContainer = document.getElementById("rreipDetailsHistory");

    function extrairHistorico(response) {
        if (!response) return [];
        if (Array.isArray(response)) return response;
        if (response.dados && Array.isArray(response.dados.historico)) return response.dados.historico;
        if (response.historico && Array.isArray(response.historico)) return response.historico;
        if (response.dados && Array.isArray(response.dados)) return response.dados;
        return [];
    }

    async function carregarHistorico() {
        if (!historyContainer) return;
        try {
            const response = await window.RREIP.requestApi(URLS.historico());
            const itens = extrairHistorico(response);
            renderizarHistorico(itens);
        } catch (_) { /* silencioso */ }
    }

    function normalizarObj(value) {
        if (!value) return {};
        if (typeof value === "object") return value;
        try { return JSON.parse(value); } catch (_) { return {}; }
    }

    function obterAlteracoes(ant, nov) {
        const a = normalizarObj(ant);
        const n = normalizarObj(nov);
        const chaves = new Set([...Object.keys(a), ...Object.keys(n)]);
        const lista = [];
        chaves.forEach(campo => {
            if (JSON.stringify(a[campo]) !== JSON.stringify(n[campo])) {
                lista.push({
                    campo,
                    anterior: a[campo] !== undefined ? a[campo] : "—",
                    novo: n[campo] !== undefined ? n[campo] : "—",
                });
            }
        });
        return lista;
    }

    function renderizarHistorico(itens) {
        if (!historyContainer) return;
        historyContainer.innerHTML = "";

        if (!itens || itens.length === 0) {
            historyContainer.appendChild(criarEl("p", "rreip-text-muted", "Nenhum evento registrado."));
            return;
        }

        itens.forEach(item => {
            const article = criarEl("article", "rreip-history-item");
            article.appendChild(criarEl("div", "rreip-history-item__marker"));

            const content = criarEl("div", "rreip-history-item__content");

            const header = criarEl("header", "rreip-history-item__header");
            const titulo = item.tipo_evento_display || item.tipo_evento || item.tipo || "Evento";
            header.appendChild(criarEl("strong", "rreip-history-item__title", titulo));

            const fmt = (typeof window.RREIP.formatarDataHora === "function")
                ? window.RREIP.formatarDataHora(item.criado_em || item.data)
                : (item.criado_em || item.data || "");
            const timeEl = criarEl("time", "rreip-history-item__date", fmt);
            if (item.criado_em) timeEl.setAttribute("datetime", item.criado_em);
            header.appendChild(timeEl);
            content.appendChild(header);

            const descricao = item.descricao || "—";
            content.appendChild(criarEl("p", "rreip-history-item__description", descricao));

            const usuarioNome = item.usuario
                ? (typeof item.usuario === "object"
                    ? (item.usuario.get_full_name || item.usuario.full_name || item.usuario.username || "Sistema")
                    : item.usuario)
                : "Sistema";
            const userSpan = criarEl("span", "rreip-history-item__user", `Por: ${usuarioNome}`);
            content.appendChild(userSpan);

            // alterações campo a campo
            if (item.dados_anteriores || item.dados_novos) {
                const alteracoes = obterAlteracoes(item.dados_anteriores, item.dados_novos);
                if (alteracoes.length > 0) {
                    const btnToggle = criarEl("button", "rreip-btn rreip-btn--text rreip-btn--small", "Ver alterações");
                    btnToggle.type = "button";
                    btnToggle.dataset.action = "toggle-history-data";
                    btnToggle.setAttribute("aria-expanded", "false");
                    content.appendChild(btnToggle);

                    const changesDiv = criarEl("div", "rreip-history-changes");
                    changesDiv.hidden = true;
                    alteracoes.forEach(alt => {
                        const row = criarEl("div", "rreip-history-change");
                        row.appendChild(criarEl("span", "rreip-history-change__field", `${alt.campo}:`));
                        const antStr = typeof alt.anterior === "object" ? JSON.stringify(alt.anterior) : String(alt.anterior);
                        const novStr = typeof alt.novo === "object" ? JSON.stringify(alt.novo) : String(alt.novo);
                        row.appendChild(criarEl("span", "rreip-history-change__old", `Antes: ${antStr}`));
                        row.appendChild(criarEl("span", "rreip-history-change__new", `Depois: ${novStr}`));
                        changesDiv.appendChild(row);
                    });
                    content.appendChild(changesDiv);
                }
            }

            article.appendChild(content);
            historyContainer.appendChild(article);
        });
    }

    /* ---------------------------------------------------------------------- *
     * 6. APROPRIAR
     * ---------------------------------------------------------------------- */
    async function apropriar() {
        try {
            await window.RREIP.requestApi(URLS.apropriar(), { method: "POST" });
            window.RREIP.showToast("Reincidência apropriada com sucesso.", "success");
            window.location.reload();
        } catch (error) {
            window.RREIP.showToast(error?.message || "Erro ao apropriar.", "error");
        }
    }

    /* ---------------------------------------------------------------------- *
     * 7. LIBERAR
     * ---------------------------------------------------------------------- */
    async function liberar() {
        const conf = await window.RREIP.showConfirm("A reincidência ficará sem responsável. Deseja continuar?");
        if (!conf) return;
        try {
            await window.RREIP.requestApi(URLS.liberar(), { method: "POST" });
            window.RREIP.showToast("Responsabilidade liberada.", "success");
            window.location.reload();
        } catch (error) {
            window.RREIP.showToast(error?.message || "Erro ao liberar.", "error");
        }
    }

    /* ---------------------------------------------------------------------- *
     * 8. TRANSFERIR
     * ---------------------------------------------------------------------- */
    const modalTransferir    = document.getElementById("rreipModalTransferir");
    const formTransferir     = document.getElementById("rreipFormTransferir");

    async function abrirTransferencia() {
        if (!modalTransferir) return;
        resetErrors(formTransferir);
        if (formTransferir) formTransferir.reset();
        setVal("rreipTransferirId", reincidenciaId);

        window.RREIP.openModal("rreipModalTransferir");

        const select = document.getElementById("rreipTransferirUsuario");
        if (!select) return;

        select.innerHTML = "";
        const opt0 = criarEl("option", "", "Carregando usuários...");
        opt0.value = "";
        select.appendChild(opt0);

        try {
            let usuarios = [];
            if (typeof window.RREIP.loadUsers === "function") {
                usuarios = await window.RREIP.loadUsers();
            } else if (typeof window.RREIP.carregarUsuarios === "function") {
                usuarios = await window.RREIP.carregarUsuarios();
            }
            select.innerHTML = "";
            const placeholder = criarEl("option", "", "Selecione o novo responsável");
            placeholder.value = "";
            select.appendChild(placeholder);
            usuarios.forEach(u => {
                const opt = criarEl("option", "", u.nome || u.full_name || u.username || String(u.id));
                opt.value = u.id;
                select.appendChild(opt);
            });
        } catch (_) {
            select.innerHTML = "";
            const errOpt = criarEl("option", "", "Erro ao carregar usuários");
            errOpt.value = "";
            select.appendChild(errOpt);
        }
    }

    async function enviarTransferencia(e) {
        e.preventDefault();
        resetErrors(formTransferir);
        const responsavelId = getVal(formTransferir, "responsavel_id");
        if (!responsavelId) {
            window.RREIP.showToast("Selecione o novo responsável.", "error");
            return;
        }
        setFormLoading(formTransferir, true, "Transferindo...");
        try {
            await window.RREIP.requestApi(URLS.transferir(), { method: "POST", body: { responsavel_id: responsavelId } });
            window.RREIP.showToast("Responsável transferido com sucesso.", "success");
            window.RREIP.closeModal("rreipModalTransferir");
            window.location.reload();
        } catch (error) {
            applyApiErrors(formTransferir, error);
        } finally {
            setFormLoading(formTransferir, false);
        }
    }

    if (formTransferir) formTransferir.addEventListener("submit", enviarTransferencia);

    /* ---------------------------------------------------------------------- *
     * 9. EDITAR CADASTRO
     * ---------------------------------------------------------------------- */
    const modalEditar = document.getElementById("rreipModalEditar");
    const formEditar  = document.getElementById("rreipFormEditar");

    async function abrirEdicao() {
        if (!modalEditar) return;
        if (formEditar) { formEditar.reset(); resetErrors(formEditar); }
        window.RREIP.openModal("rreipModalEditar");
        modalEditar.classList.add("is-loading");
        try {
            const dados = await carregarDadosAtuais();
            setVal("rreipEditarId",                  dados.id || reincidenciaId);

            // ticket de origem com fallback para ticket_atual
            setVal("rreipEditarTicketOrigem",
                dados.ticket_origem || dados.ticket_atual || "");
            setVal("rreipEditarUrlTicketOrigem",
                dados.url_ticket_origem || dados.url_ticket || "");
            setVal("rreipEditarDataTicketOrigem",
                toDatetimeLocal(dados.data_ticket_origem || dados.data_ticket || ""));
            setVal("rreipEditarDataEncerramentoOrigem",
                toDatetimeLocal(dados.data_encerramento_origem || ""));

            // operadora
            const selOp = document.getElementById("rreipEditarOperadora");
            if (selOp && dados.operadora) {
                selOp.value = dados.operadora;
            }

            setVal("rreipEditarProjeto",             dados.projeto || "");
            setVal("rreipEditarIdentificador",       dados.identificador_projeto || "");
            setVal("rreipEditarDesignacao",           dados.designacao || "");
            setVal("rreipEditarCliente",              dados.cliente || "");
            setVal("rreipEditarISP",                  dados.isp || "");
        } catch (_) {
            window.RREIP.showToast("Não foi possível carregar os dados para edição.", "error");
            window.RREIP.closeModal("rreipModalEditar");
        } finally {
            modalEditar.classList.remove("is-loading");
        }
    }

    async function enviarEdicao(e) {
        e.preventDefault();
        resetErrors(formEditar);

        const body = {
            ticket_origem:             getVal(formEditar, "ticket_origem"),
            url_ticket_origem:         getVal(formEditar, "url_ticket_origem"),
            data_ticket_origem:        getVal(formEditar, "data_ticket_origem"),
            data_encerramento_origem:  getVal(formEditar, "data_encerramento_origem"),
            operadora:                 getVal(formEditar, "operadora"),
            projeto:                   getVal(formEditar, "projeto"),
            identificador_projeto:     getVal(formEditar, "identificador_projeto"),
            designacao:                getVal(formEditar, "designacao"),
            cliente:                   getVal(formEditar, "cliente"),
            isp:                       getVal(formEditar, "isp"),
        };

        setFormLoading(formEditar, true, "Salvando...");
        try {
            await window.RREIP.requestApi(URLS.editar(), { method: "POST", body });
            window.RREIP.showToast("Dados atualizados com sucesso.", "success");
            window.RREIP.closeModal("rreipModalEditar");
            const novos = await carregarDadosAtuais();
            atualizarCamposDaPagina(novos);
            await carregarHistorico();
        } catch (error) {
            applyApiErrors(formEditar, error);
        } finally {
            setFormLoading(formEditar, false);
        }
    }

    if (formEditar) formEditar.addEventListener("submit", enviarEdicao);

    /* ---------------------------------------------------------------------- *
     * 10. CLASSIFICAR
     * ---------------------------------------------------------------------- */
    const modalClassificar = document.getElementById("rreipModalClassificar");
    const formClassificar  = document.getElementById("rreipFormClassificar");

    const CLASSIFICACOES_COM_MOTIVO_OBRIGATORIO = [
        "MASSIVA", "FALSO_POSITIVO", "FALHA_ISOLADA", "DUPLICADO", "NAO_SE_APLICA"
    ];

    function abrirClassificacao() {
        if (!modalClassificar) return;
        if (formClassificar) resetErrors(formClassificar);
        window.RREIP.openModal("rreipModalClassificar");
    }

    async function enviarClassificacao(e) {
        e.preventDefault();
        resetErrors(formClassificar);

        const classificacao = getVal(formClassificar, "classificacao");
        const motivo        = getVal(formClassificar, "motivo");

        if (CLASSIFICACOES_COM_MOTIVO_OBRIGATORIO.includes(classificacao) && !motivo) {
            const campo = formClassificar.querySelector('[name="motivo"]');
            if (campo) {
                campo.setAttribute("aria-invalid", "true");
                const errEl = criarEl("div", "rreip-form-error", "Justificativa obrigatória para este tipo de classificação.");
                campo.parentNode.appendChild(errEl);
                campo.focus();
            }
            return;
        }

        setFormLoading(formClassificar, true, "Salvando...");
        try {
            await window.RREIP.requestApi(URLS.classificar(), {
                method: "POST",
                body: { classificacao, motivo },
            });
            window.RREIP.showToast("Classificação salva com sucesso.", "success");
            window.RREIP.closeModal("rreipModalClassificar");
            const novos = await carregarDadosAtuais();
            atualizarCamposDaPagina(novos);
            await carregarHistorico();
            // se descartado pode ter ido para Finalizados — recarrega para refletir layout
            if (CLASSIFICACOES_COM_MOTIVO_OBRIGATORIO.includes(classificacao)) {
                window.location.reload();
            }
        } catch (error) {
            applyApiErrors(formClassificar, error);
        } finally {
            setFormLoading(formClassificar, false);
        }
    }

    if (formClassificar) formClassificar.addEventListener("submit", enviarClassificacao);

    /* ---------------------------------------------------------------------- *
     * 11. ANÁLISE TÉCNICA
     * ---------------------------------------------------------------------- */
    const modalAnalise = document.getElementById("rreipModalAnalise");
    const formAnalise  = document.getElementById("rreipFormAnalise");

    async function abrirAnalise() {
        if (!modalAnalise) return;
        if (formAnalise) { formAnalise.reset(); resetErrors(formAnalise); }
        window.RREIP.openModal("rreipModalAnalise");
        modalAnalise.classList.add("is-loading");
        try {
            const dados = await carregarDadosAtuais();
            setVal("rreipAnaliseId",               dados.id || reincidenciaId);
            setVal("rreipAnaliseMotivo",            dados.motivo_identificado || "");
            setVal("rreipAnaliseCausa",             dados.causa_raiz || "");
            setVal("rreipAnaliseAcaoRealizada",     dados.acao_realizada || "");
            setVal("rreipAnaliseAcaoPreventiva",    dados.acao_preventiva || "");
            setVal("rreipAnaliseConclusao",         dados.conclusao || "");
        } catch (_) {
            window.RREIP.showToast("Não foi possível carregar a análise.", "error");
            window.RREIP.closeModal("rreipModalAnalise");
        } finally {
            modalAnalise.classList.remove("is-loading");
        }
    }

    function atualizarAnaliseNaPagina(dados) {
        const campos = [
            "motivo_identificado",
            "causa_raiz",
            "acao_realizada",
            "acao_preventiva",
            "conclusao",
        ];
        campos.forEach(field => {
            const el = document.querySelector(`[data-analysis-field="${field}"] .rreip-analysis-item__content, [data-analysis-field="${field}"]`);
            if (!el) return;
            const val = dados[field];
            el.textContent = val ? val : "Não informado.";
        });
    }

    async function enviarAnalise(e) {
        e.preventDefault();
        resetErrors(formAnalise);

        const body = {
            motivo_identificado: getVal(formAnalise, "motivo_identificado"),
            causa_raiz:          getVal(formAnalise, "causa_raiz"),
            acao_realizada:      getVal(formAnalise, "acao_realizada"),
            acao_preventiva:     getVal(formAnalise, "acao_preventiva"),
            conclusao:           getVal(formAnalise, "conclusao"),
        };

        setFormLoading(formAnalise, true, "Salvando...");
        try {
            await window.RREIP.requestApi(URLS.salvarAnalise(), { method: "POST", body });
            window.RREIP.showToast("Análise salva com sucesso.", "success");
            window.RREIP.closeModal("rreipModalAnalise");
            const novos = await carregarDadosAtuais();
            atualizarAnaliseNaPagina(novos);
            await carregarHistorico();
        } catch (error) {
            applyApiErrors(formAnalise, error);
        } finally {
            setFormLoading(formAnalise, false);
        }
    }

    if (formAnalise) formAnalise.addEventListener("submit", enviarAnalise);

    /* ---------------------------------------------------------------------- *
     * 12. TEXTO PARA OTRS
     * ---------------------------------------------------------------------- */
    const textoOtrsInline = document.getElementById("rreipTextoOtrsInline");
    let textoOtrsCarregado = false;

    async function carregarTextoOtrs() {
        if (!textoOtrsInline) return;
        textoOtrsInline.value = "Gerando texto...";
        textoOtrsCarregado = false;
        try {
            const response = await window.RREIP.requestApi(URLS.textoOtrs());
            const texto = response?.texto || response?.dados?.texto || response?.data?.texto || "";
            textoOtrsInline.value = texto;
            textoOtrsCarregado = !!texto;
        } catch (_) {
            textoOtrsInline.value = "";
            window.RREIP.showToast("Erro ao gerar texto para OTRS.", "error");
        }
    }

    function copiarTextoOtrs() {
        if (!textoOtrsInline || !textoOtrsInline.value) {
            window.RREIP.showToast("Nenhum texto para copiar. Clique em Gerar primeiro.", "warning");
            return;
        }
        if (typeof window.RREIP.copyText === "function") {
            window.RREIP.copyText(textoOtrsInline.value);
        } else {
            textoOtrsInline.select();
            document.execCommand("copy");
            window.RREIP.showToast("Texto copiado.", "success");
        }
    }

    /* ---------------------------------------------------------------------- *
     * 13. PRÉVIA E ENVIO DE E-MAIL DE MONITORAMENTO
     * ---------------------------------------------------------------------- */
    const modalEmail = document.getElementById("rreipModalEmailMonitoramento");
    let emailPreviaCarregada = false;

    async function carregarPreviaEmail() {
        emailPreviaCarregada = false;
        const elDest    = document.getElementById("rreipEmailDestinatarios");
        const elCc      = document.getElementById("rreipEmailCc");
        const elAssunto = document.getElementById("rreipEmailAssunto");
        const elCorpo   = document.getElementById("rreipEmailCorpo");

        if (elCorpo) elCorpo.textContent = "Carregando prévia...";

        try {
            const response = await window.RREIP.requestApi(URLS.previaEmail());
            const dados = response?.dados || response;

            if (elDest)    elDest.textContent    = dados.destinatarios   ? `Para: ${dados.destinatarios}`   : "";
            if (elCc)      elCc.textContent      = dados.cc              ? `CC: ${dados.cc}`                : "";
            if (elAssunto) elAssunto.textContent = dados.assunto         ? `Assunto: ${dados.assunto}`      : "";
            if (elCorpo)   elCorpo.textContent   = dados.corpo           || dados.body                      || "Sem conteúdo.";

            emailPreviaCarregada = true;
        } catch (error) {
            if (elCorpo) elCorpo.textContent = "Erro ao carregar prévia do e-mail.";
            window.RREIP.showToast(error?.message || "Erro ao carregar prévia.", "error");
        }
    }

    async function abrirEmailMonitoramento() {
        if (!modalEmail) return;
        window.RREIP.openModal("rreipModalEmailMonitoramento");
        await carregarPreviaEmail();
    }

    async function confirmarEnvioEmail() {
        if (!emailPreviaCarregada) {
            window.RREIP.showToast("Aguarde a prévia ser carregada.", "warning");
            return;
        }

        const conf = await window.RREIP.showConfirm(
            "O e-mail de solicitação de monitoramento será enviado. Confirma?",
            { confirmText: "Enviar" }
        );
        if (!conf) return;

        const btnConfirmar = document.getElementById("rreipBtnConfirmarEnvioEmail");
        lockBtn(btnConfirmar);
        try {
            await window.RREIP.requestApi(URLS.enviarEmail(), { method: "POST" });
            window.RREIP.showToast("E-mail de monitoramento enviado com sucesso.", "success");
            window.RREIP.closeModal("rreipModalEmailMonitoramento");
            const novos = await carregarDadosAtuais();
            atualizarCamposDaPagina(novos);
            await carregarHistorico();
            // NÃO iniciar monitoramento aqui — status vai para AGUARDANDO_TICKET_MONITORAMENTO
        } catch (error) {
            window.RREIP.showToast(error?.message || "Erro ao enviar e-mail.", "error");
        } finally {
            unlockBtn(btnConfirmar);
        }
    }

    const btnConfirmarEmail = document.getElementById("rreipBtnConfirmarEnvioEmail");
    if (btnConfirmarEmail) {
        btnConfirmarEmail.addEventListener("click", confirmarEnvioEmail);
    }

    /* ---------------------------------------------------------------------- *
     * 14. REGISTRAR TICKET DE MONITORAMENTO
     * ---------------------------------------------------------------------- */
    const modalTicket = document.getElementById("rreipModalTicketMonitoramento");
    const formTicket  = document.getElementById("rreipFormTicketMonitoramento");

    function abrirRegistroTicket() {
        if (!modalTicket) return;
        if (formTicket) { formTicket.reset(); resetErrors(formTicket); }
        setVal("rreipTicketMonitoramentoId", reincidenciaId);
        window.RREIP.openModal("rreipModalTicketMonitoramento");
    }

    async function enviarRegistroTicket(e) {
        e.preventDefault();
        resetErrors(formTicket);

        const body = {
            ticket_monitoramento:      getVal(formTicket, "ticket_monitoramento"),
            url_ticket_monitoramento:  getVal(formTicket, "url_ticket_monitoramento"),
            data_ticket_monitoramento: getVal(formTicket, "data_ticket_monitoramento"),
        };

        if (!body.ticket_monitoramento) {
            window.RREIP.showToast("Informe o número do ticket.", "error");
            return;
        }

        setFormLoading(formTicket, true, "Salvando...");
        try {
            await window.RREIP.requestApi(URLS.registrarTicket(), { method: "POST", body });
            window.RREIP.showToast("Ticket de monitoramento registrado.", "success");
            window.RREIP.closeModal("rreipModalTicketMonitoramento");
            // NÃO iniciar os 30 dias automaticamente
            const novos = await carregarDadosAtuais();
            atualizarCamposDaPagina(novos);
            await carregarHistorico();
        } catch (error) {
            applyApiErrors(formTicket, error);
        } finally {
            setFormLoading(formTicket, false);
        }
    }

    if (formTicket) formTicket.addEventListener("submit", enviarRegistroTicket);

    /* ---------------------------------------------------------------------- *
     * 15. INICIAR MONITORAMENTO (30 dias)
     * ---------------------------------------------------------------------- */
    async function iniciarMonitoramento() {
        const conf = await window.RREIP.showConfirm(
            "O ticket foi conferido? Ao continuar, o prazo de 30 dias será iniciado.",
            { confirmText: "Iniciar monitoramento" }
        );
        if (!conf) return;

        try {
            await window.RREIP.requestApi(URLS.iniciarMonitoramento(), { method: "POST" });
            window.RREIP.showToast("Monitoramento de 30 dias iniciado.", "success");
            // redirecionar para fila Monitoramento
            const linkMon = document.querySelector('a[href*="monitoramento"]');
            if (linkMon) {
                window.location.href = linkMon.href;
            } else {
                window.location.reload();
            }
        } catch (error) {
            window.RREIP.showToast(error?.message || "Erro ao iniciar monitoramento.", "error");
        }
    }

    /* ---------------------------------------------------------------------- *
     * 16. NOVA REINCIDÊNCIA (REABRIR de Monitoramento → Tratamento)
     * ---------------------------------------------------------------------- */
    const modalNovaOcorrencia = document.getElementById("rreipModalNovaOcorrencia");
    const formNovaOcorrencia  = document.getElementById("rreipFormNovaOcorrencia");

    function abrirNovaOcorrencia() {
        if (!modalNovaOcorrencia) return;
        if (formNovaOcorrencia) { formNovaOcorrencia.reset(); resetErrors(formNovaOcorrencia); }
        setVal("rreipNovaOcorrenciaId", reincidenciaId);
        window.RREIP.openModal("rreipModalNovaOcorrencia");
    }

    async function enviarNovaOcorrencia(e) {
        e.preventDefault();
        resetErrors(formNovaOcorrencia);

        const novoTicket = getVal(formNovaOcorrencia, "novo_ticket");
        if (!novoTicket) {
            window.RREIP.showToast("Informe o número do novo ticket.", "error");
            return;
        }

        const body = {
            novo_ticket: novoTicket,
            url_ticket:  getVal(formNovaOcorrencia, "url_ticket"),
            data_ticket: getVal(formNovaOcorrencia, "data_ticket"),
        };

        setFormLoading(formNovaOcorrencia, true, "Registrando...");
        try {
            await window.RREIP.requestApi(URLS.reabrir(), { method: "POST", body });
            window.RREIP.showToast("Nova reincidência registrada. Registro retornou para Tratamento.", "success");
            window.RREIP.closeModal("rreipModalNovaOcorrencia");
            // ticket de origem e ticket de monitoramento preservados no backend
            const linkTrat = document.querySelector('a[href*="tratamento"]');
            if (linkTrat) {
                window.location.href = linkTrat.href;
            } else {
                window.location.reload();
            }
        } catch (error) {
            applyApiErrors(formNovaOcorrencia, error);
        } finally {
            setFormLoading(formNovaOcorrencia, false);
        }
    }

    if (formNovaOcorrencia) formNovaOcorrencia.addEventListener("submit", enviarNovaOcorrencia);

    /* ---------------------------------------------------------------------- *
     * 17. CONCLUIR MONITORAMENTO
     * ---------------------------------------------------------------------- */
    const modalConcluir = document.getElementById("rreipModalConcluir");
    const formConcluir  = document.getElementById("rreipFormConcluir");

    function abrirConclusao() {
        if (!modalConcluir) return;
        if (formConcluir) { formConcluir.reset(); resetErrors(formConcluir); }
        setVal("rreipConcluirId", reincidenciaId);
        window.RREIP.openModal("rreipModalConcluir");
    }

    async function enviarConclusao(e) {
        e.preventDefault();
        resetErrors(formConcluir);

        const checkboxForcar = formConcluir ? formConcluir.querySelector('[name="forcar"]') : null;
        const forcar = checkboxForcar ? checkboxForcar.checked : false;

        setFormLoading(formConcluir, true, "Concluindo...");
        try {
            await window.RREIP.requestApi(URLS.concluir(), {
                method: "POST",
                body: { forcar: forcar ? "true" : "false" },
            });
            window.RREIP.showToast("Monitoramento concluído com sucesso.", "success");
            window.RREIP.closeModal("rreipModalConcluir");
            // vai para Finalizados
            const linkFin = document.querySelector('a[href*="finalizado"]');
            if (linkFin) {
                window.location.href = linkFin.href;
            } else {
                window.location.reload();
            }
        } catch (error) {
            applyApiErrors(formConcluir, error);
        } finally {
            setFormLoading(formConcluir, false);
        }
    }

    if (formConcluir) formConcluir.addEventListener("submit", enviarConclusao);

    /* ---------------------------------------------------------------------- *
     * 18. REABRIR FINALIZADO
     * ---------------------------------------------------------------------- */
    const modalReabrirFinalizado = document.getElementById("rreipModalReabrirFinalizado");
    const formReabrirFinalizado  = document.getElementById("rreipFormReabrirFinalizado");

    function abrirReabrirFinalizado() {
        if (!modalReabrirFinalizado) return;
        if (formReabrirFinalizado) { formReabrirFinalizado.reset(); resetErrors(formReabrirFinalizado); }
        setVal("rreipReabrirFinalizadoId", reincidenciaId);
        window.RREIP.openModal("rreipModalReabrirFinalizado");
    }

    async function enviarReabrirFinalizado(e) {
        e.preventDefault();
        resetErrors(formReabrirFinalizado);

        const motivo = getVal(formReabrirFinalizado, "motivo");
        if (!motivo) {
            window.RREIP.showToast("Informe o motivo da reabertura.", "error");
            return;
        }

        setFormLoading(formReabrirFinalizado, true, "Reabrindo...");
        try {
            await window.RREIP.requestApi(URLS.reabrirFinalizado(), { method: "POST", body: { motivo } });
            window.RREIP.showToast("Registro reaberto para Tratamento.", "success");
            window.RREIP.closeModal("rreipModalReabrirFinalizado");
            // classificação volta a PENDENTE no backend; redirecionar
            const linkTrat = document.querySelector('a[href*="tratamento"]');
            if (linkTrat) {
                window.location.href = linkTrat.href;
            } else {
                window.location.reload();
            }
        } catch (error) {
            applyApiErrors(formReabrirFinalizado, error);
        } finally {
            setFormLoading(formReabrirFinalizado, false);
        }
    }

    if (formReabrirFinalizado) formReabrirFinalizado.addEventListener("submit", enviarReabrirFinalizado);

    /* ---------------------------------------------------------------------- *
     * 19. EXCLUIR
     * ---------------------------------------------------------------------- */
    async function excluir() {
        const conf = await window.RREIP.showConfirm(
            "Esta exclusão é definitiva e deve ser utilizada apenas para cadastro incorreto ou teste. Deseja continuar?",
            { danger: true, confirmText: "Excluir definitivamente" }
        );
        if (!conf) return;

        try {
            await window.RREIP.requestApi(URLS.excluir(), { method: "POST" });
            window.RREIP.showToast("Reincidência excluída.", "success");

            const fila = (page.dataset.fila || "TRATAMENTO").toLowerCase();
            const linkFila = document.querySelector(`a[href*="${fila}"]`);
            if (linkFila) {
                window.location.href = linkFila.href;
            } else {
                window.location.href = "/chamados/reincidencias/";
            }
        } catch (error) {
            window.RREIP.showToast(error?.message || "Erro ao excluir.", "error");
        }
    }

    /* ---------------------------------------------------------------------- *
     * 20. DELEGAÇÃO DE EVENTOS — listener principal em #rreipDetailsPage
     * ---------------------------------------------------------------------- */
    page.addEventListener("click", async function (e) {
        const el = e.target.closest("[data-action]");
        if (!el) return;

        // não bloquear links normais
        if (el.tagName === "A" && el.href && !el.dataset.action) return;

        const action = el.dataset.action;

        // toggle de alterações no histórico — não precisa de lock
        if (action === "toggle-history-data") {
            const item = el.closest(".rreip-history-item");
            if (!item) return;
            const changesDiv = item.querySelector(".rreip-history-changes");
            if (!changesDiv) return;
            const hidden = changesDiv.hidden;
            changesDiv.hidden = !hidden;
            el.setAttribute("aria-expanded", hidden ? "true" : "false");
            el.textContent = hidden ? "Ocultar alterações" : "Ver alterações";
            return;
        }

        // proteger contra duplo clique
        if (el.dataset.processing === "true") return;
        lockBtn(el);

        try {
            switch (action) {
                // ── apropriar / liberar
                case "apropriar":
                    await apropriar();
                    break;
                case "liberar":
                    await liberar();
                    break;

                // ── transferir
                case "transferir":
                    await abrirTransferencia();
                    break;

                // ── editar cadastro
                case "editar":
                    await abrirEdicao();
                    break;

                // ── análise (aceita dois aliases)
                case "analise":
                case "editar-analise":
                case "salvar-analise":
                    await abrirAnalise();
                    break;

                // ── classificação
                case "classificar":
                    abrirClassificacao();
                    break;

                // ── texto OTRS
                case "carregar-texto-otrs":
                    await carregarTextoOtrs();
                    break;
                case "copiar-texto-otrs":
                    copiarTextoOtrs();
                    break;

                // ── e-mail de monitoramento
                case "enviar-email-monitoramento":
                    await abrirEmailMonitoramento();
                    break;

                // ── registrar ticket de monitoramento
                case "registrar-ticket-monitoramento":
                    abrirRegistroTicket();
                    break;

                // ── iniciar monitoramento 30 dias
                case "iniciar-monitoramento":
                    await iniciarMonitoramento();
                    break;

                // ── nova reincidência (reabrir de Monitoramento)
                case "reabrir":
                    abrirNovaOcorrencia();
                    break;

                // ── concluir monitoramento
                case "concluir":
                    abrirConclusao();
                    break;

                // ── reabrir finalizado
                case "reabrir-finalizado":
                    abrirReabrirFinalizado();
                    break;

                // ── excluir
                case "excluir":
                    await excluir();
                    break;

                default:
                    break;
            }
        } catch (error) {
            window.RREIP.showToast(error?.message || "Erro ao executar ação.", "error");
        } finally {
            unlockBtn(el);
        }
    });

    /* ---------------------------------------------------------------------- *
     * 21. BOTÃO COPIAR OTRS (fora do delegador, ID fixo)
     * ---------------------------------------------------------------------- */
    const btnCopiarOtrs = document.getElementById("rreipBtnCopiarTextoOtrs");
    if (btnCopiarOtrs) {
        btnCopiarOtrs.addEventListener("click", copiarTextoOtrs);
    }

    /* ---------------------------------------------------------------------- *
     * 22. INICIALIZAÇÃO
     * ---------------------------------------------------------------------- */
    function init() {
        // histórico — carregado dinamicamente (completa o que o Django já renderizou)
        carregarHistorico();

        // se painel OTRS já tiver texto (preenchido pelo Django), não recarregar
        if (textoOtrsInline && !textoOtrsInline.value.trim()) {
            // deixa vazio até o usuário clicar em Gerar
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    /* ---------------------------------------------------------------------- *
     * 23. API PÚBLICA
     * ---------------------------------------------------------------------- */
    window.RREIPDetalhes = {
        recarregarDados:       carregarDadosAtuais,
        recarregarHistorico:   carregarHistorico,
        abrirEdicao,
        abrirAnalise,
        abrirClassificacao,
        abrirTransferencia,
        abrirNovaOcorrencia,
        abrirConclusao,
        abrirReabrirFinalizado,
    };

})();
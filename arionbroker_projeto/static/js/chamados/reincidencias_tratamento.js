/* ==========================================================================
 * Módulo: Tratamento RREIP (Client-side)
 * Descrição: Regras e eventos específicos para a fila de Tratamento.
 * ========================================================================== */
(function () {
    "use strict";

    // 1. INICIALIZAÇÃO
    const wrapper = document.getElementById("rreipWrapper");

    if (!wrapper) return;
    if (wrapper.dataset.filaAtual !== "TRATAMENTO") return;
    if (!window.RREIP) {
        console.error("Core RREIP não carregado.");
        return;
    }

    if (wrapper.dataset.tratamentoJsInicializado === "true") return;
    wrapper.dataset.tratamentoJsInicializado = "true";

    const {
        requestApi,
        showToast,
        showConfirm,
        openModal,
        closeModal,
        setFormLoading,
        applyApiErrors,
        resetFormErrors,
        buildEndpoint,
        loadDetails,
        loadUsers,
        fillProjectSelect,
        updateIdentifierLabel,
        getValue,
        setValue,
        toDatetimeLocal,
        copyText
    } = window.RREIP;


    // 2. NOVA REINCIDÊNCIA
    const formNovo = document.getElementById("rreipFormNovo");
    
    function abrirNovo() {
        if (formNovo) {
            formNovo.reset();
            resetFormErrors(formNovo);
            const selectOperadora = document.getElementById("rreipNovoOperadora");
            if (selectOperadora) {
                // Dispara o change para popular projeto com a option vazia
                selectOperadora.dispatchEvent(new Event("change"));
            }
        }
        openModal("rreipModalNovo");
        setTimeout(() => {
            const primeiroCampo = document.getElementById("rreipNovoTicketOrigem");
            if (primeiroCampo) primeiroCampo.focus();
        }, 100);
    }

    async function enviarNovaReincidencia(e) {
        e.preventDefault();
        resetFormErrors(formNovo);

        const ticketOrigem = getValue(formNovo, "ticket_origem");
        const urlTicketOrigem = getValue(formNovo, "url_ticket_origem");
        const dataTicketOrigem = getValue(formNovo, "data_ticket_origem");

        const dados = {
            // Compatibilidade com o backend atual
            ticket_atual: ticketOrigem,
            url_ticket: urlTicketOrigem,
            data_ticket: dataTicketOrigem,

            // Campos da estrutura nova de ticket de origem
            ticket_origem: ticketOrigem,
            url_ticket_origem: urlTicketOrigem,
            data_ticket_origem: dataTicketOrigem,

            operadora: getValue(formNovo, "operadora"),
            projeto: getValue(formNovo, "projeto"),
            identificador_projeto: getValue(formNovo, "identificador_projeto"),
            designacao: getValue(formNovo, "designacao"),
            cliente: getValue(formNovo, "cliente"),
            isp: getValue(formNovo, "isp")
        };

        if (!ticketOrigem) {
            showToast("Informe o ticket de origem.", "error");
            document.getElementById("rreipNovoTicketOrigem")?.focus();
            return;
        }

        if (!dados.operadora) {
            showToast("Selecione a operadora.", "error");
            document.getElementById("rreipNovoOperadora")?.focus();
            return;
        }

        if (!dados.projeto) {
            showToast("Selecione o projeto.", "error");
            document.getElementById("rreipNovoProjeto")?.focus();
            return;
        }

        if (!dados.designacao) {
            showToast("Informe a designação.", "error");
            document.getElementById("rreipNovoDesignacao")?.focus();
            return;
        }

        setFormLoading(formNovo, true, "Criando...");

        try {
            await requestApi(wrapper.dataset.urlCriar, {
                method: "POST",
                body: dados
            });

            showToast("Reincidência criada com sucesso.", "success");
            closeModal("rreipModalNovo");
            window.RREIP.refreshSummary();

            setTimeout(() => {
                window.location.reload();
            }, 500);
        } catch (error) {
            applyApiErrors(formNovo, error);
        } finally {
            setFormLoading(formNovo, false);
        }
    }

    if (formNovo) {
        formNovo.addEventListener("submit", enviarNovaReincidencia);
    }


    // 3. OPERADORA E PROJETO
    function bindProjectDependencies(prefix) {
        const opSelect = document.getElementById(`${prefix}Operadora`);
        const projSelect = document.getElementById(`${prefix}Projeto`);
        const identInput = document.getElementById(`${prefix}Identificador`);

        if (opSelect && projSelect) {
            opSelect.addEventListener("change", () => {
                fillProjectSelect(projSelect, opSelect.value, "");
                if (identInput) identInput.value = "";
                projSelect.dispatchEvent(new Event("change"));
            });
            
            projSelect.addEventListener("change", () => {
                const label = window.RREIP.updateIdentifierLabel(projSelect.value, opSelect.value);
                const labelEl = document.getElementById(`${prefix}IdentificadorLabel`);
                if (labelEl) labelEl.textContent = label;
                if (identInput) identInput.placeholder = `Informe a(o) ${label}`;
            });
        }
    }
    bindProjectDependencies("rreipNovo");
    bindProjectDependencies("rreipEditar");


    // 4. EDIÇÃO
    const formEditar = document.getElementById("rreipFormEditar");

    async function abrirEdicao(id) {
        if (formEditar) {
            formEditar.reset();
            resetFormErrors(formEditar);
        }
        
        openModal("rreipModalEditar");
        // O modal não tem containerLoading pronto no Base, então exibimos um toast de status
        showToast("Carregando dados...", "info", { duration: 1500 });

        try {
            const dados = await loadDetails(id);
            if (dados) {
                setValue("rreipEditarId", dados.id);
                setValue("rreipEditarTicketOrigem", dados.ticket_origem || dados.ticket_atual);
                setValue("rreipEditarUrlTicketOrigem", dados.url_ticket_origem || dados.url_ticket);
                setValue("rreipEditarDataTicketOrigem", toDatetimeLocal(dados.data_ticket_origem || dados.data_ticket));
                setValue("rreipEditarDataEncerramentoOrigem", toDatetimeLocal(dados.data_encerramento_origem));
                
                setValue("rreipEditarOperadora", dados.operadora);
                fillProjectSelect(document.getElementById("rreipEditarProjeto"), dados.operadora, dados.projeto);
                
                setValue("rreipEditarIdentificador", dados.identificador_projeto);
                setValue("rreipEditarDesignacao", dados.designacao);
                setValue("rreipEditarCliente", dados.cliente);
                setValue("rreipEditarISP", dados.isp);

                document.getElementById("rreipEditarProjeto")?.dispatchEvent(new Event("change"));
            }
        } catch (error) {
            showToast("Não foi possível carregar os dados para edição.", "error");
            closeModal("rreipModalEditar");
        }
    }

    async function enviarEdicao(e) {
        e.preventDefault();
        resetFormErrors(formEditar);

        const id = getValue(formEditar, "id");
        if (!id) return;

        const dados = {
            ticket_origem: getValue(formEditar, "ticket_origem"),
            url_ticket_origem: getValue(formEditar, "url_ticket_origem"),
            data_ticket_origem: getValue(formEditar, "data_ticket_origem"),
            data_encerramento_origem: getValue(formEditar, "data_encerramento_origem"),
            operadora: getValue(formEditar, "operadora"),
            projeto: getValue(formEditar, "projeto"),
            identificador_projeto: getValue(formEditar, "identificador_projeto"),
            designacao: getValue(formEditar, "designacao"),
            cliente: getValue(formEditar, "cliente"),
            isp: getValue(formEditar, "isp")
        };

        setFormLoading(formEditar, true, "Salvando...");
        try {
            await requestApi(buildEndpoint(id, "editar"), {
                method: "POST",
                body: dados
            });
            showToast("Reincidência atualizada com sucesso.", "success");
            closeModal("rreipModalEditar");
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            applyApiErrors(formEditar, error);
        } finally {
            setFormLoading(formEditar, false);
        }
    }

    if (formEditar) {
        formEditar.addEventListener("submit", enviarEdicao);
    }


    // 5. CLASSIFICAÇÃO
    const formClassificar = document.getElementById("rreipFormClassificar");

    async function abrirClassificacao(id) {
        if (formClassificar) {
            formClassificar.reset();
            resetFormErrors(formClassificar);
        }
        
        openModal("rreipModalClassificar");
        try {
            const dados = await loadDetails(id);
            if (dados) {
                setValue("rreipClassificarId", dados.id);
                setValue("rreipClassificarValor", dados.classificacao);
                setValue("rreipClassificarMotivo", dados.motivo_classificacao);
            }
        } catch (error) {
            showToast("Falha ao carregar classificação.", "error");
            closeModal("rreipModalClassificar");
        }
    }

    async function enviarClassificacao(e) {
        e.preventDefault();
        resetFormErrors(formClassificar);

        const id = getValue(formClassificar, "id");
        if (!id) return;

        const classificacao = getValue(formClassificar, "classificacao");
        const dados = {
            classificacao: classificacao,
            motivo: getValue(formClassificar, "motivo")
        };

        const reincidenciaConfirmada = classificacao === "REINCIDENCIA_CONFIRMADA" || classificacao === "PENDENTE";

        setFormLoading(formClassificar, true, "Classificando...");
        try {
            const res = await requestApi(buildEndpoint(id, "classificar"), {
                method: "POST",
                body: dados
            });
            
            showToast(res.mensagem || "Classificação salva com sucesso.", "success");
            closeModal("rreipModalClassificar");
            window.RREIP.refreshSummary();
            
            if (!reincidenciaConfirmada) {
                // Se foi descartada, o ideal é recarregar a lista pro item sumir da tabela
                setTimeout(() => window.location.reload(), 500);
            } else {
                // Mantém na tela e atualiza a badge
                const row = document.querySelector(`.rreip-row[data-id="${id}"]`);
                if (row) {
                    const statusTd = row.querySelector(".rreip-col-status");
                    const statusSelect = statusTd.querySelector("select");
                    if (statusSelect && statusSelect.value === "NOVO") {
                        statusSelect.value = "EM_ANALISE";
                        statusSelect.dataset.valorAnterior = "EM_ANALISE";
                    }
                    const payload = window.RREIP.unwrapResponse(res);
                    const classTd = row.querySelector(".rreip-col-classificacao");
                    if (classTd && payload.classificacao_display) {
                        classTd.innerHTML = `<span class="rreip-classificacao rreip-classificacao--confirmada">${payload.classificacao_display}</span>`;
                    }
                }
            }
        } catch (error) {
            applyApiErrors(formClassificar, error);
        } finally {
            setFormLoading(formClassificar, false);
        }
    }

    if (formClassificar) {
        formClassificar.addEventListener("submit", enviarClassificacao);
        
        // Listener visual pro Select de Classificação pra orientar o User
        const selectClassif = document.getElementById("rreipClassificarValor");
        const labelAviso = document.getElementById("rreipClassificarAviso");
        if (selectClassif && labelAviso) {
            selectClassif.addEventListener("change", (e) => {
                const val = e.target.value;
                if (val === "PENDENTE" || val === "REINCIDENCIA_CONFIRMADA") {
                    labelAviso.textContent = "O registro continuará na fila de Tratamento.";
                    labelAviso.style.color = "var(--rreip-text-muted)";
                } else {
                    labelAviso.textContent = "Atenção: O registro será movido para Finalizados e descartado do RREIP.";
                    labelAviso.style.color = "var(--rreip-warning)";
                }
            });
        }
    }


    // 6. ANÁLISE
    const formAnalise = document.getElementById("rreipFormAnalise");

    async function abrirAnalise(id) {
        if (formAnalise) {
            formAnalise.reset();
            resetFormErrors(formAnalise);
        }
        openModal("rreipModalAnalise");

        try {
            const dados = await loadDetails(id);
            if (dados) {
                setValue("rreipAnaliseId", dados.id);
                setValue("rreipAnaliseMotivo", dados.motivo_identificado);
                setValue("rreipAnaliseCausa", dados.causa_raiz);
                setValue("rreipAnaliseAcaoRealizada", dados.acao_realizada);
                setValue("rreipAnaliseAcaoPreventiva", dados.acao_preventiva);
                setValue("rreipAnaliseConclusao", dados.conclusao);
            }
        } catch (error) {
            showToast("Falha ao carregar análise.", "error");
            closeModal("rreipModalAnalise");
        }
    }

    async function enviarAnalise(e) {
        e.preventDefault();
        resetFormErrors(formAnalise);

        const id = getValue(formAnalise, "id");
        if (!id) return;

        const dados = {
            motivo_identificado: getValue(formAnalise, "motivo_identificado"),
            causa_raiz: getValue(formAnalise, "causa_raiz"),
            acao_realizada: getValue(formAnalise, "acao_realizada"),
            acao_preventiva: getValue(formAnalise, "acao_preventiva"),
            conclusao: getValue(formAnalise, "conclusao")
        };

        setFormLoading(formAnalise, true, "Salvando...");
        try {
            await requestApi(buildEndpoint(id, "salvar-analise"), {
                method: "POST",
                body: dados
            });
            showToast("Análise salva com sucesso.", "success");
            closeModal("rreipModalAnalise");
            window.RREIP.refreshSummary();
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            applyApiErrors(formAnalise, error);
        } finally {
            setFormLoading(formAnalise, false);
        }
    }

    if (formAnalise) {
        formAnalise.addEventListener("submit", enviarAnalise);
    }


    // 7. PRÉVIA E ENVIO DE E-MAIL
    async function abrirPreviaEmail(id) {
        openModal("rreipModalEmailMonitoramento");
        const btnEnviar = document.getElementById("rreipBtnConfirmarEnvioEmail");
        if (btnEnviar) {
            btnEnviar.disabled = true;
            btnEnviar.textContent = "Carregando...";
        }

        try {
            const url = buildEndpoint(id, "previa-email-monitoramento");
            const res = await requestApi(url);
            const dados = res.dados || {};

            document.getElementById("rreipEmailRegistroId").value = id;
            document.getElementById("rreipEmailAssunto").textContent = dados.assunto || "Sem assunto gerado";
            document.getElementById("rreipEmailCorpo").textContent = dados.corpo || "Sem corpo de texto";
            
            if (btnEnviar) {
                btnEnviar.disabled = false;
                btnEnviar.textContent = "Enviar solicitação";
            }
        } catch (error) {
            showToast("Não foi possível carregar a prévia do e-mail.", "error");
            closeModal("rreipModalEmailMonitoramento");
        }
    }

    async function dispararEnvioEmail() {
        const id = document.getElementById("rreipEmailRegistroId").value;
        if (!id) return;

        const ok = await showConfirm("O e-mail será despachado via SMTP para as caixas configuradas do projeto. Confirma o envio?");
        if (!ok) return;

        const btnEnviar = document.getElementById("rreipBtnConfirmarEnvioEmail");
        window.RREIP.setLoading(btnEnviar, true, "Enviando...");

        try {
            const url = buildEndpoint(id, "enviar-email-monitoramento");
            const res = await requestApi(url, { method: "POST" });
            
            showToast(res.mensagem || "Solicitação de monitoramento enviada com sucesso.", "success");
            closeModal("rreipModalEmailMonitoramento");
            window.RREIP.refreshSummary();
            setTimeout(() => window.location.reload(), 800);
        } catch (error) {
            showToast(error.message || "Erro no envio do e-mail.", "error");
        } finally {
            window.RREIP.setLoading(btnEnviar, false);
        }
    }

    const btnEnvioEmail = document.getElementById("rreipBtnConfirmarEnvioEmail");
    if (btnEnvioEmail) {
        btnEnvioEmail.addEventListener("click", dispararEnvioEmail);
    }


    // 8. REGISTRAR TICKET OTRS (Segundo Ticket)
    const formTicketMonitoramento = document.getElementById("rreipFormTicketMonitoramento");

    function abrirTicketMonitoramento(id) {
        if (formTicketMonitoramento) {
            formTicketMonitoramento.reset();
            resetFormErrors(formTicketMonitoramento);
            setValue("rreipTicketMonitoramentoId", id);
        }
        openModal("rreipModalTicketMonitoramento");
        setTimeout(() => {
            const campo = document.getElementById("rreipTicketMonitoramentoNumero");
            if (campo) campo.focus();
        }, 100);
    }

    async function enviarTicketMonitoramento(e) {
        e.preventDefault();
        resetFormErrors(formTicketMonitoramento);

        const id = getValue(formTicketMonitoramento, "id");
        if (!id) return;

        const dados = {
            ticket_monitoramento: getValue(formTicketMonitoramento, "ticket_monitoramento"),
            url_ticket_monitoramento: getValue(formTicketMonitoramento, "url_ticket_monitoramento"),
            data_ticket_monitoramento: getValue(formTicketMonitoramento, "data_ticket_monitoramento")
        };

        setFormLoading(formTicketMonitoramento, true, "Salvando...");
        try {
            await requestApi(buildEndpoint(id, "registrar-ticket-monitoramento"), {
                method: "POST",
                body: dados
            });
            showToast("Ticket de monitoramento registrado.", "success");
            closeModal("rreipModalTicketMonitoramento");
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            applyApiErrors(formTicketMonitoramento, error);
        } finally {
            setFormLoading(formTicketMonitoramento, false);
        }
    }

    if (formTicketMonitoramento) {
        formTicketMonitoramento.addEventListener("submit", enviarTicketMonitoramento);
    }


    // 9. INICIAR 30 DIAS
    async function dispararIniciarMonitoramento(id, btn) {
        const ok = await showConfirm("O ticket do OTRS confere? O relógio de 30 dias será iniciado agora.");
        if (!ok) return;

        window.RREIP.setLoading(btn, true);
        try {
            await requestApi(buildEndpoint(id, "mover-monitoramento"), { method: "POST" });
            showToast("Monitoramento de 30 dias iniciado com sucesso.", "success");
            window.RREIP.refreshSummary();
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            window.RREIP.setLoading(btn, false);
        }
    }


    // 10. TRANSFERIR
    const formTransferir = document.getElementById("rreipFormTransferir");

    async function abrirTransferencia(id) {
        if (formTransferir) {
            formTransferir.reset();
            resetFormErrors(formTransferir);
            setValue("rreipTransferirId", id);
        }
        
        openModal("rreipModalTransferir");

        try {
            const usuarios = await loadUsers();
            const select = document.getElementById("rreipTransferirUsuario");
            if (select) {
                select.innerHTML = '<option value="">Selecione um responsável</option>';
                usuarios.forEach(u => {
                    const opt = document.createElement("option");
                    opt.value = u.id;
                    opt.textContent = u.nome || u.username;
                    select.appendChild(opt);
                });
            }
        } catch (e) {
            closeModal("rreipModalTransferir");
        }
    }

    async function enviarTransferencia(e) {
        e.preventDefault();
        resetFormErrors(formTransferir);

        const id = getValue(formTransferir, "id");
        const responsavel_id = getValue(formTransferir, "responsavel_id");
        if (!id || !responsavel_id) {
            showToast("Selecione um usuário válido.", "error");
            return;
        }

        setFormLoading(formTransferir, true);
        try {
            await requestApi(buildEndpoint(id, "transferir"), {
                method: "POST",
                body: { responsavel_id }
            });
            showToast("Responsável transferido.", "success");
            closeModal("rreipModalTransferir");
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            applyApiErrors(formTransferir, error);
        } finally {
            setFormLoading(formTransferir, false);
        }
    }

    if (formTransferir) {
        formTransferir.addEventListener("submit", enviarTransferencia);
    }


    // 11. TEXTO OTRS (COPIAR)
    async function abrirTextoOtrs(id) {
        openModal("rreipModalTextoOtrs");
        const textArea = document.getElementById("rreipTextoOtrsConteudo");
        if (textArea) textArea.value = "Carregando...";

        try {
            const res = await requestApi(buildEndpoint(id, "texto-otrs"));
            if (textArea) textArea.value = res.dados?.texto || "";
        } catch (error) {
            showToast("Erro ao gerar o texto OTRS.", "error");
            closeModal("rreipModalTextoOtrs");
        }
    }

    const btnCopiarOtrs = document.getElementById("rreipBtnCopiarTextoOtrs");
    if (btnCopiarOtrs) {
        btnCopiarOtrs.addEventListener("click", () => {
            const txt = document.getElementById("rreipTextoOtrsConteudo").value;
            copyText(txt, "Texto copiado. Cole no OTRS.");
        });
    }


    // 12. AÇÕES DIRETAS (Apropriar, Liberar, Excluir, Status)
    async function executarApropriar(id, btn) {
        window.RREIP.setLoading(btn, true);
        try {
            await requestApi(buildEndpoint(id, "apropriar"), { method: "POST" });
            showToast("Reincidência apropriada.", "success");
            setTimeout(() => window.location.reload(), 300);
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            window.RREIP.setLoading(btn, false);
        }
    }

    async function executarLiberar(id, btn) {
        const ok = await showConfirm("A reincidência ficará sem responsável. Deseja continuar?");
        if (!ok) return;
        window.RREIP.setLoading(btn, true);
        try {
            await requestApi(buildEndpoint(id, "liberar"), { method: "POST" });
            showToast("Responsável liberado.", "success");
            setTimeout(() => window.location.reload(), 300);
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            window.RREIP.setLoading(btn, false);
        }
    }

    async function executarExcluir(id, btn) {
        const ok = await showConfirm("ATENÇÃO: Esta exclusão é definitiva e deve ser usada somente para registro criado por engano ou teste. Deseja continuar?", { danger: true });
        if (!ok) return;
        window.RREIP.setLoading(btn, true);
        try {
            await requestApi(buildEndpoint(id, "excluir"), { method: "POST" });
            showToast("Registro excluído permanentemente.", "success");
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            showToast(error.message, "error");
        } finally {
            window.RREIP.setLoading(btn, false);
        }
    }

    async function alterarStatusTabela(id, status, select) {
        try {
            await requestApi(buildEndpoint(id, "status"), {
                method: "POST",
                body: { status }
            });
            showToast("Status atualizado.", "success");
            select.dataset.valorAnterior = status;
            window.RREIP.refreshSummary();
        } catch (error) {
            showToast(error.message, "error");
            select.value = select.dataset.valorAnterior;
        }
    }


    // 13. DELEGAÇÃO CENTRAL DE CLIQUES E MUDANÇAS
    document.addEventListener("change", (e) => {
        if (e.target.dataset.action === "alterar-status") {
            const id = e.target.dataset.id;
            const status = e.target.value;
            if (!e.target.dataset.valorAnterior) {
                e.target.dataset.valorAnterior = e.target.querySelector("option[selected]")?.value || "";
            }
            alterarStatusTabela(id, status, e.target);
        }
    });

    wrapper.addEventListener("click", (e) => {
        const data = window.RREIP.getActionData(e);
        if (!data) return;

        const { action, id, button } = data;

        if (action === "novo") {
            abrirNovo();
            return;
        }

        if (!id) return;

        switch (action) {
            case "editar":
                abrirEdicao(id);
                break;
            case "classificar":
                abrirClassificacao(id);
                break;
            case "analise":
                abrirAnalise(id);
                break;
            case "enviar-email-monitoramento":
                abrirPreviaEmail(id);
                break;
            case "registrar-ticket-monitoramento":
                abrirTicketMonitoramento(id);
                break;
            case "iniciar-monitoramento":
                dispararIniciarMonitoramento(id, button);
                break;
            case "apropriar":
                executarApropriar(id, button);
                break;
            case "liberar":
                executarLiberar(id, button);
                break;
            case "transferir":
                abrirTransferencia(id);
                break;
            case "excluir":
                executarExcluir(id, button);
                break;
            case "copiar-otrs":
                abrirTextoOtrs(id);
                break;
        }
    });


    // 14. MENU DE AÇÕES (DROPDOWN FLUTUANTE)
   document.addEventListener("toggle", function (e) {
    if (!e.target.matches(".rreip-actions-menu")) return;
    const menu = e.target;
    if (!menu.open) return;

    const summary = menu.querySelector("summary");
    const content = menu.querySelector(".rreip-actions-menu__content");
    if (!summary || !content) return;

    // Força um reflow antes de medir, evita offsetWidth/Height = 0
    requestAnimationFrame(() => {
        const rect = summary.getBoundingClientRect();
        const menuWidth = content.offsetWidth || 200;
        const menuHeight = content.offsetHeight || 150;

        let left = rect.right - menuWidth;
        if (left < 8) left = 8;
        if (left + menuWidth > window.innerWidth - 8) {
            left = window.innerWidth - menuWidth - 8;
        }

        let top = rect.bottom + 4;
        if (top + menuHeight > window.innerHeight - 8) {
            top = rect.top - menuHeight - 4;
        }
        if (top < 8) top = 8;

        content.style.top = `${top}px`;
        content.style.left = `${left}px`;
    });
}, true);

    // Fecha o menu ao clicar fora dele
    document.addEventListener("click", function (e) {
        document.querySelectorAll(".rreip-actions-menu[open]").forEach((menu) => {
            if (!menu.contains(e.target)) menu.removeAttribute("open");
        });
    });

    // Fecha o menu ao rolar a tabela (evita ele "flutuando" fora de lugar)
    document.addEventListener("scroll", function () {
        document.querySelectorAll(".rreip-actions-menu[open]").forEach((menu) => {
            menu.removeAttribute("open");
        });
    }, true);

})();
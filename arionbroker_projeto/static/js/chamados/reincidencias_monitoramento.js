/* ==========================================================================
 * 1. Inicialização e referências
 * ========================================================================== */
(function () {
    "use strict";

    const wrapper = document.getElementById("rreipWrapper");

    if (!wrapper || !window.RREIP) {
        return;
    }

    if (wrapper.dataset.monitoramentoJsInicializado === "true") {
        return;
    }

    wrapper.dataset.monitoramentoJsInicializado = "true";

    const urlCriar = wrapper.dataset.urlCriar;
    const apiBase = urlCriar.replace(/criar\/?$/, "");

    const modalEditar = document.getElementById("rreipModalEditar");
    const modalAnalise = document.getElementById("rreipModalAnalise");
    const modalDetalhes = document.getElementById("rreipModalDetalhes");
    const modalTransferir = document.getElementById("rreipModalTransferir");
    const modalReabrir = document.getElementById("rreipModalReabrir");
    const modalConcluir = document.getElementById("rreipModalConcluir");

    const formEditar = document.getElementById("rreipFormEditar");
    const formAnalise = document.getElementById("rreipFormAnalise");
    const formTransferir = document.getElementById("rreipFormTransferir");
    const formReabrir = document.getElementById("rreipFormReabrir");
    const formConcluir = document.getElementById("rreipFormConcluir");

    /* ==========================================================================
     * 2. Helpers de formulário
     * ========================================================================== */
    function definirValor(element, value) {
        if (!element) return;
        element.value = value || "";
    }

    function obterValor(form, name) {
        const campo = obterCampo(form, name);
        if (!campo) return "";
        return typeof campo.value === "string" ? campo.value.trim() : campo.value;
    }

    function obterCampo(form, name) {
        return form.querySelector(`[name="${name}"]`);
    }

    function converterParaDatetimeLocal(value) {
        if (!value) return "";
        try {
            if (value.length >= 16 && value.includes("T")) {
                return value.substring(0, 16);
            }
            return "";
        } catch (e) {
            return "";
        }
    }

    function extrairDadosResposta(response) {
        return response?.dados || response || {};
    }

    /* ==========================================================================
     * 3. Loading e erros
     * ========================================================================== */
    function setFormLoading(form, loading, text = "Salvando...") {
        const button = form.querySelector('button[type="submit"]');
        if (!button) return;

        if (loading) {
            if (!button.dataset.originalContent) {
                button.dataset.originalContent = button.innerHTML;
            }
            button.disabled = true;
            button.classList.add("is-loading");
            button.innerHTML = `<span class="rreip-btn-spinner"></span> ${text}`;
        } else {
            button.disabled = false;
            button.classList.remove("is-loading");
            if (button.dataset.originalContent) {
                button.innerHTML = button.dataset.originalContent;
                delete button.dataset.originalContent;
            }
        }
    }

    function definirModalCarregando(modal, carregando) {
        if (!modal) return;
        if (carregando) {
            modal.classList.add("is-loading");
        } else {
            modal.classList.remove("is-loading");
        }
    }

    function resetarErros(form) {
        if (!form) return;
        form.querySelectorAll("[aria-invalid]").forEach(el => el.removeAttribute("aria-invalid"));
        form.querySelectorAll(".rreip-form-error").forEach(el => el.remove());
    }

    function mostrarErroCampo(campo, mensagem) {
        if (!campo) return;
        campo.setAttribute("aria-invalid", "true");
        
        const errorEl = document.createElement("div");
        errorEl.className = "rreip-form-error";
        errorEl.textContent = mensagem;
        
        campo.parentNode.appendChild(errorEl);
    }

    function aplicarErrosApi(form, error) {
        resetarErros(form);
        
        const dados = error?.data || {};
        const camposComErro = dados.campos || dados.errors;
        
        if (camposComErro && typeof camposComErro === "object") {
            let focouPrimeiro = false;
            
            for (const [name, messages] of Object.entries(camposComErro)) {
                const campo = obterCampo(form, name);
                if (campo) {
                    const msg = Array.isArray(messages) ? messages[0] : messages;
                    mostrarErroCampo(campo, msg);
                    if (!focouPrimeiro) {
                        campo.focus();
                        focouPrimeiro = true;
                    }
                }
            }
            if (focouPrimeiro) return;
        }

        const msgGeral = error?.message || "Ocorreu um erro ao concluir a operação.";
        window.RREIP.showToast(msgGeral, "error");
    }

    /* ==========================================================================
     * 4. Operadora, projeto e identificador
     * ========================================================================== */
    function preencherProjetosEdicao(operadora, projetoAtual) {
        const selectProjeto = document.getElementById("rreipEditarProjeto");
        if (!selectProjeto) return;

        selectProjeto.innerHTML = '<option value="">Selecione o projeto</option>';
        
        if (!operadora && !projetoAtual) return;

        let projetosList = window.RREIP.PROJETOS_POR_OPERADORA[operadora];
        if (!projetosList && operadora) projetosList = window.RREIP.PROJETOS_POR_OPERADORA["Outros"];
        
        if (projetoAtual && (!projetosList || !projetosList.includes(projetoAtual))) {
            projetosList = projetosList ? [...projetosList, projetoAtual] : [projetoAtual];
        }

        if (projetosList) {
            projetosList.forEach(proj => {
                const option = document.createElement("option");
                option.value = proj;
                option.textContent = proj;
                if (proj === projetoAtual) option.selected = true;
                selectProjeto.appendChild(option);
            });
        }
        
        atualizarLabelIdentificadorEdicao();
    }

    function atualizarLabelIdentificadorEdicao() {
        const selectProjeto = document.getElementById("rreipEditarProjeto");
        const labelEl = document.getElementById("rreipEditarIdentificadorLabel");
        const inputIdent = document.getElementById("rreipEditarIdentificador");

        if (selectProjeto && labelEl && inputIdent) {
            const projeto = selectProjeto.value;
            const labelStr = window.RREIP.obterIdentificadorLabel(projeto);
            
            labelEl.textContent = labelStr;
            inputIdent.placeholder = `Informe o ${labelStr}`;
        }
    }

    const editarOperadora = document.getElementById("rreipEditarOperadora");
    if (editarOperadora) {
        editarOperadora.addEventListener("change", () => {
            preencherProjetosEdicao(editarOperadora.value, null);
        });
    }

    const editarProjeto = document.getElementById("rreipEditarProjeto");
    if (editarProjeto) {
        editarProjeto.addEventListener("change", atualizarLabelIdentificadorEdicao);
    }

    /* ==========================================================================
     * 5. Edição
     * ========================================================================== */
    async function abrirEdicao(id) {
        if (!id) return;
        
        if (formEditar) {
            formEditar.reset();
            resetarErros(formEditar);
        }

        window.RREIP.openModal("rreipModalEditar");
        definirModalCarregando(modalEditar, true);

        try {
            const dados = await window.RREIP.carregarDetalhes(id);
            if (dados) {
                definirValor(document.getElementById("rreipEditarId"), dados.id);
                definirValor(document.getElementById("rreipEditarTicket"), dados.ticket_atual);
                definirValor(document.getElementById("rreipEditarUrlTicket"), dados.url_ticket);
                definirValor(document.getElementById("rreipEditarOperadora"), dados.operadora);
                
                preencherProjetosEdicao(dados.operadora, dados.projeto);
                
                definirValor(document.getElementById("rreipEditarIdentificador"), dados.identificador_projeto);
                definirValor(document.getElementById("rreipEditarDesignacao"), dados.designacao);
                definirValor(document.getElementById("rreipEditarCliente"), dados.cliente);
                definirValor(document.getElementById("rreipEditarISP"), dados.isp);
                
                const dataFormatada = converterParaDatetimeLocal(dados.data_ticket);
                definirValor(document.getElementById("rreipEditarDataTicket"), dataFormatada);
            }
        } catch (error) {
            window.RREIP.showToast("Não foi possível carregar os dados para edição.", "error");
            window.RREIP.closeModal("rreipModalEditar");
        } finally {
            definirModalCarregando(modalEditar, false);
        }
    }

    async function enviarEdicao(e) {
        e.preventDefault();
        resetarErros(formEditar);

        const id = obterValor(formEditar, "id");
        if (!id) return;

        const dados = {
            ticket_atual: obterValor(formEditar, "ticket_atual"),
            url_ticket: obterValor(formEditar, "url_ticket"),
            operadora: obterValor(formEditar, "operadora"),
            projeto: obterValor(formEditar, "projeto"),
            identificador_projeto: obterValor(formEditar, "identificador_projeto"),
            designacao: obterValor(formEditar, "designacao"),
            cliente: obterValor(formEditar, "cliente"),
            isp: obterValor(formEditar, "isp"),
            data_ticket: obterValor(formEditar, "data_ticket"),
        };

        setFormLoading(formEditar, true, "Salvando...");
        try {
            await window.RREIP.requestApi(`${apiBase}${id}/editar/`, {
                method: "POST",
                body: dados
            });
            window.RREIP.showToast("Reincidência atualizada com sucesso.", "success");
            window.RREIP.closeModal("rreipModalEditar");
            window.RREIP.atualizarResumo();
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            aplicarErrosApi(formEditar, error);
            setFormLoading(formEditar, false);
        }
    }

    if (formEditar) {
        formEditar.addEventListener("submit", enviarEdicao);
    }

    /* ==========================================================================
     * 6. Análise
     * ========================================================================== */
    async function abrirAnalise(id) {
        if (!id) return;
        
        if (formAnalise) {
            formAnalise.reset();
            resetarErros(formAnalise);
        }

        window.RREIP.openModal("rreipModalAnalise");
        definirModalCarregando(modalAnalise, true);

        try {
            const dados = await window.RREIP.carregarDetalhes(id);
            if (dados) {
                definirValor(document.getElementById("rreipAnaliseId"), dados.id);
                definirValor(document.getElementById("rreipAnaliseMotivo"), dados.motivo_identificado);
                definirValor(document.getElementById("rreipAnaliseCausa"), dados.causa_raiz);
                definirValor(document.getElementById("rreipAnaliseAcao"), dados.acao_preventiva);
                definirValor(document.getElementById("rreipAnaliseConclusao"), dados.conclusao);

                if (dados.pode_editar === false) {
                    formAnalise.querySelectorAll("textarea").forEach(el => el.readOnly = true);
                    const btnSubmit = formAnalise.querySelector('button[type="submit"]');
                    if (btnSubmit) btnSubmit.style.display = "none";
                } else {
                    formAnalise.querySelectorAll("textarea").forEach(el => el.readOnly = false);
                    const btnSubmit = formAnalise.querySelector('button[type="submit"]');
                    if (btnSubmit) btnSubmit.style.display = "";
                }
            }
        } catch (error) {
            window.RREIP.showToast("Não foi possível carregar a análise.", "error");
            window.RREIP.closeModal("rreipModalAnalise");
        } finally {
            definirModalCarregando(modalAnalise, false);
        }
    }

    async function enviarAnalise(e) {
        e.preventDefault();
        resetarErros(formAnalise);

        const id = obterValor(formAnalise, "id");
        if (!id) return;

        const dados = {
            motivo_identificado: obterValor(formAnalise, "motivo_identificado"),
            causa_raiz: obterValor(formAnalise, "causa_raiz"),
            acao_preventiva: obterValor(formAnalise, "acao_preventiva"),
            conclusao: obterValor(formAnalise, "conclusao"),
        };

        setFormLoading(formAnalise, true, "Salvando...");
        try {
            await window.RREIP.requestApi(`${apiBase}${id}/salvar-analise/`, {
                method: "POST",
                body: dados
            });
            window.RREIP.showToast("Análise RREIP atualizada com sucesso.", "success");
            window.RREIP.closeModal("rreipModalAnalise");
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            aplicarErrosApi(formAnalise, error);
            setFormLoading(formAnalise, false);
        }
    }

    if (formAnalise) {
        formAnalise.addEventListener("submit", enviarAnalise);
    }

    /* ==========================================================================
     * 7. Transferência
     * ========================================================================== */
    async function abrirTransferencia(id) {
        if (!id) return;
        
        if (formTransferir) {
            formTransferir.reset();
            resetarErros(formTransferir);
            definirValor(document.getElementById("rreipTransferirId"), id);
        }

        window.RREIP.openModal("rreipModalTransferir");
        definirModalCarregando(modalTransferir, true);

        try {
            const usuarios = await window.RREIP.carregarUsuarios();
            const select = document.getElementById("rreipTransferirResponsavel");
            if (select) {
                select.innerHTML = '<option value="">Selecione um responsável</option>';
                usuarios.forEach(usuario => {
                    const option = document.createElement("option");
                    option.value = usuario.id;
                    option.textContent = usuario.nome || usuario.username;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            // Tratado globalmente
        } finally {
            definirModalCarregando(modalTransferir, false);
        }
    }

    async function enviarTransferencia(e) {
        e.preventDefault();
        resetarErros(formTransferir);

        const id = obterValor(formTransferir, "id");
        const responsavelId = obterValor(formTransferir, "responsavel_id");
        if (!id || !responsavelId) return;

        setFormLoading(formTransferir, true, "Transferindo...");
        try {
            await window.RREIP.requestApi(`${apiBase}${id}/transferir/`, {
                method: "POST",
                body: { responsavel_id: responsavelId }
            });
            window.RREIP.showToast("Responsável transferido com sucesso.", "success");
            window.RREIP.closeModal("rreipModalTransferir");
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            aplicarErrosApi(formTransferir, error);
            setFormLoading(formTransferir, false);
        }
    }

    if (formTransferir) {
        formTransferir.addEventListener("submit", enviarTransferencia);
    }

    /* ==========================================================================
     * 8. Reabertura
     * ========================================================================== */
    function abrirReabertura(id) {
        if (!id) return;

        if (formReabrir) {
            formReabrir.reset();
            resetarErros(formReabrir);
            definirValor(document.getElementById("rreipReabrirId"), id);
        }

        window.RREIP.openModal("rreipModalReabrir");
        setTimeout(() => {
            const campoTicket = document.getElementById("rreipReabrirTicket");
            if (campoTicket) campoTicket.focus();
        }, 100);
    }

    async function enviarReabertura(e) {
        e.preventDefault();
        resetarErros(formReabrir);

        const id = obterValor(formReabrir, "id");
        const novoTicket = obterValor(formReabrir, "novo_ticket");
        const urlTicket = obterValor(formReabrir, "url_ticket");
        const dataTicket = obterValor(formReabrir, "data_ticket");

        if (!id || !novoTicket) return;

        const confirmado = await window.RREIP.showConfirm(
            "O registro voltará para a fila de Tratamento e a quantidade de reincidências será incrementada.",
            {
                title: "Registrar nova reincidência",
                confirmText: "Registrar",
                danger: true,
            }
        );

        if (!confirmado) return;

        setFormLoading(formReabrir, true, "Registrando...");
        try {
            await window.RREIP.requestApi(`${apiBase}${id}/reabrir/`, {
                method: "POST",
                body: {
                    novo_ticket: novoTicket,
                    url_ticket: urlTicket,
                    data_ticket: dataTicket,
                }
            });
            window.RREIP.showToast("Nova reincidência registrada. O chamado retornou para Tratamento.", "success");
            window.RREIP.closeModal("rreipModalReabrir");
            window.RREIP.atualizarResumo();

            setTimeout(() => {
                const linkTratamento = document.querySelector('.rreip-tab[href*="tratamento"]');
                if (linkTratamento) {
                    window.location.href = linkTratamento.href;
                } else {
                    window.location.reload();
                }
            }, 500);
        } catch (error) {
            aplicarErrosApi(formReabrir, error);
            setFormLoading(formReabrir, false);
        }
    }

    if (formReabrir) {
        formReabrir.addEventListener("submit", enviarReabertura);
    }

    /* ==========================================================================
     * 9. Conclusão
     * ========================================================================== */
    function abrirConclusao(id, forcar) {
        if (!id) return;

        if (formConcluir) {
            formConcluir.reset();
            resetarErros(formConcluir);
            definirValor(document.getElementById("rreipConcluirId"), id);
            definirValor(document.getElementById("rreipConcluirForcar"), forcar ? "true" : "false");

            const msgEl = document.getElementById("rreipConcluirMensagem");
            if (msgEl) {
                if (forcar) {
                    msgEl.textContent = "O monitoramento ainda está dentro do prazo de 30 dias. Confirma a conclusão antecipada?";
                } else {
                    msgEl.textContent = "Confirma a conclusão do monitoramento desta reincidência?";
                }
            }
        }

        window.RREIP.openModal("rreipModalConcluir");
    }

    async function enviarConclusao(e) {
        e.preventDefault();
        resetarErros(formConcluir);

        const id = obterValor(formConcluir, "id");
        const forcar = obterValor(formConcluir, "forcar") === "true";

        if (!id) return;

        setFormLoading(formConcluir, true, "Concluindo...");
        try {
            await window.RREIP.requestApi(`${apiBase}${id}/concluir/`, {
                method: "POST",
                body: {
                    forcar: forcar ? "true" : "false"
                }
            });

            const msgSucesso = forcar ? "Monitoramento concluído antecipadamente." : "Monitoramento concluído com sucesso.";
            window.RREIP.showToast(msgSucesso, "success");
            window.RREIP.closeModal("rreipModalConcluir");
            window.RREIP.atualizarResumo();
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            aplicarErrosApi(formConcluir, error);
            setFormLoading(formConcluir, false);
        }
    }

    if (formConcluir) {
        formConcluir.addEventListener("submit", enviarConclusao);
    }

    /* ==========================================================================
     * 10. Detalhes e histórico
     * ========================================================================== */
    function criarElemento(tag, className, text) {
        const el = document.createElement(tag);
        if (className) el.className = className;
        if (text !== undefined && text !== null) el.textContent = text;
        return el;
    }

    function criarCampoDetalhe(label, value) {
        const container = criarElemento("div", "rreip-details-item");
        container.appendChild(criarElemento("strong", "rreip-details-item__label", label + ": "));
        
        let valStr = window.RREIP.textoOuTraco(value);
        if (label === "Ticket" && value && value.url) {
            const link = criarElemento("a", "rreip-ticket rreip-ticket--link", value.texto);
            link.href = value.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            container.appendChild(link);
        } else {
            container.appendChild(criarElemento("span", "rreip-details-item__value", valStr));
        }
        return container;
    }

    function extrairHistorico(response) {
        if (!response) return [];
        if (Array.isArray(response)) return response;
        if (response.dados && Array.isArray(response.dados.historico)) return response.dados.historico;
        if (response.historico && Array.isArray(response.historico)) return response.historico;
        if (response.dados && Array.isArray(response.dados)) return response.dados;
        return [];
    }

    async function abrirDetalhes(id) {
        if (!id) return;

        const tituloEl = document.getElementById("rreipDetalhesTitulo");
        const conteudoEl = document.getElementById("rreipDetalhesConteudo");
        const historicoEl = document.getElementById("rreipDetalhesHistorico");

        if (tituloEl) tituloEl.textContent = "Detalhes da Reincidência";
        if (conteudoEl) conteudoEl.textContent = "Carregando detalhes...";
        if (historicoEl) historicoEl.textContent = "";

        window.RREIP.openModal("rreipModalDetalhes");
        definirModalCarregando(modalDetalhes, true);

        try {
            const [detalhesResponse, historicoResponse] = await Promise.all([
                window.RREIP.requestApi(`${apiBase}${id}/detalhes/`),
                window.RREIP.requestApi(`${apiBase}${id}/historico/`)
            ]);

            const dados = extrairDadosResposta(detalhesResponse);
            const historico = extrairHistorico(historicoResponse);

            if (dados && dados.reincidencia) {
                montarDetalhesSeguro(conteudoEl, dados.reincidencia);
                if (tituloEl) tituloEl.textContent = `Detalhes — Ticket ${dados.reincidencia.ticket_atual}`;
            } else if (dados) {
                montarDetalhesSeguro(conteudoEl, dados);
                if (tituloEl) tituloEl.textContent = `Detalhes — Ticket ${dados.ticket_atual}`;
            }

            montarHistoricoSeguro(historicoEl, historico);

        } catch (error) {
            if (conteudoEl) conteudoEl.textContent = "Erro ao carregar os detalhes.";
            window.RREIP.showToast(error?.message || "Falha ao carregar detalhes.", "error");
        } finally {
            definirModalCarregando(modalDetalhes, false);
        }
    }

    function montarDetalhesSeguro(container, dados) {
        if (!container) return;
        container.innerHTML = "";

        const grid = criarElemento("div", "rreip-details-grid");
        
        let ticketData = dados.ticket_atual;
        if (dados.url_ticket) {
            ticketData = { texto: dados.ticket_atual, url: dados.url_ticket };
        }

        let diasRestantesStr = "—";
        if (dados.dias_restantes !== undefined && dados.dias_restantes !== null) {
            if (dados.dias_restantes <= 0) {
                diasRestantesStr = "Prazo concluído";
            } else {
                diasRestantesStr = `${dados.dias_restantes} dias restantes`;
            }
        }

        grid.appendChild(criarCampoDetalhe("Ticket", ticketData));
        grid.appendChild(criarCampoDetalhe("Operadora", dados.operadora));
        grid.appendChild(criarCampoDetalhe("Projeto", dados.projeto));
        grid.appendChild(criarCampoDetalhe("Identificador", dados.identificador_formatado || dados.identificador_projeto));
        grid.appendChild(criarCampoDetalhe("Designação", dados.designacao));
        grid.appendChild(criarCampoDetalhe("Cliente", dados.cliente));
        grid.appendChild(criarCampoDetalhe("ISP", dados.isp));
        grid.appendChild(criarCampoDetalhe("Fila", dados.fila_display || dados.fila));
        grid.appendChild(criarCampoDetalhe("Status", dados.status_display || dados.status));
        grid.appendChild(criarCampoDetalhe("Qtd. Reincidências", dados.quantidade_reincidencias));
        grid.appendChild(criarCampoDetalhe("Responsável", dados.responsavel));
        grid.appendChild(criarCampoDetalhe("Data do Ticket", window.RREIP.formatarDataHora(dados.data_ticket)));
        grid.appendChild(criarCampoDetalhe("Início Monitoramento", window.RREIP.formatarDataHora(dados.data_inicio_monitoramento)));
        grid.appendChild(criarCampoDetalhe("Fim Previsto", window.RREIP.formatarDataHora(dados.data_fim_monitoramento)));
        grid.appendChild(criarCampoDetalhe("Prazo", diasRestantesStr));
        grid.appendChild(criarCampoDetalhe("Criado em", window.RREIP.formatarDataHora(dados.criado_em)));
        grid.appendChild(criarCampoDetalhe("Atualizado em", window.RREIP.formatarDataHora(dados.atualizado_em)));

        container.appendChild(grid);

        const analiseSection = criarElemento("div", "rreip-details-analysis");
        analiseSection.style.marginTop = "1.5rem";
        analiseSection.appendChild(criarElemento("h4", "", "Análise"));
        
        analiseSection.appendChild(criarCampoDetalhe("Motivo Identificado", dados.motivo_identificado));
        analiseSection.appendChild(criarCampoDetalhe("Causa Raiz", dados.causa_raiz));
        analiseSection.appendChild(criarCampoDetalhe("Ação Preventiva", dados.acao_preventiva));
        analiseSection.appendChild(criarCampoDetalhe("Conclusão", dados.conclusao));

        container.appendChild(analiseSection);
    }

    function montarHistoricoSeguro(container, historico) {
        if (!container) return;
        container.innerHTML = "";

        if (!historico || historico.length === 0) {
            const empty = criarElemento("div", "rreip-history-empty", "Nenhum evento registrado no histórico.");
            container.appendChild(empty);
            return;
        }

        const list = criarElemento("div", "rreip-history");

        historico.forEach(evento => {
            const item = criarElemento("div", "rreip-history-item");
            
            const header = criarElemento("div", "rreip-history-item__header");
            
            const titulo = evento.tipo_evento_display || evento.tipo_evento || evento.tipo || "Evento";
            header.appendChild(criarElemento("strong", "rreip-history-item__title", titulo));
            
            const dataStr = window.RREIP.formatarDataHora(evento.criado_em || evento.data);
            header.appendChild(criarElemento("span", "rreip-history-item__date", dataStr));
            
            item.appendChild(header);

            const usuarioStr = evento.usuario || evento.usuario_nome || "Sistema";
            item.appendChild(criarElemento("div", "rreip-history-item__user", `Por: ${usuarioStr}`));

            if (evento.descricao) {
                item.appendChild(criarElemento("div", "rreip-history-item__description", evento.descricao));
            } else if (evento.tipo_evento === "OBSERVACAO") {
                item.appendChild(criarElemento("div", "rreip-history-item__description", "Dados cadastrais alterados."));
            }

            list.appendChild(item);
        });

        container.appendChild(list);
    }

    /* ==========================================================================
     * 11. Eventos
     * ========================================================================== */
    document.addEventListener("rreip:editar", (e) => {
        const id = Number(e.detail?.id);
        if (id) abrirEdicao(id);
        else window.RREIP.showToast("Não foi possível identificar a reincidência.", "error");
    });

    document.addEventListener("rreip:analise", (e) => {
        const id = Number(e.detail?.id);
        if (id) abrirAnalise(id);
        else window.RREIP.showToast("Não foi possível identificar a reincidência.", "error");
    });

    document.addEventListener("rreip:transferir", (e) => {
        const id = Number(e.detail?.id);
        if (id) abrirTransferencia(id);
        else window.RREIP.showToast("Não foi possível identificar a reincidência.", "error");
    });

    document.addEventListener("rreip:detalhes", (e) => {
        const id = Number(e.detail?.id);
        if (id) abrirDetalhes(id);
        else window.RREIP.showToast("Não foi possível identificar a reincidência.", "error");
    });

    document.addEventListener("rreip:reabrir", (e) => {
        const id = Number(e.detail?.id);
        if (id) abrirReabertura(id);
        else window.RREIP.showToast("Não foi possível identificar a reincidência.", "error");
    });

    document.addEventListener("rreip:concluir", (e) => {
        const id = Number(e.detail?.id);
        const forcar = e.detail?.forcar === true || e.detail?.forcar === "true";
        if (id) abrirConclusao(id, forcar);
        else window.RREIP.showToast("Não foi possível identificar a reincidência.", "error");
    });

    /* ==========================================================================
     * 12. Inicialização
     * ========================================================================== */
    function init() {
        // Inicialização específica se necessária
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    /* ==========================================================================
     * 13. API pública
     * ========================================================================== */
    window.RREIPMonitoramento = {
        abrirEdicao,
        abrirAnalise,
        abrirDetalhes,
        abrirTransferencia,
        abrirReabertura,
        abrirConclusao,
    };

})();
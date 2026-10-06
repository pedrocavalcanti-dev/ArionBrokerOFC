/* ============================================================================
 * modais.js — MODAIS
 * Abrir/preencher/salvar de todos os modais usados nas telas de Cancelamento.
 * Depende de window.Cancelamentos (definido em cancelamentos.js).
 *
 * ORDEM DE CARREGAMENTO: carregar DEPOIS de cancelamentos.js.
 * ==========================================================================*/
(function () {
    'use strict';

    const C = window.Cancelamentos;

    if (!C) {
        console.error('modais.js: window.Cancelamentos não encontrado. Carregue cancelamentos.js antes.');
        return;
    }

    const {
        root,
        requestApi,
        showToast,
        setLoading,
        openModal,
        closeModal
    } = C;

    /* HELPERS */
    function setVal(elId, valor) {
        const el = document.getElementById(elId);
        if (!el) return;

        el.value = valor !== null && valor !== undefined ? valor : '';
    }

    function getVal(elId) {
        const el = document.getElementById(elId);
        return el ? el.value : '';
    }

    function setText(elId, valor) {
        const el = document.getElementById(elId);
        if (el) el.textContent = valor;
    }

    function dataLocalHoje() {
        const agora = new Date();

        const ano = agora.getFullYear();
        const mes = String(agora.getMonth() + 1).padStart(2, '0');
        const dia = String(agora.getDate()).padStart(2, '0');

        return `${ano}-${mes}-${dia}`;
    }

    function numeroSeguro(valor) {
        if (valor === null || valor === undefined || valor === '') return 0;

        const numero = Number(
            String(valor)
                .trim()
                .replace(',', '.')
        );

        return Number.isFinite(numero) ? numero : 0;
    }

    function formatarMoeda(valor) {
        return numeroSeguro(valor).toLocaleString('pt-BR', {
            style: 'currency',
            currency: 'BRL',
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    /* 1. DROPDOWN DE STATUS */
    const VIEWPORT_MARGIN = 10;
    const GAP = 6;
    const MAX_HEIGHT = 360;
    const MIN_USEFUL_HEIGHT = 140;

    const statusDropdownState = {
        anchor: null,
        dropdown: null
    };

    let repositionRaf = null;

    function posicionarStatusDropdown(dropdown, anchor) {
        const rect = anchor.getBoundingClientRect();

        dropdown.style.visibility = 'hidden';
        dropdown.style.top = '0px';
        dropdown.style.left = '0px';

        const largura = dropdown.offsetWidth;

        const espacoAbaixo = window.innerHeight - rect.bottom - VIEWPORT_MARGIN - GAP;
        const espacoAcima = rect.top - VIEWPORT_MARGIN - GAP;

        const abrirParaCima = espacoAbaixo < 220 && espacoAcima > espacoAbaixo;
        const espacoDisponivel = abrirParaCima ? espacoAcima : espacoAbaixo;

        const maxHeight = Math.min(
            MAX_HEIGHT,
            Math.max(MIN_USEFUL_HEIGHT, espacoDisponivel)
        );

        dropdown.style.maxHeight = `${maxHeight}px`;

        const altura = dropdown.offsetHeight;

        let left = rect.left;

        if (left + largura > window.innerWidth - VIEWPORT_MARGIN) {
            left = window.innerWidth - largura - VIEWPORT_MARGIN;
        }

        if (left < VIEWPORT_MARGIN) {
            left = VIEWPORT_MARGIN;
        }

        let top = abrirParaCima
            ? rect.top - altura - GAP
            : rect.bottom + GAP;

        top = Math.max(
            VIEWPORT_MARGIN,
            Math.min(
                top,
                window.innerHeight - altura - VIEWPORT_MARGIN
            )
        );

        dropdown.style.top = `${top}px`;
        dropdown.style.left = `${left}px`;
        dropdown.style.visibility = 'visible';
    }

    function fecharDropdownStatus() {
        if (
            statusDropdownState.dropdown &&
            statusDropdownState.dropdown.isConnected
        ) {
            statusDropdownState.dropdown.remove();
        }

        if (statusDropdownState.anchor) {
            statusDropdownState.anchor.classList.remove('is-open');
        }

        statusDropdownState.anchor = null;
        statusDropdownState.dropdown = null;

        if (repositionRaf) {
            cancelAnimationFrame(repositionRaf);
            repositionRaf = null;
        }
    }

    function atualizarPosicaoStatusDropdown() {
        if (
            !statusDropdownState.dropdown ||
            !statusDropdownState.anchor ||
            !statusDropdownState.anchor.isConnected
        ) {
            return;
        }

        if (repositionRaf) {
            cancelAnimationFrame(repositionRaf);
        }

        repositionRaf = requestAnimationFrame(() => {
            posicionarStatusDropdown(
                statusDropdownState.dropdown,
                statusDropdownState.anchor
            );
        });
    }

    window.addEventListener(
        'scroll',
        atualizarPosicaoStatusDropdown,
        { passive: true }
    );

    window.addEventListener('resize', () => {
        if (statusDropdownState.dropdown) {
            fecharDropdownStatus();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            fecharDropdownStatus();
        }
    });

    document.addEventListener('click', (e) => {
        const btnEditarStatus = e.target.closest('[data-action="editar-status"]');

        if (btnEditarStatus) {
            e.stopPropagation();

            const jaAberto = statusDropdownState.anchor === btnEditarStatus;

            fecharDropdownStatus();

            if (jaAberto) return;

            const template = document.getElementById('templateStatusDropdown');
            if (!template) return;

            const clone = template.content.cloneNode(true);
            const dropdown = clone.querySelector('.status-dropdown');

            if (!dropdown) return;

            document.body.appendChild(dropdown);

            dropdown.style.overflowY = 'auto';
            dropdown.style.overflowX = 'hidden';
            dropdown.style.overscrollBehavior = 'contain';
            dropdown.style.touchAction = 'pan-y';

            dropdown.querySelectorAll('.status-option').forEach((option) => {
                option.style.flexShrink = '0';
                option.style.flex = '0 0 auto';
            });

            posicionarStatusDropdown(
                dropdown,
                btnEditarStatus
            );

            statusDropdownState.anchor = btnEditarStatus;
            statusDropdownState.dropdown = dropdown;

            btnEditarStatus.classList.add('is-open');

            const row = btnEditarStatus.closest('tr[data-id]');

            const id = row
                ? row.dataset.id
                : root.dataset.cancelamentoId;

            dropdown.addEventListener(
                'wheel',
                (event) => event.stopPropagation(),
                { passive: true }
            );

            dropdown.addEventListener(
                'touchmove',
                (event) => event.stopPropagation(),
                { passive: true }
            );

            dropdown.querySelectorAll('.status-option').forEach((option) => {
                option.addEventListener('click', (event) => {
                    event.stopPropagation();

                    const status = option.dataset.status;

                    C.alterarStatus(
                        id,
                        status,
                        option
                    );

                    fecharDropdownStatus();
                });
            });

            if (window.DEBUG_CANCELAMENTOS === true) {
                console.debug('[STATUS DROPDOWN]', {
                    clientHeight: dropdown.clientHeight,
                    scrollHeight: dropdown.scrollHeight,
                    podeRolar: dropdown.scrollHeight > dropdown.clientHeight,
                    overflowY: getComputedStyle(dropdown).overflowY,
                    maxHeight: getComputedStyle(dropdown).maxHeight,
                    opcoes: dropdown.querySelectorAll('.status-option').length
                });
            }

            return;
        }

        if (
            statusDropdownState.dropdown &&
            e.target.closest('.status-dropdown')
        ) {
            return;
        }

        fecharDropdownStatus();
    });

/* 2. MODAL: CRIAR CANCELAMENTO */
    const DRAFT_KEY_NOVO = 'arion_draft_novo_cancelamento';

    function salvarRascunhoNovo() {
        const form = document.getElementById('formNovo');
        if (!form) return;
        const fd = new FormData(form);
        const dados = {};
        fd.forEach((value, key) => { dados[key] = value; });
        localStorage.setItem(DRAFT_KEY_NOVO, JSON.stringify(dados));
    }

    function carregarRascunhoNovo() {
        const form = document.getElementById('formNovo');
        if (!form) return;
        try {
            const salvo = localStorage.getItem(DRAFT_KEY_NOVO);
            if (salvo) {
                const dados = JSON.parse(salvo);
                Object.entries(dados).forEach(([key, value]) => {
                    const input = form.elements[key];
                    if (input) input.value = value;
                });
            }
        } catch (e) {
            console.warn('Erro ao carregar rascunho', e);
        }
    }

    function limparRascunhoNovo() {
        localStorage.removeItem(DRAFT_KEY_NOVO);
        const form = document.getElementById('formNovo');
        if (form) form.reset();
    }

    // Salvar rascunho automaticamente a cada mudança/digitação
    const formNovo = document.getElementById('formNovo');
    if (formNovo) {
        formNovo.addEventListener('input', salvarRascunhoNovo);
        formNovo.addEventListener('change', salvarRascunhoNovo);
    }

    // 👇 TRECHO NOVO: Limpar o rascunho ao clicar no "X" ou "Cancelar"
    const botoesFecharNovo = document.querySelectorAll('[data-close-modal="modalNovo"]');
    botoesFecharNovo.forEach(btn => {
        btn.addEventListener('click', limparRascunhoNovo);
    });
    // 👆 FIM DO TRECHO NOVO

    const btnNovo = document.getElementById('btnNovoCancelamento');

    if (btnNovo) {
        btnNovo.addEventListener('click', () => {
            const erroBox = document.getElementById('formNovoErro');

            if (erroBox) {
                erroBox.textContent = '';
                erroBox.style.display = 'none';
            }

            // Puxa o rascunho (se existir) ao invés de resetar o form inteiro
            carregarRascunhoNovo();

            openModal('modalNovo');
        });
    }

    const btnSalvarNovo = document.getElementById('btnSalvarNovo');

    if (btnSalvarNovo) {
        btnSalvarNovo.addEventListener('click', async () => {
            const form = document.getElementById('formNovo');
            const erroBox = document.getElementById('formNovoErro');

            if (!form) return;

            if (erroBox) {
                erroBox.textContent = '';
                erroBox.style.display = 'none';
            }

            if (!form.reportValidity()) return;

            const fd = new FormData(form);

            setLoading(
                btnSalvarNovo,
                true,
                'Salvando...'
            );

            try {
                await requestApi(
                    C.urlCriar,
                    {
                        method: 'POST',
                        body: fd
                    }
                );

                showToast(
                    'Cancelamento criado com sucesso.',
                    'success'
                );

                // Limpa a memória do navegador apenas após o sucesso
                limparRascunhoNovo();

                window.location.reload();

            } catch (err) {
                if (err.status === 500) {
                    showToast(
                        'Houve uma falha no servidor, mas o registro pode ter sido salvo. Atualize a página.',
                        'warning'
                    );

                    setTimeout(
                        () => window.location.reload(),
                        2500
                    );

                    return;
                }

                if (erroBox) {
                    erroBox.textContent = err.message;
                    erroBox.style.display = 'block';
                } else {
                    showToast(
                        err.message,
                        'error'
                    );
                }

                setLoading(
                    btnSalvarNovo,
                    false
                );
            }
        });
    }

    /* 3. MODAL: OBSERVAÇÕES */
    let obsCancelamentoId = null;

    async function abrirModalObs(id, ticket) {
        obsCancelamentoId = id;

        setText(
            'obsTicket',
            ticket || ''
        );

        const lista = document.getElementById('obsLista');

        if (lista) {
            lista.innerHTML = '<div class="obs-loading">Carregando observações...</div>';
        }

        const textarea = document.getElementById('obsTextarea');

        if (textarea) {
            textarea.value = '';
        }

        openModal('modalObs');

        try {
            const observacoes = await C.listarObservacoes(id);

            renderizarObservacoes(
                observacoes
            );

        } catch (err) {
            if (lista) {
                lista.innerHTML = `<div class="obs-erro">${err.message}</div>`;
            }
        }
    }

    function renderizarObservacoes(observacoes) {
        const lista = document.getElementById('obsLista');

        if (!lista) return;

        if (!observacoes || !observacoes.length) {
            lista.innerHTML = '<div class="canc-empty-mini" style="text-align:center; color:gray; font-size:12px;">Nenhuma observação registrada.</div>';
            return;
        }

        const ordenadas = observacoes.slice().reverse();

        lista.innerHTML = ordenadas
            .map((o) => `
                <div class="obs-item">
                    <div class="obs-item__topo">
                        <span class="obs-item__autor">${C.textoOuTraco(o.criado_por)}</span>
                        <span class="obs-item__data">${C.formatDataHora(o.criado_em)}</span>
                    </div>
                    <p class="obs-item__texto"></p>
                </div>
            `)
            .join('');

        lista
            .querySelectorAll('.obs-item__texto')
            .forEach((el, idx) => {
                el.textContent = ordenadas[idx].texto;
            });
    }

    const btnSalvarObs = document.getElementById('btnSalvarObs');

    if (btnSalvarObs) {
        btnSalvarObs.addEventListener('click', async () => {
            const textarea = document.getElementById('obsTextarea');

            if (
                !obsCancelamentoId ||
                !textarea
            ) {
                return;
            }

            const obs = await C.adicionarObservacao(
                obsCancelamentoId,
                textarea.value,
                btnSalvarObs
            );

            if (!obs) return;

            textarea.value = '';

            const observacoes = await C.listarObservacoes(
                obsCancelamentoId
            );

            renderizarObservacoes(
                observacoes
            );

            const badge = document.querySelector(
                `tr[data-id="${obsCancelamentoId}"] [data-action="ver-obs"] .obs-btn__count`
            );

            if (badge) {
                badge.textContent = observacoes.length;
            }
        });
    }

    /* 4. MODAL: MOVER DE FILA */
    function abrirModalMovimentacao(id, filaDestino) {
        const modal = document.getElementById('modalMovimentacao');

        if (!modal) {
            C.moverCancelamento(
                id,
                filaDestino,
                ''
            );

            return;
        }

        modal.dataset.cancelamentoId = id;
        modal.dataset.filaDestino = filaDestino;

        setText(
            'movDestinoLabel',
            filaDestino
        );

        setVal(
            'movMotivo',
            ''
        );

        openModal('modalMovimentacao');
    }

    const btnConfirmarMovimentacao = document.getElementById(
        'btnConfirmarMovimentacao'
    );

    if (btnConfirmarMovimentacao) {
        btnConfirmarMovimentacao.addEventListener('click', async () => {
            const modal = document.getElementById('modalMovimentacao');

            if (!modal) return;

            const motivo = getVal('movMotivo');

            const ok = await C.moverCancelamento(
                modal.dataset.cancelamentoId,
                modal.dataset.filaDestino,
                motivo,
                btnConfirmarMovimentacao
            );

            if (ok) {
                closeModal('modalMovimentacao');
            }
        });
    }

    /* =========================================================================
     * 5. MODAL: NOVA PENDÊNCIA
     *
     * MODOS:
     * - Salvar Pendência:
     *   salva a pendência atual e encerra o fluxo normal.
     *
     * - Adicionar outra pendência:
     *   salva a pendência atual, mantém o modal aberto, limpa os campos
     *   e permite cadastrar outra sem fechar/reabrir.
     *
     * Quando o modal foi aberto com moverParaPendencia=true:
     * - "Adicionar outra pendência" NÃO move o chamado ainda;
     * - "Salvar Pendência" salva a última pendência e só então move
     *   o chamado para a fila PENDENCIA.
     * =======================================================================*/
    function abrirModalPendencia(id, opcoes = {}) {
        const modal = document.getElementById('modalPendencia');

        if (!modal) return;

        /*
         * Aceita os dois formatos temporariamente:
         *
         * moverParaPendencia
         * mover_para_pendencia
         *
         * Assim mantemos compatibilidade com telas antigas.
         */
        const moverParaPendencia = Boolean(
            opcoes.moverParaPendencia ??
            opcoes.mover_para_pendencia ??
            false
        );

        modal.dataset.cancelamentoId = id;
        modal.dataset.mover = moverParaPendencia ? '1' : '0';
        modal.dataset.pendenciasAdicionadas = '0';

        const form = document.getElementById('formPendencia');
        const feedback = document.getElementById('pendenciaSequenciaFeedback');

        if (form) {
            form.reset();
        }

        if (feedback) {
            feedback.textContent = '';
            feedback.style.display = 'none';
        }

        openModal('modalPendencia');

        requestAnimationFrame(() => {
            const primeiroCampo = form?.querySelector('[name="tipo"]');
            primeiroCampo?.focus();
        });
    }

    function limparFormularioPendencia(form) {
        if (!form) return;

        form.reset();

        const primeiroCampo = form.querySelector('[name="tipo"]');

        requestAnimationFrame(() => {
            primeiroCampo?.focus();
        });
    }

    function atualizarFeedbackPendencias(modal) {
        const feedback = document.getElementById('pendenciaSequenciaFeedback');

        if (!feedback || !modal) return;

        const total = Number(
            modal.dataset.pendenciasAdicionadas || '0'
        );

        if (total <= 0) {
            feedback.textContent = '';
            feedback.style.display = 'none';
            return;
        }

        feedback.textContent = total === 1
            ? '1 pendência adicionada nesta sequência. Você pode cadastrar outra.'
            : `${total} pendências adicionadas nesta sequência. Você pode cadastrar outra.`;

        feedback.style.display = 'block';
    }

    async function salvarPendenciaModal({
        adicionarOutra = false,
        botao = null
    } = {}) {
        const modal = document.getElementById('modalPendencia');
        const form = document.getElementById('formPendencia');

        if (!modal || !form) {
            return false;
        }

        if (!form.reportValidity()) {
            return false;
        }

        const id = modal.dataset.cancelamentoId;

        if (!id) {
            showToast(
                'Não foi possível identificar o cancelamento.',
                'error'
            );

            return false;
        }

        const fd = new FormData(form);

        const payload = {
            tipo: fd.get('tipo'),
            descricao: fd.get('descricao') || '',
            valor: fd.get('valor') || '',
            data_prevista: fd.get('data_prevista') || ''
        };

        const pendencia = await C.criarPendencia(
            id,
            payload,
            botao
        );

        if (!pendencia) {
            return false;
        }

        const totalAtual = Number(
            modal.dataset.pendenciasAdicionadas || '0'
        );

        modal.dataset.pendenciasAdicionadas = String(
            totalAtual + 1
        );

        /*
         * "Adicionar outra pendência":
         * salva imediatamente no backend, mas não fecha o modal
         * e não move de fila ainda.
         */
        if (adicionarOutra) {
            limparFormularioPendencia(form);
            atualizarFeedbackPendencias(modal);

            return true;
        }

        /*
         * Fluxo que também deve mover para PENDENCIA:
         * primeiro garantimos que a última pendência foi salva,
         * depois movemos o chamado.
         */
        if (modal.dataset.mover === '1') {
            const moveu = await C.moverCancelamento(
                id,
                'PENDENCIA',
                'Pendência identificada.',
                botao
            );

            return moveu !== false;
        }

        closeModal('modalPendencia');

        window.location.reload();

        return true;
    }

    const btnSalvarPendencia = document.getElementById(
        'btnSalvarPendencia'
    );

    const btnSalvarAdicionarPendencia = document.getElementById(
        'btnSalvarAdicionarPendencia'
    );

    if (btnSalvarPendencia) {
        btnSalvarPendencia.addEventListener(
            'click',
            async () => {
                await salvarPendenciaModal({
                    adicionarOutra: false,
                    botao: btnSalvarPendencia
                });
            }
        );
    }

    if (btnSalvarAdicionarPendencia) {
        btnSalvarAdicionarPendencia.addEventListener(
            'click',
            async () => {
                await salvarPendenciaModal({
                    adicionarOutra: true,
                    botao: btnSalvarAdicionarPendencia
                });
            }
        );
    }

    /* =========================================================================
     * 6. MODAL: DADOS FINANCEIROS
     * LEGADO — MANTIDO TEMPORARIAMENTE
     * =======================================================================*/
    const CAMPOS_FINANCEIRO = [
        'finDataCancelamento',
        'finCompetencia',
        'finValorMulta',
        'finValorEquipamento',
        'finValorOutros',
        'finDataBaixa',
        'finObservacao'
    ];

    function limparCamposFinanceiro() {
        CAMPOS_FINANCEIRO.forEach((elId) => {
            setVal(
                elId,
                ''
            );
        });

        const chk = document.getElementById('finConfirmacao');

        if (chk) {
            chk.checked = false;
        }
    }

    async function abrirModalFinanceiro(id, ticket) {
        const modal = document.getElementById('modalFinanceiro');

        if (!modal) return;

        modal.dataset.cancelamentoId = id;

        setText(
            'finTicket',
            ticket || ''
        );

        limparCamposFinanceiro();

        openModal('modalFinanceiro');

        try {
            const c = await C.buscarDetalhe(id);

            if (!c) return;

            setVal('finDataCancelamento', c.data_cancelamento_confirmado);
            setVal('finCompetencia', c.ultima_competencia_faturada);
            setVal('finValorMulta', c.valor_multa_rescisao);
            setVal('finValorEquipamento', c.valor_equipamento);
            setVal('finValorOutros', c.valor_outros);
            setVal('finDataBaixa', c.data_baixa_financeira);
            setVal('finObservacao', c.observacao_financeira);

            const chk = document.getElementById('finConfirmacao');

            if (chk) {
                chk.checked = Boolean(
                    c.confirmacao_sem_nova_cobranca
                );
            }

        } catch (err) {
            showToast(
                'Não foi possível carregar os valores financeiros atuais.',
                'warning'
            );
        }
    }

    const btnSalvarFinanceiro = document.getElementById('btnSalvarFinanceiro');

    if (btnSalvarFinanceiro) {
        btnSalvarFinanceiro.addEventListener('click', async () => {
            const modal = document.getElementById('modalFinanceiro');

            if (!modal) return;

            const id =
                modal.dataset.cancelamentoId ||
                root.dataset.cancelamentoId;

            if (!id) return;

            const chk = document.getElementById('finConfirmacao');

            const payload = {
                valor_multa_rescisao: getVal('finValorMulta'),
                valor_equipamento: getVal('finValorEquipamento'),
                valor_outros: getVal('finValorOutros'),
                ultima_competencia_faturada: getVal('finCompetencia'),
                data_baixa_financeira: getVal('finDataBaixa'),
                confirmacao_sem_nova_cobranca: chk && chk.checked ? 'true' : 'false',
                observacao_financeira: getVal('finObservacao'),
                data_cancelamento_confirmado: getVal('finDataCancelamento')
            };

            await C.atualizarFinanceiro(
                id,
                payload,
                btnSalvarFinanceiro
            );
        });
    }

    /* =========================================================================
     * 7. MODAL: CONCLUIR CANCELAMENTO
     *
     * NOVO FLUXO:
     *
     * Pendências
     *      ↓
     * valores calculados automaticamente
     *      ↓
     * data do cancelamento
     *      ↓
     * observação opcional
     *      ↓
     * concluir
     *      ↓
     * Concluídos
     * =======================================================================*/

    function limparModalConcluir() {
        setText(
            'concluirResumoMulta',
            formatarMoeda(0)
        );

        setText(
            'concluirResumoEquipamento',
            formatarMoeda(0)
        );

        setText(
            'concluirResumoOutros',
            formatarMoeda(0)
        );

        setText(
            'concluirResumoTotal',
            formatarMoeda(0)
        );

        setVal(
            'concluirDataCancelamento',
            dataLocalHoje()
        );

        setVal(
            'concluirObservacao',
            ''
        );

        const erro = document.getElementById('concluirErro');

        if (erro) {
            erro.textContent = '';
            erro.style.display = 'none';
        }

        const btn = document.getElementById(
            'btnConfirmarConclusao'
        );

        if (btn) {
            btn.disabled = true;
        }
    }

    function preencherResumoConclusao(cancelamento) {
        /*
         * Estes valores vêm diretamente das propriedades calculadas
         * pelas pendências no backend.
         *
         * NÃO usamos valor_multa_rescisao etc. aqui porque antes
         * da conclusão esses campos ainda podem não possuir a
         * fotografia final.
         */

        const multa = numeroSeguro(
            cancelamento.valor_pendencias_multa
        );

        const equipamento = numeroSeguro(
            cancelamento.valor_pendencias_equipamento
        );

        const outros = numeroSeguro(
            cancelamento.valor_pendencias_outros
        );

        const totalBackend = numeroSeguro(
            cancelamento.valor_pendencias_total
        );

        /*
         * Usa prioritariamente o total enviado pelo backend.
         * Como segurança visual, caso não venha, recalcula no navegador.
         */
        const total = (
            cancelamento.valor_pendencias_total !== null &&
            cancelamento.valor_pendencias_total !== undefined
        )
            ? totalBackend
            : multa + equipamento + outros;

        setText(
            'concluirResumoMulta',
            formatarMoeda(multa)
        );

        setText(
            'concluirResumoEquipamento',
            formatarMoeda(equipamento)
        );

        setText(
            'concluirResumoOutros',
            formatarMoeda(outros)
        );

        setText(
            'concluirResumoTotal',
            formatarMoeda(total)
        );
    }

    async function abrirModalConcluir(id, ticket) {
        const modal = document.getElementById('modalConcluir');

        if (!modal) return;

        modal.dataset.cancelamentoId = id;

        limparModalConcluir();

        setText(
            'concluirTicket',
            ticket || ''
        );

        /*
         * Modal abre imediatamente.
         * Enquanto carrega os valores, o botão de conclusão permanece
         * desabilitado para impedir fechamento sem o resumo atual.
         */
        openModal('modalConcluir');

        try {
            const c = await C.buscarDetalhe(id);

            if (!c) {
                throw new Error(
                    'Os dados do cancelamento não foram encontrados.'
                );
            }

            if (!ticket && c.ticket_arion) {
                setText(
                    'concluirTicket',
                    c.ticket_arion
                );
            }

            preencherResumoConclusao(c);

            /*
             * Se já existir uma data, preserva.
             * Caso contrário, mantém a data atual preenchida inicialmente.
             */
            setVal(
                'concluirDataCancelamento',
                c.data_cancelamento_confirmado || dataLocalHoje()
            );

            setVal(
                'concluirObservacao',
                c.observacao_financeira || ''
            );

            const btn = document.getElementById(
                'btnConfirmarConclusao'
            );

            if (btn) {
                btn.disabled = false;
            }

        } catch (err) {
            const erro = document.getElementById('concluirErro');

            if (erro) {
                erro.textContent =
                    err.message ||
                    'Não foi possível carregar os dados do cancelamento.';

                erro.style.display = 'block';
            }

            showToast(
                'Não foi possível carregar os dados atuais do cancelamento.',
                'warning'
            );
        }
    }

    const btnConfirmarConclusao = document.getElementById('btnConfirmarConclusao');

    if (btnConfirmarConclusao) {
        btnConfirmarConclusao.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();

            if (btnConfirmarConclusao.dataset.enviando === '1') return;

            const modal = document.getElementById('modalConcluir');
            if (!modal) return;

            const id = modal.dataset.cancelamentoId || root.dataset.cancelamentoId;
            if (!id) return;

            const dataCancelamento = getVal('concluirDataCancelamento');

            if (!dataCancelamento) {
                showToast('Informe a data do cancelamento.', 'warning');
                return;
            }

            btnConfirmarConclusao.dataset.enviando = '1';
            btnConfirmarConclusao.disabled = true;

            const payload = new FormData();
            payload.append('data_cancelamento_confirmado', dataCancelamento);
            payload.append('observacao_financeira', getVal('concluirObservacao'));

            try {
                const sucesso = await C.concluirCancelamento(id, payload, btnConfirmarConclusao);

                if (!sucesso) {
                    btnConfirmarConclusao.dataset.enviando = '0';
                    btnConfirmarConclusao.disabled = false;
                }
            } catch (err) {
                btnConfirmarConclusao.dataset.enviando = '0';
                btnConfirmarConclusao.disabled = false;
                showToast(err.message || 'Não foi possível concluir o cancelamento.', 'error');
            }
        });
    }

    /* 8. MODAL: TRANSFERIR RESPONSÁVEL */
    function abrirModalTransferir(id) {
        const modal = document.getElementById('modalTransferir');

        if (!modal) return;

        modal.dataset.cancelamentoId = id;

        const select = document.getElementById(
            'transferirSelectAnalista'
        );

        if (select) {
            select.value = '';
        }

        openModal('modalTransferir');
    }

    const btnConfirmarTransferir = document.getElementById(
        'btnConfirmarTransferir'
    );

    if (btnConfirmarTransferir) {
        btnConfirmarTransferir.addEventListener('click', async () => {
            const modal = document.getElementById('modalTransferir');
            const select = document.getElementById('transferirSelectAnalista');

            if (
                !modal ||
                !select ||
                !select.value
            ) {
                showToast(
                    'Selecione o novo responsável.',
                    'warning'
                );

                return;
            }

            const resultado = await C.transferirCancelamento(
                modal.dataset.cancelamentoId,
                select.value,
                btnConfirmarTransferir
            );

            if (resultado !== false) {
                closeModal('modalTransferir');
            }
        });
    }

    /* 9. MODAL: EDITAR CANCELAMENTO */
    async function abrirModalEditar(id) {
        const modal = document.getElementById('modalEditar');
        const form = document.getElementById('formEditar');
        const erroBox = document.getElementById('formEditarErro');

        if (!modal) return;

        modal.dataset.cancelamentoId = id;

        if (form) form.reset();

        if (erroBox) {
            erroBox.textContent = '';
            erroBox.style.display = 'none';
        }

        openModal('modalEditar');

        try {
            const c = await C.buscarDetalhe(id);
            if (!c) {
                throw new Error('Não foi possível encontrar os dados deste cancelamento.');
            }

            // Preenche os campos do formulário baseando-se no "name"
            if (form) {
                Object.entries(c).forEach(([key, value]) => {
                    const inputs = form.querySelectorAll(`[name="${key}"]`);
                    inputs.forEach(input => {
                        if (input.type === 'checkbox' || input.type === 'radio') {
                            if (String(input.value) === String(value) || (input.type === 'checkbox' && value)) {
                                input.checked = true;
                            } else {
                                input.checked = false;
                            }
                        } else {
                            input.value = value !== null && value !== undefined ? value : '';
                        }
                    });
                });
            }

        } catch (err) {
            showToast('Não foi possível carregar os dados para edição.', 'warning');

            if (erroBox) {
                erroBox.textContent = err.message;
                erroBox.style.display = 'block';
            }
        }
    }

    const btnSalvarEditar = document.getElementById('btnSalvarEditar');

    if (btnSalvarEditar) {
        btnSalvarEditar.addEventListener('click', async () => {
            const modal = document.getElementById('modalEditar');
            const form = document.getElementById('formEditar');
            const erroBox = document.getElementById('formEditarErro');

            if (!modal || !form) return;

            const id = modal.dataset.cancelamentoId;
            if (!id) return;

            if (erroBox) {
                erroBox.textContent = '';
                erroBox.style.display = 'none';
            }

            if (!form.reportValidity()) return;

            const fd = new FormData(form);

            const sucesso = await C.editarCancelamento(
                id,
                fd,
                btnSalvarEditar
            );

            if (sucesso) {
                closeModal('modalEditar');
                window.location.reload();
            }
        });
    }

    /* 10. REGISTRO NO NAMESPACE */
    C.Modais.abrirModalObs = abrirModalObs;
    C.Modais.abrirModalMovimentacao = abrirModalMovimentacao;
    C.Modais.abrirModalPendencia = abrirModalPendencia;
    C.Modais.abrirModalFinanceiro = abrirModalFinanceiro;
    C.Modais.abrirModalConcluir = abrirModalConcluir;
    C.Modais.abrirModalTransferir = abrirModalTransferir;
    C.Modais.abrirModalEditar = abrirModalEditar; // <- FUNÇÃO REGISTRADA AQUI

})();

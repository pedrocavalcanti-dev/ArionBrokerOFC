/* ============================================================================
 * cancelamentos.js — NÚCLEO
 * Módulo base do front-end das filas de Cancelamento (ARION Broker).
 * ==========================================================================*/
(function () {
    'use strict';

    const wrapper = document.getElementById('cancWrapper');
    const root = wrapper || document.getElementById('cancDetalheWrapper');
    if (!root) return;

    const API_BASE = '/cancelamentos/api/';
    const filaAtual = root.dataset.filaAtual || '';
    const urlCriar = root.dataset.urlCriar || (API_BASE + 'criar/');

    /* =========================================================================
     * 1. ESTADO TEMPORÁRIO DA PÁGINA
     * Busca/filtros/última fila não usam armazenamento local.
     * =======================================================================*/
    const FILTROS_QUERY = ['responsavel', 'status', 'data_inicio', 'data_fim', 'ordenacao'];

    function filtrosAtuaisDaUrl() {
        const url = new URL(window.location.href);
        const filtros = {};
        FILTROS_QUERY.forEach((chave) => { filtros[chave] = url.searchParams.get(chave) || ''; });
        return filtros;
    }

    function construirUrlComFiltros(path, filtros = {}) {
        const url = new URL(path, window.location.origin);
        Object.entries(filtros).forEach(([chave, valor]) => {
            if (valor !== null && valor !== undefined && valor !== '') url.searchParams.set(chave, valor);
        });
        return url.pathname + (url.search ? url.search : '');
    }

    /* 2. CSRF TOKEN E COOKIES */
    function getCookie(name) {
        const valor = document.cookie
            .split('; ')
            .find((row) => row.startsWith(name + '='));

        return valor ? decodeURIComponent(valor.split('=')[1]) : null;
    }

    function getCsrfToken() {
        const input = document.querySelector('[name=csrfmiddlewaretoken]');

        if (input && input.value) {
            return input.value;
        }

        return getCookie('csrftoken');
    }

    /* 3. TRATAMENTO DE ERROS */
    class ApiError extends Error {
        constructor(message, status, isHtml = false) {
            super(message);
            this.status = status;
            this.isHtml = isHtml;
        }
    }

    function mensagemPorStatus(status) {
        switch (status) {
            case 400:
                return 'Dados inválidos. Verifique os campos e tente novamente.';

            case 403:
                return 'Você não tem permissão para executar esta ação.';

            case 404:
                return 'Registro não encontrado. A página pode estar desatualizada.';

            case 500:
                return 'Erro interno no servidor. Recarregue a página para conferir.';

            default:
                return 'Ocorreu um erro inesperado.';
        }
    }

    /* 4. MOTOR DE REQUISIÇÕES */
    async function requestApi(url, { method = 'POST', body = null } = {}) {
        const opts = {
            method,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        };

        if (method !== 'GET') {
            opts.headers['X-CSRFToken'] = getCsrfToken();
        }

        if (body instanceof FormData) {
            opts.body = body;
        } else if (body && typeof body === 'object') {
            const fd = new FormData();

            Object.entries(body).forEach(([chave, valor]) => {
                if (valor !== undefined && valor !== null) {
                    fd.append(chave, valor);
                }
            });

            opts.body = fd;
        }

        let resp;

        try {
            resp = await fetch(url, opts);
        } catch (err) {
            throw new ApiError(
                'Falha de rede. Verifique sua conexão e tente novamente.',
                0
            );
        }

        const textoResposta = await resp.text();

        let data = null;
        let isHtmlErro = false;

        try {
            data = textoResposta ? JSON.parse(textoResposta) : {};
        } catch (err) {
            isHtmlErro = true;
        }

        if (!resp.ok) {
            const msg = data && data.erro
                ? data.erro
                : mensagemPorStatus(resp.status);

            throw new ApiError(
                msg,
                resp.status,
                isHtmlErro
            );
        }

        if (data && data.ok === false) {
            throw new ApiError(
                data.erro || 'Operação bloqueada pelas regras de negócio.',
                resp.status
            );
        }

        return data || {};
    }

    /* 5. TOASTS */
    function ensureToastContainer() {
        let container = document.getElementById('cancToastContainer');

        if (!container) {
            container = document.createElement('div');
            container.id = 'cancToastContainer';
            container.className = 'canc-toast-container';
            document.body.appendChild(container);
        }

        return container;
    }

    function showToast(mensagem, tipo = 'info') {
        const container = ensureToastContainer();
        const el = document.createElement('div');

        el.className = `canc-toast canc-toast--${tipo}`;
        el.textContent = mensagem;

        container.appendChild(el);

        requestAnimationFrame(() => {
            el.classList.add('canc-toast--show');
        });

        setTimeout(() => {
            el.classList.remove('canc-toast--show');

            setTimeout(() => {
                el.remove();
            }, 300);
        }, 5000);
    }

   /* 6. MODAIS */
    function openModal(id) {
        const el = document.getElementById(id);
        if (el) {
            el.style.display = 'flex';
        }
    }

    function closeModal(id) {
        const el = document.getElementById(id);
        if (el) {
            el.style.display = 'none';
        }
    }

    document.addEventListener('click', (e) => {
        const closeBtn = e.target.closest('[data-close-modal]');

        if (closeBtn) {
            closeModal(closeBtn.dataset.closeModal);
            return;
        }

        if (
            e.target.classList &&
            e.target.classList.contains('modal-overlay')
        ) {
            // Bloqueia fechamento ao clicar fora nos formulários principais
            if (e.target.id === 'modalNovo' || e.target.id === 'modalEditar') {
                const box = e.target.querySelector('.modal-box');
                if (box) {
                    // Feedback visual (leve pulso) indicando que o clique fora foi bloqueado
                    box.style.transform = 'scale(1.02)';
                    box.style.transition = 'transform 0.15s ease-in-out';
                    setTimeout(() => box.style.transform = 'scale(1)', 150);
                }
                return;
            }
            e.target.style.display = 'none';
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;

        document.querySelectorAll('.modal-overlay').forEach((modal) => {
            if (modal.style.display !== 'none') {
                // Bloqueia fechamento via ESC nos formulários principais
                if (modal.id === 'modalNovo' || modal.id === 'modalEditar') {
                    const box = modal.querySelector('.modal-box');
                    if (box) {
                        box.style.transform = 'scale(1.02)';
                        box.style.transition = 'transform 0.15s ease-in-out';
                        setTimeout(() => box.style.transform = 'scale(1)', 150);
                    }
                    return;
                }
                modal.style.display = 'none';
            }
        });
    });

    /* 7. CONFIRMAÇÃO GENÉRICA */
    function ensureConfirmModal() {
        let el = document.getElementById('cancConfirmModal');

        if (el) return el;

        el = document.createElement('div');
        el.className = 'modal-overlay';
        el.id = 'cancConfirmModal';
        el.style.display = 'none';

        el.innerHTML = `
            <div class="modal-box modal-box--confirm">
                <div class="modal-box__header">
                    <span class="modal-box__title" id="cancConfirmTitulo">Confirmar ação</span>
                </div>
                <div class="modal-box__body">
                    <p id="cancConfirmTexto"></p>
                </div>
                <div class="modal-box__footer">
                    <button type="button" class="btn-secondary" id="cancConfirmCancelar">Cancelar</button>
                    <button type="button" class="btn-primary" id="cancConfirmOk">Confirmar</button>
                </div>
            </div>
        `;

        document.body.appendChild(el);

        return el;
    }

    function showConfirm(
        texto,
        {
            titulo = 'Confirmar ação',
            textoOk = 'Confirmar',
            perigo = false
        } = {}
    ) {
        return new Promise((resolve) => {
            const el = ensureConfirmModal();

            el.querySelector('#cancConfirmTitulo').textContent = titulo;
            el.querySelector('#cancConfirmTexto').textContent = texto;

            const okBtn = el.querySelector('#cancConfirmOk');
            const cancelBtn = el.querySelector('#cancConfirmCancelar');

            okBtn.textContent = textoOk;
            okBtn.classList.toggle('btn-danger', perigo);

            function limpar(resultado) {
                el.style.display = 'none';

                okBtn.removeEventListener('click', onOk);
                cancelBtn.removeEventListener('click', onCancel);

                resolve(resultado);
            }

            function onOk() {
                limpar(true);
            }

            function onCancel() {
                limpar(false);
            }

            okBtn.addEventListener('click', onOk);
            cancelBtn.addEventListener('click', onCancel);

            el.style.display = 'flex';
        });
    }

    /* 8. LOADING */
    function setLoading(btn, loading, textoCarregando = 'Processando...') {
        if (!btn) return;

        if (loading) {
            if (btn.disabled) return;

            btn.dataset.textoOriginal = btn.innerHTML;
            btn.disabled = true;
            btn.classList.add('is-loading');
            btn.innerHTML = `<span class="btn-spinner"></span> ${textoCarregando}`;

            return;
        }

        btn.disabled = false;
        btn.classList.remove('is-loading');

        if (btn.dataset.textoOriginal) {
            btn.innerHTML = btn.dataset.textoOriginal;
            delete btn.dataset.textoOriginal;
        }
    }

    /* 9. FORMATAÇÕES */
    function formatDataHora(iso) {
        if (!iso) return '—';

        const d = new Date(iso);

        if (isNaN(d.getTime())) {
            return '—';
        }

        return `${d.toLocaleDateString('pt-BR')} às ${d.toLocaleTimeString('pt-BR', {
            hour: '2-digit',
            minute: '2-digit'
        })}`;
    }

    function textoOuTraco(valor) {
        return valor === null ||
               valor === undefined ||
               valor === ''
            ? '—'
            : valor;
    }

    /* 10. FILTROS SEM PERSISTÊNCIA LOCAL */
    const formFiltros = document.getElementById('cancFormFiltros');

    document.querySelectorAll('[data-filtro-responsavel]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const filtros = filtrosAtuaisDaUrl();
            filtros.responsavel = btn.dataset.filtroResponsavel || '';
            window.location.href = construirUrlComFiltros(window.location.pathname, filtros);
        });
    });

    if (formFiltros) {
        formFiltros.addEventListener('submit', (e) => {
            e.preventDefault();
            const fd = new FormData(formFiltros);
            const filtros = {};
            fd.forEach((valor, chave) => { filtros[chave] = valor || ''; });
            if (!Object.prototype.hasOwnProperty.call(filtros, 'responsavel')) {
                filtros.responsavel = filtrosAtuaisDaUrl().responsavel || '';
            }
            window.location.href = construirUrlComFiltros(window.location.pathname, filtros);
        });
    }

    document.querySelectorAll('[data-limpar-filtros]').forEach((btn) => {
        btn.addEventListener('click', () => { window.location.href = window.location.pathname; });
    });

    /* =========================================================================
     * 15. BUSCA GLOBAL EM TEMPO REAL
     * Mostra resultados de TODAS as filas na tabela atual; não redireciona.
     * =======================================================================*/
    const inputBusca = document.getElementById('cancBusca');
    const btnBuscaClear = document.getElementById('cancBuscaClear');
    const tabela = document.getElementById('cancTabelaBody');
    const tabelaElemento = document.getElementById('cancTabela');
    const tabelaCabecalho = tabelaElemento ? tabelaElemento.querySelector('thead tr') : null;
    const buscaVazia = document.getElementById('cancBuscaVazia');
    const contagemVisivel = document.getElementById('cancContagemVisivel');
    const tabelaOriginalHtml = tabela ? tabela.innerHTML : '';
    const cabecalhoOriginalHtml = tabelaCabecalho ? tabelaCabecalho.innerHTML : '';
    let buscaTimer = null;
    let buscaController = null;
    let modoBuscaGlobal = false;

    function escaparHtml(valor) {
        return String(valor ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
    }
    function formatarDataTabela(iso) {
        if (!iso) return '—';
        const p=String(iso).split('-');
        return p.length===3 ? `${p[2]}/${p[1]}/${p[0]}` : escaparHtml(iso);
    }
    function iniciaisResponsavel(nome) {
        const p=String(nome||'').trim().split(/\s+/).filter(Boolean);
        if (!p.length) return '--';
        if (p.length===1) return p[0].slice(0,2).toUpperCase();
        return (p[0][0]+p[p.length-1][0]).toUpperCase();
    }
    function atualizarContagem(total) { if (contagemVisivel) contagemVisivel.textContent=total; }
    function mostrarBuscaVazia(mostrar) { if (buscaVazia) buscaVazia.style.display=mostrar?'flex':'none'; }

    function restaurarTabelaOriginal() {
        if (!tabela) return;
        modoBuscaGlobal=false;
        tabela.innerHTML=tabelaOriginalHtml;
        if (tabelaCabecalho) tabelaCabecalho.innerHTML=cabecalhoOriginalHtml;
        mostrarBuscaVazia(false);
        atualizarContagem(tabela.querySelectorAll('tr.canc-row').length);
    }

    function montarCabecalhoBuscaGlobal() {
        if (!tabelaCabecalho) return;
        tabelaCabecalho.innerHTML=`
            <th class="col-ticket">Ticket</th><th class="col-designacao">Designação</th>
            <th class="col-cliente">Cliente Final</th><th class="col-cidade">Cidade/UF</th>
            <th class="col-sigla">ISP</th><th class="col-protocolo">Protocolo</th>
            <th class="col-data">Data de Abertura</th><th class="col-status">Status</th>
            <th class="col-responsavel">Responsável</th><th class="col-fila">Fila</th>
            <th class="col-obs">Observações</th><th class="col-acoes">Ações</th>`;
    }

    function montarLinhaBuscaGlobal(item) {
        const detalheUrl = escaparHtml(
            item.detalhe_url || `/cancelamentos/${item.id}/`
        );

        const ticketUrl = String(
            item.ticket_url || ''
        ).trim();

        const fila = escaparHtml(
            item.fila || ''
        );

        const status = escaparHtml(
            item.status || ''
        );

        const cidadeUf = (
            item.cidade || item.uf
        )
            ? `${escaparHtml(item.cidade || '—')}/${escaparHtml(item.uf || '—')}`
            : '—';

        const obs = Number(
            item.total_observacoes || 0
        );

        const ticketHtml = ticketUrl
            ? (
                `<a href="${escaparHtml(ticketUrl)}" ` +
                `target="_blank" rel="noopener noreferrer" ` +
                `class="ticket-chip ticket-link" ` +
                `title="Abrir ticket no OTRS">` +
                `${escaparHtml(item.ticket_arion || '—')}` +
                `</a>`
            )
            : (
                `<span class="ticket-chip" ` +
                `title="Ticket sem link do OTRS cadastrado">` +
                `${escaparHtml(item.ticket_arion || '—')}` +
                `</span>`
            );

        return `
            <tr
                class="canc-row canc-row--global"
                data-id="${escaparHtml(item.id)}"
                data-fila="${fila}"
                data-detail-url="${detalheUrl}"
                tabindex="0"
            >
                <td class="col-ticket">
                    ${ticketHtml}
                </td>

                <td class="col-designacao font-mono">
                    <a
                        href="${detalheUrl}"
                        class="canc-global-detail-link"
                        title="Ver detalhes do cancelamento"
                    >
                        ${escaparHtml(item.designacao_circuito || '—')}
                    </a>
                </td>

                <td class="col-cliente canc-cliente">
                    ${escaparHtml(item.cliente_final || item.cliente || '—')}
                </td>

                <td class="col-cidade">
                    ${cidadeUf}
                </td>

                <td class="col-sigla">
                    ${escaparHtml(item.isp || '—')}
                </td>

                <td class="col-protocolo">
                    ${escaparHtml(item.protocolo || '—')}
                </td>

                <td class="col-data">
                    ${formatarDataTabela(item.data_criacao_chamado)}
                </td>

                <td class="col-status">
                    <span class="status-badge status-badge--${status.toLowerCase()}">
                        ${escaparHtml(item.status_label || '—')}
                    </span>
                </td>

                <td class="col-responsavel">
                    <div class="responsavel-cell">
                        <span class="responsavel-avatar">
                            ${iniciaisResponsavel(item.responsavel)}
                        </span>
                        <span class="responsavel-nome">
                            ${escaparHtml(item.responsavel || 'Sem responsável')}
                        </span>
                    </div>
                </td>

                <td class="col-fila">
                    <span class="canc-fila-badge canc-fila-badge--${fila.toLowerCase()}">
                        ${escaparHtml(item.fila_label || item.fila || '—')}
                    </span>
                </td>

                <td class="col-obs">
                    <button
                        class="obs-btn"
                        data-action="ver-obs"
                        type="button"
                    >
                        Ver
                        ${
                            obs
                                ? ` <span class="obs-btn__count">${obs}</span>`
                                : ''
                        }
                    </button>
                </td>

                <td class="col-acoes">
                    <div class="row-actions">
                        <a
                            href="${detalheUrl}"
                            class="row-action-btn"
                            title="Ver detalhes"
                            aria-label="Ver detalhes"
                        >
                            <svg
                                width="14"
                                height="14"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                            >
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                <circle cx="12" cy="12" r="3"/>
                            </svg>
                        </a>
                    </div>
                </td>
            </tr>
        `;
    }

    function renderizarResultadosGlobais(resultados) {
        if (!tabela) return;
        modoBuscaGlobal=true;
        montarCabecalhoBuscaGlobal();
        if (!resultados.length) { tabela.innerHTML=''; atualizarContagem(0); mostrarBuscaVazia(true); return; }
        tabela.innerHTML=resultados.map(montarLinhaBuscaGlobal).join('');
        atualizarContagem(resultados.length); mostrarBuscaVazia(false);
    }

    function parametrosBuscaGlobal(termo) {
        const params=new URLSearchParams(); params.set('q',termo);
        Object.entries(filtrosAtuaisDaUrl()).forEach(([k,v])=>{ if(v) params.set(k,v); });
        return params;
    }
    async function consultarBuscaGlobal(termo) {
        if (buscaController) buscaController.abort();
        buscaController=new AbortController();
        try {
            const resp=await fetch(`${API_BASE}busca-global/?${parametrosBuscaGlobal(termo).toString()}`,{method:'GET',headers:{'X-Requested-With':'XMLHttpRequest'},signal:buscaController.signal});
            if(!resp.ok) return null;
            const data=await resp.json(); return data&&data.ok!==false?data:null;
        } catch(err) { if(err.name!=='AbortError') showToast('Não foi possível concluir a pesquisa global.','warning'); return null; }
    }
    async function executarBuscaGlobal() {
        if(!inputBusca) return;
        const termo=inputBusca.value.trim();
        if(termo.length<2){restaurarTabelaOriginal();return;}
        const resposta=await consultarBuscaGlobal(termo);
        if(!inputBusca||inputBusca.value.trim()!==termo||!resposta) return;
        renderizarResultadosGlobais(Array.isArray(resposta.resultados)?resposta.resultados:[]);
    }

    if(inputBusca){
        inputBusca.value='';
        const u=new URL(window.location.href);
        if(u.searchParams.has('busca')){u.searchParams.delete('busca');history.replaceState({},'',u.pathname+(u.search?u.search:''));}
        inputBusca.addEventListener('input',()=>{clearTimeout(buscaTimer);const t=inputBusca.value.trim();if(t.length<2){restaurarTabelaOriginal();return;}buscaTimer=setTimeout(executarBuscaGlobal,300);});
        inputBusca.addEventListener('keydown',(e)=>{if(e.key==='Enter'){e.preventDefault();clearTimeout(buscaTimer);executarBuscaGlobal();}});
    }
    if(btnBuscaClear){btnBuscaClear.addEventListener('click',()=>{clearTimeout(buscaTimer);if(buscaController)buscaController.abort();if(inputBusca){inputBusca.value='';inputBusca.focus();}restaurarTabelaOriginal();});}

    document.addEventListener('click',(e)=>{
        if(!modoBuscaGlobal)return;
        const row=e.target.closest('tr.canc-row--global'); if(!row)return;
        if(e.target.closest('a,button,input,select,textarea,label'))return;
        if(row.dataset.detailUrl)window.location.href=row.dataset.detailUrl;
    });
    document.addEventListener('keydown',(e)=>{
        if(!modoBuscaGlobal||e.key!=='Enter')return;
        const row=e.target.closest('tr.canc-row--global');
        if(row&&row.dataset.detailUrl)window.location.href=row.dataset.detailUrl;
    });

    /* 16. SELEÇÃO E MOVIMENTAÇÃO DE FILA EM LOTE */
    const bulkbar = document.getElementById('cancBulkbar');
    const bulkCount = document.getElementById('cancBulkCount');
    const bulkCancelar = document.getElementById('cancBulkCancelar');

    function checkboxesLote() {
        return Array.from(
            document.querySelectorAll(
                '#cancTabelaBody .canc-row-checkbox'
            )
        );
    }

    function selecionadosLote() {
        return checkboxesLote()
            .filter((checkbox) => checkbox.checked)
            .map((checkbox) => String(checkbox.dataset.id || checkbox.value || '').trim())
            .filter(Boolean);
    }

    function atualizarSelecaoLote() {
        const checkboxes = checkboxesLote();
        const selecionados = checkboxes.filter(
            (checkbox) => checkbox.checked
        );

        document
            .querySelectorAll('#cancTabelaBody tr.canc-row')
            .forEach((row) => {
                const checkbox = row.querySelector(
                    '.canc-row-checkbox'
                );

                row.classList.toggle(
                    'is-selected',
                    Boolean(checkbox && checkbox.checked)
                );
            });

        const selecionarTodos = document.getElementById(
            'cancSelecionarTodos'
        );

        if (selecionarTodos) {
            selecionarTodos.checked = (
                checkboxes.length > 0 &&
                selecionados.length === checkboxes.length
            );

            selecionarTodos.indeterminate = (
                selecionados.length > 0 &&
                selecionados.length < checkboxes.length
            );
        }

        if (bulkCount) {
            bulkCount.textContent = selecionados.length;
        }

        if (bulkbar) {
            bulkbar.classList.toggle(
                'canc-bulkbar--visible',
                selecionados.length > 0
            );
        }
    }

    function limparSelecaoLote() {
        checkboxesLote().forEach((checkbox) => {
            checkbox.checked = false;
        });

        const selecionarTodos = document.getElementById(
            'cancSelecionarTodos'
        );

        if (selecionarTodos) {
            selecionarTodos.checked = false;
            selecionarTodos.indeterminate = false;
        }

        atualizarSelecaoLote();
    }

    async function moverCancelamentosLote(
        ids,
        filaDestino,
        btn
    ) {
        const idsValidos = Array.from(
            new Set(
                (ids || [])
                    .map((id) => String(id).trim())
                    .filter(Boolean)
            )
        );

        if (!idsValidos.length) {
            showToast(
                'Selecione pelo menos um cancelamento.',
                'warning'
            );

            return false;
        }

        if (!filaDestino) {
            showToast(
                'Não foi possível identificar a fila de destino.',
                'error'
            );

            return false;
        }

        const filaLabel = (
            btn &&
            btn.textContent
        )
            ? btn.textContent
                .replace(/\s+/g, ' ')
                .trim()
                .replace(/^Mover para\s+/i, '')
            : filaDestino;

        const confirmar = await showConfirm(
            (
                `Mover ${idsValidos.length} cancelamento(s) ` +
                `para ${filaLabel}?`
            ),
            {
                titulo: 'Mover cancelamentos em lote',
                textoOk: 'Mover selecionados'
            }
        );

        if (!confirmar) {
            return false;
        }

        setLoading(
            btn,
            true,
            'Movendo...'
        );

        const fd = new FormData();

        idsValidos.forEach((id) => {
            fd.append('ids', id);
        });

        fd.append(
            'fila_destino',
            filaDestino
        );

        fd.append(
            'motivo',
            'Movimentação em lote.'
        );

        try {
            const data = await requestApi(
                `${API_BASE}mover-lote/`,
                {
                    method: 'POST',
                    body: fd
                }
            );

            const movidos = Number(
                data.movidos || 0
            );

            const falhas = Array.isArray(
                data.falhas
            )
                ? data.falhas
                : [];

            if (falhas.length === 0) {
                showToast(
                    (
                        `${movidos} cancelamento(s) ` +
                        `movido(s) para ${filaLabel}.`
                    ),
                    'success'
                );
            } else {
                const primeiraFalha = falhas[0];
                const restante = Math.max(
                    0,
                    falhas.length - 1
                );

                let mensagem = (
                    `${movidos} movido(s). ` +
                    `${falhas.length} não puderam ser movidos.`
                );

                if (
                    primeiraFalha &&
                    primeiraFalha.ticket_arion
                ) {
                    mensagem += (
                        ` ${primeiraFalha.ticket_arion}: ` +
                        `${primeiraFalha.erro || 'erro na movimentação'}.`
                    );
                }

                if (restante > 0) {
                    mensagem += (
                        ` E mais ${restante} falha(s).`
                    );
                }

                showToast(
                    mensagem,
                    movidos > 0
                        ? 'warning'
                        : 'error'
                );
            }

            limparSelecaoLote();

            setTimeout(
                () => window.location.reload(),
                700
            );

            return movidos > 0;

        } catch (err) {
            showToast(
                err.message ||
                'Não foi possível mover os cancelamentos selecionados.',
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    document.addEventListener(
        'change',
        (e) => {
            if (
                e.target.matches(
                    '#cancSelecionarTodos'
                )
            ) {
                const marcado = e.target.checked;

                checkboxesLote().forEach(
                    (checkbox) => {
                        checkbox.checked = marcado;
                    }
                );

                atualizarSelecaoLote();
                return;
            }

            if (
                e.target.matches(
                    '.canc-row-checkbox'
                )
            ) {
                atualizarSelecaoLote();
            }
        }
    );

    if (bulkCancelar) {
        bulkCancelar.addEventListener(
            'click',
            limparSelecaoLote
        );
    }

    /* 16. AÇÕES DE API */
    async function apropriarCancelamento(id, btn) {
        setLoading(btn, true, 'Assumindo...');

        try {
            await requestApi(
                `${API_BASE}${id}/apropriar/`,
                {
                    method: 'POST'
                }
            );

            showToast(
                'Chamado apropriado com sucesso.',
                'success'
            );

            window.location.reload();

            return true;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    async function liberarCancelamento(id, btn) {
        const ok = await showConfirm(
            'O chamado ficará sem responsável e poderá ser assumido por qualquer analista. Deseja continuar?',
            {
                titulo: 'Liberar chamado',
                textoOk: 'Liberar'
            }
        );

        if (!ok) return false;

        setLoading(
            btn,
            true,
            'Liberando...'
        );

        try {
            await requestApi(
                `${API_BASE}${id}/liberar/`,
                {
                    method: 'POST'
                }
            );

            showToast(
                'Chamado liberado.',
                'success'
            );

            window.location.reload();

            return true;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    async function transferirCancelamento(id, responsavelId, btn) {
        if (!responsavelId) {
            showToast(
                'Selecione um responsável para transferir.',
                'warning'
            );

            return false;
        }

        setLoading(
            btn,
            true,
            'Transferindo...'
        );

        try {
            await requestApi(
                `${API_BASE}${id}/transferir/`,
                {
                    method: 'POST',
                    body: {
                        responsavel_id: responsavelId
                    }
                }
            );

            showToast(
                'Responsável transferido com sucesso.',
                'success'
            );

            window.location.reload();

            return true;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    async function alterarStatus(id, status, btn) {
        setLoading(
            btn,
            true,
            'Atualizando...'
        );

        try {
            await requestApi(
                `${API_BASE}${id}/status/`,
                {
                    method: 'POST',
                    body: {
                        status
                    }
                }
            );

            showToast(
                'Status atualizado.',
                'success'
            );

            window.location.reload();

            return true;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    async function moverCancelamento(id, filaDestino, motivo, btn) {
        setLoading(
            btn,
            true,
            'Movendo...'
        );

        try {
            await requestApi(
                `${API_BASE}${id}/mover/`,
                {
                    method: 'POST',
                    body: {
                        fila_destino: filaDestino,
                        motivo: motivo || ''
                    }
                }
            );

            showToast(
                'Cancelamento movido de fila com sucesso.',
                'success'
            );

            window.location.reload();

            return true;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    async function buscarDetalhe(id) {
        const data = await requestApi(
            `${API_BASE}${id}/`,
            {
                method: 'GET'
            }
        );

        return data.cancelamento || null;
    }

    async function editarCancelamento(id, dados, btn) {
        if (!id) return false;

        setLoading(btn, true, 'Salvando...');

        try {
            await requestApi(
                `${API_BASE}${id}/editar/`,
                {
                    method: 'POST',
                    body: dados
                }
            );

            showToast(
                'Dados atualizados com sucesso.',
                'success'
            );

            return true;

        } catch (err) {
            showToast(
                err.message || 'Não foi possível atualizar os dados.',
                'error'
            );

            return false;

        } finally {
            setLoading(
                btn,
                false
            );
        }
    }

    async function listarObservacoes(id) {
        const data = await requestApi(
            `${API_BASE}${id}/observacoes/`,
            {
                method: 'GET'
            }
        );

        return data.observacoes || [];
    }

    async function adicionarObservacao(id, texto, btn) {
        if (!texto || !texto.trim()) {
            showToast(
                'Escreva um texto antes de salvar a observação.',
                'warning'
            );

            return null;
        }

        setLoading(
            btn,
            true,
            'Salvando...'
        );

        try {
            const data = await requestApi(
                `${API_BASE}${id}/observacoes/adicionar/`,
                {
                    method: 'POST',
                    body: {
                        texto: texto.trim()
                    }
                }
            );

            showToast(
                'Observação adicionada.',
                'success'
            );

            return data.observacao;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            return null;

        } finally {
            setLoading(
                btn,
                false
            );
        }
    }

    async function criarPendencia(id, payload, btn) {
        if (
            payload.data_prevista &&
            typeof payload.data_prevista === 'string'
        ) {
            const regex = /^\d{4}-\d{2}-\d{2}$/;

            if (!regex.test(payload.data_prevista)) {
                showToast(
                    'Data deve estar no formato YYYY-MM-DD.',
                    'warning'
                );

                return null;
            }
        }

        setLoading(
            btn,
            true,
            'Salvando pendência...'
        );

        try {
            const data = await requestApi(
                `${API_BASE}${id}/pendencias/criar/`,
                {
                    method: 'POST',
                    body: payload
                }
            );

            showToast(
                'Pendência adicionada com sucesso.',
                'success'
            );

            return data.pendencia;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            return null;

        } finally {
            setLoading(
                btn,
                false
            );
        }
    }

    async function resolverPendencia(pendenciaId, btn) {
        const ok = await showConfirm(
            'Confirma a resolução desta pendência?',
            {
                titulo: 'Resolver pendência',
                textoOk: 'Resolver'
            }
        );

        if (!ok) return null;

        setLoading(
            btn,
            true,
            'Resolvendo...'
        );

        try {
            const data = await requestApi(
                `${API_BASE}pendencias/${pendenciaId}/resolver/`,
                {
                    method: 'POST'
                }
            );

            showToast(
                'Pendência resolvida.',
                'success'
            );

            return data.pendencia;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            return null;

        } finally {
            setLoading(
                btn,
                false
            );
        }
    }

    async function descartarPendencia(pendenciaId, btn) {
        const ok = await showConfirm(
            'A pendência não será apagada, apenas marcada como descartada. Deseja continuar?',
            {
                titulo: 'Descartar pendência',
                textoOk: 'Descartar',
                perigo: true
            }
        );

        if (!ok) return null;

        setLoading(
            btn,
            true,
            'Descartando...'
        );

        try {
            const data = await requestApi(
                `${API_BASE}pendencias/${pendenciaId}/descartar/`,
                {
                    method: 'POST'
                }
            );

            showToast(
                'Pendência descartada.',
                'success'
            );

            return data.pendencia;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            return null;

        } finally {
            setLoading(
                btn,
                false
            );
        }
    }

    async function atualizarFinanceiro(id, payload, btn) {
        setLoading(
            btn,
            true,
            'Salvando...'
        );

        try {
            await requestApi(
                `${API_BASE}${id}/financeiro/`,
                {
                    method: 'POST',
                    body: payload
                }
            );

            showToast(
                'Dados financeiros atualizados.',
                'success'
            );

            window.location.reload();

            return true;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    async function concluirCancelamento(id, payload, btn) {
        setLoading(
            btn,
            true,
            'Concluindo...'
        );

        try {
            await requestApi(
                `${API_BASE}${id}/concluir/`,
                {
                    method: 'POST',
                    body: payload
                }
            );

            showToast(
                'Cancelamento concluído e encerrado.',
                'success'
            );

            window.location.reload();

            return true;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    async function excluirCancelamento(id, btn) {
        const ok = await showConfirm(
            'Esta ação é irreversível. Deseja realmente excluir este cancelamento?',
            {
                titulo: 'Excluir cancelamento',
                textoOk: 'Excluir',
                perigo: true
            }
        );

        if (!ok) return false;

        setLoading(
            btn,
            true,
            'Excluindo...'
        );

        try {
            await requestApi(
                `${API_BASE}${id}/excluir/`,
                {
                    method: 'POST'
                }
            );

            showToast(
                'Cancelamento excluído.',
                'success'
            );

            const row = document.querySelector(
                `tr[data-id="${id}"]`
            );

            if (row) {
                row.remove();
            } else {
                window.location.href = '/cancelamentos/';
            }

            return true;

        } catch (err) {
            showToast(
                err.message,
                'error'
            );

            setLoading(
                btn,
                false
            );

            return false;
        }
    }

    /* 17. NAMESPACE PÚBLICO */
    window.Cancelamentos = {
        root,
        wrapper,
        API_BASE,
        filaAtual,
        urlCriar,

        requestApi,
        ApiError,
        getCsrfToken,

        showToast,
        showConfirm,
        openModal,
        closeModal,
        setLoading,

        formatDataHora,
        textoOuTraco,

        filtrosAtuaisDaUrl,
        construirUrlComFiltros,

        apropriarCancelamento,
        liberarCancelamento,
        transferirCancelamento,
        alterarStatus,
        moverCancelamento,
        moverCancelamentosLote,
        buscarDetalhe,
        editarCancelamento,

        listarObservacoes,
        adicionarObservacao,

        criarPendencia,
        resolverPendencia,
        descartarPendencia,

        atualizarFinanceiro,
        concluirCancelamento,
        excluirCancelamento,

        Modais: {}
    };

    /* 18. BLOQUEIA SUBMIT NATIVO DOS MODAIS */
    document.addEventListener('submit', (e) => {
        if (e.target.closest('.modal-box')) {
            e.preventDefault();
        }
    });

    /* 19. DELEGAÇÃO GLOBAL DE EVENTOS */
    document.addEventListener('click', (e) => {
        const acaoBtn = e.target.closest('[data-action]');

        if (!acaoBtn) return;
        if (acaoBtn.disabled) return;

        const acao = acaoBtn.dataset.action;

        /*
         * Ação em lote fica fora de uma <tr>, portanto precisa ser
         * tratada antes da validação de ID individual.
         */
        if (acao === 'mover-fila-lote') {
            const ids = selecionadosLote();
            const filaDestino =
                acaoBtn.dataset.filaDestino ||
                root.dataset.proximaFila;

            moverCancelamentosLote(
                ids,
                filaDestino,
                acaoBtn
            );

            return;
        }

        const row = e.target.closest('tr[data-id]');

        const id = row
            ? row.dataset.id
            : root.dataset.cancelamentoId;

        if (!id) return;

        const Modais = window.Cancelamentos.Modais || {};

        switch (acao) {

            case 'apropriar':
            case 'apropriar-detalhe':
                apropriarCancelamento(
                    id,
                    acaoBtn
                );
                break;

            case 'liberar':
            case 'liberar-detalhe':
                liberarCancelamento(
                    id,
                    acaoBtn
                );
                break;

            case 'excluir':
                excluirCancelamento(
                    id,
                    acaoBtn
                );
                break;

            /*
             * EDITAR DADOS
             */
            case 'editar':
            case 'editar-detalhe':

                if (Modais.abrirModalEditar) {
                    Modais.abrirModalEditar(
                        id
                    );
                } else {
                    showToast(
                        'O modal de edição ainda não está disponível.',
                        'warning'
                    );
                }

                break;

            /*
             * CONCLUSÃO
             */
            case 'concluir': {

                const ticketEl = row
                    ? row.querySelector('.ticket-chip')
                    : document.getElementById('detalheTicketArion');

                if (Modais.abrirModalConcluir) {
                    Modais.abrirModalConcluir(
                        id,
                        ticketEl
                            ? ticketEl.textContent.trim()
                            : ''
                    );
                }

                break;
            }

            /*
             * OBSERVAÇÕES
             */
            case 'ver-obs': {

                const ticketEl = row
                    ? row.querySelector('.ticket-chip')
                    : document.getElementById('detalheTicketArion');

                if (Modais.abrirModalObs) {
                    Modais.abrirModalObs(
                        id,
                        ticketEl
                            ? ticketEl.textContent.trim()
                            : ''
                    );
                }

                break;
            }

            /*
             * MOVIMENTAÇÃO DE FILA
             */
            case 'mover-fila': {

                const filaDestino =
                    acaoBtn.dataset.filaDestino ||
                    root.dataset.proximaFila;

                if (!filaDestino) {
                    break;
                }

                if (Modais.abrirModalMovimentacao) {
                    Modais.abrirModalMovimentacao(
                        id,
                        filaDestino
                    );
                }

                break;
            }

            /*
             * CRIA PENDÊNCIA E MOVE PARA PENDÊNCIA
             */
            case 'enviar-pendencia':

                if (Modais.abrirModalPendencia) {
                    Modais.abrirModalPendencia(
                        id,
                        {
                            moverParaPendencia: true
                        }
                    );
                }

                break;

            /*
             * APENAS ADICIONA PENDÊNCIA
             */
            case 'adicionar-pendencia':

                if (Modais.abrirModalPendencia) {
                    Modais.abrirModalPendencia(
                        id,
                        {
                            moverParaPendencia: false
                        }
                    );
                }

                break;

            /*
             * FINANCEIRO LEGADO
             */
            case 'editar-financeiro': {

                const ticketEl = row
                    ? row.querySelector('.ticket-chip')
                    : document.getElementById('detalheTicketArion');

                if (Modais.abrirModalFinanceiro) {
                    Modais.abrirModalFinanceiro(
                        id,
                        ticketEl
                            ? ticketEl.textContent.trim()
                            : ''
                    );
                }

                break;
            }

            /*
             * RESOLVER PENDÊNCIA
             */
            case 'resolver-pendencia':

                resolverPendencia(
                    acaoBtn.dataset.pendenciaId,
                    acaoBtn
                ).then((p) => {

                    if (p) {
                        window.location.reload();
                    }

                });

                break;

            /*
             * DESCARTAR PENDÊNCIA
             */
            case 'descartar-pendencia':

                descartarPendencia(
                    acaoBtn.dataset.pendenciaId,
                    acaoBtn
                ).then((p) => {

                    if (p) {
                        window.location.reload();
                    }

                });

                break;

            /*
             * TRANSFERIR RESPONSÁVEL
             */
            case 'transferir':

                if (Modais.abrirModalTransferir) {
                    Modais.abrirModalTransferir(
                        id
                    );
                }

                break;
        }
    });

})();

/* ============================================================
   ARION PROJETOS — BROKER
   dashboard.js — Filtros, seleção, modal, toggle robô, polling,
   e consumo dinâmico de KPIs do OTRS (Gráficos e Cards)
   ============================================================ */

(function () {
    'use strict';

    // ── UTILS ────────────────────────────────────────────────
    function escapeHtml(str) {
        if (str === null || str === undefined) return '—';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function getCsrf() {
        return window.ArionBroker && window.ArionBroker.getCsrf
            ? window.ArionBroker.getCsrf()
            : (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    }

    function post(url, payload) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrf(),
            },
            body: JSON.stringify(payload),
        }).then(function (r) {
            if (!r.ok) {
                return r.json().catch(() => ({})).then(errBody => {
                    throw new Error(errBody.erro || ('HTTP ' + r.status));
                });
            }
            return r.json();
        });
    }

    // ── ESTADO LOCAL — RECs ──────────────────────────────────
    let filtroStatus  = 'todos';
    let filtroProjeto = 'todos';
    let filtroChamado = 'todos';
    let termoBusca    = '';
    let ultimoPollTs  = Math.floor(Date.now() / 1000);

    // ── REFS ELEMENTOS CLÁSSICOS ─────────────────────────────
    const recsBody          = document.getElementById('recsBody');
    const bulkBar           = document.getElementById('bulkBar');
    const checkAll          = document.getElementById('checkAll');
    const selectedCount     = document.getElementById('selectedCount');
    const btnDisparar       = document.getElementById('btnDispararSelecionados');
    const btnBaixarSemEmail = document.getElementById('btnBaixarSemEmail');
    const btnDesmarcar      = document.getElementById('btnDesmarcar');
    const btnSelPendentes   = document.getElementById('btnSelecionarPendentes');
    const searchInput       = document.getElementById('searchInput');
    const btnToggleRobo     = document.getElementById('btnToggleRobo');
    const iconRobo          = document.getElementById('iconRobo');
    const textoRobo         = document.getElementById('textoRobo');
    const btnSincronizar    = document.getElementById('btnSincronizar');
    const modalSync         = document.getElementById('modalSync');
    const syncResultsContent = document.getElementById('syncResultsContent');

    // ── REFS NOVOS ELEMENTOS DE KPIs (DASHBOARD OTRS) ────────
    const kpiGrid             = document.getElementById('kpi-grid');
    const canvasChartOp       = document.getElementById('chartOp');
    const operadorasContainer = document.getElementById('operadoras-container');
    let chartInstance         = null;

    // ── MAPEAMENTO DE OPERADORAS E PROJETOS POR ID (Infalível) ──
    const ESTRUTURA = [
        {
            id: 'claro', nome: 'Claro', cor: 'claro',
            projetos: [
                { nome: 'Bradesco',        kpi_id: '613_2', is_brad: true, op_key: 'CLARO' },
                { nome: 'Banco do Brasil', kpi_id: '655_2' },
                { nome: 'Caixa Econômica', kpi_id: '682_2' },
                { nome: 'Correios',        kpi_id: '640_2' },
                { nome: 'Carrefour',       kpi_id: '702_2' }, // Carrefour mapeado pelo ID exato
                { nome: 'Diversos',        kpi_id: '686_2' }
            ]
        },
        {
            id: 'vivo', nome: 'Vivo', cor: 'vivo',
            projetos: [
                { nome: 'Bradesco',        kpi_id: '613_2', is_brad: true, op_key: 'VIVO' },
                { nome: "McDonald's",      kpi_id: '643_2' },
                { nome: 'L2L (LAN-to-LAN)',kpi_id: '654_2' }
            ]
        },
        {
            id: 'algar', nome: 'Algar', cor: 'algar',
            projetos: [
                { nome: 'Escolas Conectadas', kpi_id: '701_2' }
            ]
        }
    ];

    // ── EVENTOS DE FILTROS ───────────────────────────────────
    document.querySelectorAll('.dash-tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.dash-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            filtroStatus = tab.dataset.filter;
            aplicarFiltros();
        });
    });

    document.querySelectorAll('.filter-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filtroProjeto = btn.dataset.proj;
            aplicarFiltros();
        });
    });

    document.querySelectorAll('.chamado-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.chamado-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filtroChamado = btn.dataset.chamado;
            aplicarFiltros();
        });
    });

    if (searchInput) {
        searchInput.addEventListener('input', function () {
            termoBusca = this.value.toLowerCase().trim();
            aplicarFiltros();
        });
    }

    // ── LÓGICA DE FILTRAGEM RECs ─────────────────────────────
    function aplicarFiltros() {
        const rows = document.querySelectorAll('.rec-row');
        let visiveis = 0;
        if (!rows.length) return;
        if (recsBody) recsBody.style.display = 'none';

        rows.forEach(function (row) {
            const status     = row.dataset.status     || '';
            const proj       = row.dataset.proj       || '';
            const temChamado = row.dataset.temChamado || '';
            const search     = (row.dataset.search    || '').toLowerCase();

            const okStatus  = (
                filtroStatus === 'todos' ||
                status === filtroStatus ||
                (filtroStatus === 'PENDENTE' && (status === 'NOVO' || status === 'REVISAO'))
            );
            const okProjeto = (filtroProjeto === 'todos' || proj === filtroProjeto);
            const okChamado = (filtroChamado === 'todos' || temChamado === filtroChamado);
            const okBusca   = (!termoBusca || search.includes(termoBusca));

            const visivel = okStatus && okProjeto && okChamado && okBusca;
            row.style.display = visivel ? '' : 'none';
            if (visivel) visiveis++;
        });

        const emptyRow = document.getElementById('emptyRow');
        if (emptyRow) emptyRow.style.display = visiveis === 0 ? '' : 'none';
        if (recsBody) recsBody.style.display = '';
        atualizarBulkBar();
    }

    function atualizarBulkBar() {
        if (!selectedCount || !bulkBar) return;
        const total = document.querySelectorAll('.rec-check:checked').length;
        selectedCount.textContent = total;

        if (total > 0) {
            bulkBar.classList.add('visible');
        } else {
            bulkBar.classList.remove('visible');
            if (checkAll) checkAll.checked = false;
        }
    }

    // ── SELEÇÃO ───────────────────────────────────────────────
    if (checkAll) {
        checkAll.addEventListener('change', function () {
            document.querySelectorAll('.rec-row').forEach(function (row) {
                if (row.style.display !== 'none') {
                    const cb = row.querySelector('.rec-check');
                    if (cb) cb.checked = checkAll.checked;
                }
            });
            atualizarBulkBar();
        });
    }

    if (recsBody) {
        recsBody.addEventListener('change', function (e) {
            if (e.target.classList.contains('rec-check')) {
                atualizarBulkBar();
            }
        });
    }

    if (btnDesmarcar) {
        btnDesmarcar.addEventListener('click', function () {
            document.querySelectorAll('.rec-check:checked').forEach(cb => cb.checked = false);
            atualizarBulkBar();
        });
    }

    if (btnSelPendentes) {
        btnSelPendentes.addEventListener('click', function () {
            document.querySelectorAll('.rec-row').forEach(function (row) {
                if (row.style.display === 'none') return;
                const status = row.dataset.status || '';
                if (status === 'NOVO' || status === 'REVISAO') {
                    const cb = row.querySelector('.rec-check');
                    if (cb) cb.checked = true;
                }
            });
            atualizarBulkBar();
        });
    }

    function getSelecionados() {
        return Array.from(document.querySelectorAll('.rec-check:checked')).map(cb => cb.value);
    }

    if (btnDisparar) {
        btnDisparar.addEventListener('click', function () {
            const ids = getSelecionados();
            if (!ids.length) return;
            if (!window.confirm(`Disparar e-mail para ${ids.length} REC(s) selecionada(s)?`)) return;

            btnDisparar.disabled = true;
            post('/painel/disparar/', { recs: ids })
                .then(data => {
                    alert(data.mensagem || 'Disparo concluído.');
                    window.location.reload();
                })
                .catch(err => {
                    alert('Erro ao disparar: ' + err.message);
                    btnDisparar.disabled = false;
                });
        });
    }

    if (btnBaixarSemEmail) {
        btnBaixarSemEmail.addEventListener('click', function () {
            const ids = getSelecionados();
            if (!ids.length) return;
            if (!window.confirm(`Marcar ${ids.length} REC(s) como enviada(s) sem disparar e-mail?`)) return;

            btnBaixarSemEmail.disabled = true;
            post('/painel/baixar-sem-email/', { recs: ids })
                .then(data => {
                    alert(data.mensagem || 'RECs marcadas.');
                    window.location.reload();
                })
                .catch(err => {
                    alert('Erro: ' + err.message);
                    btnBaixarSemEmail.disabled = false;
                });
        });
    }

    // Habilita/desabilita botões de bulk conforme seleção
    const observerSelecao = function () {
        const total = document.querySelectorAll('.rec-check:checked').length;
        if (btnDisparar)       btnDisparar.disabled = total === 0;
        if (btnBaixarSemEmail) btnBaixarSemEmail.disabled = total === 0;
    };
    if (recsBody) recsBody.addEventListener('change', observerSelecao);
    if (checkAll) checkAll.addEventListener('change', observerSelecao);

    // ── ENVIO INDIVIDUAL (botão da linha) ────────────────────
    if (recsBody) {
        recsBody.addEventListener('click', function (e) {
            const btn = e.target.closest('.row-action--send');
            if (!btn) return;
            const recId = btn.dataset.rec;
            if (!recId) return;
            if (!window.confirm(`Enviar e-mail para a REC ${recId}?`)) return;

            post('/painel/disparar/', { recs: [recId] })
                .then(data => {
                    alert(data.mensagem || `REC ${recId} enviada.`);
                    window.location.reload();
                })
                .catch(err => alert('Erro ao enviar: ' + err.message));
        });
    }

    // ── MODAL DETALHES REC E OUTROS PROCESSOS ────────────────
    const modalOverlay   = document.getElementById('modalOverlay');
    const modalRecId     = document.getElementById('modalRecId');
    const modalBl        = document.getElementById('modalBl');
    const modalProjeto   = document.getElementById('modalProjeto');
    const modalSintoma   = document.getElementById('modalSintoma');

    window.abrirModal = function (recId, bl, projeto, sintoma) {
        if (!modalRecId) return;
        modalRecId.textContent   = recId   || '—';
        modalBl.textContent      = bl      || '—';
        modalProjeto.textContent = projeto || '—';
        modalSintoma.textContent = sintoma || 'Sem sintoma registrado.';
        modalOverlay.classList.add('open');
        document.body.style.overflow = 'hidden';
    };

    window.fecharModal = function () {
        if (modalOverlay) modalOverlay.classList.remove('open');
        document.body.style.overflow = '';
    };

    window.fecharModalSync = function () {
        if (modalSync) modalSync.classList.remove('open');
        document.body.style.overflow = '';
    };

    window.descartarRec = function (recId) {
        if (!window.confirm(`Descartar a REC ${recId}?`)) return;
        post('/painel/descartar/', { rec_id: recId })
            .then(() => window.location.reload())
            .catch(err => alert('Erro ao descartar: ' + err.message));
    };

    // ── REENVIO MANUAL (RECs já ENVIADO/REGISTRADO) ──────────
    // Não altera o status da REC — apenas redispara o e-mail.
    // Uso restrito: botão só aparece pra admin no template.
    window.reenviarRec = function (recId) {
        if (!window.confirm(`Reenviar a REC ${recId}?\n\nIsso disparará o e-mail novamente. Use apenas para teste ou reenvio controlado — o status da REC não será alterado.`)) return;

        post('/painel/reenviar/', { rec_id: recId })
            .then(data => {
                alert(data.mensagem || `REC ${recId} reenviada.`);
                window.location.reload();
            })
            .catch(err => {
                alert('Erro ao reenviar: ' + err.message);
            });
    };

    function pollNovasRecs() {
        if (!recsBody) return;
        fetch(`/painel/recs/recentes/?desde=${ultimoPollTs}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (!data || !data.recs || data.recs.length === 0) return;
            ultimoPollTs = Math.floor(Date.now() / 1000);
            window.location.reload();
        }).catch(() => {});
    }

    // ── ROBÔ: TOGGLE ATIVO/PAUSADO ───────────────────────────
    if (btnToggleRobo) {
        btnToggleRobo.addEventListener('click', function () {
            btnToggleRobo.disabled = true;
            post('/painel/robo/toggle/', {})
                .then(data => {
                    const ativo = data.ativo;
                    btnToggleRobo.dataset.ativo = ativo ? 'true' : 'false';
                    btnToggleRobo.classList.toggle('btn-robo--ativo', ativo);
                    btnToggleRobo.classList.toggle('btn-robo--pausado', !ativo);
                    if (iconRobo) {
                        iconRobo.className = 'bi ' + (ativo ? 'bi-robot' : 'bi-pause-circle');
                    }
                    if (textoRobo) {
                        textoRobo.textContent = 'Robô: ' + (ativo ? 'Ativo' : 'Pausado');
                    }
                })
                .catch(err => alert('Erro ao alternar robô: ' + err.message))
                .finally(() => { btnToggleRobo.disabled = false; });
        });
    }

    // ── SINCRONIZAR PORTAL (SCRAPER MANUAL) ──────────────────
    if (btnSincronizar) {
        btnSincronizar.addEventListener('click', function () {
            btnSincronizar.disabled = true;
            if (modalSync) modalSync.classList.add('open');
            document.body.style.overflow = 'hidden';
            if (syncResultsContent) {
                syncResultsContent.innerHTML = `
                    <div style="text-align:center;color:#888;">
                        <i class="bi bi-gear spin-icon" style="font-size:2rem;"></i>
                        <p>Sincronizando com o portal da Claro...</p>
                    </div>
                `;
            }

            post('/painel/sincronizar/', {})
                .then(data => {
                    if (syncResultsContent) {
                        const erros = data.erros || [];
                        let errosHtml = '';
                        if (erros.length) {
                            errosHtml = `<ul style="color:#c62828; margin-top:10px;">${erros.map(e => `<li>${escapeHtml(e)}</li>`).join('')}</ul>`;
                        }
                        syncResultsContent.innerHTML = `
                            <div style="text-align:center;">
                                <i class="bi bi-check-circle-fill" style="font-size:2rem;color:#2e7d32;"></i>
                                <p>${escapeHtml(data.mensagem || 'Sincronização concluída.')}</p>
                                <p class="text-muted-sm">Novas: ${data.novas || 0} · Ignoradas: ${data.ignoradas || 0}</p>
                                ${errosHtml}
                            </div>
                        `;
                    }
                })
                .catch(err => {
                    if (syncResultsContent) {
                        syncResultsContent.innerHTML = `
                            <div style="text-align:center;color:#c62828;">
                                <i class="bi bi-x-circle-fill" style="font-size:2rem;"></i>
                                <p>Erro: ${escapeHtml(err.message)}</p>
                            </div>
                        `;
                    }
                })
                .finally(() => { btnSincronizar.disabled = false; });
        });
    }

    /* ============================================================
       ═ CONSUMO E RENDERIZAÇÃO DE KPIs ALINHADOS COM O BACKEND ═
       ============================================================ */

    function carregarDadosKpiOtrs() {
        fetch('/chamados/api/kpis/')
            .then(response => {
                if (!response.ok) throw new Error("Erro HTTP " + response.status);
                return response.json();
            })
            .then(data => {
                if (!data.ok) return;

                // Planifica tudo numa única array para facilitar a busca
                const listaKpisPlanificada = [];
                data.grupos.forEach(g => {
                    g.kpis.forEach(k => listaKpisPlanificada.push(k));
                });

                renderizarCardsSuperiores(listaKpisPlanificada);
                renderizarGraficoOperadoras(listaKpisPlanificada);
                renderizarOperadoras(listaKpisPlanificada);
                renderizarAlertasOperacionais(listaKpisPlanificada);
            })
            .catch(err => console.error("[KPI] Erro ao buscar métricas:", err));
    }

    // Renderiza os Cards do Topo (Global)
    function renderizarCardsSuperiores(kpis) {
        if (!kpiGrid) return;

        // KPI 251_2 é o "PROJETOS" global (total em aberto)
        const kpiProjetos = kpis.find(k => k.kpi_id === '251_2');
        const abertos = kpiProjetos ? kpiProjetos.valor : 0;

        // Atrasados: soma de tudo do grupo "CHAMADOS POR GESTORES +4D"
        const kpisAtrasados = kpis.filter(k => String(k.grupo).trim().toUpperCase() === 'CHAMADOS POR GESTORES +4D');
        const atrasados = kpisAtrasados.reduce((acc, k) => acc + k.valor, 0);

        kpiGrid.innerHTML = `
            <div class="kpi-card kpi-card--aberto">
                <div class="kpi-card__icon" style="background:rgba(59,130,246,0.12);color:var(--status-aberto)">
                    <svg width="18" height="18" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M12 8v4l3 3"/></svg>
                </div>
                <div class="kpi-card__label">Em Aberto</div>
                <div class="kpi-card__value" style="color:var(--status-aberto)">${abertos}</div>
                <div class="kpi-card__sub">Fila Geral OTRS</div>
            </div>
            <div class="kpi-card kpi-card--resolv">
                <div class="kpi-card__icon" style="background:rgba(34,197,94,0.12);color:var(--sla-ok)">
                    <svg width="18" height="18" fill="none" viewBox="0 0 24 24"><path stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                </div>
                <div class="kpi-card__label">Resolvidos</div>
                <div class="kpi-card__value" style="color:var(--sla-ok)">—</div>
                <div class="kpi-card__sub">Em breve</div>
            </div>
            <div class="kpi-card kpi-card--sla">
                <div class="kpi-card__icon" style="background:rgba(239,68,68,0.12);color:var(--sla-critico)">
                    <svg width="18" height="18" fill="none" viewBox="0 0 24 24"><path stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                </div>
                <div class="kpi-card__label">SLA Crítico</div>
                <div class="kpi-card__value" style="color:var(--sla-critico)">${atrasados}</div>
                <div class="kpi-card__sub">Gestores +4 Dias</div>
            </div>
        `;
    }

    // Renderiza os Cards agrupados por Operadora (Claro, Vivo, Algar)
    function renderizarOperadoras(kpis) {
        if (!operadorasContainer) return;

        let html = '';

        ESTRUTURA.forEach(op => {
            let opTotal = 0;
            let cardsHtml = '';

            op.projetos.forEach(proj => {
                // AGORA BUSCA PELO kpi_id EXATO! Fim do problema de string do Carrefour.
                const kpi = kpis.find(k => k.kpi_id === proj.kpi_id);
                let valor = 0;

                if (kpi) {
                    if (proj.is_brad) {
                        valor = (kpi.brad_por_operadora && kpi.brad_por_operadora[proj.op_key]) ? kpi.brad_por_operadora[proj.op_key] : 0;
                    } else {
                        valor = kpi.valor;
                    }
                }

                opTotal += valor;

                cardsHtml += `
                    <div class="projeto-card projeto-card--${op.cor}">
                        <div class="projeto-card__name">${escapeHtml(proj.nome)}</div>
                        <div class="projeto-card__num">${valor}</div>
                    </div>
                `;
            });

            html += `
                <div class="operadora-section operadora-section--${op.cor}">
                    <div class="operadora-header">
                        <span class="operadora-badge operadora-badge--${op.cor}">${op.nome}</span>
                        <span class="operadora-total-text">${opTotal} chamados</span>
                        <div class="operadora-divider"></div>
                    </div>
                    <div class="operadora-section__body">
                        <div class="projetos-grid">${cardsHtml}</div>
                    </div>
                </div>
            `;
        });

        // Remove a renderização antiga das operadoras se houver
        const wrapper = document.getElementById('op-blocks');
        if (wrapper) {
            wrapper.innerHTML = html;
        } else {
            operadorasContainer.insertAdjacentHTML('afterbegin', `<div id="op-blocks">${html}</div>`);
        }
    }

    function renderizarGraficoOperadoras(kpis) {
        if (!canvasChartOp) return;

        const bradKpi = kpis.find(k => k.kpi_id === '613_2');
        const bradVivo  = bradKpi && bradKpi.brad_por_operadora ? (bradKpi.brad_por_operadora.VIVO  || 0) : 0;
        const bradClaro = bradKpi && bradKpi.brad_por_operadora ? (bradKpi.brad_por_operadora.CLARO || 0) : 0;

        const algarKpi = kpis.find(k => k.kpi_id === '701_2');
        const algar    = algarKpi ? algarKpi.valor : 0;

        const dadosGrafico = {
            labels: ['Bradesco Vivo', 'Bradesco Claro', 'Projeto Algar'],
            datasets: [{
                label: 'Chamados Abertos',
                data: [bradVivo, bradClaro, algar],
                backgroundColor: [
                    'rgba(102, 0, 153, 0.75)',
                    'rgba(239, 26, 46, 0.75)',
                    'rgba(0, 154, 222, 0.75)'
                ],
                borderColor: ['#4a0072', '#b3000f', '#006ba1'],
                borderWidth: 1.5, borderRadius: 6
            }]
        };

        if (chartInstance) {
            chartInstance.data.datasets[0].data = dadosGrafico.datasets[0].data;
            chartInstance.update();
        } else {
            const ctx = canvasChartOp.getContext('2d');
            chartInstance = new Chart(ctx, {
                type: 'bar',
                data: dadosGrafico,
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
                }
            });
        }
    }

    function renderizarAlertasOperacionais(kpis) {
        if (!operadorasContainer) return;

        const gestoresKpi      = kpis.filter(k => String(k.grupo).trim().toUpperCase() === 'CHAMADOS POR GESTORES +4D');
        const cancelamentosKpi = kpis.filter(k => String(k.grupo).trim().toUpperCase() === 'CANCELAMENTOS');

        let html = '';

        if (gestoresKpi.length > 0) {
            html += `
                <div class="alert-section" style="margin-top:30px;">
                    <h4 class="alert-section__title" style="color:#d32f2f; margin-bottom:10px; font-weight:600;">
                        <i class="bi bi-exclamation-triangle-fill"></i> Alertas de Gestão (+4 Dias sem resolver)
                    </h4>
                    <div class="alert-list" style="display:flex; flex-direction:column; gap:8px;">
            `;
            gestoresKpi.forEach(k => {
                if (k.valor > 0) {
                    html += `
                        <div class="alert-item" style="display:flex; justify-content:space-between; background:#ffebee; color:#c62828; padding:12px; border-radius:6px; font-size:14px;">
                            <span>Fila: <strong>${escapeHtml(k.titulo)}</strong></span>
                            <span class="badge bg-danger" style="margin-left:auto; padding:4px 8px; border-radius:4px; color:#fff;">${k.valor} travados</span>
                        </div>
                    `;
                }
            });
            html += `</div></div>`;
        }

        if (cancelamentosKpi.length > 0) {
            html += `
                <div class="alert-section" style="margin-top:25px;">
                    <h4 class="alert-section__title" style="color:#e65100; margin-bottom:10px; font-weight:600;">
                        <i class="bi bi-x-circle-fill"></i> Fluxo de Cancelamentos Ativos (OTRS)
                    </h4>
                    <div class="alert-list" style="display:flex; flex-direction:column; gap:8px;">
            `;
            cancelamentosKpi.forEach(k => {
                if (k.valor > 0) {
                    html += `
                        <div class="alert-item" style="display:flex; justify-content:space-between; background:#fff3e0; color:#e65100; padding:12px; border-radius:6px; font-size:14px;">
                            <span>Alerta: <strong>${escapeHtml(k.titulo)}</strong></span>
                            <span class="badge bg-warning text-dark" style="margin-left:auto; padding:4px 8px; border-radius:4px;">${k.valor} chamados</span>
                        </div>
                    `;
                }
            });
            html += `</div></div>`;
        }

        const alertWrapper = document.getElementById('op-alerts');
        if (alertWrapper) {
            alertWrapper.innerHTML = html;
        } else {
            operadorasContainer.insertAdjacentHTML('beforeend', `<div id="op-alerts">${html}</div>`);
        }
    }

    // ── RUNNERS ──────────────────────────────────────────────
    setInterval(pollNovasRecs, 30000);

    if (kpiGrid || canvasChartOp) {
        carregarDadosKpiOtrs();
        setInterval(carregarDadosKpiOtrs, 60000);
    }

    atualizarBulkBar();
    aplicarFiltros();

})();
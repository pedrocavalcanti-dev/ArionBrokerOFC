/* ============================================================
   ARION PROJETOS — projetos.js
   Dropdown de status, busca, ordenação.
   + Lógica de "Em Aberto" unificada (!== resolvido)
   + Salvamento de filtros INSTANTÂNEO no Banco de Dados
   + Persistência do status individual do chamado no Banco de Dados
   ============================================================ */

(function () {
    'use strict';

    // ── REFS ─────────────────────────────────────────────────
    const tbody        = document.getElementById('tbody-chamados');
    const inputBusca   = document.getElementById('buscaChamado');
    const btnLimpar    = document.getElementById('btnLimparBusca');
    const filtroAging  = document.getElementById('filtroAging');
    const countVisivel = document.getElementById('count-visivel');
    const emptySearch  = document.getElementById('emptySearch');
    const emptyTerm    = document.getElementById('emptySearchTerm');
    const modalObs     = document.getElementById('modalObs');
    const modalObsTxt  = document.getElementById('modalObsTexto');
    const fecharModal  = document.getElementById('fecharModalObs');
    const cancelarModal= document.getElementById('cancelarModalObs');
    const salvarModal  = document.getElementById('salvarModalObs');
    const filterBtns   = document.querySelectorAll('.proj-filter-btn');
    const portal       = document.getElementById('statusDropdownPortal');

    // ── ESTADO INICIAL (Vindo do Banco de Dados) ─────────────
    const CONFIG = window.CHAMADOS_CONFIG || {};
    const filtrosBd = CONFIG.filtrosSalvos || {};

    let filtroStatus = filtrosBd.status || 'aberto';
    let termoBusca   = filtrosBd.busca || '';
    let filtroAgingV = filtrosBd.aging || '';

    let obsTargetBtn = null;
    let portalOwner  = null;

    // ── SALVAR NO BANCO DE DADOS (AJAX INSTANTÂNEO) ──────────
    function salvarFiltrosNoBanco() {
        if (!CONFIG.urlSalvarFiltro) return;

        const payload = {
            status: filtroStatus,
            busca: termoBusca,
            aging: filtroAgingV
        };

        const csrfEl = document.querySelector('input[name="csrfmiddlewaretoken"]');
        const csrf = csrfEl ? csrfEl.value : '';

        fetch(CONFIG.urlSalvarFiltro, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf
            },
            body: JSON.stringify(payload),
            credentials: 'same-origin'
        }).catch(function () {
            // Falhas de rede ignoradas silenciosamente
        });
    }

    // ── HELPERS ──────────────────────────────────────────────
    function setText(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    window.contarCards = function contarCards() {
        const rows = tbody ? Array.from(tbody.querySelectorAll('tr.chamado-row')) : [];
        let total = rows.length, aberto = 0, resolvido = 0, atendimento = 0, agingAlto = 0;

        rows.forEach(function (r) {
            const st    = r.dataset.status || '';
            const aging = parseInt(r.dataset.aging, 10) || 0;

            if (st !== 'resolvido')   aberto++;
            if (st === 'resolvido')   resolvido++;
            if (st === 'atendimento') atendimento++;
            if (aging > 7)            agingAlto++;
        });

        setText('stat-total',       total);
        setText('stat-aberto',      aberto);
        setText('stat-resolvido',   resolvido);
        setText('stat-atendimento', atendimento);
        setText('stat-aging',       agingAlto);
        setText('total-chamados',   total);
        setText('count-visivel',    total);

        if (rows.length > 0) {
            const soma = rows.reduce(function (acc, r) {
                return acc + (parseInt(r.dataset.aging, 10) || 0);
            }, 0);
            setText('aging-medio', (soma / rows.length).toFixed(1));
        }
    };

    // ── FILTROS ───────────────────────────────────────────────
    window.aplicarFiltros = function aplicarFiltros(isInicial = false) {
        if (!tbody) return;
        const rows = Array.from(tbody.querySelectorAll('tr.chamado-row'));
        const termo = termoBusca.trim().toLowerCase();
        let visiveis = 0;

        rows.forEach(function (r) {
            const status = r.dataset.status || '';
            const isReincidente = r.classList.contains('row-reincidente');
            const aging  = parseInt(r.dataset.aging, 10) || 0;
            const search = (r.dataset.search || '').toLowerCase();

            let passaStatus = false;

            if (filtroStatus === 'todos') {
                passaStatus = true;
            } else if (filtroStatus === 'reincidente') {
                passaStatus = isReincidente;
            } else if (filtroStatus === 'aberto') {
                passaStatus = (status !== 'resolvido');
            } else {
                passaStatus = (status === filtroStatus);
            }

            const passaBusca  = !termo || search.includes(termo);

            let passaAging = true;
            if      (filtroAgingV === '3')   passaAging = aging <= 3;
            else if (filtroAgingV === '7')   passaAging = aging <= 7;
            else if (filtroAgingV === '15')  passaAging = aging <= 15;
            else if (filtroAgingV === '30')  passaAging = aging <= 30;
            else if (filtroAgingV === '30+') passaAging = aging > 30;

            const visivel = passaStatus && passaBusca && passaAging;
            r.classList.toggle('hidden-row', !visivel);
            if (visivel) visiveis++;
        });

        if (countVisivel) countVisivel.textContent = visiveis;

        if (emptySearch) {
            const show = (visiveis === 0 && rows.length > 0);
            emptySearch.style.display = show ? 'flex' : 'none';
            if (emptyTerm && termo) emptyTerm.textContent = termo;
        }

        filterBtns.forEach(function (btn) {
            const btnStatus = btn.dataset.status || 'todos';
            if (btnStatus === filtroStatus) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        if (!isInicial) {
            salvarFiltrosNoBanco();
        }
    };

    filterBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            filtroStatus = btn.dataset.status || 'todos';
            window.aplicarFiltros();
        });
    });

    if (inputBusca) {
        let timerBusca;
        inputBusca.addEventListener('input', function () {
            termoBusca = this.value;
            clearTimeout(timerBusca);
            timerBusca = setTimeout(function() {
                window.aplicarFiltros();
            }, 300);
        });
    }

    if (btnLimpar) {
        btnLimpar.addEventListener('click', function () {
            if (inputBusca) { inputBusca.value = ''; termoBusca = ''; }
            window.aplicarFiltros();
            if (inputBusca) inputBusca.focus();
        });
    }

    if (filtroAging) {
        filtroAging.addEventListener('change', function () {
            filtroAgingV = this.value;
            window.aplicarFiltros();
        });
    }

    // ── STATUS DROPDOWN PORTAL ────────────────────────────────
    function fecharPortal() {
        if (!portal) return;
        portal.style.display = 'none';
        portalOwner = null;
    }

    function abrirPortal(editBtn) {
        if (!portal) return;

        const cell = editBtn.closest('.status-cell');
        if (!cell) return;

        if (portalOwner === cell) {
            fecharPortal();
            return;
        }

        const dataEl = cell.querySelector('.status-dropdown-data');
        if (!dataEl) return;

        const currentSlug = dataEl.dataset.current || '';
        const opcoes = Array.from(dataEl.querySelectorAll('span[data-slug]'));

        portal.innerHTML = opcoes.map(function (op) {
            const slug  = op.dataset.slug;
            const label = op.dataset.label;
            const active = (slug === currentSlug) ? ' active' : '';
            return (
                '<button class="status-option' + active + '" ' +
                        'data-slug="' + slug + '" ' +
                        'data-label="' + label + '">' +
                    '<span class="status-dot status-dot--' + slug + '"></span>' +
                    label +
                '</button>'
            );
        }).join('');

        const rect = editBtn.getBoundingClientRect();
        portal.style.display = 'block';
        portal.style.top  = (rect.bottom + 6 + window.scrollY) + 'px';
        portal.style.left = rect.left + 'px';
        portal.style.right = 'auto';
        portal.style.bottom = 'auto';

        portalOwner = cell;

        requestAnimationFrame(function () {
            const pr = portal.getBoundingClientRect();
            if (pr.right > window.innerWidth - 8) {
                portal.style.left = 'auto';
                portal.style.right = (window.innerWidth - rect.right) + 'px';
            }
            if (pr.bottom > window.innerHeight - 8) {
                portal.style.top  = 'auto';
                portal.style.bottom = (window.innerHeight - rect.top + 6) + 'px';
            }
        });
    }

    // ── PERSISTIR STATUS NO BANCO ──────────────────────────────
    function persistirStatusChamado(chamadoId, novoSlug) {
        if (!chamadoId || !CONFIG.urlAtualizarStatusTemplate) return;

        const url = CONFIG.urlAtualizarStatusTemplate.replace(/\/0\/status\/$/, '/' + chamadoId + '/status/');
        const csrfEl = document.querySelector('input[name="csrfmiddlewaretoken"]');
        const csrf = csrfEl ? csrfEl.value : '';

        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify({ status: novoSlug }),
            credentials: 'same-origin'
        })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
            if (!data.ok) throw new Error(data.erro || 'Erro ao salvar status');
        })
        .catch(function (err) {
            alert('Não foi possível salvar o novo status: ' + err.message + '\nRecarregue a página.');
        });
    }

    document.addEventListener('click', function (e) {
        const editBtn = e.target.closest('.status-edit-btn');
        if (editBtn) {
            e.stopPropagation();
            abrirPortal(editBtn);
            return;
        }

        const option = e.target.closest('.status-option');
        if (option && portal.contains(option)) {
            e.stopPropagation();

            const cell = portalOwner;
            if (!cell) { fecharPortal(); return; }

            const row      = cell.closest('tr.chamado-row');
            const badge    = cell.querySelector('.status-badge');
            const dataEl   = cell.querySelector('.status-dropdown-data');
            const newSlug  = option.dataset.slug;
            const newLabel = option.dataset.label;
            const chamadoId = row ? row.dataset.id : null;

            if (badge) {
                badge.className = 'status-badge status-badge--' + newSlug;
                badge.textContent = newLabel;
            }

            if (row) {
                Array.from(row.classList)
                    .filter(function (c) { return c.startsWith('status-'); })
                    .forEach(function (c) { row.classList.remove(c); });
                row.classList.add('status-' + newSlug);
                row.dataset.status = newSlug;
            }

            if (dataEl) dataEl.dataset.current = newSlug;

            window.contarCards();
            window.aplicarFiltros();
            fecharPortal();

            persistirStatusChamado(chamadoId, newSlug);

            return;
        }

        if (portal && portal.style.display !== 'none') {
            fecharPortal();
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            fecharPortal();
            if (modalObs) modalObs.style.display = 'none';
        }
    });

    window.addEventListener('scroll', function () { fecharPortal(); }, { passive: true });
    window.addEventListener('resize', function () { fecharPortal(); }, { passive: true });

    // ── MODAL OBS ─────────────────────────────────────────────
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.obs-btn');
        if (btn && modalObs && modalObsTxt) {
            obsTargetBtn = btn;
            modalObsTxt.value = btn.dataset.obs || '';
            modalObs.style.display = 'flex';
            setTimeout(function () { modalObsTxt.focus(); }, 50);
        }
    });

    function fecharModalObs() {
        if (modalObs) modalObs.style.display = 'none';
        obsTargetBtn = null;
    }

    function salvarObs() {
        if (!obsTargetBtn || !modalObsTxt) { fecharModalObs(); return; }
        const novo = modalObsTxt.value.trim();

        obsTargetBtn.dataset.obs = novo;
        if (novo) {
            obsTargetBtn.className = 'obs-btn';
            obsTargetBtn.innerHTML =
                '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> Ver';
        } else {
            obsTargetBtn.className = 'obs-btn obs-btn--empty';
            obsTargetBtn.innerHTML =
                '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Add';
        }

        fecharModalObs();
    }

    if (fecharModal)    fecharModal.addEventListener('click', fecharModalObs);
    if (cancelarModal)  cancelarModal.addEventListener('click', fecharModalObs);
    if (salvarModal)    salvarModal.addEventListener('click', salvarObs);

    if (modalObs) {
        modalObs.addEventListener('click', function (e) {
            if (e.target === modalObs) fecharModalObs();
        });
    }

    if (modalObsTxt) {
        modalObsTxt.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) salvarObs();
        });
    }

    // ── ORDENAÇÃO ─────────────────────────────────────────────
    var sortState = { col: null, dir: 'asc' };

    document.querySelectorAll('.proj-table thead th[data-sort]').forEach(function (th) {
        th.addEventListener('click', function () {
            const col = th.dataset.sort;
            sortState.dir = (sortState.col === col && sortState.dir === 'asc') ? 'desc' : 'asc';
            sortState.col = col;

            document.querySelectorAll('.proj-table thead th').forEach(function (t) {
                t.classList.remove('sorted-asc', 'sorted-desc');
            });
            th.classList.add('sorted-' + sortState.dir);
            ordenarTabela(col, sortState.dir);
        });
    });

    function ordenarTabela(col, dir) {
        if (!tbody) return;
        const rows     = Array.from(tbody.querySelectorAll('tr.chamado-row'));
        const colIndex = getColIndex(col);
        if (colIndex === -1) return;

        rows.sort(function (a, b) {
            const ta = getText(a, colIndex);
            const tb = getText(b, colIndex);
            const na = parseFloat(ta.replace(/[^\d.]/g, ''));
            const nb = parseFloat(tb.replace(/[^\d.]/g, ''));
            let cmp  = (!isNaN(na) && !isNaN(nb)) ? (na - nb) : ta.localeCompare(tb, 'pt-BR');
            return dir === 'asc' ? cmp : -cmp;
        });

        rows.forEach(function (r) { tbody.appendChild(r); });
    }

    function getText(row, idx) {
        const cells = row.querySelectorAll('td');
        return cells[idx] ? (cells[idx].textContent || '').trim().toLowerCase() : '';
    }

    function getColIndex(col) {
        const headers = Array.from(document.querySelectorAll('.proj-table thead th'));
        return headers.findIndex(function (h) { return h.dataset.sort === col; });
    }

    // ── EXCLUIR CHAMADO ───────────────────────────────────────
    document.addEventListener('click', async function (e) {
        const btn = e.target.closest('.row-action-btn--danger');
        if (!btn) return;

        const row = btn.closest('tr.chamado-row');
        if (!row) return;

        const id = row.dataset.id;
        const confirmado = confirm('Excluir este chamado? Essa ação não pode ser desfeita.');
        if (!confirmado) return;

        if (!CONFIG.urlExcluirTemplate) return;

        const url = CONFIG.urlExcluirTemplate.replace('/0/excluir/', '/' + id + '/excluir/');
        const csrfEl = document.querySelector('input[name="csrfmiddlewaretoken"]');
        const csrf = csrfEl ? csrfEl.value : '';

        btn.disabled = true;

        try {
            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrf },
            });
            const data = await resp.json();

            if (!resp.ok || !data.ok) {
                alert(data.erro || 'Erro ao excluir o chamado.');
                btn.disabled = false;
                return;
            }

            row.remove();
            window.contarCards();
            window.aplicarFiltros();

        } catch (err) {
            alert('Falha de conexão. Tente novamente.');
            btn.disabled = false;
        }
    });

    const btnExportar = document.getElementById('btnExportar');
    if (btnExportar) {
        btnExportar.addEventListener('click', function () {
            alert('Exportação em desenvolvimento.');
        });
    }

    // ── INIT ──────────────────────────────────────────────────

    if (inputBusca) inputBusca.value = termoBusca;
    if (filtroAging) filtroAging.value = filtroAgingV;

    window.contarCards();
    window.aplicarFiltros(true);

}());
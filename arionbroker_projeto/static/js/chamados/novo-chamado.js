(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {

        const CONFIG = window.CHAMADOS_CONFIG || {};
        const EXIBE_CONTATO       = !!CONFIG.exibeContato;
        const STATUS_OPCOES       = CONFIG.statusOpcoes || [];
        const URL_CRIAR           = CONFIG.urlCriar;
        const URL_EDITAR_TEMPLATE = CONFIG.urlEditarTemplate;

        const btnAbrir    = document.getElementById('btnNovoChamado');
        const modal       = document.getElementById('modalNovoChamado');
        const modalTitulo = document.getElementById('modalNovoChamadoTitulo');
        const btnFechar   = document.getElementById('fecharModalNovoChamado');
        const btnCancelar = document.getElementById('cancelarModalNovoChamado');
        const btnSalvar   = document.getElementById('salvarModalNovoChamado');
        const divErro     = document.getElementById('novoChamadoErro');
        const tbody       = document.getElementById('tbody-chamados');

        if (!modal || !btnAbrir) return;

        // Guarda o id do chamado em edição. null = modo "criar".
        let chamadoEditandoId = null;

        // ── CSRF ────────────────────────────────────────────────
        function getCsrfToken() {
            const el = document.querySelector('input[name="csrfmiddlewaretoken"]');
            return el ? el.value : '';
        }

        const CAMPOS = ['ncTicket', 'ncUrlTicket', 'ncIdPersonalizado', 'ncDesignacao', 'ncIsp', 'ncContato', 'ncLocal', 'ncObs'];

        function limparCampos() {
            CAMPOS.forEach(function (id) {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
        }

        // ── ABRIR MODAL — CRIAR ───────────────────────────────────
        function abrirModalCriar() {
            chamadoEditandoId = null;
            divErro.style.display = 'none';
            divErro.textContent = '';
            limparCampos();
            if (modalTitulo) modalTitulo.textContent = 'Novo Chamado';
            if (btnSalvar) btnSalvar.textContent = 'Salvar Chamado';
            modal.style.display = 'flex';
            setTimeout(function () {
                const first = document.getElementById('ncTicket');
                if (first) first.focus();
            }, 50);
        }

        // ── ABRIR MODAL — EDITAR ──────────────────────────────────
        function abrirModalEditar(row) {
            chamadoEditandoId = row.dataset.id;
            divErro.style.display = 'none';
            divErro.textContent = '';

            document.getElementById('ncTicket').value          = row.dataset.ticketArion || '';
            document.getElementById('ncUrlTicket').value        = row.dataset.urlTicket || '';
            document.getElementById('ncIdPersonalizado').value  = row.dataset.idPersonalizado || '';
            document.getElementById('ncDesignacao').value       = row.dataset.designacao || '';
            document.getElementById('ncIsp').value              = row.dataset.isp || '';
            if (document.getElementById('ncContato')) {
                document.getElementById('ncContato').value = row.dataset.contato || '';
            }
            document.getElementById('ncLocal').value            = row.dataset.local || '';
            document.getElementById('ncObs').value              = row.dataset.obsFull || '';

            if (modalTitulo) modalTitulo.textContent = 'Editar Chamado';
            if (btnSalvar) btnSalvar.textContent = 'Salvar Alterações';

            modal.style.display = 'flex';
            setTimeout(function () {
                const first = document.getElementById('ncTicket');
                if (first) first.focus();
            }, 50);
        }

        function fecharModal() {
            modal.style.display = 'none';
            chamadoEditandoId = null;
        }

        btnAbrir.addEventListener('click', abrirModalCriar);
        if (btnFechar)    btnFechar.addEventListener('click', fecharModal);
        if (btnCancelar)  btnCancelar.addEventListener('click', fecharModal);

        modal.addEventListener('click', function (e) {
            if (e.target === modal) fecharModal();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.style.display !== 'none') fecharModal();
        });

        // Clique no botão "Editar" de cada linha (ícone de lápis)
        document.addEventListener('click', function (e) {
            const btn = e.target.closest('.row-action-btn');
            if (!btn || btn.classList.contains('row-action-btn--danger')) return;

            const row = btn.closest('tr.chamado-row');
            if (!row) return;

            abrirModalEditar(row);
        });

        // ── HELPERS ────────────────────────────────────────────
        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str || '';
            return div.innerHTML;
        }

        function montarTicketHtml(c) {
            if (c.url_ticket) {
                return '<a class="ticket-chip" href="' + escapeHtml(c.url_ticket) + '" target="_blank" rel="noopener">' + escapeHtml(c.ticket_arion) + '</a>';
            }
            return '<span class="ticket-chip">' + escapeHtml(c.ticket_arion) + '</span>';
        }

        function montarStatusDropdownData(statusAtual) {
            return STATUS_OPCOES.map(function (op) {
                const ativo = op.slug === statusAtual ? ' data-active="1"' : '';
                return '<span data-slug="' + op.slug + '" data-label="' + op.label + '"' + ativo + '></span>';
            }).join('');
        }

        function montarLinha(c) {
            const tr = document.createElement('tr');
            tr.className = 'chamado-row status-' + c.status_slug;
            tr.dataset.status = c.status_slug;
            tr.dataset.id = c.id;
            tr.dataset.search = [
                c.designacao, c.isp, c.local, c.ticket_arion, c.id_personalizado
            ].join(' ').toLowerCase();

            // dados usados pra reabrir o modal de edição sem reload
            tr.dataset.idPersonalizado = c.id_personalizado || '';
            tr.dataset.ticketArion     = c.ticket_arion || '';
            tr.dataset.urlTicket       = c.url_ticket || '';
            tr.dataset.designacao      = c.designacao || '';
            tr.dataset.isp             = c.isp || '';
            tr.dataset.contato         = c.contato || '';
            tr.dataset.local           = c.local || '';
            tr.dataset.obsFull         = c.obs || '';

            const dataFormatada = new Date(c.data).toLocaleDateString('pt-BR');

            tr.innerHTML =
                '<td class="col-brad font-mono">' + (c.id_personalizado ? '<strong>' + escapeHtml(c.id_personalizado) + '</strong>' : '<span class="text-muted">—</span>') + '</td>' +
                '<td class="col-ticket">' + montarTicketHtml(c) + '</td>' +
                '<td class="col-designacao font-mono">' + escapeHtml(c.designacao) + '</td>' +
                '<td>' + (c.isp ? escapeHtml(c.isp) : '—') + '</td>' +
                (EXIBE_CONTATO ? '<td class="col-contato text-mono-sm">' + (c.contato ? escapeHtml(c.contato) : '—') + '</td>' : '') +
                '<td>' + (c.local ? escapeHtml(c.local) : '—') + '</td>' +
                '<td class="col-status">' +
                    '<div class="status-cell" data-current="' + c.status_slug + '">' +
                        '<span class="status-badge status-badge--' + c.status_slug + '">' + escapeHtml(c.status_display) + '</span>' +
                        '<button class="status-edit-btn" title="Alterar status" tabindex="-1">' +
                            '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
                                '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />' +
                                '<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4z" />' +
                            '</svg>' +
                        '</button>' +
                        '<div class="status-dropdown-data" style="display:none;" data-current="' + c.status_slug + '">' +
                            montarStatusDropdownData(c.status_slug) +
                        '</div>' +
                    '</div>' +
                '</td>' +
                '<td class="col-obs">' +
                    '<div class="obs-cell">' +
                        (c.obs
                            ? '<button class="obs-btn" data-obs="' + escapeHtml(c.obs) + '" title="Ver / editar observação">Ver</button>'
                            : '<button class="obs-btn obs-btn--empty" data-obs="" title="Adicionar observação">Add</button>') +
                    '</div>' +
                '</td>' +
                '<td class="col-data">' + dataFormatada + '</td>' +
                '<td>' + (c.analista ? escapeHtml(c.analista) : '—') + '</td>' +
                '<td class="col-acoes">' +
                    '<div class="row-actions">' +
                        '<button class="row-action-btn" title="Editar">' +
                            '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                                '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />' +
                                '<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />' +
                            '</svg>' +
                        '</button>' +
                        (CONFIG.isAdmin ?
                        '<button class="row-action-btn row-action-btn--danger" title="Excluir">' +
                            '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                                '<polyline points="3 6 5 6 21 6" />' +
                                '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />' +
                                '<path d="M10 11v6M14 11v6" />' +
                                '<path d="M9 6V4h6v2" />' +
                            '</svg>' +
                        '</button>' : '') +
                    '</div>' +
                '</td>';
            return tr;
        }

        function removerEmptyState() {
            const empty = tbody.querySelector('.empty-state');
            if (empty) empty.closest('tr').remove();
        }

        function coletarPayload() {
            return {
                ticket_arion:      document.getElementById('ncTicket').value.trim(),
                url_ticket:        document.getElementById('ncUrlTicket').value.trim(),
                id_personalizado:  document.getElementById('ncIdPersonalizado').value.trim(),
                designacao:        document.getElementById('ncDesignacao').value.trim(),
                isp:               document.getElementById('ncIsp').value.trim(),
                contato:           EXIBE_CONTATO ? document.getElementById('ncContato').value.trim() : '',
                local:             document.getElementById('ncLocal').value.trim(),
                obs:               document.getElementById('ncObs').value.trim(),
            };
        }

        // ── SALVAR (POST criar OU editar) ───────────────────────
        async function salvarChamado() {
            const payload = coletarPayload();

            if (!payload.ticket_arion || !payload.designacao) {
                divErro.textContent = 'Ticket Arion e Designação são obrigatórios.';
                divErro.style.display = 'block';
                return;
            }

            const editando = !!chamadoEditandoId;
            const url = editando
                ? URL_EDITAR_TEMPLATE.replace(/\/0\/editar\/$/, '/' + chamadoEditandoId + '/editar/')
                : URL_CRIAR;

            btnSalvar.disabled = true;
            btnSalvar.textContent = editando ? 'Salvando alterações…' : 'Salvando…';

            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    },
                    body: JSON.stringify(payload),
                });

                const data = await resp.json();

                if (!resp.ok || !data.ok) {
                    divErro.textContent = data.erro || 'Erro ao salvar o chamado.';
                    divErro.style.display = 'block';
                    return;
                }

                if (editando) {
                    const linhaAntiga = tbody.querySelector('tr[data-id="' + chamadoEditandoId + '"]');
                    const novaLinha = montarLinha(data.chamado);
                    if (linhaAntiga) {
                        linhaAntiga.replaceWith(novaLinha);
                    } else {
                        tbody.prepend(novaLinha);
                    }
                } else {
                    removerEmptyState();
                    const novaLinha = montarLinha(data.chamado);
                    tbody.prepend(novaLinha);
                }

                if (typeof window.contarCards === 'function') window.contarCards();
                if (typeof window.aplicarFiltros === 'function') window.aplicarFiltros();

                fecharModal();

            } catch (err) {
                divErro.textContent = 'Falha de conexão. Tente novamente.';
                divErro.style.display = 'block';
            } finally {
                btnSalvar.disabled = false;
                btnSalvar.textContent = editando ? 'Salvar Alterações' : 'Salvar Chamado';
            }
        }

        if (btnSalvar) btnSalvar.addEventListener('click', salvarChamado);
    });

}());
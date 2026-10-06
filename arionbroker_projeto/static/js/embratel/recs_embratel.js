/**
 * recs_embratel.js
 *
 * Controlador de interface para a listagem de tarefas Embratel / Modos Web.
 * Implementa busca client-side instantânea, modal acessível, navegação de linhas
 * (mouse e teclado) e gerenciamento de seleção em lote de forma independente.
 */

const EmbratelTasksPage = {
    elements: {},
    state: {
        searchTimeout: null,
        selectedIds: new Set(),
        lastFocusedBeforeModal: null
    },

    init() {
        this.cacheElements();
        if (!this.elements.tableBody) return; // Aborta se a tela não tiver tabela (empty state server-side)

        this.bindEvents();
        this.setupRowNavigation();
        this.setupCopyButtons();
        this.restoreFilters();
    },

    cacheElements() {
        this.elements = {
            searchInput: document.getElementById('embratel-search-input'),
            emptySearchState: document.getElementById('embratel-empty-search'),
            tableWrapper: document.querySelector('.table-wrapper'),
            tableBody: document.getElementById('embratel-table-body'),
            rows: document.querySelectorAll('.embratel-task-row'),

            checkAll: document.getElementById('embratel-check-all'),
            rowChecks: document.querySelectorAll('.embratel-row-check'),

            bulkBar: document.getElementById('embratel-bulk-bar'),
            bulkCount: document.getElementById('embratel-bulk-count'),
            btnClearSelection: document.getElementById('btn-clear-selection'),

            modal: document.getElementById('embratel-action-modal'),
            modalTitle: document.getElementById('embratel-modal-title'),
            modalBody: document.getElementById('embratel-modal-body'),
            modalForm: document.getElementById('embratel-modal-form'),
            modalCloseBtns: document.querySelectorAll('[data-modal-close]'),
            modalTriggers: document.querySelectorAll('[data-modal-target]'),

            forms: document.querySelectorAll('form')
        };
    },

    bindEvents() {
        // Busca com Debounce
        if (this.elements.searchInput) {
            this.elements.searchInput.addEventListener('input', (e) => {
                clearTimeout(this.state.searchTimeout);
                this.state.searchTimeout = setTimeout(() => {
                    this.applyFilters(e.target.value);
                }, 300);
            });
        }

        // Checkbox "Selecionar Todos"
        if (this.elements.checkAll) {
            this.elements.checkAll.addEventListener('change', (e) => {
                const isChecked = e.target.checked;
                // Considera apenas linhas que não estão ocultadas pela busca local
                this.elements.rowChecks.forEach(check => {
                    const row = check.closest('tr');
                    if (!row.classList.contains('d-none')) {
                        check.checked = isChecked;
                    }
                });
                this.updateSelectionState();
            });
        }

        // Checkboxes Individuais
        if (this.elements.rowChecks) {
            this.elements.rowChecks.forEach(check => {
                check.addEventListener('change', () => this.updateSelectionState());
            });
        }

        // Limpar Seleção (Bulk Bar)
        if (this.elements.btnClearSelection) {
            this.elements.btnClearSelection.addEventListener('click', () => {
                this.elements.rowChecks.forEach(c => c.checked = false);
                this.updateSelectionState();
            });
        }

        // Modais
        if (this.elements.modalTriggers) {
            this.elements.modalTriggers.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation(); // Impede o clique da linha
                    this.openModal(btn);
                });
            });
        }

        if (this.elements.modalCloseBtns) {
            this.elements.modalCloseBtns.forEach(btn => {
                btn.addEventListener('click', () => this.closeModal());
            });
        }

        // Fechar Modal ao apertar Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.elements.modal?.classList.contains('is-open')) {
                this.closeModal();
            }
        });

        // Feedback de Loading nos Formulários
        if (this.elements.forms) {
            this.elements.forms.forEach(form => {
                form.addEventListener('submit', (e) => {
                    const submitBtn = form.querySelector('button[type="submit"]');
                    if (submitBtn) {
                        if (submitBtn.classList.contains('is-loading')) {
                            e.preventDefault(); // Impede duplo clique
                            return;
                        }
                        submitBtn.classList.add('is-loading');
                        const originalText = submitBtn.innerHTML;
                        submitBtn.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Processando...';

                        // Fallback para restaurar caso a navegação falhe silenciosamente (ex: download/file)
                        setTimeout(() => {
                            submitBtn.classList.remove('is-loading');
                            submitBtn.innerHTML = originalText;
                        }, 8000);
                    }
                });
            });
        }
    },

    setupRowNavigation() {
        this.elements.rows.forEach(row => {
            row.addEventListener('click', (e) => this.handleRowActivation(e, row));

            // Suporte a teclado: linha é focável (tabindex="0") e ativa com Enter/Espaço
            row.addEventListener('keydown', (e) => {
                if (e.key !== 'Enter' && e.key !== ' ') return;
                if (e.target !== row) return; // Deixa inputs/links internos tratarem sua própria tecla
                e.preventDefault();
                this.handleRowActivation(e, row);
            });
        });
    },

    handleRowActivation(e, row) {
        // Impede navegação se o usuário interagiu com botão, input ou link dentro da linha
        const interactiveTags = ['BUTTON', 'A', 'INPUT', 'LABEL'];
        if (interactiveTags.includes(e.target.tagName) || e.target.closest('button') || e.target.closest('a')) {
            return;
        }
        const url = row.getAttribute('data-detail-url');
        if (url) {
            window.location.href = url;
        }
    },

    setupCopyButtons() {
        const triggers = document.querySelectorAll('.embratel-copy-trigger');
        triggers.forEach(el => {
            const doCopy = (e) => {
                e.stopPropagation();
                const text = el.textContent.trim();
                navigator.clipboard.writeText(text).then(() => {
                    const originalTitle = el.getAttribute('title');
                    el.setAttribute('title', 'Copiado!');
                    el.classList.add('is-copied');
                    setTimeout(() => {
                        el.setAttribute('title', originalTitle);
                        el.classList.remove('is-copied');
                    }, 2000);
                });
            };

            el.addEventListener('click', doCopy);
            el.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    doCopy(e);
                }
            });
        });
    },

    applyFilters(searchTerm) {
        const term = searchTerm.toLowerCase().trim();
        let visibleCount = 0;

        this.elements.rows.forEach(row => {
            const dataSearch = row.getAttribute('data-search') || '';
            const matchesSearch = term === '' || dataSearch.includes(term);

            if (matchesSearch) {
                row.classList.remove('d-none');
                visibleCount++;
            } else {
                row.classList.add('d-none');
                // Desmarca se foi ocultado
                const check = row.querySelector('.embratel-row-check');
                if (check && check.checked) check.checked = false;
            }
        });

        // Persistência leve na URL sem refresh
        if ('URLSearchParams' in window) {
            const url = new URL(window.location);
            if (term) {
                url.searchParams.set('q_local', term);
            } else {
                url.searchParams.delete('q_local');
            }
            window.history.replaceState({}, '', url);
        }

        this.updateVisibleCount(visibleCount);
        this.updateSelectionState(); // Reavalia checkboxes
    },

    updateVisibleCount(count) {
        if (count === 0) {
            this.elements.tableWrapper.classList.add('d-none');
            this.elements.emptySearchState.classList.remove('d-none');
        } else {
            this.elements.tableWrapper.classList.remove('d-none');
            this.elements.emptySearchState.classList.add('d-none');
        }
    },

    updateSelectionState() {
        let totalChecked = 0;
        let totalVisible = 0;

        this.elements.rowChecks.forEach(check => {
            const isVisible = !check.closest('tr').classList.contains('d-none');
            if (isVisible) {
                totalVisible++;
                if (check.checked) totalChecked++;
            }
        });

        // Atualiza checkbox geral (Indeterminate ou Checked)
        if (this.elements.checkAll) {
            this.elements.checkAll.checked = (totalChecked > 0 && totalChecked === totalVisible);
            this.elements.checkAll.indeterminate = (totalChecked > 0 && totalChecked < totalVisible);
        }

        // Atualiza e exibe barra de ações em lote
        if (totalChecked > 0) {
            this.elements.bulkCount.textContent = totalChecked;
            this.elements.bulkBar.classList.add('is-visible');
            this.elements.bulkBar.setAttribute('aria-hidden', 'false');
        } else {
            this.elements.bulkBar.classList.remove('is-visible');
            this.elements.bulkBar.setAttribute('aria-hidden', 'true');
        }
    },

    openModal(triggerElement) {
        const title = triggerElement.getAttribute('data-modal-title') || 'Confirmar Ação';
        const bodyHTML = triggerElement.getAttribute('data-modal-body') || 'Tem certeza que deseja prosseguir?';
        const actionUrl = triggerElement.getAttribute('data-modal-action');

        this.state.lastFocusedBeforeModal = triggerElement;

        this.elements.modalTitle.textContent = title;
        // Injeção segura baseada em dados de atributos estáticos formatados pelo Django
        this.elements.modalBody.innerHTML = bodyHTML;

        if (actionUrl) {
            this.elements.modalForm.setAttribute('action', actionUrl);
        }

        this.elements.modal.classList.add('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'false');

        // Foco para acessibilidade
        const firstFocusable = this.elements.modal.querySelector('button, input');
        if (firstFocusable) firstFocusable.focus();
    },

    closeModal() {
        if (!this.elements.modal) return;
        this.elements.modal.classList.remove('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'true');

        // Devolve o foco para quem abriu o modal
        if (this.state.lastFocusedBeforeModal) {
            this.state.lastFocusedBeforeModal.focus();
        }

        // Reseta conteúdo temporário
        setTimeout(() => {
            this.elements.modalForm.setAttribute('action', '');
            this.elements.modalBody.innerHTML = '';
        }, 200);
    },

    restoreFilters() {
        if ('URLSearchParams' in window) {
            const urlParams = new URLSearchParams(window.location.search);
            const localQ = urlParams.get('q_local');
            if (localQ && this.elements.searchInput) {
                this.elements.searchInput.value = localQ;
                this.applyFilters(localQ);
            }
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    EmbratelTasksPage.init();
});
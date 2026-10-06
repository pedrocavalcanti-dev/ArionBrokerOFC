/**
 * recs_enviadas.js
 *
 * Controlador de interface para a listagem de RECs Enviadas.
 * Implementa busca e filtros client-side, navegação de linhas,
 * sistema de cópia com Toast e modal acessível.
 */

const EmbratelSentPage = {
    elements: {},
    state: {
        searchTimeout: null,
        currentFilter: 'todos',
        currentSearch: '',
        toastTimeout: null,
        lastFocusedBeforeModal: null
    },

    init() {
        this.cacheElements();
        if (!this.elements.tableBody) return; // Aborta se a tela não tiver tabela

        this.bindEvents();
        this.setupRowNavigation();
        this.setupCopyButtons();
        this.restoreState();
    },

    cacheElements() {
        this.elements = {
            searchInput: document.getElementById('embratel-sent-search-input'),
            filterBtns: document.querySelectorAll('.embratel-sent-filter-btn'),
            emptySearchState: document.getElementById('embratel-sent-empty-search'),
            tableWrapper: document.getElementById('embratel-sent-table-wrapper'),
            tableBody: document.getElementById('embratel-sent-table-body'),
            rows: document.querySelectorAll('.embratel-sent-row'),

            modal: document.getElementById('embratel-sent-action-modal'),
            modalTitle: document.getElementById('embratel-sent-modal-title'),
            modalBody: document.getElementById('embratel-sent-modal-body'),
            modalForm: document.getElementById('embratel-sent-modal-form'),
            modalCloseBtns: document.querySelectorAll('[data-modal-close]'),
            modalTriggers: document.querySelectorAll('[data-modal-target]'),

            toast: document.getElementById('embratel-sent-toast'),
            forms: document.querySelectorAll('form')
        };
    },

    bindEvents() {
        // Busca com Debounce
        if (this.elements.searchInput) {
            this.elements.searchInput.addEventListener('input', (e) => {
                clearTimeout(this.state.searchTimeout);
                this.state.searchTimeout = setTimeout(() => {
                    this.state.currentSearch = e.target.value.toLowerCase().trim();
                    this.applyFilters();
                }, 300);
            });
        }

        // Filtros Rápidos (Botões)
        if (this.elements.filterBtns) {
            this.elements.filterBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    // Atualiza UI dos botões
                    this.elements.filterBtns.forEach(b => {
                        b.classList.remove('btn--primary');
                        b.classList.add('btn--outline');
                    });
                    e.target.classList.remove('btn--outline');
                    e.target.classList.add('btn--primary');

                    // Aplica filtro
                    this.state.currentFilter = e.target.getAttribute('data-filter');
                    this.applyFilters();
                });
            });
        }

        // Modais
        if (this.elements.modalTriggers) {
            this.elements.modalTriggers.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.openModal(btn);
                });
            });
        }

        if (this.elements.modalCloseBtns) {
            this.elements.modalCloseBtns.forEach(btn => {
                btn.addEventListener('click', () => this.closeModal());
            });
        }

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
                            e.preventDefault();
                            return;
                        }
                        submitBtn.classList.add('is-loading');
                        const originalText = submitBtn.innerHTML;
                        submitBtn.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Processando...';
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
            row.setAttribute('tabindex', '0');

            row.addEventListener('keydown', (e) => {
                if (e.key !== 'Enter' && e.key !== ' ') return;
                if (e.target !== row) return;
                e.preventDefault();
                this.handleRowActivation(e, row);
            });
        });
    },

    handleRowActivation(e, row) {
        const interactiveTags = ['BUTTON', 'A', 'INPUT', 'LABEL', 'SPAN']; // span adicionado por causa da cópia
        if (interactiveTags.includes(e.target.tagName) || e.target.closest('button') || e.target.closest('a')) {
            if (!e.target.closest('.embratel-sent-row')) return; 
        }
        
        // Evita navegação se o clique foi num trigger de cópia
        if (e.target.classList.contains('embratel-sent-copy-trigger')) return;

        const url = row.getAttribute('data-detail-url');
        if (url) window.location.href = url;
    },

    setupCopyButtons() {
        const triggers = document.querySelectorAll('.embratel-sent-copy-trigger');
        triggers.forEach(el => {
            el.setAttribute('tabindex', '0');
            el.setAttribute('role', 'button');

            const doCopy = (e) => {
                e.stopPropagation();
                const text = el.getAttribute('data-copy') || el.textContent.trim();
                navigator.clipboard.writeText(text).then(() => {
                    this.showToast(`Copiado: ${text}`);
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

    showToast(message) {
        if (!this.elements.toast) return;
        this.elements.toast.textContent = message;
        this.elements.toast.classList.add('is-visible');
        this.elements.toast.setAttribute('aria-hidden', 'false');

        clearTimeout(this.state.toastTimeout);
        this.state.toastTimeout = setTimeout(() => {
            this.elements.toast.classList.remove('is-visible');
            this.elements.toast.setAttribute('aria-hidden', 'true');
        }, 3000);
    },

    applyFilters() {
        let visibleCount = 0;

        this.elements.rows.forEach(row => {
            const dataSearch = row.getAttribute('data-search') || '';
            const dataStatus = row.getAttribute('data-status') || '';
            const dataOrigem = row.getAttribute('data-origem') || '';

            // Verifica texto
            const matchesSearch = this.state.currentSearch === '' || dataSearch.includes(this.state.currentSearch);
            
            // Verifica botão de filtro
            let matchesFilter = true;
            if (this.state.currentFilter !== 'todos') {
                if (['sucesso', 'erro'].includes(this.state.currentFilter)) {
                    matchesFilter = dataStatus === this.state.currentFilter;
                } else if (['automatico', 'manual'].includes(this.state.currentFilter)) {
                    matchesFilter = dataOrigem === this.state.currentFilter;
                }
            }

            if (matchesSearch && matchesFilter) {
                row.classList.remove('d-none');
                visibleCount++;
            } else {
                row.classList.add('d-none');
            }
        });

        // Persistência leve na URL sem refresh
        if ('URLSearchParams' in window) {
            const url = new URL(window.location);
            if (this.state.currentSearch) url.searchParams.set('q', this.state.currentSearch);
            else url.searchParams.delete('q');
            
            if (this.state.currentFilter !== 'todos') url.searchParams.set('f', this.state.currentFilter);
            else url.searchParams.delete('f');
            
            window.history.replaceState({}, '', url);
        }

        this.updateVisibleCount(visibleCount);
    },

    updateVisibleCount(count) {
        if (!this.elements.tableWrapper || !this.elements.emptySearchState) return;

        if (count === 0) {
            this.elements.tableWrapper.classList.add('d-none');
            this.elements.emptySearchState.classList.remove('d-none');
        } else {
            this.elements.tableWrapper.classList.remove('d-none');
            this.elements.emptySearchState.classList.add('d-none');
        }
    },

    openModal(triggerElement) {
        const title = triggerElement.getAttribute('data-modal-title') || 'Confirmar Ação';
        const bodyHTML = triggerElement.getAttribute('data-modal-body') || 'Tem certeza que deseja prosseguir?';
        const actionUrl = triggerElement.getAttribute('data-modal-action');

        this.state.lastFocusedBeforeModal = triggerElement;

        this.elements.modalTitle.textContent = title;
        this.elements.modalBody.innerHTML = bodyHTML;

        if (actionUrl) {
            this.elements.modalForm.setAttribute('action', actionUrl);
        }

        this.elements.modal.classList.add('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'false');

        const firstFocusable = this.elements.modal.querySelector('button, input');
        if (firstFocusable) firstFocusable.focus();
    },

    closeModal() {
        if (!this.elements.modal) return;
        this.elements.modal.classList.remove('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'true');

        if (this.state.lastFocusedBeforeModal) {
            this.state.lastFocusedBeforeModal.focus();
        }

        setTimeout(() => {
            this.elements.modalForm.setAttribute('action', '');
            this.elements.modalBody.innerHTML = '';
        }, 200);
    },

    restoreState() {
        if ('URLSearchParams' in window) {
            const urlParams = new URLSearchParams(window.location.search);
            const q = urlParams.get('q');
            const f = urlParams.get('f');

            if (q && this.elements.searchInput) {
                this.elements.searchInput.value = q;
                this.state.currentSearch = q.toLowerCase().trim();
            }

            if (f && this.elements.filterBtns) {
                const btn = Array.from(this.elements.filterBtns).find(b => b.getAttribute('data-filter') === f);
                if (btn) btn.click(); // Trigger simulado aplica o filtro e ajusta a UI
            } else if (q) {
                this.applyFilters();
            }
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    EmbratelSentPage.init();
});
/**
 * execucoes.js
 * 
 * Controlador client-side para a tela de monitoramento de execuções do robô Embratel.
 * Implementa buscas, filtros locais, expansão de linhas (accordion) e modal 
 * interceptador para ações de formulários (executar agora).
 */

const EmbratelExecutionsPage = {
    elements: {},
    state: {
        activeFilter: 'todos',
        searchTerm: '',
        searchTimeout: null,
        pendingActionForm: null
    },

    init() {
        this.cacheElements();
        if (!this.elements.tableBody) return; // Aborta se a tela estiver vazia (server-side)

        this.bindEvents();
        this.setupFilters();
        this.setupExpandableRows();
        this.setupCopyButtons();
        this.setupActionModal();
        this.restoreFilters();
    },

    cacheElements() {
        this.elements = {
            searchInput: document.getElementById('embratel-exec-search-input'),
            filterBtns: document.querySelectorAll('.embratel-exec-filter-btn'),
            
            tableWrapper: document.getElementById('embratel-exec-table-wrapper'),
            tableBody: document.getElementById('embratel-exec-table-body'),
            rows: document.querySelectorAll('.embratel-exec-row'),
            emptySearchState: document.getElementById('embratel-exec-empty-search'),
            
            copyBtns: document.querySelectorAll('.embratel-exec-copy-btn'),
            toast: document.getElementById('embratel-exec-toast'),
            
            modal: document.getElementById('embratel-exec-modal'),
            modalTitle: document.getElementById('embratel-exec-modal-title'),
            modalBody: document.getElementById('embratel-exec-modal-body'),
            modalCloseBtns: document.querySelectorAll('[data-modal-close]'),
            modalConfirmBtn: document.getElementById('btn-modal-confirm'),
            actionForms: document.querySelectorAll('.embratel-exec-inline-form')
        };
    },

    bindEvents() {
        // Busca com Debounce
        if (this.elements.searchInput) {
            this.elements.searchInput.addEventListener('input', (e) => {
                this.state.searchTerm = e.target.value.toLowerCase().trim();
                this.debounce(() => this.applyFilters(), 300);
            });
        }
    },

    setupFilters() {
        if (this.elements.filterBtns) {
            this.elements.filterBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    // Update UI da Toolbar
                    this.elements.filterBtns.forEach(b => {
                        b.classList.remove('btn--primary');
                        b.classList.add('btn--outline');
                    });
                    btn.classList.remove('btn--outline');
                    btn.classList.add('btn--primary');

                    // Setar Estado e Aplicar
                    this.state.activeFilter = btn.getAttribute('data-filter');
                    this.applyFilters();
                });
            });
        }
    },

    applyFilters() {
        let visibleCount = 0;

        this.elements.rows.forEach(row => {
            const dataStatus = row.getAttribute('data-status') || '';
            const dataSearch = row.getAttribute('data-search') || '';
            const detailsRow = document.getElementById(row.getAttribute('aria-controls'));

            // 1. Filtro de Status
            let matchesStatus = true;
            if (this.state.activeFilter !== 'todos') {
                matchesStatus = dataStatus === this.state.activeFilter;
            }

            // 2. Filtro de Busca Textual
            let matchesSearch = true;
            if (this.state.searchTerm !== '') {
                matchesSearch = dataSearch.includes(this.state.searchTerm);
            }

            if (matchesStatus && matchesSearch) {
                row.classList.remove('d-none');
                visibleCount++;
            } else {
                row.classList.add('d-none');
                row.setAttribute('aria-expanded', 'false');
                if (detailsRow) {
                    detailsRow.classList.add('d-none');
                    detailsRow.setAttribute('aria-hidden', 'true');
                }
            }
        });

        // Atualizar Visibilidade e Estado Vazio
        this.updateVisibleCount(visibleCount);

        // Atualizar URL (persistência sem refresh)
        if ('URLSearchParams' in window) {
            const url = new URL(window.location);
            if (this.state.activeFilter !== 'todos') url.searchParams.set('f_status', this.state.activeFilter);
            else url.searchParams.delete('f_status');
            
            if (this.state.searchTerm) url.searchParams.set('q_local', this.state.searchTerm);
            else url.searchParams.delete('q_local');
            
            window.history.replaceState({}, '', url);
        }
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

    setupExpandableRows() {
        this.elements.rows.forEach(row => {
            row.addEventListener('click', (e) => {
                // Impede que clique no copy ou links abra/feche a linha
                if (e.target.closest('button') || e.target.closest('a')) return;

                const isExpanded = row.getAttribute('aria-expanded') === 'true';
                const targetId = row.getAttribute('aria-controls');
                const targetRow = document.getElementById(targetId);

                // Comportamento Accordion: Fecha as outras (Opcional, mas limpo)
                this.elements.rows.forEach(otherRow => {
                    if (otherRow !== row && otherRow.getAttribute('aria-expanded') === 'true') {
                        this.closeDetails(otherRow);
                    }
                });

                if (isExpanded) {
                    this.closeDetails(row, targetRow);
                } else {
                    this.openDetails(row, targetRow);
                }
            });
        });
    },

    openDetails(row, targetRow) {
        row.setAttribute('aria-expanded', 'true');
        if (targetRow) {
            targetRow.classList.remove('d-none');
            targetRow.setAttribute('aria-hidden', 'false');
        }
    },

    closeDetails(row, targetRow = null) {
        row.setAttribute('aria-expanded', 'false');
        const target = targetRow || document.getElementById(row.getAttribute('aria-controls'));
        if (target) {
            target.classList.add('d-none');
            target.setAttribute('aria-hidden', 'true');
        }
    },

    setupCopyButtons() {
        if (this.elements.copyBtns) {
            this.elements.copyBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const targetId = btn.getAttribute('data-copy-target');
                    const targetElement = document.getElementById(targetId);
                    
                    if (targetElement) {
                        // Captura apenas o texto renderizado, sem tags HTML
                        const text = targetElement.innerText || targetElement.textContent;
                        navigator.clipboard.writeText(text.trim()).then(() => {
                            this.showToast('Log copiado para a área de transferência!');
                        }).catch(() => {
                            this.showToast('Erro ao copiar.');
                        });
                    }
                });
            });
        }
    },

    setupActionModal() {
        // Intercepta formulários que exigem confirmação (ex: Executar Agora)
        this.elements.actionForms.forEach(form => {
            form.addEventListener('submit', (e) => {
                const triggerBtn = form.querySelector('[data-modal-target]');
                if (triggerBtn && !this.state.pendingActionForm) {
                    e.preventDefault(); // Impede submissão real para abrir o modal primeiro
                    
                    const title = triggerBtn.getAttribute('data-modal-title') || 'Confirmar';
                    const body = triggerBtn.getAttribute('data-modal-body') || 'Prosseguir?';
                    
                    this.state.pendingActionForm = form;
                    this.openModal(title, body);
                } else if (this.state.pendingActionForm === form) {
                    // Passou do modal, aplica loading visual
                    this.setLoading(form.querySelector('button[type="submit"]'));
                }
            });
        });

        // Fechar Modal (botões e atalhos)
        this.elements.modalCloseBtns.forEach(btn => btn.addEventListener('click', () => this.closeModal()));
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.elements.modal?.classList.contains('is-open')) {
                this.closeModal();
            }
        });

        const overlay = document.querySelector('.embratel-exec-modal__overlay');
        if (overlay) overlay.addEventListener('click', () => this.closeModal());

        // Botão Confirmar do Modal
        if (this.elements.modalConfirmBtn) {
            this.elements.modalConfirmBtn.addEventListener('click', () => this.submitPendingForm());
        }
    },

    openModal(title, bodyText) {
        if (!this.elements.modal) return;
        this.elements.modalTitle.textContent = title;
        this.elements.modalBody.textContent = bodyText;
        
        this.elements.modal.classList.add('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'false');
    },

    closeModal() {
        if (!this.elements.modal) return;
        this.elements.modal.classList.remove('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'true');
        this.state.pendingActionForm = null;
    },

    submitPendingForm() {
        if (this.state.pendingActionForm) {
            // Se o botão confirmar for clicado, despacha o form via JS
            this.state.pendingActionForm.submit();
            this.setLoading(this.elements.modalConfirmBtn);
        }
    },

    setLoading(btnElement) {
        if (!btnElement) return;
        if (btnElement.classList.contains('is-loading')) return;
        
        btnElement.classList.add('is-loading');
        const ogText = btnElement.innerHTML;
        btnElement.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Aguarde...';
        
        setTimeout(() => {
            btnElement.classList.remove('is-loading');
            btnElement.innerHTML = ogText;
        }, 8000);
    },

    showToast(message) {
        const toast = this.elements.toast;
        if (!toast) return;

        toast.textContent = message;
        toast.classList.add('is-visible');

        setTimeout(() => {
            toast.classList.remove('is-visible');
        }, 3000);
    },

    debounce(func, wait) {
        clearTimeout(this.state.searchTimeout);
        this.state.searchTimeout = setTimeout(func, wait);
    },

    restoreFilters() {
        if ('URLSearchParams' in window) {
            const params = new URLSearchParams(window.location.search);
            const statusF = params.get('f_status');
            const searchQ = params.get('q_local');

            let needsFilter = false;

            if (statusF) {
                const targetBtn = document.querySelector(`.embratel-exec-filter-btn[data-filter="${statusF}"]`);
                if (targetBtn) {
                    this.state.activeFilter = statusF;
                    
                    // UI Toolbar
                    this.elements.filterBtns.forEach(b => {
                        b.classList.remove('btn--primary');
                        b.classList.add('btn--outline');
                    });
                    targetBtn.classList.remove('btn--outline');
                    targetBtn.classList.add('btn--primary');
                    needsFilter = true;
                }
            }

            if (searchQ && this.elements.searchInput) {
                this.elements.searchInput.value = searchQ;
                this.state.searchTerm = searchQ.toLowerCase().trim();
                needsFilter = true;
            }

            if (needsFilter) {
                this.applyFilters();
            }
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    EmbratelExecutionsPage.init();
});
/**
 * configuracao.js
 * 
 * Controlador client-side para a tela de configurações do módulo Embratel.
 * Implementa navegação por abas, modal de confirmação, estado "dirty" de formulário
 * (previne saída sem salvar) e loading states. Não contém regras de negócio de back-end.
 */

const EmbratelConfig = {
    elements: {},
    state: {
        isDirty: false,
        formSubmitting: false,
        pendingAction: null
    },

    init() {
        this.cacheElements();
        this.bindEvents();
        this.setupTabs();
        this.setupDirtyState();
        this.setupModal();
        this.setupForms();
        this.setupValidation();
    },

    cacheElements() {
        this.elements = {
            form: document.getElementById('embratel-config-form'),
            inputs: document.querySelectorAll('[data-track-dirty="true"]'),
            btnSave: document.getElementById('btn-save-config'),
            btnCancel: document.getElementById('btn-cancel-config'),
            
            tabBtns: document.querySelectorAll('.embratel-config-tab-btn'),
            tabPanels: document.querySelectorAll('.embratel-config-tab-content'),
            
            modal: document.getElementById('embratel-config-modal'),
            modalTitle: document.getElementById('embratel-config-modal-title'),
            modalBody: document.getElementById('embratel-config-modal-body'),
            modalCloseBtns: document.querySelectorAll('[data-modal-close]'),
            modalConfirmBtn: document.getElementById('btn-modal-confirm'),
            modalTriggers: document.querySelectorAll('[data-modal-target]'),

            toast: document.getElementById('embratel-config-toast')
        };
    },

    bindEvents() {
        // Bloqueio de saída sem salvar
        window.addEventListener('beforeunload', (e) => {
            if (this.state.isDirty && !this.state.formSubmitting) {
                e.preventDefault();
                e.returnValue = ''; // Exigência para navegadores modernos exibirem o prompt
            }
        });

        // Cancelar reseta aviso de alteração
        if (this.elements.btnCancel) {
            this.elements.btnCancel.addEventListener('click', () => {
                this.state.isDirty = false;
            });
        }
    },

    setupTabs() {
        this.elements.tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                // Remove estados ativos de todos
                this.elements.tabBtns.forEach(b => {
                    b.classList.remove('is-active');
                    b.setAttribute('aria-selected', 'false');
                });
                this.elements.tabPanels.forEach(panel => {
                    panel.setAttribute('hidden', '');
                    panel.classList.remove('is-active');
                });

                // Ativa a aba atual
                btn.classList.add('is-active');
                btn.setAttribute('aria-selected', 'true');
                
                const panelId = btn.getAttribute('aria-controls');
                const panel = document.getElementById(panelId);
                if (panel) {
                    panel.removeAttribute('hidden');
                    panel.classList.add('is-active');
                }
            });
        });
    },

    setupDirtyState() {
        this.elements.inputs.forEach(input => {
            input.addEventListener('input', () => {
                this.state.isDirty = true;
            });
            input.addEventListener('change', () => {
                this.state.isDirty = true;
            });
        });
    },

    setupForms() {
        if (this.elements.form) {
            this.elements.form.addEventListener('submit', (e) => {
                if (this.state.formSubmitting) {
                    e.preventDefault();
                    return;
                }
                
                // Validação visual simples antes do submit nativo
                if (!this.elements.form.checkValidity()) {
                    this.showToast('Por favor, preencha os campos obrigatórios corretamente.');
                    return;
                }

                this.state.isDirty = false;
                this.state.formSubmitting = true;
                
                const originalText = this.elements.btnSave.innerHTML;
                this.elements.btnSave.classList.add('is-loading');
                this.elements.btnSave.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Salvando...';

                // Fallback para destravar após 10s em caso de falha oculta de rede
                setTimeout(() => {
                    this.state.formSubmitting = false;
                    this.elements.btnSave.classList.remove('is-loading');
                    this.elements.btnSave.innerHTML = originalText;
                }, 10000);
            });
        }

        // Formulários inline isolados (ex: botão Executar do Topo)
        const inlineForms = document.querySelectorAll('.embratel-config-inline-form');
        inlineForms.forEach(form => {
            form.addEventListener('submit', (e) => {
                const btn = form.querySelector('button[type="submit"]');
                const confirmMsg = btn.getAttribute('data-confirm');
                
                // Se tiver data-confirm, impedimos o envio real e mostramos o modal
                if (confirmMsg && !this.state.pendingAction) {
                    e.preventDefault();
                    this.state.pendingAction = () => {
                        this.state.pendingAction = null; // limpa após chamar
                        form.submit();
                    };
                    this.openModal('Confirmar Execução', confirmMsg);
                    return;
                }

                if (btn && !btn.classList.contains('is-loading')) {
                    btn.classList.add('is-loading');
                    const ogHtml = btn.innerHTML;
                    btn.innerHTML = '<i class="bi bi-hourglass-split spin"></i> ...';
                    setTimeout(() => {
                        btn.classList.remove('is-loading');
                        btn.innerHTML = ogHtml;
                    }, 8000);
                }
            });
        });
    },

    setupModal() {
        // Gatilhos genéricos (botões que não são do form principal)
        this.elements.modalTriggers.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const title = btn.getAttribute('data-modal-title') || 'Confirmar';
                const body = btn.getAttribute('data-modal-body') || 'Prosseguir?';
                
                // Define a ação simulada no modal
                this.state.pendingAction = () => {
                    this.closeModal();
                    this.showToast('Ação disparada (Integração Backend PENDENTE).');
                    this.state.pendingAction = null;
                };

                this.openModal(title, body);
            });
        });

        // Fechar botões
        this.elements.modalCloseBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                this.state.pendingAction = null;
                this.closeModal();
            });
        });

        // Botão de Confirmação do Modal
        if (this.elements.modalConfirmBtn) {
            this.elements.modalConfirmBtn.addEventListener('click', () => {
                if (typeof this.state.pendingAction === 'function') {
                    this.state.pendingAction();
                } else {
                    this.closeModal();
                }
            });
        }

        // Overlay e Escape
        const overlay = document.querySelector('.embratel-config-modal__overlay');
        if (overlay) overlay.addEventListener('click', () => this.closeModal());

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.elements.modal?.classList.contains('is-open')) {
                this.state.pendingAction = null;
                this.closeModal();
            }
        });
    },

    setupValidation() {
        // Validação visual de inputs number
        const numberInputs = document.querySelectorAll('input[type="number"]');
        numberInputs.forEach(input => {
            input.addEventListener('blur', () => {
                const val = parseInt(input.value, 10);
                const min = parseInt(input.getAttribute('min') || 1, 10);
                const max = parseInt(input.getAttribute('max') || 1440, 10);

                if (isNaN(val) || val < min) input.value = min;
                if (val > max) input.value = max;
            });
        });
    },

    openModal(title, bodyText) {
        if (!this.elements.modal) return;
        this.elements.modalTitle.textContent = title;
        this.elements.modalBody.textContent = bodyText; // textContent por segurança (anti-XSS)
        
        this.elements.modal.classList.add('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'false');
        
        setTimeout(() => {
            this.elements.modalConfirmBtn?.focus();
        }, 100);
    },

    closeModal() {
        if (!this.elements.modal) return;
        this.elements.modal.classList.remove('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'true');
    },

    showToast(message) {
        if (!this.elements.toast) return;
        this.elements.toast.textContent = message;
        this.elements.toast.classList.add('is-visible');
        setTimeout(() => {
            this.elements.toast.classList.remove('is-visible');
        }, 3000);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    EmbratelConfig.init();
});
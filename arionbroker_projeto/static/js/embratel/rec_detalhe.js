/**
 * rec_detalhe.js
 *
 * Controlador client-side da tela de detalhes da automação Embratel.
 * Implementa cópia para área de transferência, modal dinâmico de ações,
 * e proteção contra multi-submissões em formulários POST.
 */

const EmbratelTaskDetail = {
    elements: {},
    toastTimeout: null,

    init() {
        this.cacheElements();
        this.bindEvents();
        this.setupCopyButtons();
    },

    cacheElements() {
        this.elements = {
            copyBtns: document.querySelectorAll('.embratel-copy-btn'),
            toast: document.getElementById('embratel-toast'),
            toastMsg: document.getElementById('embratel-toast-msg'),

            modal: document.getElementById('embratel-action-modal'),
            modalTitle: document.getElementById('embratel-modal-title'),
            modalBody: document.getElementById('embratel-modal-body'),
            modalForm: document.getElementById('embratel-modal-form'),
            modalCloseBtns: document.querySelectorAll('[data-modal-close]'),
            modalTriggers: document.querySelectorAll('[data-modal-target]')
        };
    },

    bindEvents() {
        // Modal de Ações Dinâmicas
        if (this.elements.modalTriggers) {
            this.elements.modalTriggers.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.openModal(btn);
                });
            });
        }

        if (this.elements.modalCloseBtns) {
            this.elements.modalCloseBtns.forEach(btn => {
                btn.addEventListener('click', () => this.closeModal());
            });
        }

        // Fechar Modal pelo Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.elements.modal?.classList.contains('is-open')) {
                this.closeModal();
            }
        });

        // Fechar Modal clicando no Overlay
        const overlay = document.querySelector('.embratel-modal__overlay');
        if (overlay) {
            overlay.addEventListener('click', () => this.closeModal());
        }

        // Submissão do Formulário do Modal (Prevenção de Duplo Clique / Loading)
        if (this.elements.modalForm) {
            this.elements.modalForm.addEventListener('submit', (e) => this.submitPendingForm(e));
        }
    },

    openModal(triggerBtn) {
        if (!this.elements.modal) return;

        const actionUrl = triggerBtn.getAttribute('data-action-url');
        const title = triggerBtn.getAttribute('data-action-title') || 'Confirmar';
        const msg = triggerBtn.getAttribute('data-action-msg') || 'Deseja prosseguir?';

        // Preenche o modal
        this.elements.modalTitle.textContent = title;
        // Injeção segura controlada exclusivamente por atributos data-* providos pelo backend (Django template)
        this.elements.modalBody.innerHTML = msg;
        this.elements.modalForm.setAttribute('action', actionUrl);

        // Exibe o modal
        this.elements.modal.classList.add('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'false');

        // Acessibilidade: foco no primeiro input (caso do "motivo" em ignorar) ou no botão de cancelar
        const firstInput = this.elements.modalBody.querySelector('input');
        if (firstInput) {
            firstInput.focus();
        } else {
            const cancelBtn = this.elements.modal.querySelector('[data-modal-close]');
            if (cancelBtn) cancelBtn.focus();
        }
    },

    closeModal() {
        if (!this.elements.modal) return;
        this.elements.modal.classList.remove('is-open');
        this.elements.modal.setAttribute('aria-hidden', 'true');

        // Limpeza após animação
        setTimeout(() => {
            this.elements.modalForm.setAttribute('action', '');
            this.elements.modalBody.innerHTML = '';
        }, 200);
    },

    submitPendingForm(e) {
        const submitBtn = this.elements.modalForm.querySelector('button[type="submit"]');
        if (submitBtn) {
            if (submitBtn.classList.contains('is-loading')) {
                e.preventDefault();
                return;
            }
            submitBtn.classList.add('is-loading');
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Aguarde...';

            // Restaura após 10s caso a página não recarregue por algum erro de rede oculto
            setTimeout(() => {
                submitBtn.classList.remove('is-loading');
                submitBtn.innerHTML = originalText;
            }, 10000);
        }
    },

    setupCopyButtons() {
        if (this.elements.copyBtns) {
            this.elements.copyBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    const textToCopy = btn.getAttribute('data-copy');
                    this.copyText(textToCopy, btn);
                });
            });
        }
    },

    copyText(text, sourceBtn) {
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            this.showToast('Identificador copiado com sucesso!');
            this.flashCopyFeedback(sourceBtn);
        }).catch(err => {
            console.error('Falha ao copiar texto: ', err);
            this.showToast('Erro ao copiar.', true);
        });
    },

    // Troca o ícone do botão por um "check" por 1.5s, sinalizando sucesso da cópia
    flashCopyFeedback(btn) {
        if (!btn) return;
        const icon = btn.querySelector('i');
        if (!icon) return;

        const originalClass = icon.className;
        icon.className = 'bi bi-check-lg';
        btn.classList.add('is-copied');

        setTimeout(() => {
            icon.className = originalClass;
            btn.classList.remove('is-copied');
        }, 1500);
    },

    showToast(message, isError = false) {
        const toast = this.elements.toast;
        if (!toast) return;

        clearTimeout(this.toastTimeout);

        if (this.elements.toastMsg) {
            this.elements.toastMsg.textContent = message;
        } else {
            toast.textContent = message;
        }

        const icon = toast.querySelector('i');
        if (icon) {
            icon.className = isError ? 'bi bi-exclamation-circle' : 'bi bi-check-circle';
        }

        toast.classList.toggle('is-error', isError);
        toast.classList.add('is-visible');

        this.toastTimeout = setTimeout(() => {
            toast.classList.remove('is-visible');
        }, 3000);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    EmbratelTaskDetail.init();
});
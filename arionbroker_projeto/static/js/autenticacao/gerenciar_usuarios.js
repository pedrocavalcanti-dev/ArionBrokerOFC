/**
 * ============================================================================
 * ARION BROKER — GERENCIAR USUÁRIOS
 * gerenciar_usuarios.js v6.0
 *
 * Compatível com base.js v6 / window.Arion
 * ============================================================================
 */

(function () {
    'use strict';


    // ========================================================================
    // ELEMENTOS
    // ========================================================================

    const modalNovoUsuario =
        document.getElementById('modalNovoUsuario');

    const modalSenha =
        document.getElementById('modalSenha');

    const btnNovoUsuario =
        document.getElementById('btnNovoUsuario');

    const formNovoUsuario =
        document.getElementById('formNovoUsuario');

    const formSenha =
        document.getElementById('formSenha');

    const modalSenhaDesc =
        document.getElementById('modalSenhaDesc');

    const usuariosSearch =
        document.getElementById('usuariosSearch');

    const usuariosTableBody =
        document.getElementById('usuariosTableBody');

    const usuariosSearchEmpty =
        document.getElementById('usuariosSearchEmpty');

    const toastContainer =
        document.getElementById('usuariosToastContainer');


    // ========================================================================
    // CSRF
    // ========================================================================

    function getCsrf() {
        /*
         * base.js v6
         */
        if (
            window.Arion &&
            window.Arion.utils &&
            typeof window.Arion.utils.getCsrfToken === 'function'
        ) {
            const token =
                window.Arion.utils.getCsrfToken();

            if (token) {
                return token;
            }
        }


        /*
         * Fallback cookie Django.
         */
        const match =
            document.cookie.match(
                /(?:^|;\s*)csrftoken=([^;]+)/
            );

        return match
            ? decodeURIComponent(match[1])
            : '';
    }


    // ========================================================================
    // TOAST
    // ========================================================================

    function toast(message, type = 'info') {
        if (!toastContainer) {
            console.log(
                `[ARION/${type}]`,
                message
            );

            return;
        }


        const item =
            document.createElement('div');

        item.className =
            `usuarios-toast usuarios-toast--${type}`;


        const icon =
            type === 'success'
                ? 'bi-check-circle'
                : type === 'error'
                    ? 'bi-x-circle'
                    : 'bi-info-circle';


        item.innerHTML = `
            <i class="bi ${icon}"></i>
            <span></span>
        `;


        item
            .querySelector('span')
            .textContent = message;


        toastContainer.appendChild(
            item
        );


        requestAnimationFrame(() => {
            item.classList.add(
                'show'
            );
        });


        setTimeout(() => {
            item.classList.remove(
                'show'
            );

            setTimeout(() => {
                item.remove();
            }, 220);

        }, 4000);
    }


    // ========================================================================
    // MODAIS
    // ========================================================================

    function openModal(modal) {
        if (!modal) return;

        modal.classList.add(
            'open'
        );

        modal.setAttribute(
            'aria-hidden',
            'false'
        );

        document.body.style.overflow =
            'hidden';
    }


    function closeModal(modal) {
        if (!modal) return;

        modal.classList.remove(
            'open'
        );

        modal.setAttribute(
            'aria-hidden',
            'true'
        );

        /*
         * Só libera scroll se nenhum
         * outro modal estiver aberto.
         */
        if (
            !document.querySelector(
                '.usuarios-modal-overlay.open'
            )
        ) {
            document.body.style.overflow =
                '';
        }
    }


    function closeAllModals() {
        document
            .querySelectorAll(
                '.usuarios-modal-overlay.open'
            )
            .forEach(closeModal);
    }


    // ========================================================================
    // NOVO USUÁRIO
    // ========================================================================

    function abrirModalUsuario() {
        if (!modalNovoUsuario) {
            return;
        }

        openModal(
            modalNovoUsuario
        );


        setTimeout(() => {
            document
                .getElementById('novoNome')
                ?.focus();
        }, 100);
    }


    window.fecharModalUsuario = function () {
        closeModal(
            modalNovoUsuario
        );
    };


    if (btnNovoUsuario) {
        btnNovoUsuario.addEventListener(
            'click',
            abrirModalUsuario
        );
    }


    // ========================================================================
    // MODAL SENHA
    // ========================================================================

    function montarUrlSenha(userId) {
        if (!formSenha) {
            return '';
        }


        const template =
            formSenha.dataset.actionTemplate;


        if (template) {
            return template.replace(
                '999999',
                String(userId)
            );
        }


        return `/auth/usuarios/${userId}/senha/`;
    }


    function abrirModalSenha(
        userId,
        username
    ) {
        if (
            !modalSenha ||
            !formSenha
        ) {
            return;
        }


        formSenha.reset();

        formSenha.action =
            montarUrlSenha(userId);


        if (modalSenhaDesc) {
            modalSenhaDesc.textContent =
                `Usuário: ${username}`;
        }


        openModal(
            modalSenha
        );


        setTimeout(() => {
            document
                .getElementById('novaSenha')
                ?.focus();
        }, 100);
    }


    window.abrirModalSenha =
        abrirModalSenha;


    window.fecharModalSenha =
        function () {
            closeModal(
                modalSenha
            );
        };


    // ========================================================================
    // DATA-CLOSE-MODAL
    // ========================================================================

    document.addEventListener(
        'click',
        (event) => {

            const closeButton =
                event.target.closest(
                    '[data-close-modal]'
                );


            if (closeButton) {
                const id =
                    closeButton.dataset.closeModal;

                closeModal(
                    document.getElementById(id)
                );

                return;
            }


            /*
             * Clique diretamente no fundo.
             */
            if (
                event.target.classList.contains(
                    'usuarios-modal-overlay'
                )
            ) {
                closeModal(
                    event.target
                );
            }
        }
    );


    // ========================================================================
    // ESC
    // ========================================================================

    document.addEventListener(
        'keydown',
        (event) => {
            if (event.key === 'Escape') {
                closeAllModals();
            }
        }
    );


    // ========================================================================
    // PASSWORD TOGGLE
    // ========================================================================

    document.addEventListener(
        'click',
        (event) => {

            const btn =
                event.target.closest(
                    '[data-password-toggle]'
                );


            if (!btn) {
                return;
            }


            const input =
                document.getElementById(
                    btn.dataset.passwordToggle
                );


            if (!input) {
                return;
            }


            const mostrando =
                input.type === 'text';


            input.type =
                mostrando
                    ? 'password'
                    : 'text';


            const icon =
                btn.querySelector('i');


            if (icon) {
                icon.className =
                    mostrando
                        ? 'bi bi-eye'
                        : 'bi bi-eye-slash';
            }


            btn.title =
                mostrando
                    ? 'Mostrar senha'
                    : 'Ocultar senha';


            btn.setAttribute(
                'aria-label',
                btn.title
            );
        }
    );


    // ========================================================================
    // REQUEST JSON
    // ========================================================================

    async function requestJson(
        url,
        options = {}
    ) {
        const response =
            await fetch(
                url,
                options
            );


        let data = {};


        try {
            data =
                await response.json();
        } catch (_) {
            data = {};
        }


        if (!response.ok) {
            throw new Error(
                data.erro ||
                data.mensagem ||
                `Erro HTTP ${response.status}`
            );
        }


        if (data.erro) {
            throw new Error(
                data.erro
            );
        }


        return data;
    }


    // ========================================================================
    // TOGGLE USUÁRIO
    // ========================================================================

    async function toggleUsuario(
        userId,
        username,
        url,
        button
    ) {
        const icon =
            document.getElementById(
                `icon-toggle-${userId}`
            );


        if (!icon || !url) {
            return;
        }


        const desativando =
            icon.classList.contains(
                'bi-person-slash'
            );


        const acao =
            desativando
                ? 'desativar'
                : 'ativar';


        const confirmado =
            window.confirm(
                `Deseja ${acao} o usuário "${username}"?`
            );


        if (!confirmado) {
            return;
        }


        const original =
            button.innerHTML;


        button.disabled = true;
        button.classList.add(
            'is-loading'
        );

        button.innerHTML =
            '<i class="bi bi-arrow-repeat"></i>';


        try {
            const data =
                await requestJson(
                    url,
                    {
                        method: 'POST',

                        headers: {
                            'X-CSRFToken':
                                getCsrf(),

                            'X-Requested-With':
                                'XMLHttpRequest',

                            'Content-Type':
                                'application/json'
                        },

                        body:
                            JSON.stringify({})
                    }
                );


            atualizarStatusUsuario(
                userId,
                data.ativo,
                button
            );


            toast(
                data.mensagem ||
                'Usuário atualizado com sucesso.',
                'success'
            );

        } catch (error) {

            button.innerHTML =
                original;


            toast(
                error.message ||
                'Erro ao alterar usuário.',
                'error'
            );

        } finally {

            button.disabled = false;

            button.classList.remove(
                'is-loading'
            );
        }
    }


    function atualizarStatusUsuario(
        userId,
        ativo,
        button
    ) {
        const status =
            document.getElementById(
                `status-${userId}`
            );


        const icon =
            document.getElementById(
                `icon-toggle-${userId}`
            );


        const row =
            document.getElementById(
                `row-user-${userId}`
            );


        const avatar =
            row?.querySelector(
                '.user-avatar-mini'
            );


        if (ativo) {

            if (status) {
                status.className =
                    'usuario-badge usuario-badge--active';

                status.innerHTML = `
                    <span class="usuario-status-dot"></span>
                    Ativo
                `;
            }


            if (icon) {
                icon.className =
                    'bi bi-person-slash';
            }


            button.className =
                'row-action row-action--danger';

            button.title =
                'Desativar usuário';

            avatar?.classList.remove(
                'user-avatar-mini--inactive'
            );

        } else {

            if (status) {
                status.className =
                    'usuario-badge usuario-badge--inactive';

                status.innerHTML = `
                    <span class="usuario-status-dot"></span>
                    Inativo
                `;
            }


            if (icon) {
                icon.className =
                    'bi bi-person-check';
            }


            button.className =
                'row-action row-action--success';

            button.title =
                'Ativar usuário';

            avatar?.classList.add(
                'user-avatar-mini--inactive'
            );
        }
    }


    // ========================================================================
    // AÇÕES DA TABELA
    // ========================================================================

    document.addEventListener(
        'click',
        (event) => {

            const button =
                event.target.closest(
                    '[data-action]'
                );


            if (!button) {
                return;
            }


            const action =
                button.dataset.action;


            if (action === 'password') {

                abrirModalSenha(
                    button.dataset.userId,
                    button.dataset.username
                );

                return;
            }


            if (action === 'toggle') {

                toggleUsuario(
                    button.dataset.userId,
                    button.dataset.username,
                    button.dataset.url,
                    button
                );
            }
        }
    );


    // ========================================================================
    // ALTERAR CARGO
    // ========================================================================

    document
        .querySelectorAll(
            'select[name="cargo"].classify-select'
        )
        .forEach((select) => {

            select.dataset.valorAnterior =
                select.value;


            select.addEventListener(
                'change',
                async () => {

                    const form =
                        select.closest(
                            'form'
                        );


                    if (!form) {
                        return;
                    }


                    const valorAnterior =
                        select.dataset.valorAnterior;


                    const novoCargo =
                        select.value;


                    const formData =
                        new FormData(form);


                    formData.set(
                        'cargo',
                        novoCargo
                    );


                    select.disabled = true;


                    try {

                        const data =
                            await requestJson(
                                form.action,
                                {
                                    method: 'POST',

                                    body: formData,

                                    headers: {
                                        'X-Requested-With':
                                            'XMLHttpRequest'
                                    }
                                }
                            );


                        select.dataset.valorAnterior =
                            novoCargo;


                        toast(
                            data.mensagem ||
                            'Cargo alterado com sucesso.',
                            'success'
                        );

                    } catch (error) {

                        select.value =
                            valorAnterior;


                        toast(
                            error.message ||
                            'Não foi possível alterar o cargo.',
                            'error'
                        );

                    } finally {

                        select.disabled = false;
                    }
                }
            );
        });


    // ========================================================================
    // VALIDAÇÃO NOVO USUÁRIO
    // ========================================================================

    if (formNovoUsuario) {

        formNovoUsuario.addEventListener(
            'submit',
            (event) => {

                const username =
                    formNovoUsuario
                        .querySelector(
                            '[name="username"]'
                        )
                        ?.value
                        .trim() || '';


                const password =
                    formNovoUsuario
                        .querySelector(
                            '[name="password"]'
                        )
                        ?.value || '';


                if (!username) {

                    event.preventDefault();

                    toast(
                        'O campo Usuário é obrigatório.',
                        'error'
                    );

                    return;
                }


                if (
                    !/^[\w.@+-]+$/.test(
                        username
                    )
                ) {

                    event.preventDefault();

                    toast(
                        'Usuário inválido. Use apenas letras, números, . @ + - _',
                        'error'
                    );

                    return;
                }


                if (password.length < 6) {

                    event.preventDefault();

                    toast(
                        'A senha deve possuir pelo menos 6 caracteres.',
                        'error'
                    );
                }
            }
        );
    }


    // ========================================================================
    // VALIDAÇÃO SENHA
    // ========================================================================

    if (formSenha) {

        formSenha.addEventListener(
            'submit',
            (event) => {

                const password =
                    formSenha
                        .querySelector(
                            '[name="nova_senha"]'
                        )
                        ?.value || '';


                if (password.length < 6) {

                    event.preventDefault();

                    toast(
                        'A nova senha deve possuir pelo menos 6 caracteres.',
                        'error'
                    );
                }
            }
        );
    }


    // ========================================================================
    // BUSCA
    // ========================================================================

    function aplicarBusca() {
        if (
            !usuariosSearch ||
            !usuariosTableBody
        ) {
            return;
        }


        const termo =
            usuariosSearch
                .value
                .trim()
                .toLowerCase();


        const rows =
            Array.from(
                usuariosTableBody.querySelectorAll(
                    '.usuario-row'
                )
            );


        let encontrados = 0;


        rows.forEach((row) => {

            const texto =
                (
                    row.dataset.search ||
                    row.textContent ||
                    ''
                )
                .toLowerCase();


            const mostrar =
                !termo ||
                texto.includes(termo);


            row.hidden =
                !mostrar;


            if (mostrar) {
                encontrados++;
            }
        });


        if (usuariosSearchEmpty) {
            usuariosSearchEmpty.hidden =
                encontrados !== 0;
        }
    }


    usuariosSearch?.addEventListener(
        'input',
        aplicarBusca
    );


    // ========================================================================
    // AUTO DISMISS MESSAGES
    // ========================================================================

    document
        .querySelectorAll(
            '.sys-log-alert'
        )
        .forEach((element) => {

            setTimeout(() => {

                element.style.transition =
                    'opacity .25s ease, transform .25s ease';

                element.style.opacity =
                    '0';

                element.style.transform =
                    'translateY(-4px)';


                setTimeout(() => {
                    element.remove();
                }, 260);

            }, 4500);
        });


    // ========================================================================
    // INIT
    // ========================================================================

    console.log(
        '✓ ARION Users UI Initialized v6.0'
    );

})();
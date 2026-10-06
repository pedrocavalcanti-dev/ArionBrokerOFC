// ============================================================================
// ARION PROJETOS — BROKER
// base.js v7.0 — preferências exclusivamente no backend
// ============================================================================

(function () {
    'use strict';

    // ------------------------------------------------------------------------
    // CONFIGURAÇÕES
    // ------------------------------------------------------------------------

    const MOBILE_BREAKPOINT = 768;

    const URL_PREFERENCIAS = '/autenticacao/preferencias/';


    // ------------------------------------------------------------------------
    // ELEMENTOS
    // ------------------------------------------------------------------------

    const html = document.documentElement;
    const body = document.body;

    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarCollapseBtn = document.getElementById('sidebarCollapseBtn');
    const sidebarCloseMobile = document.getElementById('sidebarCloseMobile');
    const sidebarOverlay = document.getElementById('sidebarOverlay');

    const themeToggle = document.getElementById('themeToggle');
    const csrfInput = document.getElementById('global-csrf');


    // ------------------------------------------------------------------------
    // HELPERS
    // ------------------------------------------------------------------------

    function isMobile() {
        return window.innerWidth <= MOBILE_BREAKPOINT;
    }


    function getCsrfToken() {
        return csrfInput?.value || '';
    }


    async function fetchWithCsrf(url, options = {}) {
        const headers = {
            'X-CSRFToken': getCsrfToken(),
            ...options.headers
        };

        if (
            options.body &&
            typeof options.body === 'string' &&
            !headers['Content-Type']
        ) {
            headers['Content-Type'] = 'application/json';
        }

        return fetch(url, {
            ...options,
            headers
        });
    }


    async function salvarPreferenciasBackend(dados) {
        if (!getCsrfToken()) {
            throw new Error('Token CSRF não encontrado.');
        }

        const resposta = await fetchWithCsrf(
            URL_PREFERENCIAS,
            {
                method: 'POST',
                body: JSON.stringify(dados)
            }
        );

        let payload = null;

        try {
            payload = await resposta.json();
        } catch {
            payload = null;
        }

        if (!resposta.ok) {
            throw new Error(
                payload?.erro ||
                `Falha ao salvar preferências (${resposta.status}).`
            );
        }

        return payload || { status: 'sucesso' };
    }


    // ========================================================================
    // SIDEBAR MOBILE
    // ========================================================================

    function abrirSidebar() {
        if (!sidebar) return;

        sidebar.classList.add('open');
        sidebarOverlay?.classList.add('active');
        body.classList.add('sidebar-open');

        if (isMobile()) {
            body.style.overflow = 'hidden';
        }
    }


    function fecharSidebar() {
        if (!sidebar) return;

        /*
         * No desktop a classe "open" pode existir por causa do template.
         * Portanto, só removemos efetivamente no modo mobile.
         */
        if (isMobile()) {
            sidebar.classList.remove('open');
        }

        sidebarOverlay?.classList.remove('active');
        body.classList.remove('sidebar-open');
        body.style.overflow = '';
    }


    function toggleSidebar() {
        if (!sidebar) return;

        if (!isMobile()) {
            toggleSidebarCollapse();
            return;
        }

        const aberta =
            sidebar.classList.contains('open') &&
            body.classList.contains('sidebar-open');

        if (aberta) {
            fecharSidebar();
        } else {
            abrirSidebar();
        }
    }


    if (sidebarToggle) {
        sidebarToggle.addEventListener(
            'click',
            toggleSidebar
        );
    }


    if (sidebarCloseMobile) {
        sidebarCloseMobile.addEventListener(
            'click',
            fecharSidebar
        );
    }


    if (sidebarOverlay) {
        sidebarOverlay.addEventListener(
            'click',
            fecharSidebar
        );
    }


    // Fecha o menu mobile quando abre uma página.
    document
        .querySelectorAll(
            '.sidebar__nav-link:not(.sidebar__nav-link--group), ' +
            '.sidebar__submenu-link'
        )
        .forEach((link) => {
            link.addEventListener('click', () => {
                if (isMobile()) {
                    fecharSidebar();
                }
            });
        });


    // ========================================================================
    // SIDEBAR RECOLHIDA — DESKTOP
    // ========================================================================

    function sidebarEstaRecolhida() {
        return body.classList.contains(
            'sidebar-closed'
        );
    }


    function atualizarIconeSidebar() {
        if (!sidebarCollapseBtn) return;

        const icon =
            sidebarCollapseBtn.querySelector('i');

        if (!icon) return;

        icon.classList.remove(
            'bi-layout-sidebar-inset',
            'bi-layout-sidebar-inset-reverse'
        );

        if (sidebarEstaRecolhida()) {
            icon.classList.add(
                'bi-layout-sidebar-inset-reverse'
            );

            sidebarCollapseBtn.title =
                'Expandir menu lateral';

            sidebarCollapseBtn.setAttribute(
                'aria-label',
                'Expandir menu lateral'
            );

            sidebarCollapseBtn.setAttribute(
                'aria-pressed',
                'true'
            );

        } else {
            icon.classList.add(
                'bi-layout-sidebar-inset'
            );

            sidebarCollapseBtn.title =
                'Recolher menu lateral';

            sidebarCollapseBtn.setAttribute(
                'aria-label',
                'Recolher menu lateral'
            );

            sidebarCollapseBtn.setAttribute(
                'aria-pressed',
                'false'
            );
        }
    }


    async function definirSidebarRecolhida(
        recolhida,
        salvar = true
    ) {
        const estadoAnterior = sidebarEstaRecolhida();

        body.classList.toggle(
            'sidebar-closed',
            recolhida
        );

        atualizarIconeSidebar();

        if (!salvar) return true;

        try {
            await salvarPreferenciasBackend({
                sidebar_aberta: !recolhida
            });
            return true;
        } catch (erro) {
            body.classList.toggle(
                'sidebar-closed',
                estadoAnterior
            );
            atualizarIconeSidebar();
            console.error(
                '[ARION] Falha ao salvar estado da sidebar:',
                erro
            );
            return false;
        }
    }


    function toggleSidebarCollapse() {
        if (isMobile()) return;

        definirSidebarRecolhida(
            !sidebarEstaRecolhida()
        );
    }


    function initSidebarCollapse() {
        /* O estado inicial é renderizado pelo Django no <body>. */
        atualizarIconeSidebar();
    }


    if (sidebarCollapseBtn) {
        sidebarCollapseBtn.addEventListener(
            'click',
            toggleSidebarCollapse
        );
    }


    // ========================================================================
    // GRUPOS EXPANSÍVEIS
    // ========================================================================

    function toggleNavGroup(groupName) {
        const group = document.getElementById(
            `group-${groupName}`
        );

        const submenu = document.getElementById(
            `submenu-${groupName}`
        );

        if (!group || !submenu) return;

        const aberto = submenu.classList.contains(
            'open'
        );

        group.classList.toggle(
            'active',
            !aberto
        );

        submenu.classList.toggle(
            'open',
            !aberto
        );

        const button = group.querySelector(
            '.sidebar__nav-link--group'
        );

        if (button) {
            button.setAttribute(
                'aria-expanded',
                String(!aberto)
            );
        }
    }


    /*
     * O HTML usa onclick="toggleNavGroup('claro')",
     * então precisamos expor globalmente.
     */
    window.toggleNavGroup = toggleNavGroup;


    // ========================================================================
    // NAVEGAÇÃO ATIVA
    // ========================================================================

    function normalizarPath(path) {
        if (!path) return '/';

        try {
            const url = new URL(
                path,
                window.location.origin
            );

            let pathname = url.pathname;

            if (
                pathname.length > 1 &&
                pathname.endsWith('/')
            ) {
                pathname = pathname.slice(
                    0,
                    -1
                );
            }

            return pathname;

        } catch {
            return path;
        }
    }


    function setActiveNav() {
        const navLinks = Array.from(
            document.querySelectorAll(
                '[data-nav-link]'
            )
        );

        const currentPath = normalizarPath(
            window.location.pathname
        );

        let melhorLink = null;
        let melhorTamanho = -1;


        navLinks.forEach((link) => {
            const href = link.getAttribute(
                'href'
            );

            if (!href) return;

            /*
             * Não tenta tornar link externo,
             * # ou javascript como ativo.
             */
            if (
                href.startsWith('#') ||
                href.startsWith('javascript:')
            ) {
                return;
            }

            const linkPath = normalizarPath(
                href
            );

            if (linkPath === '/') return;

            const combina =
                currentPath === linkPath ||
                currentPath.startsWith(
                    `${linkPath}/`
                );

            if (
                combina &&
                linkPath.length > melhorTamanho
            ) {
                melhorLink = link;
                melhorTamanho = linkPath.length;
            }
        });


        /*
         * Não apaga classes do Django de forma indiscriminada.
         * Apenas define a melhor correspondência encontrada.
         */
        if (!melhorLink) return;


        const itemAtual =
            melhorLink.closest(
                '.sidebar__nav-item'
            );

        if (itemAtual) {
            itemAtual.classList.add(
                'active'
            );
        }


        /*
         * Caso seja item dentro de submenu,
         * abre automaticamente o grupo pai.
         */
        const submenu =
            melhorLink.closest(
                '.sidebar__submenu'
            );

        if (submenu) {
            submenu.classList.add(
                'open'
            );

            const groupName =
                submenu.id.replace(
                    'submenu-',
                    ''
                );

            const group =
                document.getElementById(
                    `group-${groupName}`
                );

            if (group) {
                group.classList.add(
                    'active'
                );

                const button =
                    group.querySelector(
                        '.sidebar__nav-link--group'
                    );

                button?.setAttribute(
                    'aria-expanded',
                    'true'
                );
            }
        }
    }


    // ========================================================================
    // TEMA
    // ========================================================================

    function temaAtual() {
        return html.getAttribute(
            'data-theme'
        ) || 'dark';
    }


    function atualizarBotaoTema() {
        if (!themeToggle) return;

        const icon =
            themeToggle.querySelector('i');

        const text =
            themeToggle.querySelector('span');

        if (!icon) return;

        icon.classList.remove(
            'bi-moon-stars',
            'bi-sun',
            'bi-sun-fill'
        );


        if (temaAtual() === 'dark') {
            /*
             * Estamos no escuro:
             * mostramos sol porque esta é
             * a ação disponível.
             */
            icon.classList.add(
                'bi-sun'
            );

            themeToggle.title =
                'Usar tema claro';

            if (text) {
                text.textContent = 'Tema claro';
            }

        } else {
            icon.classList.add(
                'bi-moon-stars'
            );

            themeToggle.title =
                'Usar tema escuro';

            if (text) {
                text.textContent = 'Tema escuro';
            }
        }
    }


    async function definirTema(
        tema,
        salvar = true
    ) {
        const temaAnterior = temaAtual();
        const temaSeguro = tema === 'light' ? 'light' : 'dark';

        html.setAttribute('data-theme', temaSeguro);
        atualizarBotaoTema();

        if (!salvar) return true;

        try {
            await salvarPreferenciasBackend({ tema: temaSeguro });
            return true;
        } catch (erro) {
            html.setAttribute('data-theme', temaAnterior);
            atualizarBotaoTema();
            console.error('[ARION] Falha ao salvar tema:', erro);
            return false;
        }
    }


    function toggleTheme() {
        const novoTema =
            temaAtual() === 'dark'
                ? 'light'
                : 'dark';

        definirTema(
            novoTema
        );

        if (themeToggle) {
            themeToggle.animate(
                [
                    {
                        transform: 'rotate(0deg)'
                    },
                    {
                        transform: 'rotate(12deg)'
                    },
                    {
                        transform: 'rotate(0deg)'
                    }
                ],
                {
                    duration: 240,
                    easing: 'ease-out'
                }
            );
        }
    }


    function initTheme() {
        const temaDoHtml = html.getAttribute('data-theme');

        if (temaDoHtml === 'dark' || temaDoHtml === 'light') {
            definirTema(temaDoHtml, false);
            return;
        }

        definirTema('dark', false);
    }


    if (themeToggle) {
        themeToggle.addEventListener(
            'click',
            toggleTheme
        );
    }


    // ========================================================================
    // BADGES
    // ========================================================================

    function updateBadges() {
        document
            .querySelectorAll(
                '.sidebar__badge'
            )
            .forEach((badge) => {
                const valor =
                    parseInt(
                        badge.textContent.trim(),
                        10
                    );

                /*
                 * Só esconde quando for realmente zero.
                 * Se conteúdo não for número,
                 * não altera.
                 */
                if (
                    !Number.isNaN(valor) &&
                    valor <= 0
                ) {
                    badge.hidden = true;
                } else {
                    badge.hidden = false;
                }
            });
    }


    // ========================================================================
    // LINKS ÂNCORA
    // ========================================================================

    function initAnchorScroll() {
        document
            .querySelectorAll(
                'a[href^="#"]'
            )
            .forEach((anchor) => {
                anchor.addEventListener(
                    'click',
                    function (event) {
                        const href =
                            this.getAttribute(
                                'href'
                            );

                        if (
                            !href ||
                            href === '#'
                        ) {
                            return;
                        }

                        let target;

                        try {
                            target =
                                document.querySelector(
                                    href
                                );
                        } catch {
                            return;
                        }

                        if (!target) return;

                        event.preventDefault();

                        target.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                        });
                    }
                );
            });
    }


    // ========================================================================
    // TECLADO
    // ========================================================================

    function initKeyboardShortcuts() {
        document.addEventListener(
            'keydown',
            (event) => {

                /*
                 * Escape fecha sidebar mobile.
                 */
                if (
                    event.key === 'Escape' &&
                    isMobile() &&
                    body.classList.contains(
                        'sidebar-open'
                    )
                ) {
                    fecharSidebar();
                    return;
                }


                /*
                 * Ctrl/Cmd + Shift + M
                 * Sidebar
                 */
                if (
                    (event.ctrlKey || event.metaKey) &&
                    event.shiftKey &&
                    event.key.toLowerCase() === 'm'
                ) {
                    event.preventDefault();

                    if (isMobile()) {
                        toggleSidebar();
                    } else {
                        toggleSidebarCollapse();
                    }

                    return;
                }


                /*
                 * Ctrl/Cmd + Shift + T
                 * Tema
                 */
                if (
                    (event.ctrlKey || event.metaKey) &&
                    event.shiftKey &&
                    event.key.toLowerCase() === 't'
                ) {
                    event.preventDefault();
                    toggleTheme();
                }
            }
        );
    }


    // ========================================================================
    // RESIZE
    // ========================================================================

    let resizeTimer = null;


    function tratarResize() {
        clearTimeout(
            resizeTimer
        );

        resizeTimer = setTimeout(
            () => {

                if (!isMobile()) {
                    /*
                     * Saindo do mobile:
                     * remove apenas estados temporários.
                     */
                    body.classList.remove(
                        'sidebar-open'
                    );

                    sidebarOverlay?.classList.remove(
                        'active'
                    );

                    body.style.overflow = '';

                    /*
                     * O desktop não depende de .open
                     * para permanecer visível.
                     */
                    sidebar?.classList.add(
                        'open'
                    );

                } else {
                    /*
                     * Entrando no mobile:
                     * começa fechado.
                     */
                    sidebar?.classList.remove(
                        'open'
                    );

                    body.classList.remove(
                        'sidebar-open'
                    );

                    sidebarOverlay?.classList.remove(
                        'active'
                    );

                    body.style.overflow = '';
                }

            },
            120
        );
    }


    window.addEventListener(
        'resize',
        tratarResize
    );


    // ========================================================================
    // INICIALIZAÇÃO
    // ========================================================================

    function init() {
        initTheme();
        initSidebarCollapse();

        setActiveNav();
        updateBadges();

        initAnchorScroll();
        initKeyboardShortcuts();

        /*
         * No desktop, sidebar permanece visível.
         * No mobile, começa fechada.
         */
        if (isMobile()) {
            sidebar?.classList.remove(
                'open'
            );

            body.classList.remove(
                'sidebar-open'
            );

            sidebarOverlay?.classList.remove(
                'active'
            );

        } else {
            sidebar?.classList.add(
                'open'
            );
        }

        atualizarIconeSidebar();
        atualizarBotaoTema();

        console.log(
            '✓ ARION Broker UI Initialized v7.0 — Backend Preferences'
        );

        if (
            typeof window.arionOnReady ===
            'function'
        ) {
            window.arionOnReady();
        }
    }


    /*
     * Como base.js normalmente fica no final do body,
     * o DOM pode já estar carregado.
     */
    if (
        document.readyState === 'loading'
    ) {
        document.addEventListener(
            'DOMContentLoaded',
            init
        );

    } else {
        init();
    }


    // ========================================================================
    // API PÚBLICA
    // ========================================================================

    window.Arion = {
        sidebar: {
            toggle: toggleSidebar,

            open: abrirSidebar,

            close: fecharSidebar,

            toggleCollapse:
                toggleSidebarCollapse,

            collapse: () => {
                definirSidebarRecolhida(
                    true
                );
            },

            expand: () => {
                definirSidebarRecolhida(
                    false
                );
            },

            isOpen: () => {
                return sidebar?.classList.contains(
                    'open'
                ) || false;
            },

            isCollapsed:
                sidebarEstaRecolhida
        },


        nav: {
            toggle:
                toggleNavGroup,

            setActive:
                setActiveNav
        },


        theme: {
            toggle:
                toggleTheme,

            get:
                temaAtual,

            set: (theme) => {
                definirTema(
                    theme
                );
            }
        },


        badges: {
            refresh:
                updateBadges
        },


        utils: {
            isMobile,
            getCsrfToken,
            fetchWithCsrf
        }
    };

})();
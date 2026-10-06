/* ============================================================================
 * detalhes.js — PÁGINA DE DETALHE
 * Controla a navegação por abas na tela de detalhe do cancelamento.
 * Depende de window.Cancelamentos (definido em cancelamentos.js).
 *
 * RECURSOS
 *   - Indicador deslizante ("pill") sob a aba ativa, com animação suave
 *   - Transição de fade + leve slide ao trocar de painel
 *   - Navegação por teclado (← → Home End) seguindo o padrão ARIA de tabs
 *   - Estado refletido na URL (#tab-xxx) + suporte a voltar/avançar do navegador
 *   - Acessibilidade: role="tablist"/"tab"/"tabpanel", aria-selected, aria-controls
 *   - Evento customizado `cancelamentos:aba-alterada` disparado a cada troca,
 *     para outros módulos (ex.: recarregar dados de uma aba) escutarem.
 *
 * ORDEM DE CARREGAMENTO: por último, depois de cancelamentos.js e modais.js.
 * Só faz sentido incluir este arquivo em detalhe.html — as páginas de fila
 * (cancelamentos.html e filhos) não precisam dele.
 * ==========================================================================*/
(function () {
    'use strict';

    if (!window.Cancelamentos || !window.Cancelamentos.root) return;

    const wrapper = document.getElementById('cancDetalheWrapper');
    if (!wrapper) return; // só roda na página de detalhe

    const nav      = document.querySelector('.detalhe-tabs-nav');
    const abas     = Array.from(document.querySelectorAll('[data-aba-trigger]'));
    const paineis  = Array.from(document.querySelectorAll('[data-aba-painel]'));

    if (!abas.length || !paineis.length || !nav) return;

    let abaAtual  = null;
    let indicator = null;
    let resizeTimer = null;

    /* ── Acessibilidade: prepara atributos ARIA uma única vez ───────────── */
    function preparaAcessibilidade() {
        nav.setAttribute('role', 'tablist');

        abas.forEach((tab) => {
            const nome   = tab.dataset.abaTrigger;
            const painel = document.querySelector(`[data-aba-painel="${nome}"]`);
            const ativa  = tab.classList.contains('detalhe-tab--active');

            tab.setAttribute('role', 'tab');
            tab.id = tab.id || `tab-btn-${nome}`;
            tab.setAttribute('tabindex', ativa ? '0' : '-1');
            tab.setAttribute('aria-selected', ativa ? 'true' : 'false');

            if (painel) {
                painel.id = painel.id || `painel-${nome}`;
                painel.setAttribute('role', 'tabpanel');
                painel.setAttribute('aria-labelledby', tab.id);
                painel.setAttribute('aria-hidden', ativa ? 'false' : 'true');
                if (ativa) {
                    painel.removeAttribute('hidden');
                } else {
                    painel.setAttribute('hidden', '');
                }
                tab.setAttribute('aria-controls', painel.id);
            }
        });
    }

    /* ── Indicador deslizante sob a aba ativa ────────────────────────────── */
    function criaIndicador() {
        indicator = document.createElement('span');
        indicator.className = 'detalhe-tab-indicator';
        indicator.setAttribute('aria-hidden', 'true');
        nav.appendChild(indicator);
    }

    function moveIndicador(tab, animar) {
        if (!indicator || !tab) return;
        const navRect = nav.getBoundingClientRect();
        const tabRect = tab.getBoundingClientRect();
        const left = (tabRect.left - navRect.left) + nav.scrollLeft;

        indicator.classList.toggle('detalhe-tab-indicator--sem-transicao', !animar);
        indicator.style.width     = `${tabRect.width}px`;
        indicator.style.transform = `translateX(${left}px)`;

        // garante que a próxima chamada volte a animar
        if (!animar) {
            void indicator.offsetWidth;
            indicator.classList.remove('detalhe-tab-indicator--sem-transicao');
        }
    }

    /* ── Troca de painel com transição ───────────────────────────────────── */
    function ativarAba(nomeAba, opcoes) {
        const { foco = false, atualizaUrl = true, animarIndicador = true } = opcoes || {};

        const tab    = abas.find((t) => t.dataset.abaTrigger === nomeAba);
        const painel = document.querySelector(`[data-aba-painel="${nomeAba}"]`);
        if (!tab || !painel) return;

        if (nomeAba === abaAtual) {
            moveIndicador(tab, animarIndicador);
            if (foco) tab.focus();
            return;
        }

        abas.forEach((t) => {
            const ativa = t === tab;
            t.classList.toggle('detalhe-tab--active', ativa);
            t.setAttribute('aria-selected', ativa ? 'true' : 'false');
            t.setAttribute('tabindex', ativa ? '0' : '-1');
        });

        paineis.forEach((p) => {
            if (p === painel) return;
            p.classList.remove('detalhe-painel--active', 'detalhe-painel--saindo');
            p.setAttribute('aria-hidden', 'true');
            p.setAttribute('hidden', '');
        });

        painel.removeAttribute('hidden');
        painel.setAttribute('aria-hidden', 'false');
        // reinicia a animação de entrada mesmo se o painel já tiver sido visto antes
        painel.classList.remove('detalhe-painel--active');
        void painel.offsetWidth; // força reflow
        painel.classList.add('detalhe-painel--active');

        moveIndicador(tab, animarIndicador);
        abaAtual = nomeAba;

        if (foco) tab.focus();

        if (atualizaUrl && history.replaceState) {
            history.replaceState(null, '', `#tab-${nomeAba}`);
        }

        // Notifica outros módulos (ex.: recarregar dados só quando a aba abre)
        wrapper.dispatchEvent(new CustomEvent('cancelamentos:aba-alterada', {
            detail: { aba: nomeAba, painel, tab },
        }));
    }

    /* ── Clique nas abas ──────────────────────────────────────────────────── */
    abas.forEach((trigger) => {
        trigger.addEventListener('click', () => ativarAba(trigger.dataset.abaTrigger));
    });

    /* ── Navegação por teclado (padrão ARIA "tabs") ──────────────────────── */
    nav.addEventListener('keydown', (ev) => {
        const idxAtual = abas.findIndex((t) => t.classList.contains('detalhe-tab--active'));
        if (idxAtual === -1) return;

        let novoIndex = null;
        switch (ev.key) {
            case 'ArrowRight':
                novoIndex = (idxAtual + 1) % abas.length;
                break;
            case 'ArrowLeft':
                novoIndex = (idxAtual - 1 + abas.length) % abas.length;
                break;
            case 'Home':
                novoIndex = 0;
                break;
            case 'End':
                novoIndex = abas.length - 1;
                break;
            default:
                return; // não intercepta outras teclas
        }

        ev.preventDefault();
        ativarAba(abas[novoIndex].dataset.abaTrigger, { foco: true });
    });

    /* ── Suporte a voltar/avançar do navegador ───────────────────────────── */
    window.addEventListener('popstate', () => {
        const hash = window.location.hash.replace('#tab-', '');
        if (hash && abas.some((t) => t.dataset.abaTrigger === hash)) {
            ativarAba(hash, { atualizaUrl: false });
        }
    });

    /* ── Reposiciona o indicador ao redimensionar a janela ───────────────── */
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            const tabAtiva = abas.find((t) => t.classList.contains('detalhe-tab--active'));
            if (tabAtiva) moveIndicador(tabAtiva, false);
        }, 120);
    });

    /* ── Inicialização ────────────────────────────────────────────────────── */
    preparaAcessibilidade();
    criaIndicador();

    const hashInicial = window.location.hash.replace('#tab-', '');
    const abaPadrao = (abas.find((t) => t.classList.contains('detalhe-tab--active')) || abas[0]).dataset.abaTrigger;
    const abaInicial = (hashInicial && abas.some((t) => t.dataset.abaTrigger === hashInicial))
        ? hashInicial
        : abaPadrao;

    // Aguarda o layout estabilizar (fontes/ícones) antes de posicionar o indicador
    requestAnimationFrame(() => {
        ativarAba(abaInicial, { atualizaUrl: false, animarIndicador: false });
    });
})();
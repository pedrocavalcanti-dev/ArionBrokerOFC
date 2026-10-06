/* ============================================================
   ARION PROJETOS — BROKER
   rec_detalhe.js — Envio individual e classificação de projeto
   ============================================================ */

(function () {
    'use strict';

    const btnEnviar     = document.getElementById('btnEnviar');
    const btnClassificar = document.getElementById('btnClassificar');
    const cardClassificar = document.getElementById('cardClassificar');

    // ── 1. ENVIAR E-MAIL ──────────────────────────────────────
    if (btnEnviar) {
        btnEnviar.addEventListener('click', function () {
            const recId = btnEnviar.dataset.rec;
            if (!recId) return;

            const ok = window.confirm(`Confirma o envio do e-mail para a REC ${recId}?`);
            if (!ok) return;

            btnEnviar.disabled = true;
            btnEnviar.innerHTML = '<i class="bi bi-hourglass-split"></i> Enviando...';

            window.ArionBroker.post('/painel/disparar/', { recs: [recId] })
                .then(function (data) {
                    window.ArionBroker.toast(
                        `<i class="bi bi-check-circle"></i> REC ${recId} enviada com sucesso!`,
                        'success'
                    );
                    setTimeout(() => window.location.reload(), 1500);
                })
                .catch(function () {
                    window.ArionBroker.toast(
                        '<i class="bi bi-x-circle"></i> Erro ao enviar. Tente novamente.',
                        'error'
                    );
                    btnEnviar.disabled = false;
                    btnEnviar.innerHTML = '<i class="bi bi-send"></i> Enviar E-mail';
                });
        });
    }

    // ── 2. BOTÃO CLASSIFICAR (scroll até o card) ──────────────
    if (btnClassificar && cardClassificar) {
        btnClassificar.addEventListener('click', function () {
            cardClassificar.scrollIntoView({ behavior: 'smooth', block: 'center' });
            cardClassificar.style.transition = 'box-shadow 0.3s ease';
            cardClassificar.style.boxShadow  = '0 0 0 2px rgba(239,68,68,0.4)';
            setTimeout(function () {
                cardClassificar.style.boxShadow = '';
            }, 1800);
        });
    }

})();
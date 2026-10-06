/* ============================================================
   ARION PROJETOS — BROKER
   login.js v3.0 — Loading state no submit
   ============================================================ */

(function () {
    'use strict';

    const form      = document.querySelector('.login-form');
    const submitBtn = document.getElementById('submitBtn');

    if (!form || !submitBtn) return;

    form.addEventListener('submit', function () {
        const user = document.getElementById('username').value.trim();
        const pass = document.getElementById('password').value.trim();

        // Só exibe estado de loading se ambos os campos estiverem preenchidos (HTML5 validation faz o resto)
        if (user && pass) {
            submitBtn.classList.add('loading');
            
            // Um pequeno delay garante que o submit do form realmente aconteça 
            // antes de travar completamente o botão
            setTimeout(function() {
                submitBtn.disabled = true;
            }, 10);
        }
    });

})();
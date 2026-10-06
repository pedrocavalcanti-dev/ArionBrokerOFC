from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from django.conf import settings
from django.conf.urls.static import static


# =============================================================
# PERSONALIZAÇÃO DO PAINEL ADMIN
# =============================================================
admin.site.site_header = 'Arion Broker — Sistema'
admin.site.site_title = 'Arion Admin'
admin.site.index_title = 'Painel de Administração'


# =============================================================
# URLS PRINCIPAIS
# =============================================================
urlpatterns = [
    # ---------------------------------------------------------
    # HOME
    # ---------------------------------------------------------
    path(
        '',
        RedirectView.as_view(
            pattern_name='autenticacao:login'
        ),
        name='home',
    ),

    # ---------------------------------------------------------
    # ADMIN
    # ---------------------------------------------------------
    path(
        'arion-sys/painel/',
        admin.site.urls,
    ),

    # ---------------------------------------------------------
    # AUTENTICAÇÃO
    # ---------------------------------------------------------
    path(
        'autenticacao/',
        include('aplicativos.autenticacao.urls'),
    ),

    # ---------------------------------------------------------
    # PAINEL
    # ---------------------------------------------------------
    path(
        'painel/',
        include('aplicativos.painel.urls'),
    ),

    # ---------------------------------------------------------
    # AUTOMAÇÃO
    # ---------------------------------------------------------
    path(
        'automacao/',
        include('aplicativos.automacao.urls'),
    ),

    # ---------------------------------------------------------
    # AUTOMAÇÃO EMBRATEL
    # ---------------------------------------------------------
    path(
        'automacao-embratel/',
        include('aplicativos.automacao_embratel.urls'),
    ),

    # ---------------------------------------------------------
    # PROJETOS / CHAMADOS
    # ---------------------------------------------------------
    path(
        'projetos/',
        include('aplicativos.chamados.urls'),
    ),

    # ---------------------------------------------------------
    # CANCELAMENTOS
    # ---------------------------------------------------------
    path(
        'cancelamentos/',
        include('aplicativos.cancelamentos.urls'),
    ),
]


# =============================================================
# MEDIA / STATIC
# =============================================================
urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT,
)

urlpatterns += static(
    settings.STATIC_URL,
    document_root=settings.STATIC_ROOT,
)


# =============================================================
# HANDLERS DE ERRO
# =============================================================
handler400 = 'django.views.defaults.bad_request'
handler403 = 'django.views.defaults.permission_denied'
handler404 = 'django.views.defaults.page_not_found'
handler500 = 'django.views.defaults.server_error'
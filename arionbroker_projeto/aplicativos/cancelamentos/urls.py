from django.urls import path

from . import views

app_name = 'cancelamentos'

urlpatterns = [
    # =========================================================
    # PÁGINAS DAS FILAS
    # =========================================================
    path('', views.pedido, name='pedido'),
    path('solicitacao/', views.solicitacao, name='solicitacao'),
    path('pendencia/', views.pendencia, name='pendencia'),
    path('concluidos/', views.concluido, name='concluido'),

    # Fila 4 — Financeiro (Legado temporário)
    # Remover somente após: templates/JS atualizados, migration concluída e validação em prod.
    path('financeiro/', views.financeiro, name='financeiro'),

    # =========================================================
    # RELATÓRIOS
    # =========================================================
    path(
        'relatorio/excel/',
        views.exportar_relatorio_excel,
        name='exportar_relatorio_excel',
    ),

    # =========================================================
    # API — CRIAÇÃO E EDIÇÃO
    # =========================================================
    path('api/criar/', views.api_criar, name='api_criar'),
    path('api/mover-lote/', views.api_mover_lote, name='api_mover_lote'),
    path('api/<int:pk>/editar/', views.api_editar, name='api_editar'),

    # =========================================================
    # API — PENDÊNCIAS (Específicas)
    # Devem preceder rotas genéricas como 'api/<int:pk>/'
    # =========================================================
    path(
        'api/pendencias/<int:pendencia_pk>/resolver/',
        views.api_pendencia_resolver,
        name='api_pendencia_resolver',
    ),
    path(
        'api/pendencias/<int:pendencia_pk>/descartar/',
        views.api_pendencia_descartar,
        name='api_pendencia_descartar',
    ),

    # =========================================================
    # API — DETALHES, FLUXO E STATUS
    # =========================================================
    path('api/<int:pk>/', views.api_detalhe, name='api_detalhe'),
    path('api/<int:pk>/mover/', views.api_mover, name='api_mover'),
    path('api/<int:pk>/status/', views.api_status, name='api_status'),

    # =========================================================
    # API — RESPONSÁVEL
    # =========================================================
    path('api/<int:pk>/apropriar/', views.api_apropriar, name='api_apropriar'),
    path('api/<int:pk>/liberar/', views.api_liberar, name='api_liberar'),
    path('api/<int:pk>/transferir/', views.api_transferir, name='api_transferir'),

    # =========================================================
    # API — OBSERVAÇÕES
    # =========================================================
    path('api/<int:pk>/observacoes/', views.api_obs_listar, name='api_obs_listar'),
    path('api/<int:pk>/observacoes/adicionar/', views.api_obs, name='api_obs'),
    path('api/<int:pk>/obs/', views.api_obs, name='api_obs_compat'),  # Legado JS

    # =========================================================
    # API — PENDÊNCIAS E FINANCEIRO DO CANCELAMENTO
    # =========================================================
    path('api/<int:pk>/pendencias/criar/', views.api_pendencia_criar, name='api_pendencia_criar'),
    path('api/<int:pk>/financeiro/', views.api_financeiro, name='api_financeiro'),
    path('api/<int:pk>/concluir/', views.api_concluir, name='api_concluir'),

    # =========================================================
    # API — BUSCA E EXCLUSÃO
    # =========================================================
    path('api/busca-global/', views.api_busca_global, name='api_busca_global'),
    path('api/<int:pk>/excluir/', views.api_excluir, name='api_excluir'),

    # =========================================================
    # PÁGINA COMPLETA DO CANCELAMENTO
    # =========================================================
    path('<int:pk>/', views.detalhe, name='detalhe'),
]

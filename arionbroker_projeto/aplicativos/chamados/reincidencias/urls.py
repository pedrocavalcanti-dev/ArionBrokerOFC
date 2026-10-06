from django.urls import path
from . import views

app_name = "reincidencias"

urlpatterns = [
    # ==========================================================================
    # 1. PÁGINAS FIXAS
    # ==========================================================================
    path("", views.tratamento, name="tratamento"),
    path("monitoramento/", views.monitoramento, name="monitoramento"),
    path("finalizados/", views.finalizados, name="finalizados"),

    # ==========================================================================
    # 2. APIs FIXAS
    # ==========================================================================
    path("api/resumo/", views.api_resumo, name="api_resumo"),
    path("api/usuarios/", views.api_usuarios, name="api_usuarios"),
    path("api/criar/", views.api_criar, name="api_criar"),

    # ==========================================================================
    # 3. APIs COM PK (CONSULTA E EDIÇÃO)
    # ==========================================================================
    path("api/<int:pk>/detalhes/", views.api_detalhes, name="api_detalhes"),
    path("api/<int:pk>/editar/", views.api_editar, name="api_editar"),
    path("api/<int:pk>/excluir/", views.api_excluir, name="api_excluir"),

    # ==========================================================================
    # 4. APIs DE RESPONSABILIDADE
    # ==========================================================================
    path("api/<int:pk>/apropriar/", views.api_apropriar, name="api_apropriar"),
    path("api/<int:pk>/liberar/", views.api_liberar, name="api_liberar"),
    path("api/<int:pk>/transferir/", views.api_transferir, name="api_transferir"),

    # ==========================================================================
    # 5. APIs DE FLUXO E ANÁLISE
    # ==========================================================================
    path("api/<int:pk>/status/", views.api_atualizar_status, name="api_atualizar_status"),
    path("api/<int:pk>/salvar-analise/", views.api_salvar_analise, name="api_salvar_analise"),
    path("api/<int:pk>/classificar/", views.api_classificar, name="api_classificar"),

    # ==========================================================================
    # 6. APIs DE MONITORAMENTO
    # ==========================================================================
    path("api/<int:pk>/texto-otrs/", views.api_texto_otrs, name="api_texto_otrs"),
    path("api/<int:pk>/previa-email-monitoramento/", views.api_previa_email_monitoramento, name="api_previa_email_monitoramento"),
    path("api/<int:pk>/enviar-email-monitoramento/", views.api_enviar_email_monitoramento, name="api_enviar_email_monitoramento"),
    path("api/<int:pk>/registrar-ticket-monitoramento/", views.api_registrar_ticket_monitoramento, name="api_registrar_ticket_monitoramento"),
    path("api/<int:pk>/mover-monitoramento/", views.api_mover_monitoramento, name="api_mover_monitoramento"),

    # ==========================================================================
    # 7. APIs DE FINALIZAÇÃO E REABERTURA
    # ==========================================================================
    path("api/<int:pk>/reabrir/", views.api_reabrir, name="api_reabrir"),
    path("api/<int:pk>/reabrir-finalizado/", views.api_reabrir_finalizado, name="api_reabrir_finalizado"),
    path("api/<int:pk>/concluir/", views.api_concluir, name="api_concluir"),

    # ==========================================================================
    # 8. HISTÓRICO
    # ==========================================================================
    path("api/<int:pk>/historico/", views.api_historico, name="api_historico"),

    # ==========================================================================
    # 9. PÁGINA DE DETALHES (DEVE SER A ÚLTIMA PARA NÃO CONFLITAR COM AS FIXAS)
    # ==========================================================================
    path("<int:pk>/", views.detalhes, name="detalhes"),
]
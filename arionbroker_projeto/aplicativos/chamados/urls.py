from django.urls import include, path
from . import views

app_name = 'chamados'

urlpatterns = [
    # Dashboard consolidado de KPIs (página HTML)
    path('dashboard/', views.dashboard_projetos, name='dashboard_projetos'),

    # API JSON: todos os KPIs salvos no banco (usado pelos cards do OTRS)
    path('api/kpis/', views.api_kpis, name='api_kpis'),

    # API JSON: resumo consolidado por operadora para o dashboard principal
    path('api/dashboard-resumo/', views.api_dashboard_resumo, name='api_dashboard_resumo'),

    # Módulo interno RREIP - Reincidências (Com namespace explícito para resolver o NoReverseMatch)
    path('reincidencias/', include(('aplicativos.chamados.reincidencias.urls', 'reincidencias'), namespace='reincidencias')),

    # API JSON: cadastro manual de chamado (precisa vir ANTES da rota genérica abaixo)
    path('<slug:operadora_slug>/<slug:projeto_slug>/criar/', views.criar_chamado, name='criar_chamado'),

    # API JSON: edição de chamado existente (reaproveita o modal "Novo Chamado")
    path('<slug:operadora_slug>/<slug:projeto_slug>/<int:chamado_id>/editar/', views.editar_chamado, name='editar_chamado'),

    # API JSON: exclusão de chamado — somente admin (is_staff), checado na view
    path('<slug:operadora_slug>/<slug:projeto_slug>/<int:chamado_id>/excluir/', views.excluir_chamado, name='excluir_chamado'),

    # API JSON: atualização de status individual do chamado (dropdown flutuante na tabela)
    path('<slug:operadora_slug>/<slug:projeto_slug>/<int:chamado_id>/status/', views.atualizar_status_chamado, name='atualizar_status_chamado'),

    # API JSON: Salvar filtros no banco de dados para o usuário
    path('<slug:operadora_slug>/<slug:projeto_slug>/filtro/salvar/', views.salvar_filtro_usuario, name='salvar_filtro_usuario'),

    # Página individual de projeto
    path('<slug:operadora_slug>/<slug:projeto_slug>/', views.index_projetos, name='index_projetos'),
]
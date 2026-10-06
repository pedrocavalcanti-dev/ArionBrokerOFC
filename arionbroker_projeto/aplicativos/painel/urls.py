from django.urls import path
from . import views
app_name = 'painel'
urlpatterns = [
    # Telas Principais
    path('',          views.dashboard,          name='dashboard'),
    path('enviadas/', views.recs_enviadas,       name='recs_enviadas'),
    path('destinos/', views.configuracao_emails, name='destinos'),
    # Detalhes e Ações de Registro
    path('rec/<str:rec_id>/',             views.rec_detalhe,     name='rec_detalhe'),
    path('rec/<str:rec_id>/classificar/', views.classificar_rec, name='classificar_rec'),
    # Ações AJAX
    path('disparar/',         views.disparar,         name='disparar'),
    path('descartar/',        views.descartar,        name='descartar'),
    path('baixar-sem-email/', views.baixar_sem_email, name='baixar_sem_email'),
    path('reenviar/',         views.reenviar,         name='reenviar'),
    # Robô
    path('sincronizar/',   views.executar_scraper_view, name='sincronizar'),
    path('robo/toggle/',   views.toggle_robo,           name='toggle_robo'),
    path('robo/status/',   views.status_robo,           name='status_robo'),
    # Tempo real
    path('recs/recentes/', views.recs_recentes, name='recs_recentes'),
]
"""
urls.py

Roteamento interno do painel da automação Embratel.
As URLs relativas aqui definidas herdam o prefixo inserido no arquivo principal do projeto.
"""

from django.urls import path
from . import views

app_name = 'automacao_embratel'

urlpatterns = [
    # ══════════════════════════════════════════════════════════════
    #  ROTAS ESTÁTICAS (Listagens e Ações Globais)
    # ══════════════════════════════════════════════════════════════
    path('', views.listar_recs_embratel, name='lista'),
    path('enviadas/', views.listar_recs_embratel_enviadas, name='enviadas'),
    path('sincronizar/', views.sincronizar_recs_embratel, name='sincronizar'),
    path('execucoes/', views.listar_execucoes_embratel, name='execucoes'),
    path('configuracao/alternar/', views.alternar_configuracao_robo_embratel, name='alternar_configuracao'),

    # ══════════════════════════════════════════════════════════════
    #  ROTAS DINÂMICAS (Tratamento Específico por Tarefa)
    # ══════════════════════════════════════════════════════════════
    path('<int:pk>/detalhes/', views.detalhe_rec_embratel, name='detalhe'),
    path('<int:pk>/enviar/', views.enviar_rec_embratel, name='enviar'),
    path('<int:pk>/reprocessar/', views.reprocessar_rec_embratel, name='reprocessar'),
    path('<int:pk>/marcar-pendente/', views.marcar_pendente_rec_embratel, name='marcar_pendente'),
    path('<int:pk>/ignorar/', views.ignorar_rec_embratel, name='ignorar'),
]
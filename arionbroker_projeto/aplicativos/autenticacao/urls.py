from django.urls import path

from . import views

app_name = 'autenticacao'

urlpatterns = [
    # =========================================================
    # AUTENTICAÇÃO
    # =========================================================
    path(
        'login/',
        views.login_view,
        name='login',
    ),

    path(
        'logout/',
        views.logout_view,
        name='logout',
    ),

    # =========================================================
    # PREFERÊNCIAS DO USUÁRIO
    # =========================================================
    path(
        'preferencias/',
        views.atualizar_preferencias,
        name='preferencias',
    ),

    # =========================================================
    # GESTÃO DE USUÁRIOS — SOMENTE ADMIN
    # =========================================================
    path(
        'usuarios/',
        views.gerenciar_usuarios,
        name='usuarios',
    ),

    path(
        'usuarios/criar/',
        views.criar_usuario,
        name='criar_usuario',
    ),

    path(
        'usuarios/<int:user_id>/toggle/',
        views.toggle_usuario,
        name='toggle_usuario',
    ),

    path(
        'usuarios/<int:user_id>/senha/',
        views.redefinir_senha,
        name='redefinir_senha',
    ),

    path(
        'usuarios/<int:user_id>/cargo/',
        views.alterar_cargo,
        name='alterar_cargo',
    ),
]
# aplicativos/autenticacao/views.py

import json

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .decorators import admin_required
from .models import (
    Cargo,
    UserPreference,
    VisualizacaoCancelamentos,
)


# ── 1. LOGIN ──────────────────────────────────────────────────
def login_view(request):
    if request.user.is_authenticated:
        return redirect('chamados:dashboard_projetos')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        if not username or not password:
            messages.error(
                request,
                'Preencha usuário e senha.',
            )

            return render(
                request,
                'autenticacao/login.html',
            )

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:
            if not user.is_active:
                messages.error(
                    request,
                    (
                        'Esta conta está desativada. '
                        'Fale com o administrador.'
                    ),
                )

                return render(
                    request,
                    'autenticacao/login.html',
                )

            login(
                request,
                user,
            )

            next_url = request.GET.get(
                'next',
                '',
            )

            if (
                next_url
                and url_has_allowed_host_and_scheme(
                    url=next_url,
                    allowed_hosts={
                        request.get_host(),
                    },
                )
            ):
                return redirect(
                    next_url
                )

            return redirect(
                'chamados:dashboard_projetos'
            )

        messages.error(
            request,
            'Usuário ou senha incorretos.',
        )

    return render(
        request,
        'autenticacao/login.html',
    )


# ── 2. LOGOUT ─────────────────────────────────────────────────
def logout_view(request):
    logout(
        request
    )

    return redirect(
        'autenticacao:login'
    )


# ── 3. PREFERÊNCIAS (AJAX) ────────────────────────────────────
@login_required
@require_POST
def atualizar_preferencias(request):
    """
    Salva preferências persistentes do usuário no backend.

    Aceita atualmente:
    - tema
    - sidebar_aberta
    - cancelamentos_visualizar

    "cancelamentos_visualizar" é usado pelo filtro fixo:
    - todos
    - meus
    - sem_responsavel

    A preferência permanece entre:
    - troca de filas;
    - troca de páginas;
    - F5;
    - logout/login.
    """
    try:
        dados = json.loads(
            request.body or '{}'
        )

        if not isinstance(
            dados,
            dict,
        ):
            return JsonResponse(
                {
                    'erro': (
                        'O corpo da requisição deve '
                        'ser um objeto JSON.'
                    ),
                },
                status=400,
            )

        prefs, _ = (
            UserPreference.objects.get_or_create(
                user=request.user
            )
        )

        campos_atualizados = []

        # ------------------------------------------------------
        # Tema
        # ------------------------------------------------------
        if 'tema' in dados:
            tema = str(
                dados.get('tema') or ''
            ).strip().lower()

            if tema not in {
                'dark',
                'light',
            }:
                return JsonResponse(
                    {
                        'erro': 'Tema inválido.',
                    },
                    status=400,
                )

            prefs.tema = tema
            campos_atualizados.append(
                'tema'
            )

        # ------------------------------------------------------
        # Sidebar
        # ------------------------------------------------------
        if 'sidebar_aberta' in dados:
            sidebar_aberta = dados.get(
                'sidebar_aberta'
            )

            if not isinstance(
                sidebar_aberta,
                bool,
            ):
                return JsonResponse(
                    {
                        'erro': (
                            'sidebar_aberta deve '
                            'ser verdadeiro ou falso.'
                        ),
                    },
                    status=400,
                )

            prefs.sidebar_aberta = (
                sidebar_aberta
            )

            campos_atualizados.append(
                'sidebar_aberta'
            )

        # ------------------------------------------------------
        # Cancelamentos — Visualizar
        # ------------------------------------------------------
        if 'cancelamentos_visualizar' in dados:
            visualizar = str(
                dados.get(
                    'cancelamentos_visualizar'
                )
                or ''
            ).strip()

            valores_validos = {
                valor
                for valor, _label
                in VisualizacaoCancelamentos.choices
            }

            if visualizar not in valores_validos:
                return JsonResponse(
                    {
                        'erro': (
                            'Visualização de '
                            'Cancelamentos inválida.'
                        ),
                        'valores_validos': sorted(
                            valores_validos
                        ),
                    },
                    status=400,
                )

            prefs.cancelamentos_visualizar = (
                visualizar
            )

            campos_atualizados.append(
                'cancelamentos_visualizar'
            )

        if campos_atualizados:
            # updated_at não existe no model, então salvamos
            # somente os campos efetivamente alterados.
            prefs.save(
                update_fields=list(
                    dict.fromkeys(
                        campos_atualizados
                    )
                )
            )

        return JsonResponse(
            {
                'status': 'sucesso',
                'preferencias': {
                    'tema': (
                        prefs.tema
                    ),
                    'sidebar_aberta': (
                        prefs.sidebar_aberta
                    ),
                    'cancelamentos_visualizar': (
                        prefs.cancelamentos_visualizar
                    ),
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {
                'erro': (
                    'JSON inválido na requisição.'
                ),
            },
            status=400,
        )

    except Exception as e:
        return JsonResponse(
            {
                'erro': str(e),
            },
            status=400,
        )


# ── 4. GERENCIAR USUÁRIOS ─────────────────────────────────────
@login_required
@admin_required
def gerenciar_usuarios(request):
    usuarios = (
        User.objects
        .select_related(
            'preferencias'
        )
        .order_by(
            'username'
        )
    )

    context = {
        'page_title': 'Gerenciar Usuários',
        'usuarios': usuarios,
        'cargos': Cargo.choices,
    }

    return render(
        request,
        'autenticacao/gerenciar_usuarios.html',
        context,
    )


# ── 5. CRIAR USUÁRIO ──────────────────────────────────────────
@login_required
@admin_required
@require_POST
@csrf_protect
def criar_usuario(request):
    username = request.POST.get(
        'username',
        '',
    ).strip()

    password = request.POST.get(
        'password',
        '',
    ).strip()

    nome = request.POST.get(
        'nome',
        '',
    ).strip()

    sobrenome = request.POST.get(
        'sobrenome',
        '',
    ).strip()

    email = request.POST.get(
        'email',
        '',
    ).strip()

    cargo = request.POST.get(
        'cargo',
        Cargo.OPERADOR,
    ).strip()

    if not username or not password:
        messages.error(
            request,
            'Usuário e senha são obrigatórios.',
        )

        return redirect(
            'autenticacao:usuarios'
        )

    if User.objects.filter(
        username=username
    ).exists():
        messages.error(
            request,
            (
                f'O usuário "{username}" '
                'já existe.'
            ),
        )

        return redirect(
            'autenticacao:usuarios'
        )

    cargos_validos = {
        valor
        for valor, _label
        in Cargo.choices
    }

    if cargo not in cargos_validos:
        cargo = Cargo.OPERADOR

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=nome,
        last_name=sobrenome,
        email=email,
    )

    # O signal já cria UserPreference.
    user.preferencias.cargo = cargo

    user.preferencias.save(
        update_fields=[
            'cargo',
        ]
    )

    messages.success(
        request,
        (
            f'Usuário "{username}" criado '
            f'com sucesso como {cargo}.'
        ),
    )

    return redirect(
        'autenticacao:usuarios'
    )


# ── 6. ATIVAR / DESATIVAR USUÁRIO ─────────────────────────────
@login_required
@admin_required
@require_POST
@csrf_protect
def toggle_usuario(
    request,
    user_id,
):
    alvo = get_object_or_404(
        User,
        pk=user_id,
    )

    if alvo == request.user:
        return JsonResponse(
            {
                'erro': (
                    'Você não pode desativar '
                    'sua própria conta.'
                ),
            },
            status=400,
        )

    alvo.is_active = (
        not alvo.is_active
    )

    alvo.save(
        update_fields=[
            'is_active',
        ]
    )

    estado = (
        'ativado'
        if alvo.is_active
        else 'desativado'
    )

    return JsonResponse(
        {
            'ativo': alvo.is_active,
            'mensagem': (
                f'Usuário "{alvo.username}" '
                f'{estado}.'
            ),
        }
    )


# ── 7. REDEFINIR SENHA ────────────────────────────────────────
@login_required
@admin_required
@require_POST
@csrf_protect
def redefinir_senha(
    request,
    user_id,
):
    alvo = get_object_or_404(
        User,
        pk=user_id,
    )

    nova_senha = request.POST.get(
        'nova_senha',
        '',
    ).strip()

    if (
        not nova_senha
        or len(nova_senha) < 6
    ):
        messages.error(
            request,
            (
                'A senha deve ter pelo '
                'menos 6 caracteres.'
            ),
        )

        return redirect(
            'autenticacao:usuarios'
        )

    alvo.set_password(
        nova_senha
    )

    alvo.save()

    messages.success(
        request,
        (
            f'Senha de "{alvo.username}" '
            'redefinida com sucesso.'
        ),
    )

    return redirect(
        'autenticacao:usuarios'
    )


# ── 8. ALTERAR CARGO ──────────────────────────────────────────
@login_required
@admin_required
@require_POST
@csrf_protect
def alterar_cargo(
    request,
    user_id,
):
    alvo = get_object_or_404(
        User,
        pk=user_id,
    )

    cargo = request.POST.get(
        'cargo',
        '',
    ).strip()

    if alvo == request.user:
        return JsonResponse(
            {
                'erro': (
                    'Você não pode alterar '
                    'seu próprio cargo.'
                ),
            },
            status=400,
        )

    cargos_validos = {
        valor
        for valor, _label
        in Cargo.choices
    }

    if cargo not in cargos_validos:
        return JsonResponse(
            {
                'erro': 'Cargo inválido.',
            },
            status=400,
        )

    prefs, _ = (
        UserPreference.objects.get_or_create(
            user=alvo
        )
    )

    prefs.cargo = cargo

    prefs.save(
        update_fields=[
            'cargo',
        ]
    )

    return JsonResponse(
        {
            'cargo': cargo,
            'mensagem': (
                f'Cargo de "{alvo.username}" '
                f'alterado para {cargo}.'
            ),
        }
    )

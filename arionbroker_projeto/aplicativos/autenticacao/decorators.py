from functools import wraps
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages


def admin_required(view_func):
    """
    Bloqueia operadores de acessar views restritas a administradores.
    Redireciona com mensagem de erro para requisições normais.
    Retorna 403 JSON para requisições AJAX.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('autenticacao:login')

        try:
            is_admin = request.user.preferencias.is_admin
        except Exception:
            is_admin = False

        if not is_admin:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
               request.content_type == 'application/json':
                return JsonResponse(
                    {'erro': 'Acesso restrito a administradores.'},
                    status=403
                )
            messages.error(request, 'Você não tem permissão para acessar esta área.')
            return redirect('painel:dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper
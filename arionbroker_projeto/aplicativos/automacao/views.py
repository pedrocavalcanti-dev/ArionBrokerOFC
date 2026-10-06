import traceback
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from .scraper import executar_scraper

LOGIN_URL = 'autenticacao:login'


@login_required(login_url=LOGIN_URL)
@require_POST
def sincronizar(request):
    """
    Trigger manual do scraper.
    Chamado pelo botão "Sincronizar Portal" no dashboard.
    """
    try:
        resultado = executar_scraper()

        return JsonResponse({
            'mensagem': f"{resultado['novas']} REC(s) nova(s) capturada(s).",
            'novas': resultado['novas'],
            'ignoradas': resultado['ignoradas'],
            'erros': resultado['erros'],
        })

    except Exception as e:
        print("\n" + "=" * 50)
        print("🚨 ERRO CRÍTICO AO RODAR O SCRAPER 🚨")
        traceback.print_exc()
        print("=" * 50 + "\n")

        return JsonResponse(
            {'erro': f'Falha na sincronização: {str(e)}'},
            status=500
        )
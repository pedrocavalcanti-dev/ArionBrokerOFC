"""
ARION PROJETOS — BROKER
aplicativos/automacao/claro_registro.py

Registra o ticket OTRS no portal da Claro via API REST.
O Login é feito simulando o navegador real (Playwright)
para driblar o Firewall/WAF da Claro.
"""

import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from decouple import config
from django.utils import timezone
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

from aplicativos.core_broker.models import TicketREC

logger = logging.getLogger(__name__)

URL_LOGIN  = "https://nocclaro.com.br/pbroker/#/login"
API_LOGIN  = "https://nocclaro.com.br/Webservice/pbrokerApi/api/login"
API_EDIT   = 'https://nocclaro.com.br/Webservice/pbrokerApi/api/tickets/edit/'
API_GET    = 'https://nocclaro.com.br/Webservice/pbrokerApi/api/tickets/'
API_LOGOUT = 'https://nocclaro.com.br/Webservice/pbrokerApi/api/logout'

USUARIO      = config('SCRAPER_USUARIO')
SENHA        = config('SCRAPER_SENHA')
EMPRESA      = 'ARION'
EMPRESA_NOME = 'ARION - SIMÉTRICO'


# ── SESSÃO HTTP COM RETRY AUTOMÁTICO ──────────────────────────
# Reutilizar uma única Session (em vez de requests.get/post soltos) mantém
# conexões TCP/TLS vivas (menos handshakes = menos chance de erro SSL
# intermitente) e permite configurar retry automático para falhas
# transitórias de rede (timeout, conexão resetada, 5xx, etc).
def _criar_sessao() -> requests.Session:
    sessao = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,          # espera 1.5s, 3s, 6s entre tentativas
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sessao.mount("https://", adapter)
    sessao.mount("http://", adapter)
    return sessao


_SESSAO = _criar_sessao()


# ── HEADERS COM DISFARCE ──────────────────────────────────────
def _headers(token: str) -> dict:
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Origin': 'https://nocclaro.com.br',
        'Referer': 'https://nocclaro.com.br/pbroker/#/',
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/123.0.0.0 Safari/537.36'
        ),
    }


# ── LÓGICA DE LOGIN COM PLAYWRIGHT ────────────────────────────
def _is_login_response(response) -> bool:
    try:
        return (
            response.request.method.upper() == "POST"
            and response.url.rstrip("/") == API_LOGIN.rstrip("/")
        )
    except Exception:
        return False

def _extrair_token_do_json(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("token"):
        return str(payload["token"]).strip()
    data = payload.get("data")
    if isinstance(data, dict):
        if data.get("token"):
            return str(data["token"]).strip()
        if data.get("access_token"):
            return str(data["access_token"]).strip()
    if payload.get("access_token"):
        return str(payload["access_token"]).strip()
    return None

def _fazer_login_playwright(page: Page) -> str:
    logger.info("[CLARO-REG] Acessando portal da Claro para obter o token de inserção...")
    page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(1_500)

    page.locator('input[type="email"], input[name="email"], input[type="text"]').first.fill(USUARIO)
    page.locator('input[type="password"]').first.fill(SENHA)

    with page.expect_response(_is_login_response, timeout=30_000) as login_info:
        page.locator(
            'button[type="submit"], button:has-text("Entrar"), button:has-text("Login")'
        ).first.click()

    login_response = login_info.value

    if login_response.status != 200:
        raise RuntimeError(f"[CLARO-REG] Login via Playwright retornou status {login_response.status}.")

    try:
        payload = login_response.json()
    except Exception:
        raise ValueError("[CLARO-REG] Resposta do login não é JSON válido.")

    token = _extrair_token_do_json(payload)
    if not token:
        raise ValueError("[CLARO-REG] Login 200 OK, mas token não encontrado.")

    logger.info("[CLARO-REG] Login OK. Token capturado via Playwright.")
    return token


# ── LOGOUT E CONSULTAS ────────────────────────────────────────
def _logout(token: str) -> None:
    try:
        _SESSAO.post(API_LOGOUT, headers=_headers(token), timeout=10)
    except Exception:
        pass

def _buscar_dados_rec_api(token: str, num_recup: str) -> dict | None:
    try:
        url = f'{API_GET}{num_recup}'
        resp = _SESSAO.get(url, headers=_headers(token), timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return data.get('data', data)
    except requests.exceptions.SSLError as e:
        logger.error(
            '[CLARO-REG] Falha de certificado SSL ao buscar REC %s. '
            'Verifique se o pip-system-certs está instalado e ativo no venv '
            '(pip install pip-system-certs) ou se há inspeção SSL de '
            'antivírus/firewall interceptando a conexão. Detalhe: %s',
            num_recup, e,
        )
    except Exception as e:
        logger.warning('[CLARO-REG] Erro ao buscar REC %s na API: %s', num_recup, e)
    return None


# ── MONTA PAYLOAD (CORRIGIDO PARA EVITAR ERRO 422) ────────────
def _montar_payload(rec: TicketREC, ticket_otrs: str, dados_api: dict | None) -> dict:
    observacao = f'Em atendimento | Ticket: {ticket_otrs}'

    # 1. Define uma Data de Abertura segura (Fallback para não dar erro 422)
    data_abertura_str = ''
    if dados_api and dados_api.get('data_abertura'):
        data_abertura_str = dados_api.get('data_abertura')
    elif rec.data_abertura_portal:
        data_abertura_str = rec.data_abertura_portal.strftime('%Y-%m-%d %H:%M:%S')
    else:
        data_abertura_str = rec.data_coleta.strftime('%Y-%m-%d %H:%M:%S')

    # 2. Define a Data Retroativa/Registro segura
    data_registro_str = ''
    if dados_api and dados_api.get('dh_registro_operadora'):
        data_registro_str = dados_api.get('dh_registro_operadora')
    elif rec.data_registro_operadora:
        data_registro_str = rec.data_registro_operadora.strftime('%Y-%m-%d %H:%M')
    else:
        data_registro_str = timezone.now().strftime('%Y-%m-%d %H:%M')

    # 3. Valor do item/iten rec. A API da Claro exige os DOIS campos no
    # payload ao mesmo tempo, com o mesmo valor: 'item_rec' (nome correto)
    # e 'iten_rec' (typo legado que ficou hardcoded no back-end deles).
    # Confirmado inspecionando uma edição manual bem-sucedida no portal
    # (DevTools → Network → payload de tickets/edit/), onde os dois vieram
    # juntos: item_rec: 3, iten_rec: 3. Mandar só um dos dois gera o erro
    # 422 "The iten rec field is required."
    valor_item_rec = 1
    if dados_api:
        valor_item_rec = dados_api.get('item_rec', dados_api.get('iten_rec', 1))

    payload = {
        'num_recup':             str(rec.rec_id),
        'chamado_operadora':     ticket_otrs,
        'pu':                    ticket_otrs,
        'observacoes':           observacao,
        'empresa':               EMPRESA,
        'empresa_nome':          EMPRESA_NOME,
        'id_broker':             '',
        'operadora_broker_nome': '',
        'dh_previsao':           '',
        'item_rec':              valor_item_rec,
        'iten_rec':              valor_item_rec,  # OBRIGATÓRIO junto com item_rec — ver nota acima
        'lp':                    rec.bl_dados or '',
        'desig':                 rec.designacao_claro or '',
        'razao_social':          rec.cliente or '',
        'operador':              'Arion Broker',
        'data_abertura':         data_abertura_str,
        'data_retroativa':       '',
        'dh_registro_operadora': data_registro_str,
        'cf_tm':                 '',
    }

    if dados_api:
        payload.update({
            'cf_tm':    dados_api.get('cf_tm', ''),
            'operador': dados_api.get('operador', 'Arion Broker'),
        })

    return payload


# ── REGISTRA UMA REC ──────────────────────────────────────────
def _registrar_uma_rec(token: str, rec: TicketREC, ticket_otrs: str) -> bool:
    num_recup = str(rec.rec_id)
    dados_api = _buscar_dados_rec_api(token, num_recup)
    payload = _montar_payload(rec, ticket_otrs, dados_api)

    logger.info('[CLARO-REG] POST edit -> REC %s | ticket %s', num_recup, ticket_otrs)

    try:
        resp = _SESSAO.post(
            API_EDIT,
            json=payload,
            headers=_headers(token),
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                logger.info('[CLARO-REG] [OK] REC %s registrada com ticket %s.', num_recup, ticket_otrs)
                return True
            logger.error('[CLARO-REG] success=false para REC %s: %s', num_recup, data)
        else:
            logger.error('[CLARO-REG] HTTP %s ao editar REC %s: %s', resp.status_code, num_recup, resp.text[:300])
    except requests.exceptions.SSLError as e:
        logger.error(
            '[CLARO-REG] Falha de certificado SSL ao registrar REC %s. '
            'Verifique se o pip-system-certs está instalado e ativo no venv '
            '(pip install pip-system-certs) ou se há inspeção SSL de '
            'antivírus/firewall interceptando a conexão. Detalhe: %s',
            num_recup, e,
        )
    except requests.exceptions.RequestException as e:
        logger.error('[CLARO-REG] Erro de rede ao editar REC %s: %s', num_recup, e, exc_info=True)
    except Exception as e:
        logger.error('[CLARO-REG] Exceção ao editar REC %s: %s', num_recup, e, exc_info=True)

    return False


# ── ENTRADA PRINCIPAL ─────────────────────────────────────────
def registrar_tickets_no_claro(tickets_encontrados: dict) -> dict:
    if not tickets_encontrados:
        return {}

    resultados = {}
    token = None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 900},
                locale="pt-BR",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            try:
                token = _fazer_login_playwright(page)
            finally:
                browser.close()

        if token:
            recs = {str(r.rec_id): r for r in TicketREC.objects.filter(rec_id__in=list(tickets_encontrados.keys()))}

            for rec_id, ticket_otrs in tickets_encontrados.items():
                rec = recs.get(rec_id)
                if rec:
                    resultados[rec_id] = _registrar_uma_rec(token, rec, ticket_otrs)
                else:
                    resultados[rec_id] = False

    except Exception as e:
        logger.error('[CLARO-REG] Erro critico no registro: %s', e, exc_info=True)
        for rec_id in tickets_encontrados:
            resultados.setdefault(rec_id, False)

    finally:
        if token:
            _logout(token)

    return resultados
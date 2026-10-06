"""
diagnostico_embratel.py

Script de DIAGNÓSTICO da autenticação no portal Modos Web (Embratel).
Fase 2 do roadmap — NÃO toca no banco, NÃO envia e-mail, NÃO salva nada.

Objetivo:
  1. Tentar login via requests puro (Estratégia A).
  2. Se falhar, cair para Playwright híbrido (Estratégia B), capturando
     a resposta real da API de login pelo listener de rede.
  3. Selecionar o módulo Recuperação.
  4. Validar a sessão (endpoint /me ou equivalente, se existir).
  5. Imprimir no console ONDE está o token, quais headers/cookies são
     obrigatórios — SEM nunca imprimir a senha ou o token completo.

Uso:
    python diagnostico_embratel.py

Variáveis de ambiente esperadas (.env):
    EMBRATEL_URL_BASE=https://modosweb.embratel.net.br
    EMBRATEL_API_BASE=https://modosweb.embratel.net.br/backend/api
    EMBRATEL_URL_LOGIN=https://modosweb.embratel.net.br/login
    EMBRATEL_USUARIO=...
    EMBRATEL_SENHA=...
    EMBRATEL_HEADLESS=true
    EMBRATEL_TIMEOUT=30

Este script é standalone (não depende do Django) para ser executado
isoladamente durante o mapeamento. Depois que tudo estiver confirmado,
a lógica validada aqui será portada para aplicativos/automacao_embratel/autenticacao.py
"""

import json
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

URL_BASE = os.getenv('EMBRATEL_URL_BASE', 'https://modosweb.embratel.net.br')
API_BASE = os.getenv('EMBRATEL_API_BASE', f'{URL_BASE}/backend/api')
URL_LOGIN_PAGINA = os.getenv('EMBRATEL_URL_LOGIN', f'{URL_BASE}/login')
USUARIO = os.getenv('EMBRATEL_USUARIO')
SENHA = os.getenv('EMBRATEL_SENHA')
HEADLESS = os.getenv('EMBRATEL_HEADLESS', 'true').strip().lower() == 'true'
TIMEOUT = int(os.getenv('EMBRATEL_TIMEOUT', '30'))

ENDPOINT_LOGIN = f'{API_BASE}/autenticacao/entrar'
ENDPOINT_MODULOS = f'{API_BASE}/ctrl-modulos'


# ══════════════════════════════════════════════════════════════
#  UTILITÁRIOS DE LOG SEGURO
# ══════════════════════════════════════════════════════════════

def log(secao, mensagem):
    agora = datetime.now().strftime('%H:%M:%S')
    print(f'[{agora}] [{secao}] {mensagem}')


def mascarar_token(token):
    if not token:
        return '(vazio)'
    if len(token) <= 12:
        return '****'
    return f'{token[:12]}...****'


def mascarar_cookies(cookies_dict):
    """Mostra apenas os NOMES dos cookies, nunca os valores."""
    if not cookies_dict:
        return '(nenhum)'
    return ', '.join(sorted(cookies_dict.keys()))


def resumir_headers(headers_dict):
    """Mostra os headers de resposta relevantes, sem valores sensíveis."""
    interessantes = [
        'set-cookie', 'authorization', 'content-type',
        'x-csrf-token', 'x-xsrf-token', 'x-auth-token',
    ]
    resumo = {}
    for chave, valor in headers_dict.items():
        if chave.lower() in interessantes:
            if chave.lower() in ('set-cookie', 'authorization', 'x-csrf-token', 'x-xsrf-token', 'x-auth-token'):
                resumo[chave] = mascarar_token(valor)
            else:
                resumo[chave] = valor
    return resumo


# ══════════════════════════════════════════════════════════════
#  ESTRATÉGIA A — REQUESTS PURO
# ══════════════════════════════════════════════════════════════

def tentar_login_requests():
    """
    Tenta autenticar diretamente via requests.Session().
    Retorna (sucesso: bool, session: requests.Session, token: str|None)
    """
    log('EMBRATEL-LOGIN', f'Tentando Estratégia A (requests puro) em {ENDPOINT_LOGIN}')

    if not USUARIO or not SENHA:
        log('EMBRATEL-LOGIN', 'ERRO: EMBRATEL_USUARIO / EMBRATEL_SENHA não definidos no .env')
        return False, None, None

    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; ArionBroker-Diagnostico/1.0)',
    })

    payload = {
        'email': USUARIO,
        'password': SENHA,
        'lembrar': False,
    }

    try:
        resposta = session.post(ENDPOINT_LOGIN, json=payload, timeout=TIMEOUT)
    except requests.exceptions.RequestException as erro:
        log('EMBRATEL-LOGIN', f'Falha de conexão na Estratégia A: {erro}')
        return False, None, None

    log('EMBRATEL-LOGIN', f'Status HTTP: {resposta.status_code}')
    log('EMBRATEL-LOGIN', f'Cookies recebidos: {mascarar_cookies(session.cookies.get_dict())}')
    log('EMBRATEL-LOGIN', f'Headers relevantes: {resumir_headers(resposta.headers)}')

    if resposta.status_code != 200:
        log('EMBRATEL-LOGIN', f'Corpo da resposta (erro): {resposta.text[:500]}')
        return False, None, None

    try:
        corpo = resposta.json()
    except ValueError:
        log('EMBRATEL-LOGIN', 'Resposta não é JSON válido. Corpo bruto (primeiros 500 chars):')
        log('EMBRATEL-LOGIN', resposta.text[:500])
        return False, None, None

    # Tenta localizar o token em chaves comuns
    token = (
        corpo.get('token')
        or corpo.get('access_token')
        or corpo.get('accessToken')
        or (corpo.get('data') or {}).get('token')
        if isinstance(corpo, dict) else None
    )

    log('EMBRATEL-LOGIN', f'Chaves do corpo da resposta: {list(corpo.keys()) if isinstance(corpo, dict) else type(corpo)}')
    log('EMBRATEL-LOGIN', f'Token localizado no corpo: {mascarar_token(token)}')

    if token:
        session.headers.update({'Authorization': f'Bearer {token}'})
        log('EMBRATEL-LOGIN', 'Estratégia A funcionou. Token e cookies capturados.')
        return True, session, token

    if session.cookies.get_dict():
        log('EMBRATEL-LOGIN', 'Sem token explícito no corpo, mas cookies de sessão foram recebidos. '
                               'Pode ser autenticação baseada em cookie/sessão.')
        return True, session, None

    log('EMBRATEL-LOGIN', 'Estratégia A não retornou token nem cookies úteis.')
    return False, None, None


# ══════════════════════════════════════════════════════════════
#  ESTRATÉGIA B — PLAYWRIGHT HÍBRIDO
# ══════════════════════════════════════════════════════════════

def tentar_login_playwright():
    """
    Faz login visualmente com Playwright e intercepta a resposta real
    da API de login pelo listener de rede, para depois continuar via requests.
    Retorna (sucesso: bool, session: requests.Session, token: str|None)
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log('EMBRATEL-LOGIN', 'ERRO: playwright não instalado. Rode: pip install playwright && playwright install')
        return False, None, None

    log('EMBRATEL-LOGIN', f'Tentando Estratégia B (Playwright híbrido) em {URL_LOGIN_PAGINA}')

    if not USUARIO or not SENHA:
        log('EMBRATEL-LOGIN', 'ERRO: EMBRATEL_USUARIO / EMBRATEL_SENHA não definidos no .env')
        return False, None, None

    capturado = {'status': None, 'corpo': None, 'headers': None}

    def ao_receber_resposta(resposta):
        if 'autenticacao/entrar' in resposta.url or 'login' in resposta.url.lower():
            try:
                capturado['status'] = resposta.status
                capturado['headers'] = dict(resposta.headers)
                try:
                    capturado['corpo'] = resposta.json()
                except Exception:
                    capturado['corpo'] = resposta.text()
            except Exception as erro:
                log('EMBRATEL-LOGIN', f'Não foi possível ler a resposta interceptada: {erro}')

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=HEADLESS)
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        pagina.on('response', ao_receber_resposta)

        try:
            log('EMBRATEL-LOGIN', f'Abrindo {URL_LOGIN_PAGINA}')
            pagina.goto(URL_LOGIN_PAGINA, timeout=TIMEOUT * 1000)

            # ATENÇÃO: seletores abaixo são um PONTO DE PARTIDA.
            # Ajuste conforme o HTML real do formulário de login do Modos Web.
            log('EMBRATEL-LOGIN', 'Preenchendo credenciais (seletores genéricos — ajustar se necessário)')
            pagina.fill('input[type="email"], input[name="email"], #email', USUARIO)
            pagina.fill('input[type="password"], input[name="password"], #password', SENHA)
            pagina.click('button[type="submit"]')

            pagina.wait_for_timeout(4000)  # aguarda a resposta da API ser capturada pelo listener

        except Exception as erro:
            log('EMBRATEL-LOGIN', f'ERRO durante navegação/preenchimento: {erro}')
            log('EMBRATEL-LOGIN', 'Verifique se os seletores do formulário correspondem ao HTML real do portal.')
            navegador.close()
            return False, None, None

        cookies_playwright = contexto.cookies()
        navegador.close()

    log('EMBRATEL-LOGIN', f'Status capturado da API de login: {capturado["status"]}')
    if isinstance(capturado['corpo'], dict):
        log('EMBRATEL-LOGIN', f'Chaves do corpo capturado: {list(capturado["corpo"].keys())}')
    else:
        log('EMBRATEL-LOGIN', f'Corpo capturado (não-JSON, truncado): {str(capturado["corpo"])[:300]}')

    token = None
    if isinstance(capturado['corpo'], dict):
        token = (
            capturado['corpo'].get('token')
            or capturado['corpo'].get('access_token')
            or capturado['corpo'].get('accessToken')
            or (capturado['corpo'].get('data') or {}).get('token')
        )

    log('EMBRATEL-LOGIN', f'Token localizado via Playwright: {mascarar_token(token)}')

    nomes_cookies = [c['name'] for c in cookies_playwright]
    log('EMBRATEL-LOGIN', f'Cookies capturados do navegador: {", ".join(nomes_cookies) if nomes_cookies else "(nenhum)"}')

    if not token and not cookies_playwright:
        log('EMBRATEL-LOGIN', 'Estratégia B não conseguiu capturar token nem cookies.')
        return False, None, None

    # Reconstrói uma sessão requests com os cookies capturados pelo navegador
    session = requests.Session()
    for cookie in cookies_playwright:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))

    session.headers.update({
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; ArionBroker-Diagnostico/1.0)',
    })
    if token:
        session.headers.update({'Authorization': f'Bearer {token}'})

    log('EMBRATEL-LOGIN', 'Estratégia B concluída. Sessão requests reconstruída com cookies/token do navegador.')
    return True, session, token


# ══════════════════════════════════════════════════════════════
#  VALIDAÇÃO PÓS-LOGIN
# ══════════════════════════════════════════════════════════════

def consultar_modulos(session):
    log('EMBRATEL-API', f'Consultando módulos em {ENDPOINT_MODULOS}')
    try:
        resposta = session.get(ENDPOINT_MODULOS, timeout=TIMEOUT)
    except requests.exceptions.RequestException as erro:
        log('EMBRATEL-API', f'Falha de conexão ao consultar módulos: {erro}')
        return None

    log('EMBRATEL-API', f'Status HTTP: {resposta.status_code}')

    if resposta.status_code != 200:
        log('EMBRATEL-API', f'Corpo da resposta (erro, truncado): {resposta.text[:500]}')
        return None

    try:
        corpo = resposta.json()
    except ValueError:
        log('EMBRATEL-API', 'Resposta de módulos não é JSON válido.')
        return None

    log('EMBRATEL-API', f'Módulos retornados (bruto, truncado): {json.dumps(corpo, ensure_ascii=False)[:800]}')

    # Tenta localizar o módulo "Recuperação" automaticamente
    lista = corpo if isinstance(corpo, list) else corpo.get('data', []) if isinstance(corpo, dict) else []
    for modulo in lista:
        if isinstance(modulo, dict):
            nome = str(modulo.get('nome') or modulo.get('name') or '').lower()
            if 'recuper' in nome:
                log('EMBRATEL-API', f'Módulo "Recuperação" encontrado: {modulo}')

    return corpo


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print('=' * 70)
    print(' DIAGNÓSTICO DE AUTENTICAÇÃO — MODOS WEB / EMBRATEL')
    print(' Fase 2 do roadmap — NÃO toca no banco, NÃO envia e-mail')
    print('=' * 70)

    sucesso, session, token = tentar_login_requests()

    if not sucesso:
        log('EMBRATEL-LOGIN', 'Estratégia A falhou ou foi inconclusiva. Caindo para Estratégia B (Playwright).')
        sucesso, session, token = tentar_login_playwright()

    if not sucesso:
        log('EMBRATEL-LOGIN', 'FALHA TOTAL: nenhuma das duas estratégias conseguiu autenticar.')
        sys.exit(1)

    log('EMBRATEL-LOGIN', 'Login confirmado. Prosseguindo para validação de módulos.')
    consultar_modulos(session)

    print('=' * 70)
    print(' DIAGNÓSTICO CONCLUÍDO')
    print(' Revise os logs acima para confirmar:')
    print('   - onde está o token (corpo JSON vs cookie)')
    print('   - quais cookies são obrigatórios')
    print('   - o formato real da resposta de módulos')
    print(' Esses achados serão portados para autenticacao.py')
    print('=' * 70)


if __name__ == '__main__':
    main()
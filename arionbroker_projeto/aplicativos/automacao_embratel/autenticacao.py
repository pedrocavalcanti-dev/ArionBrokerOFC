"""
autenticacao.py

Responsável exclusivamente pelo processo de autenticação no Modos Web.

Funções principais:
  - realizar_login(usuario, senha) → (sucesso, token, session)
  - selecionar_modulo_recuperacao(session, token) → bool
  - verificar_token(session, token) → bool
  - renovar_sessao(session, token) → (sucesso, novo_token, session)
  - realizar_logout(session, token) → bool

Dados validados pelo diagnóstico:
  - Token retorna em: response.json()['data']['token']
  - Header obrigatório: Authorization: Bearer <token>
  - X-Provedor-Id e Origin inseridos em todas requisições
  - Referer dinâmico
"""

import os
from typing import Tuple, Optional
import requests
from dotenv import load_dotenv

from . import logs

load_dotenv()

# ══════════════════════════════════════════════════════════════
#  VARIÁVEIS DE AMBIENTE
# ══════════════════════════════════════════════════════════════

URL_BASE = os.getenv('EMBRATEL_URL_BASE', 'https://modosweb.embratel.net.br')
API_BASE = os.getenv('EMBRATEL_API_BASE', f'{URL_BASE}/backend/api')
TIMEOUT = int(os.getenv('EMBRATEL_TIMEOUT', '30'))

MODULO_ID = int(os.getenv('EMBRATEL_MODULO_ID', '1'))
PROVEDOR_ID = int(os.getenv('EMBRATEL_PROVEDOR_ID', '8'))

ENDPOINT_LOGIN = f'{API_BASE}/autenticacao/entrar'
ENDPOINT_MODULO_SELECIONAR = f'{API_BASE}/ctrl-modulos/{{modulo_id}}/selecionar'
ENDPOINT_VALIDACAO = f'{API_BASE}/ctrl-modulos'  # Usado no lugar de /me por segurança
ENDPOINT_LOGOUT = f'{API_BASE}/autenticacao/sair'


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _headers_padrao(token: str = None, referer: str = None) -> dict:
    """
    Retorna headers padrão para todas as requisições.
    
    Se token for fornecido, adiciona Authorization: Bearer <token>
    Se referer for fornecido, adiciona na requisição.
    """
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (compatible; ArionBroker-Automacao/1.0)',
        'X-Provedor-Id': str(PROVEDOR_ID),
        'Origin': URL_BASE,
    }
    
    if token:
        headers['Authorization'] = f'Bearer {token}'
    
    if referer:
        headers['Referer'] = referer
        
    return headers


def _criar_sessao() -> requests.Session:
    """Cria uma nova Session com timeout global."""
    session = requests.Session()
    session.timeout = TIMEOUT
    return session


def _falhar_login(session: requests.Session) -> Tuple[bool, None, None]:
    """Helper para garantir fechamento da sessão em caso de erro."""
    if session:
        session.close()
    return False, None, None


def _extrair_token(resposta_dict: dict) -> Optional[str]:
    """
    Extrai token da resposta de login.
    Baseado no diagnóstico: token fica em response['data']['token']
    """
    if not isinstance(resposta_dict, dict):
        return None
    
    # Tenta a chave 'data' primeiro (formato confirmado pelo diagnóstico)
    data = resposta_dict.get('data')
    if isinstance(data, dict):
        token = data.get('token')
        if token:
            return token
    
    # Fallback para outras chaves possíveis
    token = (
        resposta_dict.get('token')
        or resposta_dict.get('access_token')
        or resposta_dict.get('accessToken')
    )
    
    return token


# ══════════════════════════════════════════════════════════════
#  OPERAÇÃO 1 — REALIZAR LOGIN
# ══════════════════════════════════════════════════════════════

def realizar_login(usuario: str, senha: str) -> Tuple[bool, Optional[str], Optional[requests.Session]]:
    """
    Realiza login no Modos Web via POST /autenticacao/entrar
    
    Args:
        usuario: E-mail ou usuário registrado no portal
        senha: Senha da conta
    
    Returns:
        (sucesso: bool, token: str|None, session: Session|None)
    """
    
    if not usuario or not senha:
        logs.erro('EMBRATEL-LOGIN', 'Usuário ou senha não fornecidos')
        return False, None, None
    
    logs.info('EMBRATEL-LOGIN', f'Tentando realizar login para {usuario}...')
    
    session = _criar_sessao()
    # Adicionando o Referer específico do login
    session.headers.update(_headers_padrao(referer=f'{URL_BASE}/login'))
    
    payload = {
        'email': usuario,
        'password': senha,
        'lembrar': False,
    }
    
    try:
        resposta = session.post(ENDPOINT_LOGIN, json=payload, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        logs.registrar_timeout(ENDPOINT_LOGIN)
        return _falhar_login(session)
    except requests.exceptions.RequestException as erro:
        logs.erro('EMBRATEL-LOGIN', f'Falha de conexão: {erro}', erro)
        return _falhar_login(session)
    
    # Registra detalhes da resposta (para debug)
    logs.debug(
        'EMBRATEL-LOGIN',
        f'Status HTTP: {resposta.status_code} | '
        f'Headers: {logs.mascarar_headers(resposta.headers)}'
    )
    
    # Valida status HTTP
    if resposta.status_code != 200:
        logs.erro(
            'EMBRATEL-LOGIN',
            f'Login rejeitado (status {resposta.status_code}). '
            f'Verifique usuário/senha.'
        )
        logs.debug('EMBRATEL-LOGIN', f'Resposta: {resposta.text[:300]}')
        return _falhar_login(session)
    
    # Tenta parsear JSON
    try:
        corpo = resposta.json()
    except ValueError:
        logs.erro('EMBRATEL-LOGIN', 'Resposta não é JSON válido')
        logs.debug('EMBRATEL-LOGIN', f'Resposta: {resposta.text[:300]}')
        return _falhar_login(session)
    
    # Extrai token
    token = _extrair_token(corpo)
    
    if not token:
        logs.erro(
            'EMBRATEL-LOGIN',
            'Token não encontrado na resposta (chaves presentes: '
            f'{list(corpo.keys())})'
        )
        return _falhar_login(session)
    
    # Sucesso!
    logs.registrar_login_sucesso(usuario)
    logs.registrar_token_capturado(logs.mascarar_token(token))
    
    # Atualiza headers da session com o token e muda o Referer para as próximas chamadas
    referer_interno = f'{URL_BASE}/workflow/ctrl-workflow-recuperacao'
    session.headers.update(_headers_padrao(token=token, referer=referer_interno))
    
    return True, token, session


# ══════════════════════════════════════════════════════════════
#  OPERAÇÃO 2 — SELECIONAR MÓDULO RECUPERAÇÃO
# ══════════════════════════════════════════════════════════════

def selecionar_modulo_recuperacao(
    session: requests.Session,
    token: str,
) -> bool:
    """
    Seleciona o módulo de Recuperação parametrizado no portal.
    """
    if not session or not token:
        logs.erro('EMBRATEL-LOGIN', 'Session ou token não fornecidos')
        return False
    
    modulo_id = MODULO_ID
    url = ENDPOINT_MODULO_SELECIONAR.format(modulo_id=modulo_id)
    
    logs.info('EMBRATEL-LOGIN', f'Selecionando módulo (id={modulo_id})...')
    
    try:
        resposta = session.post(url, json={}, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        logs.registrar_timeout(url)
        return False
    except requests.exceptions.RequestException as erro:
        logs.erro('EMBRATEL-LOGIN', f'Falha ao selecionar módulo: {erro}', erro)
        return False
    
    logs.debug('EMBRATEL-LOGIN', f'Status: {resposta.status_code}')
    
    if resposta.status_code not in (200, 201):
        logs.erro(
            'EMBRATEL-LOGIN',
            f'Falha ao selecionar módulo (status {resposta.status_code})'
        )
        logs.debug('EMBRATEL-LOGIN', f'Resposta: {resposta.text[:300]}')
        return False
    
    logs.info('EMBRATEL-LOGIN', 'Módulo selecionado com sucesso')
    
    return True


# ══════════════════════════════════════════════════════════════
#  OPERAÇÃO 3 — VERIFICAR TOKEN (VALIDAR SESSÃO)
# ══════════════════════════════════════════════════════════════

def verificar_token(session: requests.Session, token: str) -> bool:
    """
    Valida se o token ainda é válido consultando o endpoint de módulos.
    Garante que a autenticação ainda está ativa sem depender do /me não confirmado.
    """
    if not session or not token:
        return False
    
    logs.debug('EMBRATEL-LOGIN', 'Verificando validade do token...')
    
    try:
        resposta = session.get(ENDPOINT_VALIDACAO, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        logs.registrar_timeout(ENDPOINT_VALIDACAO)
        return False
    except requests.exceptions.RequestException as erro:
        logs.debug('EMBRATEL-LOGIN', f'Erro ao verificar token: {erro}')
        return False
    
    # 200 = válido, 401/403 = expirado
    if resposta.status_code == 200:
        logs.debug('EMBRATEL-LOGIN', 'Token validado com sucesso')
        return True
    
    if resposta.status_code in (401, 403):
        logs.registrar_sessao_expirada()
        return False
    
    # Outro status (5xx, timeout, etc.)
    logs.debug('EMBRATEL-LOGIN', f'Status desconhecido ao validar token: {resposta.status_code}')
    return False


# ══════════════════════════════════════════════════════════════
#  OPERAÇÃO 4 — RENOVAR SESSÃO
# ══════════════════════════════════════════════════════════════

def renovar_sessao(
    session: requests.Session,
    token: str,
    usuario: str,
    senha: str,
) -> Tuple[bool, Optional[str], Optional[requests.Session]]:
    """
    Renovar a sessão quando o token expirar fazendo um novo login.
    """
    if not verificar_token(session, token):
        logs.registrar_sessao_expirada()
        logs.info('EMBRATEL-LOGIN', 'Realizando novo login para renovar sessão...')
        return realizar_login(usuario, senha)
    
    # Token ainda é válido
    logs.debug('EMBRATEL-LOGIN', 'Token ainda é válido, renovação não necessária')
    return True, token, session


# ══════════════════════════════════════════════════════════════
#  OPERAÇÃO 5 — REALIZAR LOGOUT
# ══════════════════════════════════════════════════════════════

def realizar_logout(session: requests.Session, token: str) -> bool:
    """
    Realiza logout no portal com validação rigorosa de status de resposta.
    """
    if not session or not token:
        logs.debug('EMBRATEL-LOGIN', 'Logout solicitado mas session/token não disponíveis')
        return True  # Sem sessão ativa = logout bem-sucedido
    
    logs.info('EMBRATEL-LOGIN', 'Realizando logout...')
    
    try:
        resposta = session.post(ENDPOINT_LOGOUT, json={}, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        logs.registrar_timeout(ENDPOINT_LOGOUT)
        return True
    except requests.exceptions.RequestException as erro:
        logs.debug('EMBRATEL-LOGIN', f'Erro ao fazer logout: {erro}')
        return True
    
    if resposta.status_code in (200, 204, 401):
        logs.registrar_logout_sucesso()
        return True

    logs.aviso(
        'EMBRATEL-LOGIN',
        f'Logout respondeu com status {resposta.status_code}'
    )
    
    return False


# ══════════════════════════════════════════════════════════════
#  PIPELINE COMPLETO DE AUTENTICAÇÃO
# ══════════════════════════════════════════════════════════════

def autenticar_completo(usuario: str, senha: str) -> Tuple[bool, Optional[str], Optional[requests.Session]]:
    """
    Pipeline completo de autenticação:
    1. Realizar login
    2. Selecionar módulo Recuperação
    3. Verificar token
    """
    
    # Passo 1: Realizar login
    sucesso, token, session = realizar_login(usuario, senha)
    
    if not sucesso:
        return False, None, None
    
    # Passo 2: Selecionar módulo
    if not selecionar_modulo_recuperacao(session, token):
        realizar_logout(session, token)
        session.close()
        return False, None, None
    
    # Passo 3: Verificar token
    if not verificar_token(session, token):
        realizar_logout(session, token)
        session.close()
        return False, None, None
    
    logs.info('EMBRATEL-LOGIN', 'Autenticação completa realizada com sucesso')
    
    return True, token, session
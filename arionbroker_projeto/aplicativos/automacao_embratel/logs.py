"""
logs.py

Funções de log padronizadas para a automação Embratel.
Centraliza formatação, prefixos e mascaramento de dados sensíveis.

Nunca loga:
  - senha completa
  - token completo
  - cookies completos
  - informações sensíveis não truncadas
"""

import logging
from datetime import datetime


# ══════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO DO LOGGER
# ══════════════════════════════════════════════════════════════

# O Django (via settings.py) assumirá o controle de handlers e formatação
logger = logging.getLogger('automacao_embratel')


# ══════════════════════════════════════════════════════════════
#  FUNÇÕES DE MASCARAMENTO
# ══════════════════════════════════════════════════════════════

def mascarar_token(token: str) -> str:
    """
    Retorna token truncado: primeiros 12 chars + ****
    
    Exemplo:
        eyJ0eXAiOiJKV1Q... → eyJ0eXAiOiJK...****
    """
    if not token:
        return '(vazio)'
    
    if len(token) <= 12:
        return '****'
    
    return f'{token[:12]}...****'


def mascarar_senha(senha: str) -> str:
    """
    Retorna senha como ****** (sem mostrar tamanho real).
    """
    if not senha:
        return '(vazio)'
    
    return '****'


def mascarar_cookies(cookies_dict: dict) -> str:
    """
    Mostra apenas os NOMES dos cookies, nunca os valores.
    
    Exemplo:
        {'sessionid': 'abc123', 'token': 'xyz789'} → sessionid, token
    """
    if not cookies_dict:
        return '(nenhum)'
    
    return ', '.join(sorted(cookies_dict.keys()))


def mascarar_headers(headers_dict: dict) -> dict:
    """
    Retorna headers relevantes, mascarando valores sensíveis.
    """
    interessantes = {
        'set-cookie', 'authorization', 'content-type',
        'x-csrf-token', 'x-xsrf-token', 'x-auth-token',
        'x-token', 'x-api-key', 'x-access-token',
    }
    
    sensíveis = {
        'set-cookie', 'authorization', 'x-csrf-token',
        'x-xsrf-token', 'x-auth-token', 'x-token',
        'x-api-key', 'x-access-token',
    }
    
    resumo = {}
    
    for chave, valor in headers_dict.items():
        chave_lower = chave.lower()
        
        if chave_lower not in interessantes:
            continue
        
        if chave_lower in sensíveis:
            resumo[chave] = mascarar_token(valor)
        else:
            resumo[chave] = valor
    
    return resumo


# ══════════════════════════════════════════════════════════════
#  FUNÇÕES DE LOG ESTRUTURADO
# ══════════════════════════════════════════════════════════════

def info(secao: str, mensagem: str):
    """
    Log de informação com prefixo de seção.
    
    Exemplo:
        info('EMBRATEL-LOGIN', 'Login realizado com sucesso')
    """
    logger.info(f'[{secao}] {mensagem}')


def debug(secao: str, mensagem: str):
    """Log de debug com prefixo de seção."""
    logger.debug(f'[{secao}] {mensagem}')


def aviso(secao: str, mensagem: str):
    """Log de aviso com prefixo de seção."""
    logger.warning(f'[{secao}] {mensagem}')


def erro(secao: str, mensagem: str, excecao: Exception = None):
    """
    Log de erro com prefixo de seção.
    
    Se excecao for passada, também registra a stack trace usando exc_info=True.
    """
    if excecao:
        logger.error(f'[{secao}] {mensagem}', exc_info=True)
    else:
        logger.error(f'[{secao}] {mensagem}')


def critico(secao: str, mensagem: str, excecao: Exception = None):
    """
    Log crítico com prefixo de seção.
    
    Indica falha grave que pode impedir continuação.
    """
    if excecao:
        logger.critical(f'[{secao}] {mensagem}', exc_info=True)
    else:
        logger.critical(f'[{secao}] {mensagem}')


# ══════════════════════════════════════════════════════════════
#  FUNÇÕES DE LOG TEMÁTICO
# ══════════════════════════════════════════════════════════════

def registrar_inicio_ciclo(ciclo_numero: int = None):
    """Registra o início de um ciclo de automação."""
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f'Ciclo iniciado em {agora}'
    if ciclo_numero:
        msg = f'[Ciclo #{ciclo_numero}] ' + msg
    info('EMBRATEL-SCHEDULER', msg)


def registrar_fim_ciclo(
    novas: int,
    atualizadas: int,
    ignoradas: int,
    erros: int,
    duracao_segundos: float,
):
    """Registra o resumo final de um ciclo."""
    msg = (
        f'Ciclo concluído | '
        f'Novas: {novas} | '
        f'Atualizadas: {atualizadas} | '
        f'Ignoradas: {ignoradas} | '
        f'Erros: {erros} | '
        f'Duração: {duracao_segundos:.2f}s'
    )
    info('EMBRATEL-SCHEDULER', msg)


def registrar_login_sucesso(usuario_mascarado: str = None):
    """Registra login bem-sucedido."""
    msg = 'Login realizado com sucesso'
    if usuario_mascarado:
        msg += f' (usuário: {usuario_mascarado})'
    info('EMBRATEL-LOGIN', msg)


def registrar_login_falha(motivo: str = None):
    """Registra falha no login."""
    msg = 'Falha ao realizar login'
    if motivo:
        msg += f': {motivo}'
    erro('EMBRATEL-LOGIN', msg)


def registrar_token_capturado(token_mascarado: str):
    """Registra captura de token."""
    info('EMBRATEL-LOGIN', f'Token capturado: {token_mascarado}')


def registrar_sessao_renovada():
    """Registra renovação de sessão."""
    info('EMBRATEL-API', 'Sessão renovada com sucesso')


def registrar_sessao_expirada():
    """Registra detecção de sessão expirada."""
    aviso('EMBRATEL-API', 'Sessão expirada. Nova autenticação será necessária')


def registrar_logout_sucesso():
    """Registra logout bem-sucedido."""
    info('EMBRATEL-LOGIN', 'Logout realizado com sucesso')


def registrar_erro_api(endpoint: str, status_code: int, motivo: str = None):
    """Registra erro de chamada API."""
    msg = f'Erro na API | Endpoint: {endpoint} | Status: {status_code}'
    if motivo:
        msg += f' | Motivo: {motivo}'
    erro('EMBRATEL-API', msg)


def registrar_erro_tarefa(tarefa_id: str, motivo: str):
    """Registra erro ao processar tarefa específica."""
    erro('EMBRATEL-COLETA', f'Erro ao processar tarefa {tarefa_id}: {motivo}')


def registrar_tarefa_coletada(tarefa_id: str, cliente: str = None):
    """Registra coleta bem-sucedida de uma tarefa."""
    msg = f'Tarefa coletada: {tarefa_id}'
    if cliente:
        msg += f' (cliente: {cliente})'
    debug('EMBRATEL-COLETA', msg)


def registrar_email_enviado(tarefa_id: str, destinatarios: str = None):
    """Registra envio bem-sucedido de e-mail (usando -> seguro para Windows/CMD)."""
    msg = f'E-mail enviado para tarefa {tarefa_id}'
    if destinatarios:
        msg += f' -> {destinatarios}'
    info('EMBRATEL-EMAIL', msg)


def registrar_email_falha(tarefa_id: str, motivo: str):
    """Registra falha no envio de e-mail."""
    erro('EMBRATEL-EMAIL', f'Falha ao enviar e-mail da tarefa {tarefa_id}: {motivo}')


def registrar_timeout(endpoint: str = None):
    """Registra timeout em requisição."""
    msg = 'Timeout na requisição'
    if endpoint:
        msg += f' ({endpoint})'
    aviso('EMBRATEL-API', msg)


def registrar_concorrencia_detectada():
    """Registra detecção de ciclo concorrente."""
    aviso('EMBRATEL-SCHEDULER', 'Já existe um ciclo em andamento. Execução ignorada')


# ══════════════════════════════════════════════════════════════
#  CABEÇALHO DE INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════

def exibir_cabecalho_inicio():
    """Exibe cabeçalho padrão ao iniciar o robô."""
    print('=' * 70)
    print(' ARION PROJETOS — AUTOMAÇÃO EMBRATEL')
    print(' Modos Web — Recuperação')
    print('=' * 70)
    info('EMBRATEL-SCHEDULER', 'Robô iniciado')


def exibir_cabecalho_encerramento():
    """Exibe cabeçalho padrão ao encerrar o robô."""
    info('EMBRATEL-SCHEDULER', 'Robô encerrado')
    print('=' * 70)
    print(' Automação Embratel finalizada')
    print('=' * 70)
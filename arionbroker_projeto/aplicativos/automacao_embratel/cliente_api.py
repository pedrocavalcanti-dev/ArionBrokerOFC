"""
cliente_api.py

Classe ClienteApiEmbratel encapsula todas as chamadas HTTP para os
endpoints do Modos Web.

Características:
  - Bearer token nos headers com X-Provedor-Id e Referer
  - Retry automático apenas para métodos seguros (GET, HEAD, OPTIONS)
  - Tratamento de erros com exceções personalizadas (401, 403, 422, etc.)
  - Logs estruturados para cada operação

APIs mapeadas:
  - GET /backend/api/ctrl-modulos
  - POST /backend/api/pco-workflows/{workflow_id}/visualizar
  - GET /backend/api/pco-tarefas/{tarefa_id}/detalhes
  - GET /backend/api/pco-tarefas/{tarefa_id}/historico
  - GET /backend/api/pco-tarefas/{tarefa_id}/subtarefas
"""

import os
import time
from typing import Optional, Dict, List, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

from . import logs

load_dotenv()

# ══════════════════════════════════════════════════════════════
#  EXCEÇÕES CUSTOMIZADAS
# ══════════════════════════════════════════════════════════════

class ErroApiEmbratel(Exception):
    """Exceção base para erros na API da Embratel."""
    pass

class SessaoExpiradaEmbratel(ErroApiEmbratel):
    """Lançada quando a API retorna 401 (Unauthorized)."""
    pass

class AcessoNegadoEmbratel(ErroApiEmbratel):
    """Lançada quando a API retorna 403 (Forbidden)."""
    pass

class ValidacaoApiEmbratel(ErroApiEmbratel):
    """Lançada quando a API retorna 422 (Unprocessable Entity)."""
    pass


# ══════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════

URL_BASE = os.getenv('EMBRATEL_URL_BASE', 'https://modosweb.embratel.net.br')
API_BASE = os.getenv('EMBRATEL_API_BASE', f'{URL_BASE}/backend/api')
TIMEOUT = int(os.getenv('EMBRATEL_TIMEOUT', '30'))
WORKFLOW_VISUALIZACAO_ID = int(os.getenv('EMBRATEL_WORKFLOW_VISUALIZACAO_ID', '8'))
PROVEDOR_ID = int(os.getenv('EMBRATEL_PROVEDOR_ID', '8'))

MAX_RETRIES = 3
TEMPO_ESPERA_RETRY = 2  # segundos


# ══════════════════════════════════════════════════════════════
#  CLASSE PRINCIPAL
# ══════════════════════════════════════════════════════════════

class ClienteApiEmbratel:
    """
    Cliente HTTP para APIs do Modos Web.
    
    Uso típico:
        cliente = ClienteApiEmbratel(token=token, session=session)
        
        # Listar tarefas
        tarefas = cliente.listar_tarefas_recuperacao(page=1, per_page=20)
        
        # Obter detalhes
        detalhes = cliente.buscar_detalhes_tarefa(tarefa_id=123)
        
        # Finalizar
        cliente.fechar()
    """
    
    def __init__(self, token: str, session: requests.Session = None):
        """
        Inicializa o cliente.
        
        Args:
            token: Token Bearer de autenticação
            session: Session reutilizável (opcional; cria nova se não fornecida)
        """
        self.token = token
        self.session = session or requests.Session()
        self._aplicar_retry()
        self._aplicar_headers()
        self._tentativas_atuais = 0
    
    def _aplicar_headers(self):
        """Aplica headers padrão à Session."""
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'User-Agent': (
                'Mozilla/5.0 '
                '(compatible; ArionBroker-Automacao/1.0)'
            ),
            'Authorization': f'Bearer {self.token}',
            'X-Provedor-Id': str(PROVEDOR_ID),
            'Origin': URL_BASE,
            'Referer': f'{URL_BASE}/workflow/ctrl-workflow-recuperacao',
        })
    
    def _aplicar_retry(self):
        """
        Configura retry automático para erros temporários.
        
        Retenta em:
          - 429 (Too Many Requests)
          - 500, 502, 503, 504 (erros de servidor)
        Restringe a métodos seguros (GET, HEAD, OPTIONS) para não
        duplicar ações POST sem intenção.
        """
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=TEMPO_ESPERA_RETRY,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset({
                'GET',
                'HEAD',
                'OPTIONS',
            }),
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    # ══════════════════════════════════════════════════════════════
    #  MÉTODO BASE (WRAPPER PARA REQUISIÇÕES)
    # ══════════════════════════════════════════════════════════════
    
    def _requisicao(
        self,
        metodo: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Executa requisição HTTP com tratamento de erros.
        
        Args:
            metodo: 'GET', 'POST', 'PUT', 'DELETE'
            endpoint: path relativo (ex: '/pco-tarefas/123/detalhes')
            json_data: dados JSON para POST/PUT
            params: query parameters
        
        Returns:
            resposta.json()
        """
        
        url = f'{API_BASE}{endpoint}'
        
        try:
            if metodo == 'GET':
                resposta = self.session.get(url, params=params, timeout=TIMEOUT)
            elif metodo == 'POST':
                resposta = self.session.post(url, json=json_data, params=params, timeout=TIMEOUT)
            elif metodo == 'PUT':
                resposta = self.session.put(url, json=json_data, params=params, timeout=TIMEOUT)
            elif metodo == 'DELETE':
                resposta = self.session.delete(url, params=params, timeout=TIMEOUT)
            else:
                logs.erro('EMBRATEL-API', f'Método HTTP desconhecido: {metodo}')
                raise ErroApiEmbratel(f'Método HTTP desconhecido: {metodo}')
        
        except requests.exceptions.Timeout:
            logs.registrar_timeout(endpoint)
            raise ErroApiEmbratel(f'Timeout na requisição para {endpoint}')
        
        except requests.exceptions.RequestException as erro:
            logs.erro('EMBRATEL-API', f'Erro de conexão em {endpoint}: {erro}', erro)
            raise ErroApiEmbratel(f'Erro de conexão em {endpoint}: {erro}')
        
        # Tratamento por status HTTP
        return self._processar_resposta(resposta, endpoint, metodo)
    
    def _processar_resposta(
        self,
        resposta: requests.Response,
        endpoint: str,
        metodo: str,
    ) -> Optional[Dict]:
        """
        Processa resposta HTTP de acordo com status. Lança exceções se houver erros.
        
        Args:
            resposta: objeto Response
            endpoint: para logging
            metodo: para logging
        
        Returns:
            resposta.json()
        """
        
        # 2xx = sucesso
        if 200 <= resposta.status_code < 300:
            try:
                return resposta.json()
            except ValueError:
                logs.debug(
                    'EMBRATEL-API',
                    f'Resposta 2xx mas não é JSON: {endpoint}'
                )
                return {'_raw': resposta.text}  # Retorna como placeholder
        
        # 401 = token expirado
        if resposta.status_code == 401:
            logs.registrar_sessao_expirada()
            raise SessaoExpiradaEmbratel(f'Sessão expirada em {endpoint}')
        
        # 403 = acesso negado
        if resposta.status_code == 403:
            logs.erro('EMBRATEL-API', f'Acesso negado (403) em {endpoint}')
            raise AcessoNegadoEmbratel(f'Acesso negado em {endpoint}')
        
        # 404 = não encontrado
        if resposta.status_code == 404:
            logs.debug('EMBRATEL-API', f'Recurso não encontrado (404): {endpoint}')
            raise ErroApiEmbratel(f'Recurso não encontrado (404) em {endpoint}')
        
        # 422 = validação (unprocessable entity)
        if resposta.status_code == 422:
            try:
                erro_body = resposta.json()
                mensagem = erro_body.get('message', 'Erro de validação desconhecido')
            except:
                mensagem = resposta.text[:200]
            
            logs.erro('EMBRATEL-API', f'Validação rejeitada (422) em {endpoint}: {mensagem}')
            raise ValidacaoApiEmbratel(f'Validação falhou em {endpoint}: {mensagem}')
        
        # 429 = rate limit (retry automático já tentou, falhou)
        if resposta.status_code == 429:
            logs.aviso('EMBRATEL-API', f'Rate limit atingido (429) em {endpoint}')
            raise ErroApiEmbratel(f'Limite de requisições excedido (429) em {endpoint}')
        
        # 5xx = erro de servidor
        if 500 <= resposta.status_code < 600:
            logs.erro('EMBRATEL-API', f'Erro de servidor ({resposta.status_code}) em {endpoint}')
            raise ErroApiEmbratel(f'Erro interno no servidor da Embratel ({resposta.status_code}) em {endpoint}')
        
        # Outro status desconhecido
        logs.erro(
            'EMBRATEL-API',
            f'Status HTTP inesperado ({resposta.status_code}) em {endpoint}'
        )
        logs.debug('EMBRATEL-API', f'Resposta: {resposta.text[:300]}')
        
        raise ErroApiEmbratel(f'Status HTTP inesperado ({resposta.status_code}) em {endpoint}')
    
    # ══════════════════════════════════════════════════════════════
    #  OPERAÇÕES DE LEITURA
    # ══════════════════════════════════════════════════════════════
    
    def listar_modulos(self) -> Optional[Dict]:
        """
        GET /ctrl-modulos
        
        Retorna:
            {'data': [...], 'has_any_access': bool}
        """
        logs.debug('EMBRATEL-API', 'Listando módulos...')
        return self._requisicao('GET', '/ctrl-modulos')
    
    def listar_tarefas_recuperacao(
        self,
        page: int = 1,
        per_page: int = 20,
    ) -> Optional[Dict]:
        """
        POST /pco-workflows/{WORKFLOW_VISUALIZACAO_ID}/visualizar
        
        Retorna tarefas do módulo de Recuperação.
        
        Args:
            page: número da página (1-based)
            per_page: itens por página
        
        Retorna:
            {'data': [...], 'meta': {...}}
        """
        logs.debug(
            'EMBRATEL-API',
            f'Listando tarefas (página {page}, {per_page} por página)...'
        )
        
        payload = {
            'page': page,
            'per_page': per_page,
            'current_page': page,
        }
        
        endpoint = f'/pco-workflows/{WORKFLOW_VISUALIZACAO_ID}/visualizar'
        
        return self._requisicao(
            'POST', 
            endpoint, 
            json_data=payload
        )
    
    def buscar_detalhes_tarefa(self, tarefa_id: int) -> Optional[Dict]:
        """
        GET /pco-tarefas/{tarefa_id}/detalhes
        
        Retorna detalhes completos de uma tarefa específica.
        
        Args:
            tarefa_id: ID da tarefa no portal
        
        Retorna:
            {'data': {...}}
        """
        logs.debug('EMBRATEL-API', f'Buscando detalhes da tarefa {tarefa_id}...')
        return self._requisicao('GET', f'/pco-tarefas/{tarefa_id}/detalhes')
    
    def buscar_historico_tarefa(self, tarefa_id: int, page: int = 1) -> Optional[Dict]:
        """
        GET /pco-tarefas/{tarefa_id}/historico
        
        Retorna histórico de ações/eventos da tarefa.
        
        Args:
            tarefa_id: ID da tarefa
            page: página do histórico
        
        Retorna:
            {'data': [...]}
        """
        logs.debug('EMBRATEL-API', f'Buscando histórico da tarefa {tarefa_id}...')
        
        params = {'page': page}
        
        return self._requisicao(
            'GET',
            f'/pco-tarefas/{tarefa_id}/historico',
            params=params
        )
    
    def buscar_subtarefas(self, tarefa_id: int, page: int = 1) -> Optional[Dict]:
        """
        GET /pco-tarefas/{tarefa_id}/subtarefas
        
        Retorna subtarefas relacionadas.
        
        Args:
            tarefa_id: ID da tarefa pai
            page: página das subtarefas
        
        Retorna:
            {'data': [...]}
        """
        logs.debug('EMBRATEL-API', f'Buscando subtarefas da tarefa {tarefa_id}...')
        
        params = {'page': page}
        
        return self._requisicao(
            'GET',
            f'/pco-tarefas/{tarefa_id}/subtarefas',
            params=params
        )
    
    # ══════════════════════════════════════════════════════════════
    #  GERENCIAMENTO DE SESSÃO
    # ══════════════════════════════════════════════════════════════
    
    def renovar_token(self, novo_token: str):
        """
        Atualiza o token no cliente (útil quando a sessão foi renovada).
        
        Args:
            novo_token: novo token Bearer
        """
        self.token = novo_token
        self.session.headers.update({
            'Authorization': f'Bearer {novo_token}',
        })
        logs.debug('EMBRATEL-API', 'Token renovado no cliente')
    
    def fechar(self):
        """
        Fecha a session (good practice para cleanup).
        """
        if self.session:
            self.session.close()
            logs.debug('EMBRATEL-API', 'Session fechada')
    
    def __enter__(self):
        """Context manager support."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.fechar()


# ══════════════════════════════════════════════════════════════
#  FACTORY FUNCTION (ATALHO)
# ══════════════════════════════════════════════════════════════

def criar_cliente_api(token: str, session: requests.Session = None) -> ClienteApiEmbratel:
    """
    Factory function para criar cliente API.
    
    Exemplo:
        cliente = criar_cliente_api(token=token, session=session)
        tarefas = cliente.listar_tarefas_recuperacao()
        cliente.fechar()
    """
    return ClienteApiEmbratel(token=token, session=session)
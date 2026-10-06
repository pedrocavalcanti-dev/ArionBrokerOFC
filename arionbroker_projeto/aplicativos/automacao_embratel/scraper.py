"""
scraper.py

Orquestrador da coleta de tarefas no portal Modos Web (Embratel).
Responsável por:
  - Autenticar;
  - Coletar todas as páginas de tarefas;
  - Utilizar os normalizadores;
  - Persistir dados no banco com controle de transação e auditoria;
  - Evitar execução concorrente;
  - Não disparar ações externas (ex: envio de e-mail).
"""

import os
import time
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

from django.core.cache import cache
from django.db import transaction, IntegrityError, DataError
from django.utils import timezone
from dotenv import load_dotenv

from .autenticacao import autenticar_completo, realizar_logout
from .cliente_api import ClienteApiEmbratel, SessaoExpiradaEmbratel, ErroApiEmbratel
from .normalizadores import (
    extrair_lista_workflows,
    extrair_paginacao,
    normalizar_workflow,
)
from .models import (
    TarefaEmbratel,
    ExecucaoRoboEmbratel,
    HistoricoTarefaEmbratel,
    ConfiguracaoRoboEmbratel,
    StatusProcessamentoEmbratel,
    OrigemColetaEmbratel,
    StatusExecucaoEmbratel,
)
from . import logs

load_dotenv()

# Constantes
CHAVE_LOCK = "automacao_embratel:coleta_em_andamento"
TIMEOUT_LOCK = 1800  # 30 minutos


# ══════════════════════════════════════════════════════════════
#  UTILITÁRIOS E VALIDAÇÃO
# ══════════════════════════════════════════════════════════════

def validar_configuracao() -> Tuple[str, str]:
    """
    Lê credenciais do ambiente e valida sua presença.
    Lança ValueError se algo estiver faltando.
    """
    usuario = (os.getenv("EMBRATEL_USUARIO") or "").strip()
    senha = (os.getenv("EMBRATEL_SENHA") or "").strip()

    if not usuario or not senha:
        raise ValueError("Credenciais da Embratel ausentes no arquivo .env (EMBRATEL_USUARIO / EMBRATEL_SENHA)")
    
    return usuario, senha


def obter_executor_padrao(executor: Optional[str]) -> str:
    """
    Garante que exista um texto de executor válido e limitado a 150 caracteres.
    """
    final = (executor or "sistema").strip()
    return final[:150]


def limitar_texto(valor: Any, limite: int) -> Optional[str]:
    """
    Converte para string e aplica limite de caracteres para caber no CharField.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto[:limite] if texto else None


# ══════════════════════════════════════════════════════════════
#  CONTROLE DE CONCORRÊNCIA
# ══════════════════════════════════════════════════════════════

def adquirir_lock_execucao() -> bool:
    """
    Tenta criar a chave no cache para evitar que dois ciclos rodem juntos.
    """
    sucesso = cache.add(CHAVE_LOCK, True, timeout=TIMEOUT_LOCK)
    if not sucesso:
        logs.registrar_concorrencia_detectada()
        return False
    return True


def liberar_lock_execucao() -> None:
    """Remove a chave do cache, liberando o robô para um próximo ciclo."""
    cache.delete(CHAVE_LOCK)


def criar_execucao(origem: str, executor: str) -> ExecucaoRoboEmbratel:
    """Cria um registro inicial marcando o começo do ciclo."""
    return ExecucaoRoboEmbratel.objects.create(
        status=StatusExecucaoEmbratel.EM_ANDAMENTO,
        origem=origem,
        executor=executor,
        emails_enviados=0
    )


# ══════════════════════════════════════════════════════════════
#  AUDITORIA E SNAPSHOT
# ══════════════════════════════════════════════════════════════

def obter_snapshot_tarefa(tarefa: TarefaEmbratel) -> Dict:
    """
    Retorna apenas campos relevantes da tarefa em um dicionário simples 
    e serializável para posterior comparação de histórico.
    """
    if not tarefa or not tarefa.pk:
        return {}

    return {
        "status_portal": tarefa.status_portal,
        "tipo_tarefa": tarefa.tipo_tarefa,
        "cliente": tarefa.cliente,
        "provedor": tarefa.provedor,
        "designacao": tarefa.designacao,
        "circuito": tarefa.circuito,
        "projeto": tarefa.projeto,
        "sintoma": tarefa.sintoma,
        "descricao": tarefa.descricao,
        "dentro_sla": tarefa.dentro_sla,
        "aging_minutos": tarefa.aging_minutos,
        "data_finalizacao_portal": tarefa.data_finalizacao_portal.isoformat() if tarefa.data_finalizacao_portal else None,
        "status_processamento": tarefa.status_processamento,
    }


def detectar_mudancas(antes: Dict, depois: Dict) -> Dict:
    """
    Compara os snapshots ignorando falsos positivos (como None vs "").
    Retorna apenas os campos alterados.
    """
    mudancas = {}
    chaves = set(antes.keys()).union(set(depois.keys()))

    for chave in chaves:
        val_ant = antes.get(chave)
        val_dep = depois.get(chave)

        # Trata equivalência entre None e string vazia
        if val_ant is None and val_dep == "":
            continue
        if val_ant == "" and val_dep is None:
            continue

        if val_ant != val_dep:
            mudancas[chave] = {
                "anterior": val_ant,
                "novo": val_dep
            }
    
    return mudancas


def registrar_historico_se_necessario(tarefa: TarefaEmbratel, antes: Dict, depois: Dict) -> None:
    """
    Cria HistoricoTarefaEmbratel apenas se houve alterações relevantes (tarefa existente).
    """
    if not antes:  # Tarefa recém-criada
        return

    mudancas = detectar_mudancas(antes, depois)
    if not mudancas:
        return

    dados_anteriores = {k: v["anterior"] for k, v in mudancas.items()}
    dados_novos = {k: v["novo"] for k, v in mudancas.items()}

    HistoricoTarefaEmbratel.objects.create(
        tarefa=tarefa,
        status_anterior=antes.get("status_processamento", ""),
        status_novo=depois.get("status_processamento", ""),
        dados_anteriores=dados_anteriores,
        dados_novos=dados_novos,
    )


# ══════════════════════════════════════════════════════════════
#  PERSISTÊNCIA DE TAREFA
# ══════════════════════════════════════════════════════════════

def preparar_defaults_tarefa(
    dados_normalizados: Dict, 
    origem: str, 
    executor: str, 
    tarefa_existente: Optional[TarefaEmbratel] = None
) -> Dict:
    """
    Prepara o dicionário 'defaults' limitando tamanhos para os CharFields 
    e aplicando as regras de negócio de mudança de status.
    """
    defaults = {
        "id_processo": limitar_texto(dados_normalizados.get("id_processo"), 50),
        "id_workflow": limitar_texto(dados_normalizados.get("id_workflow"), 50),
        "id_tarefa_anterior": limitar_texto(dados_normalizados.get("id_tarefa_anterior"), 50),
        "status_portal": limitar_texto(dados_normalizados.get("status_portal"), 100),
        "tipo_tarefa": limitar_texto(dados_normalizados.get("tipo_tarefa"), 100),
        "cliente": limitar_texto(dados_normalizados.get("cliente"), 255),
        "provedor": limitar_texto(dados_normalizados.get("provedor"), 100),
        "designacao": limitar_texto(dados_normalizados.get("designacao"), 100),
        "circuito": limitar_texto(dados_normalizados.get("circuito"), 100),
        "projeto": limitar_texto(dados_normalizados.get("projeto"), 255),
        "sintoma": limitar_texto(dados_normalizados.get("sintoma"), 255),
        "descricao": dados_normalizados.get("descricao"),
        "dados_tecnicos": dados_normalizados.get("dados_tecnicos"),
        "data_criacao_portal": dados_normalizados.get("data_criacao_portal"),
        "data_atualizacao_portal": dados_normalizados.get("data_atualizacao_portal"),
        "data_finalizacao_portal": dados_normalizados.get("data_finalizacao_portal"),
        "dentro_sla": dados_normalizados.get("dentro_sla"),
        "aging_minutos": dados_normalizados.get("aging_minutos"),
        "url_tarefa": limitar_texto(dados_normalizados.get("url_tarefa"), 500),
        
        "data_coleta": timezone.now(),
        "origem_coleta": origem,
        "coletado_por": executor,
        "erro_processamento": None,
    }

    status_finalizado = StatusProcessamentoEmbratel.FINALIZADO
    data_finalizacao = defaults["data_finalizacao_portal"]

    if not tarefa_existente:
        # TAREFA NOVA
        defaults["status_processamento"] = status_finalizado if data_finalizacao else StatusProcessamentoEmbratel.NOVO
    else:
        # TAREFA EXISTENTE - Preserva campos imutáveis do processo
        defaults["status_processamento"] = tarefa_existente.status_processamento
        
        if data_finalizacao:
            # Pela regra, se portal finalizou e estava ENVIADO ou outro status, pode mudar pra FINALIZADO.
            # Não volta pra NOVO se estava ENVIADO.
            defaults["status_processamento"] = status_finalizado

    return defaults


def persistir_tarefa(
    dados_normalizados: Dict, 
    origem: str, 
    executor: str
) -> Tuple[Optional[TarefaEmbratel], bool, bool]:
    """
    Grava os dados no banco utilizando update_or_create dentro de uma transaction atômica.
    Gera histórico caso aplicável e isola as falhas para não abortar todo o ciclo.
    """
    id_portal = limitar_texto(dados_normalizados.get("id_portal"), 50)
    if not id_portal:
        logs.aviso("EMBRATEL-COLETA", "Tarefa não salva: id_portal está ausente.")
        return None, False, False

    try:
        tarefa_existente = TarefaEmbratel.objects.filter(id_portal=id_portal).first()
        snapshot_anterior = obter_snapshot_tarefa(tarefa_existente)
        
        defaults = preparar_defaults_tarefa(dados_normalizados, origem, executor, tarefa_existente)

        with transaction.atomic():
            tarefa, criada = TarefaEmbratel.objects.update_or_create(
                id_portal=id_portal,
                defaults=defaults
            )

        # Pegar snapshot novo após commit local garantido
        tarefa.refresh_from_db()
        snapshot_novo = obter_snapshot_tarefa(tarefa)

        mudancas = detectar_mudancas(snapshot_anterior, snapshot_novo)
        atualizada = (not criada) and bool(mudancas)

        if atualizada:
            registrar_historico_se_necessario(tarefa, snapshot_anterior, snapshot_novo)

        # Log temático apenas para nova, para não poluir
        if criada:
            logs.registrar_tarefa_coletada(id_portal, tarefa.cliente)

        return tarefa, criada, atualizada

    except (IntegrityError, DataError) as e:
        logs.erro("EMBRATEL-COLETA", f"Erro de banco na persistência (id_portal={id_portal}): {e}")
        return None, False, False
    except Exception as e:
        logs.erro("EMBRATEL-COLETA", f"Falha inesperada ao persistir (id_portal={id_portal})", e)
        return None, False, False


# ══════════════════════════════════════════════════════════════
#  COLETA API
# ══════════════════════════════════════════════════════════════

def coletar_pagina(cliente: ClienteApiEmbratel, pagina: int, por_pagina: int) -> Tuple[List[Dict], Dict]:
    """Puxa uma página da API e extrai raw workflows e os metadados de paginação."""
    resposta = cliente.listar_tarefas_recuperacao(page=pagina, per_page=por_pagina)
    if not isinstance(resposta, dict):
        raise ErroApiEmbratel(f"Resposta inválida da API ao buscar página {pagina}.")

    workflows_brutos = extrair_lista_workflows(resposta)
    paginacao = extrair_paginacao(resposta)
    
    return workflows_brutos, paginacao


def coletar_todas_paginas(
    cliente: ClienteApiEmbratel, 
    por_pagina: int = 20, 
    limite_paginas: Optional[int] = None
) -> List[Dict]:
    """
    Gira sobre as páginas da API enquanto houver "tem_proxima".
    Limitado a 1000 páginas como proteção contra loops infinitos.
    """
    pagina_atual = 1
    max_paginas_seguranca = 1000
    workflows_totais = []
    paginas_visitadas = set()

    while pagina_atual <= max_paginas_seguranca:
        if limite_paginas and pagina_atual > limite_paginas:
            break
            
        if pagina_atual in paginas_visitadas:
            break
        paginas_visitadas.add(pagina_atual)

        workflows_brutos, paginacao = coletar_pagina(cliente, pagina_atual, por_pagina)
        qtd = len(workflows_brutos)
        
        workflows_totais.extend(workflows_brutos)
        
        logs.info(
            "EMBRATEL-COLETA", 
            f"Página {pagina_atual} coletada | Itens: {qtd} | Acumulado: {len(workflows_totais)}"
        )

        if not paginacao.get("tem_proxima") or qtd == 0:
            break
        
        pagina_atual += 1

    return workflows_totais


# ══════════════════════════════════════════════════════════════
#  PROCESSAMENTO EM LOTE
# ══════════════════════════════════════════════════════════════

def processar_workflows(workflows: List[Dict], origem: str, executor: str) -> Dict:
    """
    Normaliza e persiste cada item isoladamente. Retorna estatísticas.
    """
    resumo = {
        "encontradas": len(workflows),
        "novas": 0,
        "atualizadas": 0,
        "ignoradas": 0,
        "erros": []
    }

    for wf in workflows:
        identificador = wf.get("id", "Desconhecido")
        
        try:
            dados_norm = normalizar_workflow(wf)
            if not dados_norm:
                raise ValueError("Normalização retornou vazio (falta ID ou dados cruciais).")
                
            tarefa, criada, atualizada = persistir_tarefa(dados_norm, origem, executor)
            
            if not tarefa:
                resumo["ignoradas"] += 1
            elif criada:
                resumo["novas"] += 1
            elif atualizada:
                resumo["atualizadas"] += 1
            else:
                resumo["ignoradas"] += 1

        except Exception as e:
            resumo["erros"].append(f"Erro WF {identificador}: {str(e)[:400]}")
            logs.erro("EMBRATEL-COLETA", f"Falha isolada ao processar workflow ID {identificador}: {e}")
            resumo["ignoradas"] += 1

    return resumo


# ══════════════════════════════════════════════════════════════
#  ORQUESTRADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def executar_coleta_embratel(
    origem: str = OrigemColetaEmbratel.MANUAL,
    executor: Optional[str] = None,
    por_pagina: int = 20,
    limite_paginas: Optional[int] = None
) -> Dict:
    """
    Ponto de entrada público do robô.
    Autentica, extrai páginas, normaliza, persiste, lida com configs e limpa rastros finais.
    """
    executor_final = obter_executor_padrao(executor)
    
    # 1. Lock de Concorrência
    if not adquirir_lock_execucao():
        return {
            "sucesso": False,
            "pausado": False,
            "concorrencia": True,
            "execucao_id": None,
            "tarefas_encontradas": 0,
            "tarefas_novas": 0,
            "tarefas_atualizadas": 0,
            "tarefas_ignoradas": 0,
            "erros": ["Já existe uma coleta Embratel em andamento."]
        }
    
    # 2. Configurações
    config = ConfiguracaoRoboEmbratel.obter()
    if not config.ativo:
        logs.aviso("EMBRATEL-SCHEDULER", "A automação Embratel está pausada na configuração.")
        liberar_lock_execucao()
        return {
            "sucesso": False,
            "pausado": True,
            "execucao_id": None,
            "tarefas_encontradas": 0,
            "tarefas_novas": 0,
            "tarefas_atualizadas": 0,
            "tarefas_ignoradas": 0,
            "erros": []
        }

    execucao = None
    session = None
    token = None
    cliente = None
    
    try:
        usuario, senha = validar_configuracao()
        
        # 3. Execução Inicio
        logs.registrar_inicio_ciclo()
        execucao = criar_execucao(origem, executor_final)
        
        config.ultima_execucao = timezone.now()
        config.save(update_fields=['ultima_execucao'])

        # 4. Autenticação e Cliente
        logs.info("EMBRATEL-LOGIN", "Iniciando autenticação no Modos Web")
        sucesso_login, token, session = autenticar_completo(usuario, senha)
        
        if not sucesso_login or not session or not token:
            raise ValueError("Autenticação falhou. Token ou sessão não foram criados.")

        cliente = ClienteApiEmbratel(token=token, session=session)
        
        # 5. Coleta
        tempo_inicio = time.time()
        workflows_brutos = coletar_todas_paginas(cliente, por_pagina, limite_paginas)
        
        # 6. Processamento
        resumo = processar_workflows(workflows_brutos, origem, executor_final)
        
        duracao = time.time() - tempo_inicio
        
        # 7. Finalização de Execução e Config
        execucao.tarefas_encontradas = resumo["encontradas"]
        execucao.tarefas_novas = resumo["novas"]
        execucao.tarefas_atualizadas = resumo["atualizadas"]
        execucao.erros = resumo["erros"]
        execucao.duracao_segundos = duracao
        execucao.finalizado_em = timezone.now()
        execucao.status = StatusExecucaoEmbratel.SUCESSO_COM_ERROS if resumo["erros"] else StatusExecucaoEmbratel.SUCESSO
        execucao.save()

        config.ultimo_sucesso = timezone.now()
        config.save(update_fields=['ultimo_sucesso'])

        logs.registrar_fim_ciclo(
            novas=resumo["novas"],
            atualizadas=resumo["atualizadas"],
            ignoradas=resumo["ignoradas"],
            erros=len(resumo["erros"]),
            duracao_segundos=duracao
        )
        
        return {
            "sucesso": True,
            "pausado": False,
            "execucao_id": execucao.pk,
            "tarefas_encontradas": resumo["encontradas"],
            "tarefas_novas": resumo["novas"],
            "tarefas_atualizadas": resumo["atualizadas"],
            "tarefas_ignoradas": resumo["ignoradas"],
            "erros": resumo["erros"]
        }

    except SessaoExpiradaEmbratel as e:
        msg = f"Sessão expirada durante coleta: {str(e)}"
        logs.erro("EMBRATEL-COLETA", msg)
        erros_list = [msg]
    except Exception as e:
        msg = f"Falha geral na coleta: {str(e)[:400]}"
        logs.erro("EMBRATEL-COLETA", msg, e)
        erros_list = [msg]

    # Tratamento caso caia no exception geral ou Sessão Expirada
    if execucao:
        execucao.status = StatusExecucaoEmbratel.FALHA
        execucao.finalizado_em = timezone.now()
        execucao.erros = erros_list
        execucao.save()

    config.ultima_falha = timezone.now()
    config.save(update_fields=['ultima_falha'])
    
    # Finally garante liberação de recursos
    try:
        pass
    finally:
        if session and token:
            realizar_logout(session, token)
        if cliente:
            cliente.fechar()
        elif session:
            session.close()
        liberar_lock_execucao()

    return {
        "sucesso": False,
        "pausado": False,
        "concorrencia": False,
        "execucao_id": execucao.pk if execucao else None,
        "tarefas_encontradas": 0,
        "tarefas_novas": 0,
        "tarefas_atualizadas": 0,
        "tarefas_ignoradas": 0,
        "erros": erros_list
    }
"""
tasks.py

Orquestrador de tarefas para a automação Embratel.
Responsável unicamente por coordenar as funções de coleta (scraper.py)
e as regras de negócio de e-mail/status (services.py).

Não contém regras de negócio próprias, nem chamadas HTTP, nem
alterações diretas de banco de dados. 
Pode ser importado por views, comandos de gerenciamento ou schedulers futuros.
"""

import time
from typing import Optional, Dict, Any

from . import logs
from .models import TarefaEmbratel, OrigemColetaEmbratel
from .scraper import executar_coleta_embratel
from .services import (
    processar_envios_pendentes,
    enviar_email_tarefa_embratel,
    reprocessar_tarefa_embratel,
)


# ══════════════════════════════════════════════════════════════
#  AUXILIARES
# ══════════════════════════════════════════════════════════════

def _formatar_resposta(
    sucesso: bool, 
    mensagem: str, 
    dados: Optional[Dict[str, Any]] = None, 
    erro: Optional[str] = None
) -> Dict[str, Any]:
    """Padroniza os retornos das tasks."""
    resposta: Dict[str, Any] = {
        "sucesso": sucesso,
        "mensagem": mensagem,
        "dados": dados
    }
    if not sucesso:
        resposta["erro"] = erro or "Erro não especificado."
    return resposta


# ══════════════════════════════════════════════════════════════
#  TAREFAS DE COLETA
# ══════════════════════════════════════════════════════════════

def executar_sincronizacao_manual(
    executor: Optional[str] = None, 
    limite_paginas: Optional[int] = None
) -> Dict[str, Any]:
    """Inicia a coleta configurada para execução manual (via interface/admin)."""
    logs.info("EMBRATEL-TASKS", f"Iniciando sincronização manual (Executor: {executor})")
    inicio = time.time()
    
    try:
        resultado = executar_coleta_embratel(
            origem=OrigemColetaEmbratel.MANUAL,
            executor=executor,
            limite_paginas=limite_paginas
        )
        
        sucesso = bool(resultado.get("sucesso"))
        msg = "Sincronização manual concluída com sucesso." if sucesso else "Sincronização manual pausada ou com falhas."
        
        if not sucesso and resultado.get("erros"):
            logs.aviso("EMBRATEL-TASKS", f"Sincronização manual registrou erros: {resultado.get('erros')}")

        return _formatar_resposta(sucesso=sucesso, mensagem=msg, dados=resultado)

    except Exception as e:
        msg_erro = f"Exceção crítica na sincronização manual: {str(e)}"
        logs.erro("EMBRATEL-TASKS", msg_erro, e)
        return _formatar_resposta(sucesso=False, mensagem="Erro crítico.", erro=msg_erro)
    
    finally:
        duracao = time.time() - inicio
        logs.info("EMBRATEL-TASKS", f"Sincronização manual finalizada em {duracao:.2f}s")


def executar_sincronizacao_automatica() -> Dict[str, Any]:
    """Inicia a coleta configurada para rotina automática (sem envio de e-mails aqui)."""
    logs.info("EMBRATEL-TASKS", "Iniciando sincronização automática")
    inicio = time.time()
    
    try:
        resultado = executar_coleta_embratel(
            origem=OrigemColetaEmbratel.AUTOMATICO,
            executor="scheduler",
            limite_paginas=None
        )
        
        sucesso = bool(resultado.get("sucesso"))
        msg = "Sincronização automática concluída." if sucesso else "Sincronização automática pausada ou com falhas."
        
        if not sucesso and resultado.get("erros"):
            logs.aviso("EMBRATEL-TASKS", f"Sincronização automática registrou erros: {resultado.get('erros')}")

        return _formatar_resposta(sucesso=sucesso, mensagem=msg, dados=resultado)

    except Exception as e:
        msg_erro = f"Exceção crítica na sincronização automática: {str(e)}"
        logs.erro("EMBRATEL-TASKS", msg_erro, e)
        return _formatar_resposta(sucesso=False, mensagem="Erro crítico.", erro=msg_erro)
    
    finally:
        duracao = time.time() - inicio
        logs.info("EMBRATEL-TASKS", f"Sincronização automática finalizada em {duracao:.2f}s")


# ══════════════════════════════════════════════════════════════
#  TAREFAS DE E-MAIL
# ══════════════════════════════════════════════════════════════

def executar_processamento_emails(limite: int = 50) -> Dict[str, Any]:
    """Aciona o fluxo de envio em lote para as tarefas elegíveis."""
    logs.info("EMBRATEL-TASKS", f"Iniciando processamento de e-mails (Limite: {limite})")
    inicio = time.time()
    
    try:
        resultado = processar_envios_pendentes(limite=limite, enviado_por="scheduler")
        return _formatar_resposta(
            sucesso=True, 
            mensagem=f"Lote processado. Enviados: {resultado.get('enviadas', 0)}", 
            dados=resultado
        )

    except Exception as e:
        msg_erro = f"Exceção crítica no processamento de e-mails: {str(e)}"
        logs.erro("EMBRATEL-TASKS", msg_erro, e)
        return _formatar_resposta(sucesso=False, mensagem="Erro crítico ao processar e-mails.", erro=msg_erro)
    
    finally:
        duracao = time.time() - inicio
        logs.info("EMBRATEL-TASKS", f"Processamento de e-mails finalizado em {duracao:.2f}s")


# ══════════════════════════════════════════════════════════════
#  CICLO COMPLETO
# ══════════════════════════════════════════════════════════════

def executar_ciclo_completo() -> Dict[str, Any]:
    """
    Macro-tarefa para o scheduler. 
    Realiza a coleta e, em seguida, dispara os e-mails se a coleta obteve sucesso.
    """
    logs.info("EMBRATEL-TASKS", "Iniciando ciclo completo (Coleta + E-mails)")
    inicio = time.time()
    
    retorno: Dict[str, Any] = {
        "coleta": {},
        "emails": None,
        "sucesso": False
    }

    try:
        # 1. Coleta
        res_coleta = executar_sincronizacao_automatica()
        retorno["coleta"] = res_coleta
        
        # Aborta e-mails se a coleta relatar falha
        if not res_coleta.get("sucesso"):
            logs.aviso("EMBRATEL-TASKS", "Coleta falhou ou foi pausada. Etapa de e-mails ignorada.")
            return retorno

        # 2. E-mails
        res_emails = executar_processamento_emails()
        retorno["emails"] = res_emails
        retorno["sucesso"] = res_emails.get("sucesso", False)
        
        return retorno

    except Exception as e:
        logs.erro("EMBRATEL-TASKS", "Exceção não tratada ao coordenar o ciclo completo.", e)
        retorno["sucesso"] = False
        return retorno
        
    finally:
        duracao = time.time() - inicio
        logs.info("EMBRATEL-TASKS", f"Ciclo completo finalizado em {duracao:.2f}s")


# ══════════════════════════════════════════════════════════════
#  TAREFAS PONTUAIS E DIAGNÓSTICO
# ══════════════════════════════════════════════════════════════

def reprocessar_por_id(tarefa_id: int, executor: str = "sistema") -> Dict[str, Any]:
    """Reprocessa o envio de e-mail de uma tarefa que se encontra em ERRO ou REVISÃO."""
    logs.info("EMBRATEL-TASKS", f"Iniciando reprocessamento da tarefa PK {tarefa_id} (Executor: {executor})")
    inicio = time.time()
    
    try:
        resultado = reprocessar_tarefa_embratel(tarefa_id=tarefa_id, enviado_por=executor)
        sucesso = bool(resultado.get("sucesso"))
        msg = "Reprocessamento concluído com sucesso." if sucesso else "Falha ao reprocessar tarefa."
        
        return _formatar_resposta(sucesso=sucesso, mensagem=msg, dados=resultado)

    except Exception as e:
        msg_erro = f"Exceção crítica ao reprocessar tarefa {tarefa_id}: {str(e)}"
        logs.erro("EMBRATEL-TASKS", msg_erro, e)
        return _formatar_resposta(sucesso=False, mensagem="Erro crítico.", erro=msg_erro)
    
    finally:
        duracao = time.time() - inicio
        logs.info("EMBRATEL-TASKS", f"Reprocessamento finalizado em {duracao:.2f}s")


def enviar_por_id(tarefa_id: int, executor: str = "sistema") -> Dict[str, Any]:
    """Obtém a instância e invoca o envio isolado da tarefa."""
    logs.info("EMBRATEL-TASKS", f"Iniciando envio manual da tarefa PK {tarefa_id} (Executor: {executor})")
    inicio = time.time()
    
    try:
        tarefa = TarefaEmbratel.objects.filter(pk=tarefa_id).first()
        if not tarefa:
            return _formatar_resposta(sucesso=False, mensagem="Erro de busca.", erro=f"Tarefa com PK {tarefa_id} inexistente.")
            
        resultado = enviar_email_tarefa_embratel(tarefa=tarefa, enviado_por=executor)
        sucesso = bool(resultado.get("sucesso"))
        msg = "Envio manual concluído com sucesso." if sucesso else "Falha ao enviar tarefa manualmente."
        
        return _formatar_resposta(sucesso=sucesso, mensagem=msg, dados=resultado)

    except Exception as e:
        msg_erro = f"Exceção crítica ao enviar tarefa {tarefa_id}: {str(e)}"
        logs.erro("EMBRATEL-TASKS", msg_erro, e)
        return _formatar_resposta(sucesso=False, mensagem="Erro crítico.", erro=msg_erro)
    
    finally:
        duracao = time.time() - inicio
        logs.info("EMBRATEL-TASKS", f"Envio manual finalizado em {duracao:.2f}s")


def executar_teste_conexao() -> Dict[str, Any]:
    """Gatilho de diagnóstico para atestar comunicação com o Modos Web processando apenas 1 página."""
    logs.info("EMBRATEL-TASKS", "Iniciando teste de conexão à API Embratel (Limite: 1 página)")
    inicio = time.time()
    
    try:
        resultado = executar_coleta_embratel(
            origem=OrigemColetaEmbratel.MANUAL,
            executor="teste_conexao",
            limite_paginas=1
        )
        
        sucesso = bool(resultado.get("sucesso"))
        msg = "Teste de conexão concluído com sucesso." if sucesso else "Teste de conexão reportou falhas."
        
        return _formatar_resposta(sucesso=sucesso, mensagem=msg, dados=resultado)

    except Exception as e:
        msg_erro = f"Exceção crítica no teste de conexão: {str(e)}"
        logs.erro("EMBRATEL-TASKS", msg_erro, e)
        return _formatar_resposta(sucesso=False, mensagem="Erro crítico.", erro=msg_erro)
    
    finally:
        duracao = time.time() - inicio
        logs.info("EMBRATEL-TASKS", f"Teste de conexão finalizado em {duracao:.2f}s")
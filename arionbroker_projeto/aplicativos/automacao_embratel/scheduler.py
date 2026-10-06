"""
scheduler.py

Camada de agendamento interno do robô Embratel.
Não mantém loops infinitos nem processos residentes (threads/sleep/APScheduler/Celery).
Fornece regras de avaliação de tempo, concorrência e configurações ativas para
determinar se o robô deve ser engatilhado e repassa a execução para as tasks.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Optional, Dict

from django.utils import timezone

from . import logs
from .models import (
    ConfiguracaoRoboEmbratel,
    ExecucaoRoboEmbratel,
    StatusExecucaoEmbratel,
)
from .tasks import (
    executar_ciclo_completo,
    executar_sincronizacao_automatica,
)


# ══════════════════════════════════════════════════════════════
#  UTILITÁRIOS DE AMBIENTE E CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════

def ler_booleano_ambiente(nome: str, padrao: bool = False) -> bool:
    """Lê um booleano do .env de forma segura."""
    valor = os.getenv(nome, "").strip().lower()
    if not valor:
        return padrao
    if valor in ("1", "true", "sim", "yes", "on", "t", "s", "y"):
        return True
    if valor in ("0", "false", "nao", "não", "no", "off", "f", "n"):
        return False
    return padrao


def ler_inteiro_ambiente(
    nome: str, 
    padrao: int, 
    minimo: Optional[int] = None, 
    maximo: Optional[int] = None
) -> int:
    """Lê um inteiro do .env limitando dentro de um range seguro."""
    valor = os.getenv(nome, "").strip()
    if not valor:
        return padrao
    try:
        val_int = int(valor)
        if minimo is not None and val_int < minimo:
            return minimo
        if maximo is not None and val_int > maximo:
            return maximo
        return val_int
    except (ValueError, TypeError):
        return padrao


def obter_configuracao() -> ConfiguracaoRoboEmbratel:
    """Recupera o registro Singleton de configuração."""
    return ConfiguracaoRoboEmbratel.obter()


# ══════════════════════════════════════════════════════════════
#  CÁLCULOS DE TEMPO E INTERVALOS
# ══════════════════════════════════════════════════════════════

def obter_intervalo_minutos(configuracao: ConfiguracaoRoboEmbratel) -> int:
    """Extrai e protege o intervalo configurado (1 min a 24 horas)."""
    try:
        intervalo = int(configuracao.intervalo_minutos)
        return max(1, min(1440, intervalo))
    except (ValueError, TypeError):
        return 15


def obter_ultima_execucao_referencia(configuracao: ConfiguracaoRoboEmbratel) -> Optional[datetime]:
    """Descobre a última vez que o robô rodou, garantindo timezone-aware."""
    ref = configuracao.ultima_execucao
    
    if not ref:
        ultima = ExecucaoRoboEmbratel.objects.order_by('-iniciado_em').first()
        ref = ultima.iniciado_em if ultima else None

    if ref and timezone.is_naive(ref):
        logs.aviso("EMBRATEL-SCHEDULER", "Data de última execução naive encontrada. Convertendo para aware.")
        ref = timezone.make_aware(ref, timezone.get_current_timezone())
        
    return ref


def calcular_proxima_execucao(configuracao: Optional[ConfiguracaoRoboEmbratel] = None) -> datetime:
    """Calcula exato momento em que o robô fica livre para a próxima volta."""
    config = configuracao or obter_configuracao()
    ultima = obter_ultima_execucao_referencia(config)
    
    if not ultima:
        return timezone.now()
        
    intervalo = obter_intervalo_minutos(config)
    return ultima + timedelta(minutes=intervalo)


def calcular_segundos_ate_proxima_execucao(configuracao: Optional[ConfiguracaoRoboEmbratel] = None) -> int:
    """Quantos segundos faltam (sempre não-negativo)."""
    proxima = calcular_proxima_execucao(configuracao)
    agora = timezone.now()
    diff = (proxima - agora).total_seconds()
    return int(max(0, diff))


def esta_no_horario_de_executar(configuracao: Optional[ConfiguracaoRoboEmbratel] = None) -> bool:
    """Checa se o tempo de espera já zerou."""
    return calcular_segundos_ate_proxima_execucao(configuracao) == 0


# ══════════════════════════════════════════════════════════════
#  AVALIAÇÃO E CONCORRÊNCIA
# ══════════════════════════════════════════════════════════════

def existe_execucao_em_andamento() -> bool:
    """
    Previne atropelamentos de ciclos. Se houver execução EM_ANDAMENTO muito
    antiga, assume que foi um aborto sistêmico (timeout) e não trava a esteira.
    """
    timeout_minutos = ler_inteiro_ambiente("EMBRATEL_TIMEOUT_EXECUCAO_MINUTOS", padrao=60)
    limite_tempo = timezone.now() - timedelta(minutes=timeout_minutos)
    
    em_andamento = ExecucaoRoboEmbratel.objects.filter(status=StatusExecucaoEmbratel.EM_ANDAMENTO)
    
    for execucao in em_andamento:
        if not execucao.iniciado_em:
            logs.aviso("EMBRATEL-SCHEDULER", f"Execução PK {execucao.id} em andamento sem 'iniciado_em'. Bloqueando nova execução.")
            return True
            
        if execucao.iniciado_em >= limite_tempo:
            return True
        else:
            logs.aviso(
                "EMBRATEL-SCHEDULER", 
                f"Execução PK {execucao.id} ignorada por timeout (travada há mais de {timeout_minutos} min)."
            )
            
    return False


def avaliar_execucao_scheduler(forcar: bool = False) -> Dict[str, Any]:
    """Retorna um diagnóstico completo se o robô pode ou não iniciar um novo ciclo."""
    if not ler_booleano_ambiente("EMBRATEL_SCHEDULER_ATIVO", padrao=True):
        return {
            "pode_executar": False,
            "codigo": "SCHEDULER_DESATIVADO",
            "motivo": "Scheduler desativado por variável de ambiente.",
            "segundos_restantes": 0
        }
        
    config = obter_configuracao()
    
    if not config.ativo:
        return {
            "pode_executar": False,
            "codigo": "ROBO_PAUSADO",
            "motivo": "O robô Embratel está pausado.",
            "segundos_restantes": 0
        }
        
    if existe_execucao_em_andamento():
        return {
            "pode_executar": False,
            "codigo": "EXECUCAO_EM_ANDAMENTO",
            "motivo": "Já existe uma execução Embratel em andamento.",
            "segundos_restantes": 0
        }
        
    if not forcar and not esta_no_horario_de_executar(config):
        segundos = calcular_segundos_ate_proxima_execucao(config)
        return {
            "pode_executar": False,
            "codigo": "FORA_DO_INTERVALO",
            "motivo": "Ainda não chegou o horário da próxima execução.",
            "segundos_restantes": segundos
        }
        
    return {
        "pode_executar": True,
        "codigo": "PRONTO",
        "motivo": None,
        "segundos_restantes": 0
    }


# ══════════════════════════════════════════════════════════════
#  FLUXOS PRINCIPAIS DE EXECUÇÃO
# ══════════════════════════════════════════════════════════════

def executar_ciclo_agendado(forcar: bool = False, processar_emails: Optional[bool] = None) -> Dict[str, Any]:
    """
    Função pública orquestradora da chamada agendada.
    Delega a carga bruta para tasks.py caso apto.
    """
    logs.info("EMBRATEL-SCHEDULER", "Avaliando execução automática do robô Embratel.")
    
    try:
        avaliacao = avaliar_execucao_scheduler(forcar=forcar)
        
        if not avaliacao["pode_executar"]:
            cod = avaliacao["codigo"]
            if cod == "FORA_DO_INTERVALO":
                logs.info("EMBRATEL-SCHEDULER", f"Próxima execução em {avaliacao['segundos_restantes']} segundos.")
            elif cod == "ROBO_PAUSADO":
                logs.aviso("EMBRATEL-SCHEDULER", "Execução ignorada porque o robô está pausado.")
            elif cod == "EXECUCAO_EM_ANDAMENTO":
                logs.aviso("EMBRATEL-SCHEDULER", "Execução ignorada porque já existe um ciclo em andamento.")
            
            return {
                "sucesso": True,
                "executado": False,
                "codigo": cod,
                "mensagem": avaliacao["motivo"],
                "dados": {
                    "segundos_restantes": avaliacao["segundos_restantes"],
                    "proxima_execucao": calcular_proxima_execucao().isoformat() if cod == "FORA_DO_INTERVALO" else None
                }
            }

        # Decisão de e-mails
        if processar_emails is None:
            processar_emails = ler_booleano_ambiente("EMBRATEL_PROCESSAR_EMAILS_NO_CICLO", padrao=False)

        # Repasse para as Tasks responsáveis (onde já ocorre todo try/except final, locks e updates)
        if processar_emails:
            resultado_task = executar_ciclo_completo()
        else:
            resultado_task = executar_sincronizacao_automatica()

        # Tasks.py e scraper.py já lidam com a atualização da "ultima_execucao" em ConfiguracaoRoboEmbratel.
        # Não duplicamos o save() aqui.

        return {
            "sucesso": resultado_task.get("sucesso", False),
            "executado": True,
            "codigo": "EXECUTADO",
            "mensagem": "Ciclo automático Embratel concluído.",
            "dados": resultado_task
        }

    except Exception as e:
        msg_erro = str(e)[:300]
        logs.erro("EMBRATEL-SCHEDULER", "Falha inesperada no scheduler Embratel.", e)
        return {
            "sucesso": False,
            "executado": False,
            "codigo": "ERRO_SCHEDULER",
            "mensagem": "Falha ao executar o ciclo automático Embratel.",
            "erro": msg_erro,
            "dados": None
        }


def executar_scheduler_uma_vez(forcar: bool = False, processar_emails: Optional[bool] = None) -> Dict[str, Any]:
    """
    Ponto de entrada isolado a ser importado pelo Command do Django (manage.py).
    Cumpre apenas uma volta sem gerar looping bloqueante.
    """
    return executar_ciclo_agendado(forcar=forcar, processar_emails=processar_emails)


def obter_status_scheduler() -> Dict[str, Any]:
    """Gera um dump público serializável (JSON-friendly) da aptidão do scheduler."""
    try:
        config = obter_configuracao()
        avaliacao = avaliar_execucao_scheduler()
        proxima = calcular_proxima_execucao(config)
        ultima = obter_ultima_execucao_referencia(config)
        
        return {
            "scheduler_ativo": ler_booleano_ambiente("EMBRATEL_SCHEDULER_ATIVO", padrao=True),
            "robo_ativo": config.ativo,
            "intervalo_minutos": obter_intervalo_minutos(config),
            "execucao_em_andamento": existe_execucao_em_andamento(),
            "ultima_execucao": ultima.isoformat() if ultima else None,
            "proxima_execucao": proxima.isoformat(),
            "segundos_restantes": calcular_segundos_ate_proxima_execucao(config),
            "pode_executar": avaliacao["pode_executar"],
            "codigo": avaliacao["codigo"]
        }
    except Exception as e:
        logs.erro("EMBRATEL-SCHEDULER", "Falha ao obter status do scheduler Embratel.", e)
        return {
            "scheduler_ativo": False,
            "robo_ativo": False,
            "pode_executar": False,
            "codigo": "ERRO_STATUS"
        }
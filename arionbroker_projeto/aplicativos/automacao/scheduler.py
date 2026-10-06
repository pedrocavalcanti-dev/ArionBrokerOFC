"""
ARION PROJETOS — BROKER
aplicativos/automacao/scheduler.py

Jobs registrados:

1. job_coleta_envio
   - Executa a cada 1 minuto, no segundo 00.
   - Coleta novas RECs no portal da Claro.
   - Envia os e-mails das RECs pendentes.

2. job_busca_registro
   - Executa a cada 1 minuto, no segundo 30.
   - Busca no OTRS os tickets das RECs já enviadas.
   - Registra os tickets encontrados no portal da Claro.

3. job_kpi
   - Executa a cada 5 minutos, no segundo 45.
   - Atualiza os KPIs do OTRS.

As execuções são desencontradas para reduzir concorrência entre Playwright,
login no OTRS e chamadas ao portal da Claro.

Também são usadas travas locais para impedir que dois processos utilizem
simultaneamente o Broker ou o OTRS dentro da mesma instância do servidor.
"""

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore


logger = logging.getLogger(__name__)

_scheduler = None

# Trava exclusiva para operações que usam o portal Broker/Claro.
_trava_broker = threading.Lock()

# Trava exclusiva para operações que usam o OTRS.
_trava_otrs = threading.Lock()


# ───────────────────────────────────────────────────────────────
# JOB 1 — COLETA E ENVIO
# ───────────────────────────────────────────────────────────────

def _executar_coleta_envio():
    """
    Executa a coleta de novas RECs e o envio dos e-mails.

    Se uma execução anterior ainda estiver rodando, esta execução é ignorada.
    """

    if not _trava_broker.acquire(blocking=False):
        logger.warning(
            "[COLETA] Execucao ignorada: outra coleta Broker "
            "ainda esta em andamento."
        )
        return

    try:
        from aplicativos.automacao.tasks import job_coleta_e_envio

        logger.info(
            "[COLETA] >>> Iniciando coleta e envio..."
        )

        resultado = job_coleta_e_envio()

        logger.info(
            "[COLETA] <<< Coleta e envio encerrados | resultado=%s",
            resultado,
        )

    except Exception:
        logger.exception(
            "[COLETA] Erro nao tratado durante coleta e envio."
        )

    finally:
        _trava_broker.release()


# ───────────────────────────────────────────────────────────────
# JOB 2 — BUSCA OTRS E REGISTRO CLARO
# ───────────────────────────────────────────────────────────────

def _executar_busca_registro():
    """
    Busca tickets no OTRS e registra os encontrados no portal da Claro.

    A mesma trava do OTRS também é utilizada pelo job de KPI para evitar
    concorrência de sessões, cookies e navegadores.
    """

    if not _trava_otrs.acquire(blocking=False):
        logger.warning(
            "[REGISTRO] Execucao ignorada: o OTRS ja esta sendo "
            "utilizado por outro processo."
        )
        return

    try:
        from aplicativos.automacao.tasks import job_busca_e_registro

        logger.info(
            "[REGISTRO] >>> Iniciando busca OTRS e registro Claro..."
        )

        resultado = job_busca_e_registro()

        logger.info(
            "[REGISTRO] <<< Busca e registro encerrados | resultado=%s",
            resultado,
        )

    except Exception:
        logger.exception(
            "[REGISTRO] Erro nao tratado durante busca ou registro."
        )

    finally:
        _trava_otrs.release()


# ───────────────────────────────────────────────────────────────
# JOB 3 — ATUALIZAÇÃO DE KPIs
# ───────────────────────────────────────────────────────────────

def _executar_kpi():
    """
    Atualiza os KPIs do OTRS.

    Se o OTRS estiver sendo utilizado pelo job de busca e registro,
    a atualização é ignorada neste ciclo e tentada novamente no próximo.
    """

    if not _trava_otrs.acquire(blocking=False):
        logger.warning(
            "[KPI] Atualizacao ignorada neste ciclo: "
            "o OTRS esta sendo utilizado pelo job de registro."
        )
        return

    try:
        from aplicativos.automacao.otrs_kpi_scraper import (
            rodar_pipeline_kpi,
        )

        logger.info(
            "[KPI] >>> Iniciando atualizacao dos KPIs..."
        )

        resultado = rodar_pipeline_kpi()

        logger.info(
            "[KPI] <<< Atualizacao dos KPIs encerrada | resultado=%s",
            resultado,
        )

    except Exception:
        logger.exception(
            "[KPI] Erro nao tratado durante atualizacao dos KPIs."
        )

    finally:
        _trava_otrs.release()


# ───────────────────────────────────────────────────────────────
# LIMPEZA DE JOBS ANTIGOS
# ───────────────────────────────────────────────────────────────

def _limpar_jobs_antigos():
    """
    Remove do banco os jobs persistidos que não pertencem à configuração atual.

    Isso evita:
    - execução duplicada;
    - jobs antigos do ciclo completo;
    - concorrência de logins;
    - múltiplas instâncias do Playwright.
    """

    try:
        from django_apscheduler.models import DjangoJob

        ids_validos = [
            "job_coleta_envio",
            "job_busca_registro",
            "job_kpi",
        ]

        jobs_antigos = DjangoJob.objects.exclude(
            id__in=ids_validos
        )

        quantidade = jobs_antigos.count()

        if quantidade:
            jobs_antigos.delete()

            logger.warning(
                "[SCHEDULER] %d job(s) antigo(s) removido(s) do banco.",
                quantidade,
            )

    except Exception:
        logger.exception(
            "[SCHEDULER] Falha ao limpar jobs antigos."
        )


# ───────────────────────────────────────────────────────────────
# INICIALIZAÇÃO DO SCHEDULER (Essa era a parte que faltava no seu!)
# ───────────────────────────────────────────────────────────────

def iniciar_scheduler():
    """
    Inicializa o scheduler com três jobs independentes.

    Retorna a instância ativa do scheduler.
    """

    global _scheduler

    # Evita iniciar o scheduler duas vezes dentro do mesmo processo.
    if _scheduler is not None and _scheduler.running:
        logger.warning(
            "[SCHEDULER] Tentativa de iniciar uma segunda "
            "instancia ignorada."
        )
        return _scheduler

    scheduler = BackgroundScheduler(
        timezone="America/Sao_Paulo"
    )

    scheduler.add_jobstore(
        DjangoJobStore(),
        "default",
    )

    _limpar_jobs_antigos()

    # -----------------------------------------------------------
    # JOB 1 — COLETA E ENVIO
    # Todo minuto, no segundo 00.
    # -----------------------------------------------------------
    scheduler.add_job(
        _executar_coleta_envio,
        trigger=CronTrigger(
            minute="*",
            second="0",
        ),
        id="job_coleta_envio",
        name="Broker - Coleta e envio",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    # -----------------------------------------------------------
    # JOB 2 — BUSCA OTRS E REGISTRO CLARO
    # Todo minuto, no segundo 30.
    # -----------------------------------------------------------
    scheduler.add_job(
        _executar_busca_registro,
        trigger=CronTrigger(
            minute="*",
            second="30",
        ),
        id="job_busca_registro",
        name="Broker - Busca OTRS e registro Claro",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    # -----------------------------------------------------------
    # JOB 3 — ATUALIZAÇÃO DE KPIs
    # A cada 5 minutos, no segundo 45.
    # -----------------------------------------------------------
    scheduler.add_job(
        _executar_kpi,
        trigger=CronTrigger(
            minute="*/5",
            second="45",
        ),
        id="job_kpi",
        name="OTRS - Atualizador de KPIs",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.start()

    _scheduler = scheduler

    logger.info(
        "[SCHEDULER] Scheduler iniciado com 3 jobs: "
        "job_coleta_envio, job_busca_registro e job_kpi."
    )

    logger.info(
        "[SCHEDULER] Frequencias: "
        "coleta/envio=1 minuto | "
        "busca/registro=1 minuto | "
        "KPI=5 minutos."
    )

    return scheduler
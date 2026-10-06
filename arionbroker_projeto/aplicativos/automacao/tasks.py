import os
import logging
from datetime import timedelta

from django.utils import timezone

# Permite o uso controlado do ORM nas threads executadas pelo scheduler.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from aplicativos.core_broker.models import (
    TicketREC,
    StatusEnvio,
    OrigemAcao,
    ConfiguracaoRobo,
)
from aplicativos.comunicacao.services import disparar_email
from aplicativos.automacao.scraper import executar_scraper


logger = logging.getLogger(__name__)

# Tempo máximo que uma REC pode permanecer aguardando ticket no OTRS.
# 1440 minutos = 24 horas.
TIMEOUT_TICKET_MINUTOS = 1440


def _robo_esta_ativo() -> bool:
    """
    Retorna True quando a automação estiver habilitada nas configurações.
    """
    try:
        config = ConfiguracaoRobo.get_ou_criar()
        return bool(config.ativo)
    except Exception:
        logger.exception(
            "[ROBÔ] Não foi possível consultar a configuração da automação."
        )
        return False


# ───────────────────────────────────────────────────────────────
# ETAPA 1 — COLETA E ENVIO
# ───────────────────────────────────────────────────────────────

def _etapa_coleta_e_envio() -> dict:
    """
    Executa somente a etapa rápida do Broker:

    1. Consulta o portal da Claro.
    2. Salva as novas RECs.
    3. Envia os e-mails das RECs com status NOVO.
    4. Marca as RECs como ENVIADO.

    Não consulta o OTRS e não registra o ticket na Claro.
    """

    logger.info(
        "[ROBÔ] --- Iniciando Etapa 1: Coleta e Envio ---"
    )

    resultado_final = {
        "coleta_executada": False,
        "novas": 0,
        "ignoradas": 0,
        "erros_coleta": [],
        "emails_enviados": 0,
        "erros_envio": [],
    }

    # -----------------------------------------------------------
    # 1. Coleta das RECs no Broker/Claro
    # -----------------------------------------------------------
    try:
        resultado = executar_scraper(
            origem=OrigemAcao.AUTOMATICA,
            executor="robô",
        )

        resultado_final["coleta_executada"] = True
        resultado_final["novas"] = resultado.get("novas", 0)
        resultado_final["ignoradas"] = resultado.get("ignoradas", 0)
        resultado_final["erros_coleta"] = resultado.get("erros", [])

        logger.info(
            "[ROBÔ] Coleta — Novas: %s | Ignoradas: %s | Erros: %s",
            resultado_final["novas"],
            resultado_final["ignoradas"],
            len(resultado_final["erros_coleta"]),
        )

    except Exception as erro:
        logger.exception(
            "[ROBÔ] Falha crítica durante a coleta: %s",
            erro,
        )

        resultado_final["erros_coleta"].append(str(erro))

        # Se a coleta falhar, ainda tentamos enviar RECs NOVO que já estejam
        # salvas no banco por uma execução anterior.
        logger.warning(
            "[ROBÔ] A coleta falhou, mas o sistema verificará RECs NOVO "
            "já existentes no banco."
        )

    # -----------------------------------------------------------
    # 2. Busca das RECs pendentes de envio
    # -----------------------------------------------------------
    try:
        pendentes = list(
            TicketREC.objects.filter(
                status_envio=StatusEnvio.NOVO
            ).order_by(
                "data_coleta",
                "id",
            )
        )

    except Exception:
        logger.exception(
            "[ROBÔ] Falha ao consultar RECs pendentes de envio."
        )
        return resultado_final

    if not pendentes:
        logger.info(
            "[ROBÔ] Nenhuma REC pendente para envio de e-mail."
        )
        return resultado_final

    logger.info(
        "[ROBÔ] %d REC(s) pendente(s) para envio de e-mail.",
        len(pendentes),
    )

    # -----------------------------------------------------------
    # 3. Envio dos e-mails
    # -----------------------------------------------------------
    for rec in pendentes:
        try:
            logger.info(
                "[ROBÔ] Enviando e-mail da REC %s...",
                rec.rec_id,
            )

            disparar_email(rec)

            momento_envio = timezone.now()

            atualizado = TicketREC.objects.filter(
                pk=rec.pk,
                status_envio=StatusEnvio.NOVO,
            ).update(
                status_envio=StatusEnvio.ENVIADO,
                data_envio=momento_envio,
                origem_envio=OrigemAcao.AUTOMATICA,
                enviado_por="robô",
            )

            if atualizado:
                resultado_final["emails_enviados"] += 1

                logger.info(
                    "[ROBÔ] E-mail enviado: REC %s",
                    rec.rec_id,
                )
            else:
                logger.warning(
                    "[ROBÔ] O e-mail da REC %s foi disparado, mas o status "
                    "não foi atualizado porque a REC já havia sido alterada "
                    "por outro processo.",
                    rec.rec_id,
                )

        except Exception as erro:
            mensagem_erro = (
                f"REC {rec.rec_id}: {erro}"
            )

            resultado_final["erros_envio"].append(
                mensagem_erro
            )

            logger.exception(
                "[ROBÔ] Erro ao enviar e-mail da REC %s: %s",
                rec.rec_id,
                erro,
            )

    logger.info(
        "[ROBÔ] Etapa 1 concluída. %d e-mail(s) enviado(s).",
        resultado_final["emails_enviados"],
    )

    if resultado_final["erros_envio"]:
        logger.warning(
            "[ROBÔ] Etapa 1 terminou com %d erro(s) de envio.",
            len(resultado_final["erros_envio"]),
        )

    return resultado_final


# ───────────────────────────────────────────────────────────────
# ETAPA 2 — BUSCA NO OTRS E REGISTRO NA CLARO
# ───────────────────────────────────────────────────────────────

def _etapa_busca_e_registro() -> dict:
    """
    Executa somente a etapa de acompanhamento:

    1. Busca no OTRS os tickets das RECs com e-mail já enviado.
    2. Salva o número do ticket encontrado.
    3. Registra o ticket no portal da Claro.
    4. Marca a REC como REGISTRADO.
    5. Envia para REVISÃO as RECs que ultrapassarem o timeout.

    Esta função não coleta novas RECs e não envia e-mails.
    """

    from aplicativos.automacao.otrs_scraper import buscar_tickets_otrs
    from aplicativos.automacao.claro_registro import (
        registrar_tickets_no_claro,
    )

    resultado_final = {
        "recs_aguardando": 0,
        "recs_expiradas": 0,
        "tickets_encontrados": 0,
        "recs_registradas": 0,
        "falhas_registro": 0,
    }

    agora = timezone.now()
    limite_timeout = agora - timedelta(
        minutes=TIMEOUT_TICKET_MINUTOS
    )

    # -----------------------------------------------------------
    # 1. Verifica se existem RECs aguardando processamento
    # -----------------------------------------------------------
    try:
        existe_rec_enviada = TicketREC.objects.filter(
            status_envio=StatusEnvio.ENVIADO
        ).exists()

    except Exception:
        logger.exception(
            "[REGISTRO] Falha ao verificar RECs enviadas."
        )
        return resultado_final

    if not existe_rec_enviada:
        logger.debug(
            "[REGISTRO] Nenhuma REC aguardando ticket no OTRS."
        )
        return resultado_final

    logger.info(
        "[REGISTRO] --- Iniciando Etapa 2: Busca e Registro ---"
    )

    # -----------------------------------------------------------
    # 2. RECs enviadas que ainda não possuem ticket OTRS
    # -----------------------------------------------------------
    recs_para_buscar = TicketREC.objects.filter(
        status_envio=StatusEnvio.ENVIADO,
        ticket_otrs="",
    )

    # Compatibilidade caso existam registros antigos com NULL.
    recs_para_buscar_nulas = TicketREC.objects.filter(
        status_envio=StatusEnvio.ENVIADO,
        ticket_otrs__isnull=True,
    )

    ids_busca = set(
        recs_para_buscar.values_list(
            "pk",
            flat=True,
        )
    )

    ids_busca.update(
        recs_para_buscar_nulas.values_list(
            "pk",
            flat=True,
        )
    )

    recs_sem_ticket = TicketREC.objects.filter(
        pk__in=ids_busca
    )

    # -----------------------------------------------------------
    # 3. Timeout
    # -----------------------------------------------------------
    timeout_qs = recs_sem_ticket.filter(
        data_envio__isnull=False,
        data_envio__lt=limite_timeout,
    )

    ids_expiradas = list(
        timeout_qs.values_list(
            "rec_id",
            flat=True,
        )
    )

    if ids_expiradas:
        resultado_final["recs_expiradas"] = len(
            ids_expiradas
        )

        logger.warning(
            "[REGISTRO] RECs expiradas sem ticket e enviadas para Revisão: %s",
            ids_expiradas,
        )

        timeout_qs.update(
            status_envio=StatusEnvio.REVISAO
        )

    # -----------------------------------------------------------
    # 4. RECs ainda dentro do prazo
    # -----------------------------------------------------------
    recs_vivas_qs = recs_sem_ticket.filter(
        data_envio__isnull=False,
        data_envio__gte=limite_timeout,
    ).order_by(
        "data_envio",
        "id",
    )

    recs_vivas = list(recs_vivas_qs)

    resultado_final["recs_aguardando"] = len(
        recs_vivas
    )

    if recs_vivas:
        logger.info(
            "[REGISTRO] %d REC(s) aguardando ticket no OTRS.",
            len(recs_vivas),
        )

        try:
            tickets_achados = buscar_tickets_otrs(
                recs_vivas
            ) or {}

            resultado_final["tickets_encontrados"] = len(
                tickets_achados
            )

            for rec_id, numero_ticket in tickets_achados.items():
                numero_ticket = str(
                    numero_ticket or ""
                ).strip()

                if not numero_ticket:
                    continue

                atualizado = TicketREC.objects.filter(
                    rec_id=str(rec_id),
                    status_envio=StatusEnvio.ENVIADO,
                ).update(
                    ticket_otrs=numero_ticket
                )

                if atualizado:
                    logger.info(
                        "[REGISTRO] [OK] REC %s -> Ticket OTRS %s associado",
                        rec_id,
                        numero_ticket,
                    )

        except Exception as erro:
            logger.exception(
                "[REGISTRO] Erro durante a busca no OTRS: %s",
                erro,
            )

    else:
        logger.info(
            "[REGISTRO] Nenhuma REC dentro do prazo aguardando ticket."
        )

    # -----------------------------------------------------------
    # 5. RECs com ticket encontrado, prontas para registrar
    # -----------------------------------------------------------
    recs_para_registrar = list(
        TicketREC.objects.filter(
            status_envio=StatusEnvio.ENVIADO
        ).exclude(
            ticket_otrs=""
        ).exclude(
            ticket_otrs__isnull=True
        ).order_by(
            "data_envio",
            "id",
        )
    )

    if not recs_para_registrar:
        logger.info(
            "[REGISTRO] Nenhuma REC pronta para registro na Claro."
        )
        return resultado_final

    logger.info(
        "[REGISTRO] %d REC(s) pronta(s) para registro na Claro.",
        len(recs_para_registrar),
    )

    dict_tickets = {
        str(rec.rec_id): str(rec.ticket_otrs).strip()
        for rec in recs_para_registrar
        if str(rec.ticket_otrs or "").strip()
    }

    if not dict_tickets:
        return resultado_final

    # -----------------------------------------------------------
    # 6. Registro no portal da Claro
    # -----------------------------------------------------------
    try:
        resultados = registrar_tickets_no_claro(
            dict_tickets
        ) or {}

    except Exception as erro:
        logger.exception(
            "[REGISTRO] Erro geral no registro da Claro: %s",
            erro,
        )
        return resultado_final

    for rec_id, sucesso in resultados.items():
        if sucesso:
            atualizado = TicketREC.objects.filter(
                rec_id=str(rec_id),
                status_envio=StatusEnvio.ENVIADO,
            ).update(
                status_envio=StatusEnvio.REGISTRADO
            )

            if atualizado:
                resultado_final["recs_registradas"] += 1

                logger.info(
                    "[REGISTRO] [OK] REC %s finalizada com sucesso "
                    "(Concluído).",
                    rec_id,
                )

        else:
            resultado_final["falhas_registro"] += 1

            logger.warning(
                "[REGISTRO] [FALHA] REC %s não aceitou o registro "
                "na Claro e será tentada novamente.",
                rec_id,
            )

    logger.info(
        "[REGISTRO] Etapa 2 concluída | "
        "Aguardando: %d | "
        "Tickets encontrados: %d | "
        "Registradas: %d | "
        "Falhas: %d | "
        "Expiradas: %d",
        resultado_final["recs_aguardando"],
        resultado_final["tickets_encontrados"],
        resultado_final["recs_registradas"],
        resultado_final["falhas_registro"],
        resultado_final["recs_expiradas"],
    )

    return resultado_final


# ───────────────────────────────────────────────────────────────
# JOB PÚBLICO — COLETA E ENVIO
# ───────────────────────────────────────────────────────────────

def job_coleta_e_envio():
    """
    Job independente utilizado pelo scheduler.

    Deve rodar a cada minuto para:
    - capturar novas RECs;
    - enviar os e-mails imediatamente.
    """

    if not _robo_esta_ativo():
        logger.info(
            "[COLETA] Modo automático desativado."
        )
        return {
            "ativo": False,
        }

    logger.info(
        "[COLETA] >>> Iniciando job de coleta e envio <<<"
    )

    try:
        resultado = _etapa_coleta_e_envio()

        logger.info(
            "[COLETA] <<< Job de coleta e envio encerrado >>>"
        )

        return resultado

    except Exception:
        logger.exception(
            "[COLETA] Falha não tratada no job de coleta e envio."
        )
        return {
            "ativo": True,
            "erro": True,
        }


# ───────────────────────────────────────────────────────────────
# JOB PÚBLICO — BUSCA OTRS E REGISTRO CLARO
# ───────────────────────────────────────────────────────────────

def job_busca_e_registro():
    """
    Job independente utilizado pelo scheduler.

    Deve rodar separadamente da coleta para:
    - procurar tickets já criados no OTRS;
    - registrar os tickets encontrados na Claro.
    """

    if not _robo_esta_ativo():
        logger.info(
            "[REGISTRO] Modo automático desativado."
        )
        return {
            "ativo": False,
        }

    logger.info(
        "[REGISTRO] >>> Iniciando job de busca e registro <<<"
    )

    try:
        resultado = _etapa_busca_e_registro()

        logger.info(
            "[REGISTRO] <<< Job de busca e registro encerrado >>>"
        )

        return resultado

    except Exception:
        logger.exception(
            "[REGISTRO] Falha não tratada no job de busca e registro."
        )
        return {
            "ativo": True,
            "erro": True,
        }


# ───────────────────────────────────────────────────────────────
# JOB PRINCIPAL — COMPATIBILIDADE
# ───────────────────────────────────────────────────────────────

def job_robo_mestre():
    """
    Mantém compatibilidade com chamadas antigas do sistema.

    Executa as duas etapas em sequência:

    1. Coleta e envio.
    2. Busca OTRS e registro Claro.

    O novo scheduler deve usar diretamente:
    - job_coleta_e_envio()
    - job_busca_e_registro()
    """

    if not _robo_esta_ativo():
        logger.info(
            "[ROBÔ MESTRE] Modo automático desativado."
        )
        return {
            "ativo": False,
        }

    logger.info(
        "[ROBÔ MESTRE] >>> Iniciando ciclo completo <<<"
    )

    resultado = {
        "ativo": True,
        "coleta_envio": None,
        "busca_registro": None,
    }

    try:
        resultado["coleta_envio"] = (
            _etapa_coleta_e_envio()
        )
    except Exception:
        logger.exception(
            "[ROBÔ MESTRE] Falha na etapa de coleta e envio."
        )

    try:
        resultado["busca_registro"] = (
            _etapa_busca_e_registro()
        )
    except Exception:
        logger.exception(
            "[ROBÔ MESTRE] Falha na etapa de busca e registro."
        )

    logger.info(
        "[ROBÔ MESTRE] <<< Ciclo completo encerrado >>>"
    )

    return resultado
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import ConfigEmailProjeto


logger = logging.getLogger(__name__)


# ==============================================================================
# NOMES DOS PROJETOS
# ==============================================================================

NOMES_EXTENSOS = {
    "BB": (
        "PROJETO BANCO DO BRASIL",
        "bb",
    ),
    "CAIXA": (
        "PROJETO CAIXA ECONÔMICA FEDERAL",
        "caixa",
    ),
    "CORREIOS": (
        "PROJETO CORREIOS (ECT)",
        "correios",
    ),
    "CARREFOUR": (
        "PROJETO CARREFOUR",
        "carrefour",
    ),
    "DIVERSOS": (
        "PROJETO DIVERSOS / TRIAGEM",
        "diversos",
    ),
}


# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

def normalizar_email(email):
    """
    Remove espaços e normaliza um endereço de e-mail.
    """

    if not email:
        return ""

    return email.strip()


def remover_duplicados(emails):
    """
    Remove endereços vazios e duplicados sem alterar a ordem.
    """

    resultado = []
    vistos = set()

    for email in emails:

        email = normalizar_email(email)

        if not email:
            continue

        chave = email.lower()

        if chave in vistos:
            continue

        vistos.add(chave)
        resultado.append(email)

    return resultado


# ==============================================================================
# FLUXO NORMAL - REC / BROKER
# ==============================================================================

def montar_assunto(rec) -> str:
    """
    Exemplo:

    [BANCO DO BRASIL] - SOLICITAÇÃO DE TRATATIVA
    - REC: 12345 - BL: BL30000000000
    """

    projeto_info = NOMES_EXTENSOS.get(
        rec.projeto,
        (
            "PROJETO NÃO IDENTIFICADO",
            "diversos",
        ),
    )

    nome_projeto_limpo = projeto_info[0].replace(
        "PROJETO ",
        "",
    )

    return (
        f"[{nome_projeto_limpo}] "
        f"- SOLICITAÇÃO DE TRATATIVA "
        f"- REC: {rec.rec_id} "
        f"- BL: {rec.bl_dados}"
    )


def obter_destinatarios(rec):
    """
    FLUXO:

    PARA:
        Sempre envia para a caixa monitorada pelo OTRS.

    CC:
        Destinatários configurados no painel do ARION.

    Dessa forma o OTRS sempre recebe a REC para criar o ticket.
    """

    destino_otrs = normalizar_email(
        settings.EMAIL_DESTINO_PADRAO
    )

    para = [destino_otrs]

    cc = []

    config_email = ConfigEmailProjeto.objects.filter(
        projeto=rec.projeto,
        ativo=True,
    ).first()

    if config_email:

        if config_email.destinatarios:
            cc.extend(
                config_email.lista_destinatarios()
            )

        if config_email.cc:
            cc.extend(
                config_email.lista_cc()
            )

    cc = remover_duplicados(cc)

    # Remove o próprio OTRS do CC caso alguém tenha cadastrado
    # o endereço também na tela de Destinos.
    cc = [
        email
        for email in cc
        if email.lower() != destino_otrs.lower()
    ]

    return para, cc


def disparar_email(rec):
    """
    Envia a solicitação de tratativa da REC.

    O OTRS é sempre o destinatário principal.
    Destinos cadastrados no painel recebem cópia.
    """

    projeto_info = NOMES_EXTENSOS.get(
        rec.projeto,
        (
            "PROJETO NÃO IDENTIFICADO",
            "diversos",
        ),
    )

    nome_projeto = projeto_info[0]
    slug_projeto = projeto_info[1]

    data_portal = rec.data_principal_ordenacao

    if data_portal:
        data_formatada = data_portal.strftime(
            "%d/%m/%Y %H:%M:%S"
        )
    else:
        data_formatada = "Não informada"

    context = {
        "rec": rec,
        "projeto_nome": nome_projeto,
        "projeto_slug": slug_projeto,
        "data_portal": data_formatada,
        "agora": timezone.now(),
    }

    html_content = render_to_string(
        "comunicacao/emails.html",
        context,
    )

    text_content = strip_tags(
        html_content
    )

    para, cc = obter_destinatarios(rec)

    assunto = montar_assunto(rec)

    logger.info(
        "[EMAIL] Preparando REC %s | FROM=%s | TO=%s | CC=%s",
        rec.rec_id,
        settings.DEFAULT_FROM_EMAIL,
        para,
        cc,
    )

    email = EmailMultiAlternatives(
        subject=assunto,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=para,
        cc=cc,
    )

    email.attach_alternative(
        html_content,
        "text/html",
    )

    try:

        quantidade = email.send(
            fail_silently=False
        )

        if quantidade != 1:

            raise RuntimeError(
                "SMTP retornou quantidade inesperada "
                f"de mensagens: {quantidade}"
            )

        logger.info(
            "[EMAIL] SMTP ACEITOU REC %s | TO=%s | CC=%s",
            rec.rec_id,
            para,
            cc,
        )

        print(
            f"[EMAIL] SMTP ACEITOU REC {rec.rec_id} "
            f"| TO={para} "
            f"| CC={cc}",
            flush=True,
        )

        return True

    except Exception:

        logger.exception(
            "[EMAIL] Falha SMTP na REC %s",
            rec.rec_id,
        )

        print(
            f"[EMAIL] ERRO SMTP REC {rec.rec_id}",
            flush=True,
        )

        raise


# ==============================================================================
# RREIP - REINCIDÊNCIAS
# ==============================================================================

def montar_assunto_monitoramento(
    reincidencia,
) -> str:

    projeto = (
        reincidencia.projeto
        or "PROJETO NÃO IDENTIFICADO"
    ).strip()

    projeto_info = NOMES_EXTENSOS.get(
        projeto.upper()
    )

    if projeto_info:

        nome_projeto_limpo = projeto_info[0].replace(
            "PROJETO ",
            "",
        )

    else:

        nome_projeto_limpo = projeto.upper()

    designacao = (
        reincidencia.designacao
        or "SEM DESIGNAÇÃO"
    )

    identificador = (
        reincidencia.get_identificador_formatado()
    )

    partes = [
        f"[{nome_projeto_limpo}]",
        "SOLICITAÇÃO DE MONITORAMENTO RREIP",
        f"BL: {designacao}",
    ]

    if identificador:
        partes.append(identificador)

    return " - ".join(partes)


def obter_destinatarios_monitoramento(
    reincidencia,
):
    """
    Mesmo comportamento do fluxo principal:

    PARA:
        Caixa monitorada pelo OTRS.

    CC:
        Destinatários configurados no painel.
    """

    destino_otrs = normalizar_email(
        settings.EMAIL_DESTINO_PADRAO
    )

    para = [destino_otrs]

    cc = []

    config_email = ConfigEmailProjeto.objects.filter(
        projeto=reincidencia.projeto,
        ativo=True,
    ).first()

    if config_email:

        if config_email.destinatarios:

            cc.extend(
                config_email.lista_destinatarios()
            )

        if config_email.cc:

            cc.extend(
                config_email.lista_cc()
            )

    cc = remover_duplicados(cc)

    cc = [
        email
        for email in cc
        if email.lower() != destino_otrs.lower()
    ]

    return para, cc


def montar_contexto_monitoramento(
    reincidencia,
    usuario=None,
):

    projeto_info = NOMES_EXTENSOS.get(
        (reincidencia.projeto or "").upper(),
        (
            "PROJETO NÃO IDENTIFICADO",
            "diversos",
        ),
    )

    slug_projeto = projeto_info[1]

    data_abertura = (
        reincidencia.data_ticket_origem
    )

    data_encerramento = (
        reincidencia.data_encerramento_origem
    )

    return {
        "reincidencia": reincidencia,
        "ticket_origem": (
            reincidencia.ticket_origem
            or reincidencia.ticket_atual
        ),
        "cliente": reincidencia.cliente,
        "operadora": reincidencia.operadora,
        "projeto_slug": slug_projeto,
        "projeto": reincidencia.projeto,
        "designacao": reincidencia.designacao,
        "identificador": (
            reincidencia.get_identificador_formatado()
        ),
        "isp": reincidencia.isp,

        "data_abertura": (
            data_abertura.strftime(
                "%d/%m/%Y %H:%M"
            )
            if data_abertura
            else "Não informada"
        ),

        "data_encerramento": (
            data_encerramento.strftime(
                "%d/%m/%Y %H:%M"
            )
            if data_encerramento
            else "Não informada"
        ),

        "motivo_identificado": (
            reincidencia.motivo_identificado
        ),

        "causa_raiz": (
            reincidencia.causa_raiz
        ),

        "acao_realizada": (
            reincidencia.acao_realizada
        ),

        "acao_preventiva": (
            reincidencia.acao_preventiva
        ),

        "conclusao": (
            reincidencia.conclusao
        ),

        "responsavel": (
            usuario
            or reincidencia.responsavel
        ),

        "agora": timezone.now(),
    }


def renderizar_email_monitoramento(
    reincidencia,
    usuario=None,
):

    context = montar_contexto_monitoramento(
        reincidencia,
        usuario,
    )

    html_content = render_to_string(
        "comunicacao/email_monitoramento_reincidencia.html",
        context,
    )

    text_content = strip_tags(
        html_content
    )

    return html_content, text_content


def disparar_email_monitoramento(
    reincidencia,
    usuario=None,
):

    assunto = montar_assunto_monitoramento(
        reincidencia
    )

    para, cc = obter_destinatarios_monitoramento(
        reincidencia
    )

    html_content, text_content = (
        renderizar_email_monitoramento(
            reincidencia,
            usuario,
        )
    )

    logger.info(
        "[EMAIL RREIP] Preparando ID=%s | FROM=%s | TO=%s | CC=%s",
        reincidencia.id,
        settings.DEFAULT_FROM_EMAIL,
        para,
        cc,
    )

    email = EmailMultiAlternatives(
        subject=assunto,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=para,
        cc=cc,
    )

    email.attach_alternative(
        html_content,
        "text/html",
    )

    try:

        quantidade = email.send(
            fail_silently=False
        )

        if quantidade != 1:

            raise RuntimeError(
                "SMTP retornou quantidade inesperada "
                f"de mensagens: {quantidade}"
            )

        logger.info(
            "[EMAIL RREIP] SMTP ACEITOU | ID=%s | TO=%s | CC=%s",
            reincidencia.id,
            para,
            cc,
        )

        print(
            "[EMAIL RREIP] SMTP ACEITOU "
            f"| ID={reincidencia.id} "
            f"| TO={para} "
            f"| CC={cc}",
            flush=True,
        )

    except Exception:

        logger.exception(
            "[EMAIL RREIP] Falha SMTP no ID %s",
            reincidencia.id,
        )

        raise

    return {
        "assunto": assunto,
        "destinatarios": para,
        "cc": cc,
    }
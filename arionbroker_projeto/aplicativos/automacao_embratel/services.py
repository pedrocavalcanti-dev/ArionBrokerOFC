"""
services.py

Regras de negócio e integração de e-mail para a automação Embratel.
Responsável por:
  - Avaliar elegibilidade de tarefas para envio;
  - Evitar duplicidade de envios e concorrência (select_for_update);
  - Montar contexto, assunto e corpo HTML (com fallback);
  - Resolver e validar destinatários;
  - Chamar o serviço de envio de e-mail integrado ou nativo.
  
Não interage com APIs do Modos Web.
Não possui tasks ou agendamentos.
"""

import os
import smtplib
import unicodedata
from typing import Any, Optional, Tuple, List, Dict, Iterable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, BadHeaderError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe

from . import logs
from .models import TarefaEmbratel, StatusProcessamentoEmbratel


# ══════════════════════════════════════════════════════════════
#  UTILITÁRIOS DE AMBIENTE E TEXTO
# ══════════════════════════════════════════════════════════════

def ler_booleano_ambiente(nome: str, padrao: bool = False) -> bool:
    """Lê booleanos do ambiente de forma resiliente."""
    valor = os.getenv(nome, "").strip().lower()
    if not valor:
        return padrao
    return valor in ("1", "true", "sim", "yes", "on", "t", "s", "y")


def ler_lista_ambiente(nome: str) -> List[str]:
    """Lê variáveis separadas por vírgula ou ponto e vírgula, retornando lista limpa."""
    valor = os.getenv(nome, "").strip()
    if not valor:
        return []
    
    itens = valor.replace(";", ",").split(",")
    lista_limpa = []
    for item in itens:
        limpo = item.strip()
        if limpo and limpo not in lista_limpa:
            lista_limpa.append(limpo)
    return lista_limpa


def normalizar_texto_comparacao(valor: Any) -> str:
    """Converte para string limpa, sem acentos e em minúsculas para comparações seguras."""
    if valor is None:
        return ""
    texto = str(valor).strip().lower()
    texto_sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn'
    )
    return texto_sem_acento


def mascarar_email(email: str) -> str:
    """Oculta parte do e-mail para exibição segura em logs."""
    if not email or "@" not in email:
        return "***"
    usuario, dominio = email.split("@", 1)
    if len(usuario) <= 2:
        return f"***@{dominio}"
    return f"{usuario[0]}***@{dominio}"


def normalizar_lista_emails(valor: Any) -> List[str]:
    """
    Desestrutura strings e coleções em uma lista limpa, sem duplicatas,
    validando cada formato de e-mail e mantendo a ordem original.
    """
    if not valor:
        return []
    
    itens_brutos = []
    if isinstance(valor, str):
        itens_brutos = valor.replace(";", ",").split(",")
    elif isinstance(valor, (list, tuple, set)):
        itens_brutos = list(valor)
    else:
        return []

    validados = []
    for item in itens_brutos:
        if not isinstance(item, str):
            continue
        limpo = item.strip().lower()
        if not limpo or limpo in validados:
            continue
        try:
            validate_email(limpo)
            validados.append(limpo)
        except ValidationError:
            continue
            
    return validados


def resolver_destinatarios(
    tarefa: TarefaEmbratel, 
    destinatarios: Optional[Any] = None, 
    copias: Optional[Any] = None
) -> Tuple[List[str], List[str]]:
    """
    Aplica ordem de prioridade para descobrir destinatários e cópias.
    Garante que não haja interseção entre 'to' e 'cc'.
    """
    dt = tarefa.dados_tecnicos or {}
    
    # Resolver principais
    if destinatarios:
        brutos_to = destinatarios
    else:
        brutos_to = dt.get("destinatarios") or dt.get("emails") or dt.get("email") or os.getenv("EMBRATEL_DESTINATARIOS_PADRAO")
    
    lista_to = normalizar_lista_emails(brutos_to)

    # Resolver cópias
    if copias:
        brutos_cc = copias
    else:
        brutos_cc = dt.get("copias") or dt.get("cc") or os.getenv("EMBRATEL_COPIAS_PADRAO")
        
    lista_cc = normalizar_lista_emails(brutos_cc)
    
    # Remover do CC quem já está no TO
    lista_cc_limpa = [cc for cc in lista_cc if cc not in lista_to]
    
    return lista_to, lista_cc_limpa


def obter_mapa_tarefa(tarefa: TarefaEmbratel) -> Optional[str]:
    """Lê o mapa (ex: DS102) de dentro do JSON técnico de forma segura."""
    dt = tarefa.dados_tecnicos or {}
    mapa = dt.get("mapa_tarefa")
    return str(mapa).strip() if mapa else None


def obter_numero_rec(tarefa: TarefaEmbratel) -> str:
    """
    Identifica a REC específica do chamado (ex: BRAD2907-1-3373793389).
    A REC é o identificador do chamado; a DS é apenas a etapa em que ele está.
    Cai para id_portal como último recurso caso a REC não tenha sido capturada.
    """
    dt = tarefa.dados_tecnicos or {}
    rec = dt.get("numero_rec")
    if rec:
        return str(rec).strip()
    return str(tarefa.id_portal or "").strip()


def tarefa_esta_em_ds102(tarefa: TarefaEmbratel) -> bool:
    """
    Verifica se a REC desta tarefa está atualmente na etapa DS102.
    Esta é a ÚNICA fonte de verdade sobre a etapa — usada tanto na view
    quanto no service, para não haver divergência entre as duas checagens.

    Importante: DS é só a etapa atual do chamado, não o identificador dele.
    Duas RECs diferentes podem estar na mesma DS (ex: DS118) ao mesmo tempo
    sem qualquer conflito, pois cada uma é uma linha própria (id_portal único).
    """
    if tarefa.tipo_tarefa and tarefa.tipo_tarefa.strip().upper().startswith("DS102"):
        return True

    mapa = obter_mapa_tarefa(tarefa)
    if mapa and mapa.strip().upper() == "DS102":
        return True

    return False


# ══════════════════════════════════════════════════════════════
#  IDENTIFICAÇÃO AUTOMÁTICA DE PROJETO
# ══════════════════════════════════════════════════════════════

# Mapa de palavras-chave -> nome canônico do projeto.
# A ordem importa apenas em caso de ambiguidade entre chaves parecidas;
# mantenha os termos mais específicos antes dos mais genéricos.
MAPA_PALAVRAS_CHAVE_PROJETO: List[Tuple[str, str]] = [
    ("BRADESCO", "BRADESCO"),
    ("BRAD", "BRADESCO"),
    ("CORREIOS", "CORREIOS"),
    ("CAIXA ECONOMICA", "CEF"),
    ("CEF", "CEF"),
    ("BANCO DO BRASIL", "BANCO DO BRASIL"),
    ("BB#", "BANCO DO BRASIL"),
    ("CARREFOUR", "CARREFOUR"),
    ("MC DONALDS", "MC DONALDS"),
    ("MCDONALDS", "MC DONALDS"),
]


def identificar_projeto(tarefa: TarefaEmbratel) -> str:
    """
    Identifica automaticamente o projeto a partir dos dados da tarefa.

    O campo `tarefa.projeto` nem sempre vem preenchido pelo Modos Web,
    mas o prefixo do cliente costuma aparecer embutido na REC, na
    designação, no circuito ou no nome do cliente (ex: "BRAD2907-1-...",
    "BRAD#1821-00#04"). Esta função varre esses campos em busca de
    palavras-chave conhecidas antes de cair no valor bruto de
    `tarefa.projeto` (ou "Não especificado").
    """
    dt = tarefa.dados_tecnicos or {}

    valores = [
        tarefa.projeto,
        getattr(tarefa, "id_processo", None),
        getattr(tarefa, "id_workflow", None),
        tarefa.designacao,
        tarefa.circuito,
        tarefa.cliente,
        obter_numero_rec(tarefa),
        dt.get("projeto"),
    ]

    texto = " ".join(
        str(valor).upper().strip()
        for valor in valores
        if valor
    )

    for palavra_chave, nome_projeto in MAPA_PALAVRAS_CHAVE_PROJETO:
        if palavra_chave in texto:
            return nome_projeto

    return str(tarefa.projeto).strip() if tarefa.projeto else "Não especificado"


# ══════════════════════════════════════════════════════════════
#  ELEGIBILIDADE E REGRAS DE NEGÓCIO
# ══════════════════════════════════════════════════════════════

def avaliar_elegibilidade_envio(tarefa: TarefaEmbratel) -> Dict:
    """
    Verifica minuciosamente se a tarefa atende a todos os critérios 
    para disparo automático de e-mail.

    A regra de etapa NÃO depende mais de listas configuradas no .env
    (EMBRATEL_TAREFAS_ELEGIVEIS / EMBRATEL_MAPAS_ELEGIVEIS). O fluxo do
    Modos Web já informa isso na própria tarefa: se a REC está em DS102,
    ela é elegível; se mudou de etapa (DS118, DS200, etc.), deixa de ser.
    A duplicidade de envio continua sendo controlada pela REC/id_portal
    específicos desta tarefa (linha única no banco), nunca pela DS.
    """
    if not tarefa or not tarefa.pk:
        return {"elegivel": False, "motivo": "Tarefa inválida.", "codigo": "TAREFA_INVALIDA"}

    # 1. Chave global de envio
    envio_ativo = ler_booleano_ambiente("EMBRATEL_ENVIO_ATIVO", padrao=False)
    if not envio_ativo:
        return {"elegivel": False, "motivo": "Envio global desativado.", "codigo": "ENVIO_DESATIVADO"}

    # 2. Bloqueios de Status Interno
    status = tarefa.status_processamento
    if status == StatusProcessamentoEmbratel.ENVIANDO:
        return {"elegivel": False, "motivo": "Tarefa já está sendo enviada.", "codigo": "ENVIANDO"}
    if status == StatusProcessamentoEmbratel.ENVIADO:
        return {"elegivel": False, "motivo": "Tarefa já foi enviada.", "codigo": "JA_ENVIADA"}
    if status == StatusProcessamentoEmbratel.IGNORADO:
        return {"elegivel": False, "motivo": "Tarefa marcada para ser ignorada.", "codigo": "IGNORADA"}
    if status == StatusProcessamentoEmbratel.FINALIZADO:
        return {"elegivel": False, "motivo": "Tarefa finalizada no portal.", "codigo": "FINALIZADA"}

    # 3. Bloqueio por finalização no portal
    if tarefa.data_finalizacao_portal:
        return {"elegivel": False, "motivo": "Data de finalização preenchida.", "codigo": "FINALIZADA_PORTAL"}

    # 4. Limite de tentativas
    limite = int(os.getenv("EMBRATEL_LIMITE_TENTATIVAS", "3"))
    if tarefa.tentativas >= limite:
        return {"elegivel": False, "motivo": "Limite de tentativas excedido.", "codigo": "LIMITE_EXCEDIDO"}

    # 5. Dados Mínimos
    if not tarefa.id_portal or not (tarefa.cliente or tarefa.designacao) or not (tarefa.descricao or tarefa.sintoma):
        return {"elegivel": False, "motivo": "Dados insuficientes.", "codigo": "DADOS_INCOMPLETOS"}

    # 6. Regra de Negócio: a REC precisa estar atualmente na etapa DS102.
    #    A REC (numero_rec / id_portal) identifica o chamado; a DS é apenas
    #    a condição de etapa que libera ou não o envio.
    if not tarefa_esta_em_ds102(tarefa):
        return {
            "elegivel": False,
            "motivo": "A REC não está na etapa DS102.",
            "codigo": "NAO_ELEGIVEL",
        }

    return {"elegivel": True, "motivo": None, "codigo": "ELEGIVEL"}


# ══════════════════════════════════════════════════════════════
#  GERAÇÃO DE CONTEÚDO (E-MAIL)
# ══════════════════════════════════════════════════════════════

def construir_assunto_email(tarefa: TarefaEmbratel) -> str:
    """Monta a string do assunto formatado de forma limpa."""
    prefixo = os.getenv("EMBRATEL_ASSUNTO_PREFIXO", "REC EMBRATEL").strip()
    
    numero_rec = obter_numero_rec(tarefa)
    projeto = identificar_projeto(tarefa)
    cliente = str(tarefa.cliente or "Cliente não informado").strip()
    designacao = str(tarefa.designacao or "").strip()

    partes = [f"[{prefixo}]"]
    if projeto and projeto != "Não especificado":
        partes.append(f"[{projeto}]")
    if numero_rec:
        partes.append(numero_rec)
    if cliente:
        partes.append(f"- {cliente}")
    if designacao:
        partes.append(f"- {designacao}")

    assunto_bruto = " ".join(partes)
    assunto = " ".join(assunto_bruto.split())  # Remove espaços múltiplos
    return assunto[:255]


def construir_contexto_email(tarefa: TarefaEmbratel) -> Dict:
    """Prepara o dicionário de chaves injetáveis no template de e-mail."""
    dt = tarefa.dados_tecnicos or {}
    return {
        "tarefa": tarefa,
        "id_portal": tarefa.id_portal,
        "numero_rec": obter_numero_rec(tarefa),
        "numero_protocolo": dt.get("numero_protocolo"),
        "cliente": tarefa.cliente,
        "provedor": tarefa.provedor,
        "designacao": tarefa.designacao,
        "circuito": tarefa.circuito,
        "projeto": identificar_projeto(tarefa),
        "sintoma": tarefa.sintoma,
        "descricao": tarefa.descricao,
        "observacoes": dt.get("observacoes"),
        "tipo_tarefa": tarefa.tipo_tarefa,
        "mapa_tarefa": obter_mapa_tarefa(tarefa),
        "status_portal": tarefa.status_portal,
        "dentro_sla": tarefa.dentro_sla,
        "aging_minutos": tarefa.aging_minutos,
        "data_abertura": tarefa.data_criacao_portal,
        "url_tarefa": tarefa.url_tarefa,
    }


def construir_corpo_texto(tarefa: TarefaEmbratel, contexto: Optional[Dict] = None) -> str:
    """Gera versão plain-text legível, suprimindo itens vazios."""
    ctx = contexto or construir_contexto_email(tarefa)
    
    linhas = ["Olá,", "", "Foi identificada uma nova REC Embratel para tratamento.", ""]
    
    mapeamento = [
        ("REC", ctx.get("numero_rec") or ctx.get("id_portal")),
        ("Protocolo", ctx.get("numero_protocolo")),
        ("Projeto", ctx.get("projeto")),
        ("Cliente", ctx.get("cliente")),
        ("Designação", ctx.get("designacao")),
        ("Circuito", ctx.get("circuito")),
        ("Tipo da tarefa", ctx.get("tipo_tarefa")),
        ("Status", ctx.get("status_portal")),
        ("Sintoma", ctx.get("sintoma")),
        ("Descrição", ctx.get("descricao")),
    ]
    
    for rotulo, valor in mapeamento:
        if valor and str(valor).strip() not in ("None", ""):
            linhas.append(f"{rotulo}: {valor}")
            
    if ctx.get("url_tarefa"):
        linhas.extend(["", "Acesse o portal para mais informações:", str(ctx.get("url_tarefa"))])
        
    linhas.extend(["", "Atenciosamente,", "Arion Projetos"])
    return "\n".join(linhas)


def renderizar_corpo_html(tarefa: TarefaEmbratel, contexto: Optional[Dict] = None) -> str:
    """Tenta usar o template; se não existir, constrói HTML nativo e seguro."""
    ctx = contexto or construir_contexto_email(tarefa)
    template_path = "automacao_embratel/emails/abertura_rec_embratel.html"
    
    try:
        return render_to_string(template_path, ctx)
    except TemplateDoesNotExist:
        partes = [
            "<p>Olá,</p>",
            "<p>Foi identificada uma nova REC Embratel para tratamento.</p>",
            "<ul>"
        ]
        
        mapeamento = [
            ("REC", ctx.get("numero_rec") or ctx.get("id_portal")),
            ("Protocolo", ctx.get("numero_protocolo")),
            ("Projeto", ctx.get("projeto")),
            ("Cliente", ctx.get("cliente")),
            ("Designação", ctx.get("designacao")),
            ("Circuito", ctx.get("circuito")),
            ("Tipo da tarefa", ctx.get("tipo_tarefa")),
            ("Status", ctx.get("status_portal")),
        ]
        
        for rotulo, valor in mapeamento:
            if valor and str(valor).strip() not in ("None", ""):
                partes.append(f"<li><strong>{escape(rotulo)}:</strong> {escape(valor)}</li>")
                
        partes.append("</ul>")
        
        if ctx.get("descricao") and str(ctx.get("descricao")).strip() not in ("None", ""):
            partes.append(f"<p><strong>Descrição:</strong><br>{escape(ctx.get('descricao')).replace(chr(10), '<br>')}</p>")
            
        if ctx.get("url_tarefa"):
            partes.append(f'<p><a href="{escape(ctx.get("url_tarefa"))}">Acessar Tarefa no Portal</a></p>')
            
        partes.append("<p>Atenciosamente,<br>Arion Projetos</p>")
        
        return mark_safe("".join(partes))


# ══════════════════════════════════════════════════════════════
#  BACKEND DE INTEGRAÇÃO (SMTP)
# ══════════════════════════════════════════════════════════════

def obter_servico_envio_email() -> Any:
    """
    Retorna None para forçar a utilização do backend nativo do Django (EmailMultiAlternatives),
    compartilhando exatamente o mesmo SMTP/Brevo utilizado globalmente pelo Broker.
    """
    return None


def enviar_email_backend(
    assunto: str, 
    corpo_texto: str, 
    corpo_html: str, 
    destinatarios: List[str], 
    copias: List[str], 
    remetente: Optional[str] = None
) -> Dict:
    """Dispara a comunicação SMTP através do serviço disponível."""
    remetente = remetente or os.getenv("EMBRATEL_EMAIL_REMETENTE") or settings.DEFAULT_FROM_EMAIL
    
    # 1. Tenta serviço integrado (Caso esteja configurado)
    servico_integrado = obter_servico_envio_email()
    if servico_integrado:
        try:
            resultado = servico_integrado(
                assunto=assunto,
                mensagem=corpo_texto,
                mensagem_html=corpo_html,
                destinatarios=destinatarios,
                cc=copias,
                remetente=remetente
            )
            if isinstance(resultado, dict):
                return resultado
            return {"sucesso": True, "message_id": None, "erro": None}
        except Exception as e:
            return {"sucesso": False, "message_id": None, "erro": f"Falha no serviço integrado: {str(e)[:200]}"}

    # 2. Fallback nativo do Django utilizando as chaves globais de SMTP / Brevo
    try:
        mensagem = EmailMultiAlternatives(
            subject=assunto,
            body=corpo_texto,
            from_email=remetente,
            to=destinatarios,
            cc=copias,
        )
        mensagem.attach_alternative(corpo_html, "text/html")
        quantidade = mensagem.send(fail_silently=False)
        
        if quantidade > 0:
            return {"sucesso": True, "message_id": None, "erro": None}
        return {"sucesso": False, "message_id": None, "erro": "SMTP não reportou erro, mas não disparou a mensagem."}
        
    except smtplib.SMTPException as e:
        return {"sucesso": False, "message_id": None, "erro": f"Erro SMTP: {str(e)[:200]}"}
    except BadHeaderError:
        return {"sucesso": False, "message_id": None, "erro": "Cabeçalho de e-mail malformado."}
    except Exception as e:
        return {"sucesso": False, "message_id": None, "erro": f"Falha sistêmica no envio: {str(e)[:200]}"}


# ══════════════════════════════════════════════════════════════
#  TRANSAÇÕES DE ESTADO (BANCO)
# ══════════════════════════════════════════════════════════════

def marcar_tarefa_para_revisao(tarefa: TarefaEmbratel, motivo: str) -> None:
    """Aborta processamento e empurra tarefa para revisão manual."""
    tarefa.status_processamento = StatusProcessamentoEmbratel.REVISAO
    tarefa.erro_processamento = str(motivo)[:2000]
    tarefa.save(update_fields=['status_processamento', 'erro_processamento'])


def iniciar_tentativa_envio(tarefa_id: int) -> Optional[TarefaEmbratel]:
    """
    Aplica lock pessimista no banco para impedir duplo disparo.
    Retorna a instância da tarefa bloqueada para uso ou None se inválida.
    """
    with transaction.atomic():
        try:
            tarefa = TarefaEmbratel.objects.select_for_update().get(pk=tarefa_id)
        except TarefaEmbratel.DoesNotExist:
            return None

        if tarefa.status_processamento in (StatusProcessamentoEmbratel.ENVIANDO, StatusProcessamentoEmbratel.ENVIADO):
            return None
            
        tarefa.status_processamento = StatusProcessamentoEmbratel.ENVIANDO
        tarefa.tentativas += 1
        tarefa.erro_processamento = None
        tarefa.save(update_fields=['status_processamento', 'tentativas', 'erro_processamento'])
        
        return tarefa


def concluir_envio_sucesso(tarefa: TarefaEmbratel, enviado_por: Optional[str] = None, message_id: Optional[str] = None) -> None:
    """Registra envio bem sucedido liberando a transação."""
    with transaction.atomic():
        agora = timezone.now()
        tarefa.status_processamento = StatusProcessamentoEmbratel.ENVIADO
        tarefa.data_envio = agora
        tarefa.enviado_por = enviado_por or "sistema"
        tarefa.erro_processamento = None
        
        dt = tarefa.dados_tecnicos or {}
        dt["email_enviado_em"] = agora.isoformat()
        if message_id:
            dt["email_message_id"] = message_id
        tarefa.dados_tecnicos = dt
        
        tarefa.save(update_fields=['status_processamento', 'data_envio', 'enviado_por', 'erro_processamento', 'dados_tecnicos'])


def concluir_envio_falha(tarefa: TarefaEmbratel, erro: str) -> None:
    """Recua status se houve falha após tentativa, estourando limite pra revisão se necessário."""
    limite = int(os.getenv("EMBRATEL_LIMITE_TENTATIVAS", "3"))
    novo_status = StatusProcessamentoEmbratel.REVISAO if tarefa.tentativas >= limite else StatusProcessamentoEmbratel.ERRO

    tarefa.status_processamento = novo_status
    tarefa.erro_processamento = str(erro)[:2000]
    tarefa.save(update_fields=['status_processamento', 'erro_processamento'])


def marcar_pendente_envio(tarefa: TarefaEmbratel) -> None:
    """Puxa a tarefa de volta para a fila caso estava em ERRO/REVISAO/NOVO."""
    estados_permitidos = (
        StatusProcessamentoEmbratel.NOVO,
        StatusProcessamentoEmbratel.ERRO,
        StatusProcessamentoEmbratel.REVISAO
    )
    if tarefa.status_processamento in estados_permitidos:
        tarefa.status_processamento = StatusProcessamentoEmbratel.PENDENTE_ENVIO
        tarefa.save(update_fields=['status_processamento'])


def ignorar_tarefa(tarefa: TarefaEmbratel, motivo: Optional[str] = None) -> None:
    """Pula o processamento da tarefa definitivamente."""
    if tarefa.status_processamento != StatusProcessamentoEmbratel.ENVIANDO:
        tarefa.status_processamento = StatusProcessamentoEmbratel.IGNORADO
        if motivo:
            tarefa.erro_processamento = str(motivo)[:2000]
        tarefa.save(update_fields=['status_processamento', 'erro_processamento'])


# ══════════════════════════════════════════════════════════════
#  FLUXOS PÚBLICOS DE ORQUESTRAÇÃO
# ══════════════════════════════════════════════════════════════

def enviar_email_tarefa_embratel(
    tarefa: TarefaEmbratel, 
    enviado_por: Optional[str] = None, 
    destinatarios: Optional[List[str]] = None, 
    copias: Optional[List[str]] = None, 
    forcar: bool = False
) -> Dict:
    """
    Fluxo primário para envio de notificação de UMA tarefa.
    Aplica regras, reserva a tarefa atomicamente, e efetua disparo SMTP.

    A elegibilidade é sempre avaliada para ESTA tarefa/REC específica
    (tarefa.pk / tarefa.id_portal), nunca para o conjunto de tarefas que
    compartilham a mesma DS. Duas RECs na mesma etapa são sempre tratadas
    de forma independente.
    """
    retorno_base = {
        "tarefa_id": tarefa.pk,
        "id_portal": tarefa.id_portal,
        "numero_rec": obter_numero_rec(tarefa),
        "status": tarefa.status_processamento,
        "destinatarios": [],
        "copias": [],
        "message_id": None,
        "erro": None
    }

    # 1. Validação Regras
    elegibilidade = avaliar_elegibilidade_envio(tarefa)
    if not elegibilidade["elegivel"] and not forcar:
        retorno_base.update({"sucesso": False, "codigo": elegibilidade["codigo"], "erro": elegibilidade["motivo"]})
        return retorno_base

    # 2. Validação Barreiras Críticas 
    if tarefa.status_processamento in (StatusProcessamentoEmbratel.ENVIANDO, StatusProcessamentoEmbratel.FINALIZADO):
        retorno_base.update({"sucesso": False, "codigo": "BLOQUEIO_STATUS", "erro": "Status atual impede forçar envio."})
        return retorno_base
    if tarefa.status_processamento == StatusProcessamentoEmbratel.ENVIADO and not forcar:
        retorno_base.update({"sucesso": False, "codigo": "JA_ENVIADA", "erro": "Tarefa já foi enviada."})
        return retorno_base

    # 3. Resolução Destinatários
    lista_to, lista_cc = resolver_destinatarios(tarefa, destinatarios, copias)
    if not lista_to:
        marcar_tarefa_para_revisao(tarefa, "Nenhum destinatário válido foi encontrado.")
        retorno_base.update({
            "sucesso": False, 
            "status": StatusProcessamentoEmbratel.REVISAO, 
            "codigo": "SEM_DESTINATARIO", 
            "erro": "Nenhum destinatário válido foi encontrado."
        })
        return retorno_base

    # 4. Início Atômico (usa tarefa.pk — a linha específica desta REC)
    tarefa_bloqueada = iniciar_tentativa_envio(tarefa.pk)
    if not tarefa_bloqueada:
        retorno_base.update({"sucesso": False, "codigo": "CONCORRENCIA", "erro": "Falha de concorrência ou tarefa já em andamento."})
        return retorno_base

    logs.info("EMBRATEL-EMAIL", f"Iniciando envio da REC {obter_numero_rec(tarefa_bloqueada)} (id_portal={tarefa_bloqueada.id_portal})")

    # 5. Geração e SMTP (Fora da transação)
    try:
        assunto = construir_assunto_email(tarefa_bloqueada)
        contexto = construir_contexto_email(tarefa_bloqueada)
        texto = construir_corpo_texto(tarefa_bloqueada, contexto)
        html = renderizar_corpo_html(tarefa_bloqueada, contexto)

        resp_envio = enviar_email_backend(
            assunto=assunto,
            corpo_texto=texto,
            corpo_html=html,
            destinatarios=lista_to,
            copias=lista_cc,
        )

        if resp_envio["sucesso"]:
            concluir_envio_sucesso(tarefa_bloqueada, enviado_por, resp_envio.get("message_id"))
            
            str_dest = ", ".join(mascarar_email(d) for d in lista_to)
            logs.registrar_email_enviado(tarefa_bloqueada.id_portal, destinatarios=str_dest)
            
            retorno_base.update({
                "sucesso": True,
                "status": StatusProcessamentoEmbratel.ENVIADO,
                "destinatarios": lista_to,
                "copias": lista_cc,
                "message_id": resp_envio.get("message_id")
            })
        else:
            erro_txt = resp_envio.get("erro", "Erro desconhecido SMTP")
            concluir_envio_falha(tarefa_bloqueada, erro_txt)
            logs.registrar_email_falha(tarefa_bloqueada.id_portal, erro_txt)
            
            retorno_base.update({
                "sucesso": False,
                "status": tarefa_bloqueada.status_processamento,
                "codigo": "FALHA_SMTP",
                "erro": erro_txt
            })

    except Exception as e:
        msg_erro = f"Falha inesperada no bloco de e-mail: {str(e)[:200]}"
        concluir_envio_falha(tarefa_bloqueada, msg_erro)
        logs.registrar_email_falha(tarefa_bloqueada.id_portal, msg_erro)
        
        retorno_base.update({
            "sucesso": False,
            "status": tarefa_bloqueada.status_processamento,
            "codigo": "EXCECAO_GERAL",
            "erro": msg_erro
        })

    return retorno_base


def processar_envios_pendentes(limite: int = 50, enviado_por: str = "sistema") -> Dict:
    """
    Vasculha tarefas aptas no banco e dispara seus e-mails iterativamente.
    Cada tarefa da fila é uma REC própria (linha única por id_portal);
    o processamento de uma REC nunca afeta outra que esteja na mesma DS.
    Engole erros locais para não quebrar a fila toda.
    """
    resumo = {
        "processadas": 0,
        "enviadas": 0,
        "revisao": 0,
        "ignoradas": 0,
        "erros": []
    }
    
    limite_tentativas = int(os.getenv("EMBRATEL_LIMITE_TENTATIVAS", "3"))

    tarefas = TarefaEmbratel.objects.filter(
        status_processamento__in=[
            StatusProcessamentoEmbratel.NOVO,
            StatusProcessamentoEmbratel.PENDENTE_ENVIO,
            StatusProcessamentoEmbratel.ERRO,
        ],
        tentativas__lt=limite_tentativas
    ).exclude(
        Q(data_finalizacao_portal__isnull=False) | Q(status_portal__icontains="finalizado")
    ).order_by("data_criacao_portal", "criado_em")[:limite]

    for t in tarefas:
        resumo["processadas"] += 1
        try:
            resultado = enviar_email_tarefa_embratel(tarefa=t, enviado_por=enviado_por)
            
            if resultado["sucesso"]:
                resumo["enviadas"] += 1
            elif resultado.get("status") == StatusProcessamentoEmbratel.REVISAO:
                resumo["revisao"] += 1
            elif resultado.get("codigo") in ("NAO_ELEGIVEL", "DADOS_INCOMPLETOS", "LIMITE_EXCEDIDO"):
                resumo["ignoradas"] += 1
            else:
                resumo["erros"].append(f"Tarefa {t.id_portal}: {resultado.get('erro')}")
                
        except Exception as e:
            resumo["erros"].append(f"Exceção catastrófica na tarefa {t.id_portal}: {str(e)[:200]}")

    return resumo


def reprocessar_tarefa_embratel(
    tarefa_id: int, 
    enviado_por: Optional[str] = None, 
    destinatarios: Optional[List[str]] = None, 
    copias: Optional[List[str]] = None
) -> Dict:
    """
    Interface futura para chamada manual através de Views.
    Restringe a forçar apenas tickets em ERRO ou REVISÃO.
    """
    try:
        tarefa = TarefaEmbratel.objects.get(pk=tarefa_id)
    except TarefaEmbratel.DoesNotExist:
        return {"sucesso": False, "codigo": "NAO_ENCONTRADO", "erro": "Tarefa não existe."}

    permitidos_reprocessar = (StatusProcessamentoEmbratel.ERRO, StatusProcessamentoEmbratel.REVISAO)
    if tarefa.status_processamento not in permitidos_reprocessar:
        return {
            "sucesso": False,
            "codigo": "REPROCESSAMENTO_NEGADO",
            "erro": f"Status '{tarefa.status_processamento}' não permite reprocessamento manual."
        }

    return enviar_email_tarefa_embratel(
        tarefa=tarefa,
        enviado_por=enviado_por,
        destinatarios=destinatarios,
        copias=copias,
        forcar=True
    )
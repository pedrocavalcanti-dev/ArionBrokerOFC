"""
views.py

Controladores de interface (Painel) da automação Embratel.
Permite listar, detalhar, sincronizar, enviar e gerenciar tarefas.
As ações sensíveis são protegidas por POST e permissões.
Não realiza chamadas diretas às APIs do Modos Web.
"""

import logging
from urllib.parse import urlencode
from datetime import datetime, date
from typing import Optional, Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_GET, require_POST
from django.core.paginator import Paginator
from django.db.models import Q, Count, Case, When, Value, IntegerField
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.utils import timezone

from .models import (
    TarefaEmbratel,
    ConfiguracaoRoboEmbratel,
    ExecucaoRoboEmbratel,
    HistoricoTarefaEmbratel,
    StatusProcessamentoEmbratel,
    OrigemColetaEmbratel,
    StatusExecucaoEmbratel,
)
from .scraper import executar_coleta_embratel
from .services import (
    enviar_email_tarefa_embratel,
    reprocessar_tarefa_embratel,
    marcar_pendente_envio,
    ignorar_tarefa,
)
from . import logs

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
#  FUNÇÕES AUXILIARES
# ══════════════════════════════════════════════════════════════

def obter_parametro_texto(request: HttpRequest, nome: str, padrao: str = '', limite: int = 255) -> str:
    """Obtém parâmetro string com limite de segurança."""
    valor = request.GET.get(nome) or request.POST.get(nome) or ''
    return str(valor).strip()[:limite] if str(valor).strip() else padrao


def obter_parametro_inteiro(request: HttpRequest, nome: str, padrao: Optional[int] = None) -> Optional[int]:
    """Obtém parâmetro numérico capturando falhas silenciosamente."""
    valor = request.GET.get(nome) or request.POST.get(nome)
    if not valor:
        return padrao
    try:
        return int(valor)
    except (ValueError, TypeError):
        return padrao


def parse_data_filtro(valor: str) -> Optional[date]:
    """Tenta converter string para data."""
    if not valor:
        return None
    try:
        return parse_date(valor)
    except (ValueError, TypeError):
        return None


def construir_querystring_filtros(request: HttpRequest, excluir: Optional[list] = None) -> str:
    """Reconstrói a querystring ignorando os campos fornecidos em 'excluir'."""
    excluir = excluir or ['page']
    parametros = request.GET.copy()
    for chave in excluir:
        if chave in parametros:
            parametros.pop(chave)
    
    parametros_limpos = {k: v for k, v in parametros.items() if v}
    return urlencode(parametros_limpos, doseq=True)


def obter_usuario_executor(request: HttpRequest) -> str:
    """Extrai nome identificável do usuário atual."""
    user = request.user
    if not user.is_authenticated:
        return "sistema"
    
    nome = user.get_full_name() or user.username or user.email or "sistema"
    return str(nome).strip()[:150]


def resposta_acao(
    request: HttpRequest, 
    sucesso: bool, 
    mensagem: str, 
    redirect_name: str, 
    redirect_kwargs: Optional[dict] = None, 
    dados: Optional[dict] = None
) -> HttpResponse:
    """
    Padroniza a resposta. Se cliente pediu JSON, retorna JsonResponse.
    Caso contrário, registra message do Django e redireciona.
    """
    formato = request.GET.get('format', '').lower()
    accept = request.headers.get('accept', '').lower()
    quer_json = formato == 'json' or 'application/json' in accept

    if quer_json:
        status_code = 200 if sucesso else 400
        return JsonResponse({
            'sucesso': sucesso,
            'mensagem': mensagem,
            'dados': dados or {}
        }, status=status_code)

    if sucesso:
        messages.success(request, mensagem)
    else:
        messages.error(request, mensagem)

    if redirect_kwargs:
        return redirect(redirect_name, **redirect_kwargs)
    return redirect(redirect_name)


# ══════════════════════════════════════════════════════════════
#  VIEWS DE LISTAGEM
# ══════════════════════════════════════════════════════════════

@login_required
@require_GET
def listar_recs_embratel(request: HttpRequest) -> HttpResponse:
    """Lista tarefas pendentes aptas para envio (apenas DS102 e não finalizadas)."""
    q = obter_parametro_texto(request, 'q', limite=100)
    status = obter_parametro_texto(request, 'status', limite=50)
    status_portal = obter_parametro_texto(request, 'status_portal', limite=100)
    provedor = obter_parametro_texto(request, 'provedor', limite=100)
    tipo_tarefa = obter_parametro_texto(request, 'tipo_tarefa', limite=100)
    dentro_sla = obter_parametro_texto(request, 'dentro_sla', limite=10)
    data_inicio_str = obter_parametro_texto(request, 'data_inicio')
    data_fim_str = obter_parametro_texto(request, 'data_fim')
    
    page = obter_parametro_inteiro(request, 'page', 1)
    por_pagina = obter_parametro_inteiro(request, 'por_pagina', 25)
    if por_pagina not in (25, 50, 100):
        por_pagina = 25

    status_pendentes = [
        StatusProcessamentoEmbratel.NOVO,
        StatusProcessamentoEmbratel.PENDENTE_ENVIO,
        StatusProcessamentoEmbratel.ERRO,
        StatusProcessamentoEmbratel.REVISAO,
        StatusProcessamentoEmbratel.ENVIANDO,
    ]
    
    base_pendentes = (
        TarefaEmbratel.objects
        .filter(
            status_processamento__in=status_pendentes,
            data_finalizacao_portal__isnull=True,
        )
        .filter(
            Q(tipo_tarefa__icontains="DS102") |
            Q(dados_tecnicos__mapa_tarefa__iexact="DS102")
        )
    )
    qs = base_pendentes

    if q:
        qs = qs.filter(
            Q(id_portal__icontains=q) |
            Q(id_processo__icontains=q) |
            Q(id_workflow__icontains=q) |
            Q(cliente__icontains=q) |
            Q(designacao__icontains=q) |
            Q(circuito__icontains=q) |
            Q(projeto__icontains=q) |
            Q(sintoma__icontains=q) |
            Q(status_portal__icontains=q)
        )
    
    if status and status in StatusProcessamentoEmbratel.values:
        qs = qs.filter(status_processamento=status)
        
    if status_portal:
        qs = qs.filter(status_portal__icontains=status_portal)
        
    if provedor:
        qs = qs.filter(provedor__icontains=provedor)
        
    if tipo_tarefa:
        qs = qs.filter(tipo_tarefa__icontains=tipo_tarefa)

    if dentro_sla:
        val_bool = dentro_sla in ('sim', 'true', '1')
        qs = qs.filter(dentro_sla=val_bool)

    dt_inicio = parse_data_filtro(data_inicio_str)
    if dt_inicio:
        qs = qs.filter(data_coleta__date__gte=dt_inicio)

    dt_fim = parse_data_filtro(data_fim_str)
    if dt_fim:
        qs = qs.filter(data_coleta__date__lte=dt_fim)

    prioridade = Case(
        When(status_processamento=StatusProcessamentoEmbratel.ERRO, then=Value(1)),
        When(status_processamento=StatusProcessamentoEmbratel.REVISAO, then=Value(2)),
        When(status_processamento=StatusProcessamentoEmbratel.NOVO, then=Value(3)),
        When(status_processamento=StatusProcessamentoEmbratel.PENDENTE_ENVIO, then=Value(4)),
        When(status_processamento=StatusProcessamentoEmbratel.ENVIANDO, then=Value(5)),
        default=Value(99),
        output_field=IntegerField()
    )
    qs = qs.annotate(prioridade=prioridade).order_by('prioridade', '-data_criacao_portal', '-criado_em')

    paginator = Paginator(qs, por_pagina)
    pagina = paginator.get_page(page)

    resumo_agregado = base_pendentes.aggregate(
        total_pendentes=Count("id"),
        novas=Count(
            "id",
            filter=Q(status_processamento=StatusProcessamentoEmbratel.NOVO),
        ),
        erros=Count(
            "id",
            filter=Q(status_processamento=StatusProcessamentoEmbratel.ERRO),
        ),
        revisao=Count(
            "id",
            filter=Q(status_processamento=StatusProcessamentoEmbratel.REVISAO),
        ),
        enviando=Count(
            "id",
            filter=Q(status_processamento=StatusProcessamentoEmbratel.ENVIANDO),
        ),
    )

    contexto = {
        "tarefas": pagina,
        "pagina": pagina,
        "filtros": request.GET,
        "querystring_filtros": construir_querystring_filtros(request),
        "status_disponiveis": [
            (c.value, c.label) for c in StatusProcessamentoEmbratel if c.value in status_pendentes
        ],
        "configuracao": ConfiguracaoRoboEmbratel.obter(),
        "ultima_execucao": ConfiguracaoRoboEmbratel.obter().ultima_execucao,
        "resumo": resumo_agregado
    }
    
    return render(request, 'automacao_embratel/recs_embratel.html', contexto)

@login_required
@require_GET
def listar_recs_embratel_enviadas(request: HttpRequest) -> HttpResponse:
    """
    Lista o histórico de tarefas concluídas da automação Embratel.

    Inclui:
    - enviadas;
    - finalizadas no portal;
    - ignoradas;
    - resumo por origem;
    - resumo de registros com erro;
    - filtros e paginação.
    """
    q = obter_parametro_texto(request, 'q', limite=100)
    status = obter_parametro_texto(request, 'status', limite=50)
    cliente = obter_parametro_texto(request, 'cliente', limite=100)
    provedor = obter_parametro_texto(request, 'provedor', limite=100)
    data_inicio_str = obter_parametro_texto(request, 'data_inicio')
    data_fim_str = obter_parametro_texto(request, 'data_fim')

    page = obter_parametro_inteiro(request, 'page', 1)
    por_pagina = obter_parametro_inteiro(request, 'por_pagina', 25)
    if por_pagina not in (25, 50, 100):
        por_pagina = 25

    status_concluidos = [
        StatusProcessamentoEmbratel.ENVIADO,
        StatusProcessamentoEmbratel.FINALIZADO,
        StatusProcessamentoEmbratel.IGNORADO,
    ]

    base_qs = TarefaEmbratel.objects.filter(
        status_processamento__in=status_concluidos
    )
    qs = base_qs

    if q:
        qs = qs.filter(
            Q(id_portal__icontains=q) |
            Q(id_processo__icontains=q) |
            Q(id_workflow__icontains=q) |
            Q(cliente__icontains=q) |
            Q(designacao__icontains=q) |
            Q(circuito__icontains=q) |
            Q(projeto__icontains=q) |
            Q(provedor__icontains=q) |
            Q(sintoma__icontains=q) |
            Q(tipo_tarefa__icontains=q)
        )

    if status and status in status_concluidos:
        qs = qs.filter(status_processamento=status)

    if cliente:
        qs = qs.filter(cliente__icontains=cliente)

    if provedor:
        qs = qs.filter(provedor__icontains=provedor)

    dt_inicio = parse_data_filtro(data_inicio_str)
    if dt_inicio:
        qs = qs.filter(data_envio__date__gte=dt_inicio)

    dt_fim = parse_data_filtro(data_fim_str)
    if dt_fim:
        qs = qs.filter(data_envio__date__lte=dt_fim)

    qs = qs.order_by('-data_envio', '-atualizado_em')

    paginator = Paginator(qs, por_pagina)
    pagina = paginator.get_page(page)

    resumo_agregado = base_qs.aggregate(
        total=Count('id'),
        automatico=Count(
            'id',
            filter=Q(origem_coleta=OrigemColetaEmbratel.AUTOMATICO),
        ),
        manual=Count(
            'id',
            filter=Q(origem_coleta=OrigemColetaEmbratel.MANUAL),
        ),
        erros=Count(
            'id',
            filter=(
                Q(erro_processamento__isnull=False) &
                ~Q(erro_processamento='')
            ),
        ),
        enviadas=Count(
            'id',
            filter=Q(
                status_processamento=StatusProcessamentoEmbratel.ENVIADO
            ),
        ),
        finalizadas=Count(
            'id',
            filter=Q(
                status_processamento=StatusProcessamentoEmbratel.FINALIZADO
            ),
        ),
        ignoradas=Count(
            'id',
            filter=Q(
                status_processamento=StatusProcessamentoEmbratel.IGNORADO
            ),
        ),
    )

    contexto = {
        "tarefas": pagina,
        "pagina": pagina,
        "filtros": request.GET,
        "querystring_filtros": construir_querystring_filtros(request),
        "status_disponiveis": [
            (c.value, c.label)
            for c in StatusProcessamentoEmbratel
            if c.value in status_concluidos
        ],
        "resumo": resumo_agregado,
    }

    return render(
        request,
        'automacao_embratel/recs_embratel_enviadas.html',
        contexto
    )


@login_required
@require_GET
def detalhe_rec_embratel(request: HttpRequest, pk: int) -> HttpResponse:
    """Exibe os dados técnicos e o histórico de uma tarefa específica."""
    tarefa = get_object_or_404(TarefaEmbratel, pk=pk)
    
    historico = tarefa.historico.all()[:50]
    execucoes_recentes = ExecucaoRoboEmbratel.objects.all()[:10]
    
    sp = tarefa.status_processamento
    finalizada_portal = bool(tarefa.data_finalizacao_portal)
    
    eh_ds102 = tarefa.tipo_tarefa and tarefa.tipo_tarefa.startswith("DS102")
    if not eh_ds102 and isinstance(tarefa.dados_tecnicos, dict):
        eh_ds102 = tarefa.dados_tecnicos.get("mapa_tarefa") == "DS102"
    
    pode_enviar = (
        sp in (
            StatusProcessamentoEmbratel.NOVO,
            StatusProcessamentoEmbratel.PENDENTE_ENVIO,
            StatusProcessamentoEmbratel.ERRO,
            StatusProcessamentoEmbratel.REVISAO,
        ) 
        and not finalizada_portal
        and eh_ds102
    )
    
    pode_reprocessar = sp in (StatusProcessamentoEmbratel.ERRO, StatusProcessamentoEmbratel.REVISAO)
    
    pode_ignorar = sp not in (
        StatusProcessamentoEmbratel.ENVIANDO, 
        StatusProcessamentoEmbratel.ENVIADO, 
        StatusProcessamentoEmbratel.FINALIZADO
    )
    
    pode_marcar_pendente = sp in (
        StatusProcessamentoEmbratel.NOVO, 
        StatusProcessamentoEmbratel.ERRO, 
        StatusProcessamentoEmbratel.REVISAO
    )

    contexto = {
        "tarefa": tarefa,
        "historico": historico,
        "execucoes_recentes": execucoes_recentes,
        "pode_enviar": pode_enviar,
        "pode_reprocessar": pode_reprocessar,
        "pode_ignorar": pode_ignorar,
        "pode_marcar_pendente": pode_marcar_pendente,
    }
    
    return render(request, 'automacao_embratel/rec_embratel_detalhe.html', contexto)


# ══════════════════════════════════════════════════════════════
#  VIEWS DE AÇÕES (MANUAIS / ESCRITA)
# ══════════════════════════════════════════════════════════════
@login_required
@require_POST
def sincronizar_recs_embratel(request: HttpRequest) -> HttpResponse:
    """Aciona a coleta no Modos Web (via scraper). Disponível para usuários logados."""

    executor = obter_usuario_executor(request)

    limite_paginas_bruto = request.POST.get('limite_paginas')
    limite_paginas = None

    if limite_paginas_bruto and limite_paginas_bruto.isdigit():
        limite_paginas = int(limite_paginas_bruto)

        if limite_paginas > 20:
            limite_paginas = 20

    logs.info(
        'EMBRATEL-VIEW',
        f'Sincronização manual solicitada por {executor}'
    )

    try:
        resultado = executar_coleta_embratel(
            origem=OrigemColetaEmbratel.MANUAL,
            executor=executor,
            limite_paginas=limite_paginas
        )

        # Já existe uma coleta sendo executada
        if resultado.get("concorrencia"):
            return resposta_acao(
                request,
                False,
                "Já existe uma sincronização Embratel em andamento.",
                'automacao_embratel:lista'
            )

        # Robô pausado
        if resultado.get("pausado"):
            return resposta_acao(
                request,
                False,
                "O robô Embratel está pausado.",
                'automacao_embratel:lista'
            )

        msg_base = (
            f"Sincronização concluída: "
            f"{resultado['tarefas_encontradas']} encontradas | "
            f"{resultado['tarefas_novas']} novas | "
            f"{resultado['tarefas_atualizadas']} atualizadas | "
            f"{resultado['tarefas_ignoradas']} ignoradas."
        )

        if resultado["sucesso"]:
            return resposta_acao(
                request,
                True,
                msg_base,
                'automacao_embratel:lista',
                dados=resultado
            )

        msg_erro = " - ".join(
            resultado.get("erros", [])
        )[:200]

        msg_final = (
            f"{msg_base} "
            f"Alertas ocorridos: {msg_erro}"
        )

        return resposta_acao(
            request,
            False,
            msg_final,
            'automacao_embratel:lista',
            dados=resultado
        )

    except Exception as e:
        logs.erro(
            'EMBRATEL-VIEW',
            'Falha inesperada ao sincronizar tarefas',
            e
        )

        return resposta_acao(
            request,
            False,
            "Falha sistêmica durante a sincronização.",
            'automacao_embratel:lista'
        )

@login_required
@require_POST
def enviar_rec_embratel(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Função protegida de envio de e-mail com instrumentação completa de logs
    e retenção na tela de detalhe da REC.
    """
    tarefa = get_object_or_404(TarefaEmbratel, pk=pk)
    usuario = request.user.get_username() or str(request.user)

    logger.warning(
        "[EMBRATEL-EMAIL] Botão enviar acionado | tarefa=%s | portal=%s | usuário=%s",
        tarefa.pk,
        tarefa.id_portal,
        usuario,
    )

    # Validação da etapa DS102
    eh_ds102 = tarefa.tipo_tarefa and tarefa.tipo_tarefa.startswith("DS102")
    if not eh_ds102 and isinstance(tarefa.dados_tecnicos, dict):
        eh_ds102 = tarefa.dados_tecnicos.get("mapa_tarefa") == "DS102"

    if not eh_ds102:
        messages.error(request, "Somente chamados na etapa DS102 podem ser enviados.")
        return redirect('automacao_embratel:detalhe', pk=tarefa.pk)

    # Validação se já está finalizada
    if tarefa.data_finalizacao_portal:
        messages.error(request, "Este chamado já foi encerrado e não pode ser enviado.")
        return redirect('automacao_embratel:detalhe', pk=tarefa.pk)

    # Validação se já foi enviada
    if tarefa.status_processamento in (StatusProcessamentoEmbratel.ENVIADO, StatusProcessamentoEmbratel.FINALIZADO):
        messages.warning(request, "Esta REC já foi enviada. Somente administradores podem reenviar.")
        return redirect('automacao_embratel:detalhe', pk=tarefa.pk)
    
    destinatarios = request.POST.get('destinatarios')
    copias = request.POST.get('copias')

    try:
        resultado = enviar_email_tarefa_embratel(
            tarefa=tarefa,
            enviado_por=usuario,
            destinatarios=destinatarios,
            copias=copias,
            forcar=False
        )

        logger.warning(
            "[EMBRATEL-EMAIL] Resultado do envio | tarefa=%s | resultado=%s",
            tarefa.pk,
            resultado,
        )

        if resultado.get("sucesso"):
            destinatarios_finais = resultado.get("destinatarios", [])

            logger.info(
                "[EMBRATEL-EMAIL] E-mail enviado com sucesso | tarefa=%s | para=%s",
                tarefa.pk,
                ", ".join(destinatarios_finais),
            )

            messages.success(
                request,
                f"E-mail enviado com sucesso para: {', '.join(destinatarios_finais) or 'destinatário configurado'}."
            )
        else:
            erro = resultado.get("erro") or "Falha desconhecida."

            logger.error(
                "[EMBRATEL-EMAIL] Falha no envio | tarefa=%s | erro=%s",
                tarefa.pk,
                erro,
            )

            messages.error(
                request,
                f"Não foi possível enviar o e-mail: {erro}"
            )

    except Exception as erro:
        logger.exception(
            "[EMBRATEL-EMAIL] Exceção inesperada no envio | tarefa=%s",
            tarefa.pk,
        )

        messages.error(
            request,
            f"Erro inesperado ao enviar o e-mail: {erro}"
        )

    return redirect('automacao_embratel:detalhe', pk=tarefa.pk)


@login_required
@permission_required('automacao_embratel.change_tarefaembratel', raise_exception=True)
@require_POST
def reprocessar_rec_embratel(request: HttpRequest, pk: int) -> HttpResponse:
    """Tenta forçar o envio e avaliação de uma tarefa travada (ERRO/REVISAO)."""
    executor = obter_usuario_executor(request)
    destinatarios = request.POST.get('destinatarios')
    copias = request.POST.get('copias')

    resultado = reprocessar_tarefa_embratel(
        tarefa_id=pk,
        enviado_por=executor,
        destinatarios=destinatarios,
        copias=copias
    )
    
    if resultado.get("sucesso"):
        return resposta_acao(request, True, "Tarefa reprocessada e enviada com sucesso.", 'automacao_embratel:detalhe', {'pk': pk}, dados=resultado)
    else:
        erro = resultado.get("erro", "Não foi possível reprocessar.")
        return resposta_acao(request, False, f"Falha ao reprocessar: {erro}", 'automacao_embratel:detalhe', {'pk': pk}, dados=resultado)


@login_required
@permission_required('automacao_embratel.change_tarefaembratel', raise_exception=True)
@require_POST
def marcar_pendente_rec_embratel(request: HttpRequest, pk: int) -> HttpResponse:
    """Move uma tarefa manualmente para o status de PENDENTE_ENVIO."""
    tarefa = get_object_or_404(TarefaEmbratel, pk=pk)
    
    marcar_pendente_envio(tarefa)
    tarefa.refresh_from_db()
    
    if tarefa.status_processamento == StatusProcessamentoEmbratel.PENDENTE_ENVIO:
        return resposta_acao(request, True, "Tarefa movida para pendente com sucesso.", 'automacao_embratel:detalhe', {'pk': pk})
    else:
        return resposta_acao(request, False, "Status atual não permite mover para pendente.", 'automacao_embratel:detalhe', {'pk': pk})


@login_required
@permission_required('automacao_embratel.change_tarefaembratel', raise_exception=True)
@require_POST
def ignorar_rec_embratel(request: HttpRequest, pk: int) -> HttpResponse:
    """Pula o envio e processamento de uma tarefa permanentemente."""
    tarefa = get_object_or_404(TarefaEmbratel, pk=pk)
    motivo = obter_parametro_texto(request, 'motivo', limite=1000)
    
    if len(motivo) < 3:
        return resposta_acao(request, False, "O motivo deve conter pelo menos 3 caracteres.", 'automacao_embratel:detalhe', {'pk': pk})
        
    ignorar_tarefa(tarefa, motivo)
    tarefa.refresh_from_db()

    if tarefa.status_processamento == StatusProcessamentoEmbratel.IGNORADO:
        return resposta_acao(request, True, "Tarefa ignorada com sucesso.", 'automacao_embratel:detalhe', {'pk': pk})
    else:
        return resposta_acao(request, False, "A tarefa não pôde ser ignorada (pode estar em envio ou já finalizada).", 'automacao_embratel:detalhe', {'pk': pk})


@login_required
@permission_required('automacao_embratel.change_configuracaoroboembratel', raise_exception=True)
@require_POST
def alternar_configuracao_robo_embratel(request: HttpRequest) -> HttpResponse:
    """Pausa ou ativa a automação globalmente."""
    config = ConfiguracaoRoboEmbratel.obter()
    novo_estado = not config.ativo
    
    config.ativo = novo_estado
    config.alterado_por = obter_usuario_executor(request)
    
    config.save(update_fields=['ativo', 'alterado_por', 'alterado_em'])

    msg = "Robô Embratel ativado com sucesso." if novo_estado else "Robô Embratel pausado com sucesso."
    return resposta_acao(request, True, msg, 'automacao_embratel:lista')


# ══════════════════════════════════════════════════════════════
#  VIEWS DE ADMINISTRAÇÃO E STATUS
# ══════════════════════════════════════════════════════════════

@login_required
@require_GET
def listar_execucoes_embratel(request: HttpRequest) -> HttpResponse:
    """Listagem de histórico das execuções sistêmicas (logs em alto nível do banco)."""
    status = obter_parametro_texto(request, 'status', limite=50)
    origem = obter_parametro_texto(request, 'origem', limite=50)
    executor = obter_parametro_texto(request, 'executor', limite=150)
    data_inicio_str = obter_parametro_texto(request, 'data_inicio')
    data_fim_str = obter_parametro_texto(request, 'data_fim')
    page = obter_parametro_inteiro(request, 'page', 1)

    qs = ExecucaoRoboEmbratel.objects.all()

    if status:
        qs = qs.filter(status=status)
    if origem:
        qs = qs.filter(origem=origem)
    if executor:
        qs = qs.filter(executor__icontains=executor)

    dt_inicio = parse_data_filtro(data_inicio_str)
    if dt_inicio:
        qs = qs.filter(iniciado_em__date__gte=dt_inicio)

    dt_fim = parse_data_filtro(data_fim_str)
    if dt_fim:
        qs = qs.filter(iniciado_em__date__lte=dt_fim)

    qs = qs.order_by('-iniciado_em')

    paginator = Paginator(qs, 50)
    pagina = paginator.get_page(page)

    resumo_agregado = ExecucaoRoboEmbratel.objects.aggregate(
        total=Count('id'),
        sucesso=Count('id', filter=Q(status=StatusExecucaoEmbratel.SUCESSO)),
        sucesso_com_erros=Count('id', filter=Q(status=StatusExecucaoEmbratel.SUCESSO_COM_ERROS)),
        falha=Count('id', filter=Q(status=StatusExecucaoEmbratel.FALHA)),
        em_andamento=Count('id', filter=Q(status=StatusExecucaoEmbratel.EM_ANDAMENTO)),
    )

    contexto = {
        "execucoes": pagina,
        "pagina": pagina,
        "filtros": request.GET,
        "querystring_filtros": construir_querystring_filtros(request),
        "configuracao": ConfiguracaoRoboEmbratel.obter(),
        "resumo": resumo_agregado
    }
    
    return render(request, 'automacao_embratel/execucoes_embratel.html', contexto)
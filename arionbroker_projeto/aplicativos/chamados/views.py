import json
import logging
from datetime import timedelta

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from aplicativos.chamados.models import Chamado, KpiOtrs, ConfiguracaoSLA, FiltroProjeto
from aplicativos.chamados.dashboard_otrs import obter_dashboard_atacado

logger = logging.getLogger(__name__)

# ── KPI IDs — mapeamento fixo dos perfis do OTRS ──────────────
KPI_BRAD           = '613_2'   # BRAD — tem brad_por_operadora {CLARO, VIVO, OUTROS}
KPI_CORREIOS       = '640_2'   # CORREIOS
KPI_LAN2LAN        = '654_2'   # LAN-TO-LAN (Vivo)
KPI_MCDONALDS      = '643_2'   # MC DONALDS (Vivo)
KPI_ALGAR          = '701_2'   # PROJETO ALGAR
KPI_BB             = '655_2'   # PROJETO BB (Banco do Brasil — Claro)
KPI_CARREFOUR      = '702_2'   # PROJETO CARREFOUR (Claro)
KPI_CEF            = '682_2'   # PROJETO CEF (Caixa — Claro)
KPI_DIVERSOS       = '686_2'   # PROJETO DIVERSOS (Claro)
KPI_PROJETOS       = '251_2'   # NOC - ATACADO — não é total global comprovado
KPI_NGO            = '185_2'   # NGO - NÃO GEOGRÁFICO (bucket "Outros", informativo)
KPI_REINCIDENCIAS  = '724_2'   # REINCIDENTES (30 dias); 723_2 é Monitoramento RREIP


@login_required
def api_kpis(request):
    """
    Endpoint JSON que retorna os KPIs do OTRS salvos no banco.
    GET /chamados/api/kpis/
    """
    try:
        kpis = KpiOtrs.objects.all().order_by('grupo', 'titulo')

        grupos_dict = {}
        ultima_atualizacao = None

        for kpi in kpis:
            grupo_nome = kpi.grupo or 'OUTROS'
            if grupo_nome not in grupos_dict:
                grupos_dict[grupo_nome] = []

            grupos_dict[grupo_nome].append({
                'kpi_id':             kpi.kpi_id,
                'titulo':             kpi.titulo,
                'valor':              kpi.valor,
                'brad_por_operadora': kpi.brad_por_operadora,
                'coletado_ok':        kpi.coletado_ok,
                'atualizado_em':      kpi.atualizado_em.strftime('%d/%m/%Y %H:%M:%S') if kpi.atualizado_em else None,
            })

            if ultima_atualizacao is None or (kpi.atualizado_em and kpi.atualizado_em > ultima_atualizacao):
                ultima_atualizacao = kpi.atualizado_em

        grupos_lista = [
            {'nome': nome, 'kpis': kpis_lista}
            for nome, kpis_lista in grupos_dict.items()
        ]

        return JsonResponse({
            'ok': True,
            'atualizado_em': ultima_atualizacao.strftime('%d/%m/%Y %H:%M:%S') if ultima_atualizacao else None,
            'grupos': grupos_lista,
        })

    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


@login_required
def api_dashboard_resumo(request):
    """
    Endpoint JSON com os totais consolidados para o dashboard principal.
    GET /projetos/api/dashboard-resumo/
    """
    try:
        # ATACADO vem da sessão OTRS existente; esta API não grava KPIs no banco.
        data = dict(obter_dashboard_atacado())

        # Preserva a origem atual do SLA e do NGO. Não inferir resolvidos dos KPIs.
        atrasados_qs = KpiOtrs.objects.filter(grupo='CHAMADOS POR GESTORES +4D')
        data['atrasados'] = sum(k.valor for k in atrasados_qs)
        ngo = KpiOtrs.objects.filter(kpi_id=KPI_NGO, coletado_ok=True).first()
        ngo_valor = ngo.valor if ngo else None
        reincidentes = next(p for p in data['atacado']['projetos']
                            if p['id'] == 'reincidentes_30_dias')
        data['outros'] = {
            'total': ngo_valor,
            'projetos': [
                {'id': 'ngo', 'nome': 'NGO - Não Geográfico', 'valor': ngo_valor},
                {'id': 'reincidencias', 'nome': 'Reincidências',
                 'valor': reincidentes['valor'], 'kpi_id': KPI_REINCIDENCIAS},
            ],
        }
        data['ok'] = True
        return JsonResponse(data)

    except Exception as exc:
        logger.error('[OTRS DASHBOARD] Resumo indisponível (%s)', type(exc).__name__)
        return JsonResponse({'ok': False, 'erro': 'Resumo OTRS indisponível; verifique a sessão existente.'}, status=503)


@login_required
def dashboard_projetos(request):
    """
    Renderiza o painel consolidado de KPIs por Operadora e Cliente.
    """
    return render(request, 'chamados/dashboard.html')


# ── PROJETOS INDIVIDUAIS ───────────────────────────────────────

STATUS_OPCOES_BASE = [
    ('aberto',        'Em Aberto'),
    ('resolvido',     'Resolvido'),
    ('atendimento',   'Em atendimento pela ISP'),
    ('pendente',      'Pendente financeira'),
    ('ag_visita',     'AG. VISITA TECNICA'),
    ('analise',       'Em analise pelo POS VENDAS'),
    ('troca',         'Troca de titularidade'),
    ('cancelamento',  'Cancelamento do Link'),
    ('massiva',       'Massiva'),   # ← novo
]

SLA_VALOR_PADRAO   = 5
SLA_UNIDADE_PADRAO = 'dias'


def _montar_projeto_context(operadora_slug, projeto_slug):
    nome_operadora = operadora_slug.capitalize()
    nome_projeto   = projeto_slug.replace('-', ' ').title()

    if projeto_slug == 'mcdonalds':
        nome_projeto = "McDonald's"
    elif projeto_slug == 'escolas-conectadas':
        nome_projeto = "Escolas Conectadas"

    operadora = {'nome': nome_operadora, 'slug': operadora_slug}

    status_opcoes = list(STATUS_OPCOES_BASE)
    if operadora_slug == 'claro':
        status_opcoes.append(('aguardando', 'Aguardando validação da CLARO'))
    else:
        status_opcoes.append(('aguardando', 'Aguardando validação da VIVO'))

    status_opcoes.append(('cgnat', 'CGNAT'))
    status_opcoes.append(('tunel', 'Túneis'))

    projeto = {
        'nome': nome_projeto,
        'slug': projeto_slug,
        'col_id_nome': 'CI',
        'exibe_contato': True,
    }

    if projeto_slug == 'bradesco':
        projeto['col_id_nome'] = 'BRAD'
    elif projeto_slug in ['mcdonalds', 'arcos-dourados']:
        projeto['col_id_nome'] = 'SIGLA'

    return operadora, projeto, status_opcoes


def _status_display_map():
    return dict(Chamado.STATUS_CHOICES)


def _get_sla_config(operadora_slug, projeto_slug):
    config = ConfiguracaoSLA.objects.filter(
        operadora_slug=operadora_slug, projeto_slug=projeto_slug
    ).first()
    if config:
        return config.sla_valor, config.sla_unidade
    return SLA_VALOR_PADRAO, SLA_UNIDADE_PADRAO


def _duracao_sla_em_segundos(sla_valor, sla_unidade):
    if sla_unidade == 'minutos':
        return sla_valor * 60
    elif sla_unidade == 'horas':
        return sla_valor * 3600
    return sla_valor * 86400


def _calcular_deadline_sla(data_abertura, sla_valor, sla_unidade):
    if sla_unidade == 'minutos':
        delta = timedelta(minutes=sla_valor)
    elif sla_unidade == 'horas':
        delta = timedelta(hours=sla_valor)
    else:
        delta = timedelta(days=sla_valor)
    return data_abertura + delta


def _determinar_cor_sla(restante_segundos, total_segundos, resolvido):
    if resolvido:
        return 'ok'
    if restante_segundos < 0:
        return 'critico'
    if total_segundos <= 0:
        return 'critico'

    pct_restante = restante_segundos / total_segundos
    if pct_restante <= 0.05:
        return 'critico'
    elif pct_restante <= 0.20:
        return 'alto'
    elif pct_restante <= 0.50:
        return 'medio'
    return 'ok'


def _formatar_sla_texto(restante_segundos, resolvido):
    if resolvido:
        return 'Concluído'

    if restante_segundos < 0:
        atraso = abs(restante_segundos)
        dias, resto = divmod(int(atraso), 86400)
        horas, resto = divmod(resto, 3600)
        minutos = resto // 60
        if dias > 0:
            return f'Atrasado {dias}d {horas}h'
        return f'Atrasado {horas}h {minutos}m'

    dias, resto = divmod(int(restante_segundos), 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    if dias > 0:
        return f'{dias}d {horas}h restantes'
    return f'{horas}h {minutos}m restantes'


def _checar_reincidencia(chamado, todos_do_mes):
    designacao = (chamado.designacao or '').strip().lower()
    if not designacao:
        return False
    ocorrencias = [c for c in todos_do_mes if c.designacao.strip().lower() == designacao]
    return len(ocorrencias) > 1


def _serializar_chamado(chamado, sla_valor, sla_unidade, todos_do_mes, status_map):
    resolvido = chamado.status == 'resolvido'
    deadline = _calcular_deadline_sla(chamado.data_abertura, sla_valor, sla_unidade)
    total_segundos = _duracao_sla_em_segundos(sla_valor, sla_unidade)
    restante_segundos = (deadline - timezone.now()).total_seconds()

    sla_cor = _determinar_cor_sla(restante_segundos, total_segundos, resolvido)
    atrasado = (not resolvido) and restante_segundos < 0

    # Puxar o usuário/analista: Pega o nome completo. Se estiver vazio, pega o nome de usuário.
    nome_analista = '—'
    if chamado.analista:
        nome_analista = chamado.analista.get_full_name().strip()
        if not nome_analista:
            nome_analista = chamado.analista.username

    # Garantir que a URL do ticket tenha http/https para não quebrar o link
    url_ticket = (chamado.url_ticket or '').strip()
    if url_ticket and not (url_ticket.startswith('http://') or url_ticket.startswith('https://')):
        url_ticket = f'https://{url_ticket}'

    return {
        'id':               chamado.id,
        'id_personalizado': chamado.id_personalizado,
        'ticket_arion':     chamado.ticket_arion,
        'url_ticket':       url_ticket,
        'designacao':       chamado.designacao,
        'isp':              chamado.isp,
        'contato':          chamado.contato,
        'local':            chamado.local,
        'status_slug':      chamado.status,
        'status_display':   status_map.get(chamado.status, chamado.status),
        'obs':              chamado.obs,
        'data':             chamado.data_abertura,
        'deadline_iso':       deadline.isoformat() if not resolvido else None,
        'sla_total_segundos': total_segundos if not resolvido else None,
        'sla_texto':        _formatar_sla_texto(restante_segundos, resolvido),
        'sla_cor':          sla_cor,
        'atrasado':         atrasado,
        'analista':         nome_analista,
        'is_reincidente':   _checar_reincidencia(chamado, todos_do_mes),
    }


@login_required
def index_projetos(request, operadora_slug, projeto_slug):
    operadora, projeto, status_opcoes = _montar_projeto_context(operadora_slug, projeto_slug)

    if (operadora_slug == 'vivo' and projeto_slug == 'bradesco') or \
       projeto_slug in ['mcdonalds', 'arcos-dourados'] or \
       operadora_slug == 'algar':
        analista_fixo = "Vinicius Floriano"
    else:
        analista_fixo = "Pedro Cavalcanti"

    sla_valor, sla_unidade = _get_sla_config(operadora_slug, projeto_slug)
    status_map = _status_display_map()

    chamados_qs = Chamado.objects.filter(
        operadora_slug=operadora_slug, projeto_slug=projeto_slug
    ).select_related('analista').order_by('-data_abertura')

    hoje = timezone.now()
    todos_do_mes = list(chamados_qs.filter(
        data_abertura__year=hoje.year, data_abertura__month=hoje.month
    ))

    chamados = [
        _serializar_chamado(c, sla_valor, sla_unidade, todos_do_mes, status_map)
        for c in chamados_qs
    ]

    total_atrasados = sum(1 for c in chamados if c['atrasado'])

    # Filtro ÚNICO e compartilhado deste projeto (não é mais por usuário).
    # Isso é o que garante que o filtro fica fixo entre F5, outros logins, etc,
    # e é o mesmo para todo mundo que acessa este operadora/projeto.
    filtro_projeto, _created = FiltroProjeto.objects.get_or_create(
        operadora_slug=operadora_slug,
        projeto_slug=projeto_slug,
    )

    context = {
        'operadora':       operadora,
        'projeto':         projeto,
        'chamados':        chamados,
        'total_chamados':  len(chamados),
        'total_atrasados': total_atrasados,
        'status_opcoes':   status_opcoes,
        'analista_fixo':   analista_fixo,
        # Variáveis do filtro salvas no BD (compartilhadas)
        'filtro_salvo_status': filtro_projeto.status,
        'filtro_salvo_busca': filtro_projeto.busca,
        'filtro_salvo_aging': filtro_projeto.aging,
    }

    return render(request, 'chamados/projetos.html', context)


@login_required
@require_POST
def criar_chamado(request, operadora_slug, projeto_slug):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'erro': 'JSON inválido.'}, status=400)

    ticket_arion = (payload.get('ticket_arion') or '').strip()
    designacao   = (payload.get('designacao') or '').strip()

    if not ticket_arion or not designacao:
        return JsonResponse(
            {'ok': False, 'erro': 'Ticket Arion e Designação são obrigatórios.'},
            status=400
        )

    chamado = Chamado.objects.create(
        operadora_slug=operadora_slug,
        projeto_slug=projeto_slug,
        id_personalizado=(payload.get('id_personalizado') or '').strip(),
        ticket_arion=ticket_arion,
        url_ticket=(payload.get('url_ticket') or '').strip(),
        designacao=designacao,
        isp=(payload.get('isp') or '').strip(),
        contato=(payload.get('contato') or '').strip(),
        local=(payload.get('local') or '').strip(),
        obs=(payload.get('obs') or '').strip(),
        status='aberto',
        analista=request.user,
    )

    sla_valor, sla_unidade = _get_sla_config(operadora_slug, projeto_slug)
    status_map = _status_display_map()

    hoje = timezone.now()
    todos_do_mes = list(Chamado.objects.filter(
        operadora_slug=operadora_slug, projeto_slug=projeto_slug,
        data_abertura__year=hoje.year, data_abertura__month=hoje.month,
    ))

    return JsonResponse({
        'ok': True,
        'chamado': _serializar_chamado(chamado, sla_valor, sla_unidade, todos_do_mes, status_map),
    })


@login_required
@require_POST
def excluir_chamado(request, operadora_slug, projeto_slug, chamado_id):
    if not request.user.is_staff:
        return JsonResponse(
            {'ok': False, 'erro': 'Você não tem permissão para excluir chamados.'},
            status=403
        )

    try:
        chamado = Chamado.objects.get(
            id=chamado_id,
            operadora_slug=operadora_slug,
            projeto_slug=projeto_slug,
        )
    except Chamado.DoesNotExist:
        return JsonResponse({'ok': False, 'erro': 'Chamado não encontrado.'}, status=404)

    chamado.delete()

    return JsonResponse({'ok': True, 'id': chamado_id})


@login_required
@require_POST
def atualizar_status_chamado(request, operadora_slug, projeto_slug, chamado_id):
    """
    Atualiza o status de um chamado individual (dropdown flutuante na tabela).
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'erro': 'JSON inválido.'}, status=400)

    novo_status = payload.get('status', '')
    slugs_validos = dict(Chamado.STATUS_CHOICES)

    if novo_status not in slugs_validos:
        return JsonResponse({'ok': False, 'erro': 'Status inválido.'}, status=400)

    try:
        chamado = Chamado.objects.get(
            id=chamado_id,
            operadora_slug=operadora_slug,
            projeto_slug=projeto_slug,
        )
    except Chamado.DoesNotExist:
        return JsonResponse({'ok': False, 'erro': 'Chamado não encontrado.'}, status=404)

    chamado.status = novo_status
    chamado.save(update_fields=['status', 'atualizado_em'])

    return JsonResponse({'ok': True, 'status': chamado.status})


@login_required
@require_POST
def salvar_filtro_usuario(request, operadora_slug, projeto_slug):
    """
    Salva o filtro ÚNICO e COMPARTILHADO deste projeto (operadora + projeto).
    Não é mais por usuário: qualquer um que salvar aqui, atualiza o filtro
    que todo mundo vê, e ele fica assim até alguém mudar de novo.
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'erro': 'JSON inválido.'}, status=400)

    try:
        filtro, _created = FiltroProjeto.objects.get_or_create(
            operadora_slug=operadora_slug,
            projeto_slug=projeto_slug,
        )

        filtro.status = payload.get('status', 'aberto')
        filtro.busca = payload.get('busca', '')
        filtro.aging = payload.get('aging', '')
        filtro.atualizado_por = request.user
        filtro.save()

        return JsonResponse({'ok': True})

    except Exception as e:
        # SE DER ERRO 500, ELE VAI PRINTAR O MOTIVO REAL NO SEU TERMINAL/PROMPT DO PYTHON
        print(f"\n[ERRO NO FILTRO] Ocorreu um erro ao salvar: {str(e)}\n")
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)



@login_required
@require_POST
def editar_chamado(request, operadora_slug, projeto_slug, chamado_id):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'erro': 'JSON inválido.'}, status=400)

    ticket_arion = (payload.get('ticket_arion') or '').strip()
    designacao   = (payload.get('designacao') or '').strip()

    if not ticket_arion or not designacao:
        return JsonResponse(
            {'ok': False, 'erro': 'Ticket Arion e Designação são obrigatórios.'},
            status=400
        )

    try:
        chamado = Chamado.objects.get(
            id=chamado_id,
            operadora_slug=operadora_slug,
            projeto_slug=projeto_slug,
        )
    except Chamado.DoesNotExist:
        return JsonResponse({'ok': False, 'erro': 'Chamado não encontrado.'}, status=404)

    chamado.id_personalizado = (payload.get('id_personalizado') or '').strip()
    chamado.ticket_arion     = ticket_arion
    chamado.url_ticket       = (payload.get('url_ticket') or '').strip()
    chamado.designacao       = designacao
    chamado.isp              = (payload.get('isp') or '').strip()
    chamado.contato          = (payload.get('contato') or '').strip()
    chamado.local            = (payload.get('local') or '').strip()
    chamado.obs              = (payload.get('obs') or '').strip()
    chamado.save()

    sla_valor, sla_unidade = _get_sla_config(operadora_slug, projeto_slug)
    status_map = _status_display_map()

    hoje = timezone.now()
    todos_do_mes = list(Chamado.objects.filter(
        operadora_slug=operadora_slug, projeto_slug=projeto_slug,
        data_abertura__year=hoje.year, data_abertura__month=hoje.month,
    ))

    return JsonResponse({
        'ok': True,
        'chamado': _serializar_chamado(chamado, sla_valor, sla_unidade, todos_do_mes, status_map),
    })

import json
import logging
import threading
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.db.models.functions import Coalesce

from aplicativos.core_broker.models import TicketREC, StatusEnvio, Projeto, OrigemAcao, ConfiguracaoRobo
from aplicativos.comunicacao.models import ConfigEmailProjeto
from aplicativos.automacao.scraper import executar_scraper
from aplicativos.autenticacao.decorators import admin_required   # ← NOVO

logger = logging.getLogger(__name__)
LOGIN_URL = 'autenticacao:login'
MAX_RECS_POR_DISPARO = 10


# ── 1. DASHBOARD ──────────────────────────────────────────────
# ── 1. DASHBOARD ──────────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
def dashboard(request):
    recs = TicketREC.objects.all().order_by(
        Coalesce(
            'data_abertura_portal',
            'data_registro_operadora',
            'data_atualizacao_portal',
            'data_coleta',
        ).desc()
    )

    context = {
        'page_title':              'Dashboard',
        'recs':                    recs,
        'total_recs':              recs.count(),
        'total_novos':             recs.filter(status_envio=StatusEnvio.NOVO).count(),
        'total_enviados':          recs.filter(status_envio=StatusEnvio.ENVIADO).count(), # "Aguardando OTRS"
        'total_revisao':           recs.filter(status_envio=StatusEnvio.REVISAO).count(),
        'total_concluidos':        recs.filter(status_envio=StatusEnvio.REGISTRADO).count(), # <-- NOVO CARD CONCLUÍDOS
        'revisao_count':           recs.filter(status_envio=StatusEnvio.REVISAO).count(),
        'total_com_chamado_arion': recs.exclude(chamado_operadora='').exclude(chamado_operadora__isnull=True).count(),
        'total_sem_chamado_arion': recs.filter(chamado_operadora='').count(),
        'robo_ativo':              ConfiguracaoRobo.get_ou_criar().ativo,
    }
    return render(request, 'painel/dashboard.html', context)


# ── 2. DETALHE DA REC ─────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
def rec_detalhe(request, rec_id):
    rec = get_object_or_404(TicketREC, rec_id=rec_id)
    context = {
        'page_title': f'REC {rec.rec_id}',
        'rec':        rec,
    }
    return render(request, 'painel/rec_detalhe.html', context)


# ── 3. DISPARAR E-MAIL ────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_POST
@csrf_protect
def disparar(request):
    try:
        body    = json.loads(request.body)
        rec_ids = body.get('recs', [])

        if not isinstance(rec_ids, list):
            return JsonResponse({'erro': 'Formato inválido.'}, status=400)

        rec_ids = [str(r).strip() for r in rec_ids if r]

    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'erro': 'JSON inválido.'}, status=400)

    if not rec_ids:
        return JsonResponse({'erro': 'Nenhuma REC informada.'}, status=400)

    if len(rec_ids) > MAX_RECS_POR_DISPARO:
        return JsonResponse(
            {'erro': f'Máximo de {MAX_RECS_POR_DISPARO} RECs por disparo.'},
            status=400
        )

    enviadas, erros = [], []

    from aplicativos.comunicacao.services import disparar_email

    for rec_id in rec_ids:
        try:
            rec = TicketREC.objects.get(rec_id=rec_id)

            if rec.ja_enviado:
                erros.append(f'{rec_id}: Já foi enviada anteriormente.')
                continue

            disparar_email(rec)
            rec.status_envio  = StatusEnvio.ENVIADO
            rec.data_envio    = timezone.now()
            rec.origem_envio  = OrigemAcao.MANUAL
            rec.enviado_por   = str(request.user)
            rec.save(update_fields=['status_envio', 'data_envio', 'origem_envio', 'enviado_por'])
            enviadas.append(rec_id)
            logger.info('[Arion] REC %s enviada manualmente pelo usuário %s', rec_id, request.user)
        except TicketREC.DoesNotExist:
            erros.append(f'{rec_id}: Não encontrada.')
        except Exception as e:
            logger.error('[Arion] Falha crítica ao enviar REC %s: %s', rec_id, str(e), exc_info=True)
            erros.append(f'{rec_id}: Falha no envio.')

    return JsonResponse({
        'mensagem': f'{len(enviadas)} REC(s) enviada(s) com sucesso.',
        'enviadas': enviadas,
        'erros':    erros,
    })


# ── 4. DESCARTAR REC ──────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_POST
@csrf_protect
def descartar(request):
    try:
        body   = json.loads(request.body)
        rec_id = str(body.get('rec_id', '')).strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'erro': 'JSON inválido.'}, status=400)

    if not rec_id:
        return JsonResponse({'erro': 'ID da REC não informado.'}, status=400)

    deleted, _ = TicketREC.objects.filter(rec_id=rec_id).delete()

    if deleted:
        logger.info('[Arion] REC %s descartada pelo usuário %s', rec_id, request.user)
        return JsonResponse({'mensagem': f'REC {rec_id} descartada.'})

    return JsonResponse({'erro': 'REC não encontrada no sistema.'}, status=404)


# ── 5. CLASSIFICAR PROJETO ────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_POST
def classificar_rec(request, rec_id):
    rec     = get_object_or_404(TicketREC, rec_id=rec_id)
    projeto = request.POST.get('projeto', '').strip()

    projetos_validos = [p.value for p in Projeto]

    if projeto not in projetos_validos:
        messages.error(request, 'O projeto selecionado é inválido.')
        return redirect('painel:rec_detalhe', rec_id=rec_id)

    rec.projeto      = projeto
    rec.status_envio = StatusEnvio.NOVO
    rec.save(update_fields=['projeto', 'status_envio'])

    logger.info('[Arion] REC %s classificada como %s pelo usuário %s', rec_id, projeto, request.user)
    messages.success(
        request,
        f'REC {rec_id} foi classificada como {rec.get_projeto_display()} e liberada para envio.'
    )
    return redirect('painel:rec_detalhe', rec_id=rec_id)


# ── 6. EXECUTAR SCRAPER ───────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_POST
@csrf_protect
def executar_scraper_view(request):
    resultado = {}
    excecao   = []

    def _rodar():
        try:
            resultado.update(
                executar_scraper(
                    origem=OrigemAcao.MANUAL,
                    executor=str(request.user),
                )
            )
        except Exception as e:
            excecao.append(str(e))

    t = threading.Thread(target=_rodar, daemon=True)
    t.start()
    t.join(timeout=300)

    if t.is_alive():
        logger.error('[Arion] Scraper ultrapassou o timeout de 5 minutos.')
        return JsonResponse({'erro': 'Timeout: o robô demorou mais de 5 minutos.'}, status=504)

    if excecao:
        logger.error('[Arion] Scraper encerrou com erro: %s', excecao[0])
        return JsonResponse(
            {'erro': 'Scraper encerrou com erro crítico. Verifique os logs do servidor.'},
            status=500
        )

    logger.info(
        '[Arion] Scraper executado manualmente por %s: %s novas, %s ignoradas',
        request.user, resultado.get('novas', 0), resultado.get('ignoradas', 0)
    )

    return JsonResponse({
        'mensagem':  f"{resultado.get('novas', 0)} REC(s) nova(s) salva(s).",
        'novas':     resultado.get('novas', 0),
        'ignoradas': resultado.get('ignoradas', 0),
        'erros':     resultado.get('erros', []),
    })


# ── 7. RECS ENVIADAS (HISTÓRICO) ──────────────────────────────
@login_required(login_url=LOGIN_URL)
def recs_enviadas(request):
    recs = TicketREC.objects.filter(status_envio=StatusEnvio.ENVIADO).order_by('-data_envio')

    configs_dict = {
        config.projeto: config.destinatarios
        for config in ConfigEmailProjeto.objects.filter(ativo=True)
    }

    for rec in recs:
        rec.destino_email = configs_dict.get(rec.projeto, '')

    context = {
        'page_title':    'Histórico de Envios',
        'recs':          recs,
        'revisao_count': TicketREC.objects.filter(status_envio=StatusEnvio.REVISAO).count(),
    }
    return render(request, 'painel/recs_enviadas.html', context)


# ── 8. GESTÃO DE DESTINOS — SOMENTE ADMIN ─────────────────────
@login_required(login_url=LOGIN_URL)
@admin_required                          # ← NOVO
def configuracao_emails(request):
    if request.method == "POST":
        for proj_code, _ in Projeto.choices:
            dest = request.POST.get(f'dest_{proj_code}', '').strip()
            cc   = request.POST.get(f'cc_{proj_code}', '').strip()

            ConfigEmailProjeto.objects.update_or_create(
                projeto=proj_code,
                defaults={
                    'destinatarios': dest if dest else 'atendimento@grupoarion.com.br',
                    'cc':   cc,
                    'ativo': True,
                }
            )
        messages.success(request, "Destinatários atualizados com sucesso!")
        return redirect('painel:destinos')

    configs = {c.projeto: c for c in ConfigEmailProjeto.objects.all()}
    projetos_info = []
    for proj_code, proj_name in Projeto.choices:
        projetos_info.append({
            'code':   proj_code,
            'name':   proj_name,
            'config': configs.get(proj_code),
        })

    context = {
        'page_title':    'Configurar Destinos',
        'projetos':      projetos_info,
        'revisao_count': TicketREC.objects.filter(status_envio=StatusEnvio.REVISAO).count(),
    }
    return render(request, 'painel/configuracao_emails.html', context)


# ── 9. MARCAR COMO LIDA SEM ENVIAR E-MAIL ─────────────────────
@login_required(login_url=LOGIN_URL)
@require_POST
@csrf_protect
def baixar_sem_email(request):
    try:
        body    = json.loads(request.body)
        rec_ids = [str(r).strip() for r in body.get('recs', []) if r]
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'erro': 'JSON inválido.'}, status=400)

    if not rec_ids:
        return JsonResponse({'erro': 'Nenhuma REC informada.'}, status=400)

    baixadas = []
    for rec_id in rec_ids:
        try:
            rec = TicketREC.objects.get(
                rec_id=rec_id,
                status_envio__in=[StatusEnvio.NOVO, StatusEnvio.REVISAO]
            )
            rec.status_envio = StatusEnvio.ENVIADO
            rec.data_envio   = timezone.now()
            rec.origem_envio = OrigemAcao.MANUAL
            rec.enviado_por  = str(request.user)
            rec.save(update_fields=['status_envio', 'data_envio', 'origem_envio', 'enviado_por'])
            baixadas.append(rec_id)
            logger.info('[Arion] REC %s baixada sem e-mail pelo usuário %s', rec_id, request.user)
        except Exception:
            pass

    return JsonResponse({
        'mensagem': f'{len(baixadas)} REC(s) marcada(s) como enviada(s) com sucesso!'
    })

# ── 10. TOGGLE DO ROBÔ ────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@admin_required  # ← DECORATOR ADICIONADO AQUI: Bloqueia quem não é ADMIN
@require_POST
@csrf_protect
def toggle_robo(request):
    config       = ConfiguracaoRobo.get_ou_criar()
    config.ativo = not config.ativo
    # ── NOVO: rastreabilidade ─────────────────────────────────
    config.alterado_por = str(request.user)
    config.alterado_em  = timezone.now()
    config.save(update_fields=['ativo', 'alterado_por', 'alterado_em'])

    estado = 'ATIVO' if config.ativo else 'PAUSADO'
    logger.info('[Arion] Robô %s pelo usuário %s', estado, request.user)

    return JsonResponse({
        'ativo':    config.ativo,
        'mensagem': f'Robô {estado} por {request.user}.',
    })


# ── 11. STATUS DO ROBÔ ────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
def status_robo(request):
    config = ConfiguracaoRobo.get_ou_criar()
    return JsonResponse({'ativo': config.ativo})


# ── 12. RECS RECENTES (POLLING) ───────────────────────────────
@login_required(login_url=LOGIN_URL)
def recs_recentes(request):
    desde_unix = request.GET.get('desde')

    if not desde_unix:
        return JsonResponse({'recs': []})

    try:
        desde_unix = float(desde_unix)
        desde_dt   = timezone.datetime.fromtimestamp(desde_unix, tz=timezone.get_current_timezone())
    except (ValueError, TypeError, OSError):
        return JsonResponse({'erro': 'Timestamp inválido.'}, status=400)

    novas = TicketREC.objects.filter(data_coleta__gt=desde_dt).order_by('-data_coleta')

    dados = []
    for rec in novas:
        data_portal = (
            rec.data_abertura_portal or
            rec.data_registro_operadora or
            rec.data_atualizacao_portal or
            rec.data_coleta
        )
        dados.append({
            'rec_id':            rec.rec_id,
            'designacao_claro':  rec.designacao_claro,
            'bl_dados':          rec.bl_dados,
            'projeto':           rec.projeto,
            'projeto_display':   rec.get_projeto_display(),
            'chamado_operadora': rec.chamado_operadora,
            'status_envio':      rec.status_envio,
            'status_interface':  rec.status_interface,
            'origem_coleta':     rec.origem_coleta,
            'coletado_por':      rec.coletado_por,
            'origem_envio':      rec.origem_envio,
            'enviado_por':       rec.enviado_por,
            'sintoma':           rec.sintoma,
            'data_portal':       data_portal.strftime('%d/%m/%Y %H:%M') if data_portal else '—',
            'data_portal_iso':   data_portal.strftime('%Y-%m-%d %H:%M') if data_portal else '',
            'tem_chamado':       'sim' if rec.chamado_operadora else 'nao',
        })

    return JsonResponse({'recs': dados})



# ── 13. REENVIAR (TESTE MANUAL / CONTROLADO) ──────────────────
@login_required(login_url=LOGIN_URL)
@admin_required
@require_POST
@csrf_protect
def reenviar(request):
    try:
        body   = json.loads(request.body)
        rec_id = str(body.get('rec_id', '')).strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'erro': 'JSON inválido.'}, status=400)

    if not rec_id:
        return JsonResponse({'erro': 'ID da REC não informado.'}, status=400)

    try:
        rec = TicketREC.objects.get(rec_id=rec_id)
    except TicketREC.DoesNotExist:
        return JsonResponse({'erro': 'REC não encontrada.'}, status=404)

    # Só reenvia o que já saiu pelo menos uma vez.
    # Para REC nova/revisão, usar o fluxo normal de disparo (/painel/disparar/).
    if rec.status_envio not in [StatusEnvio.ENVIADO, StatusEnvio.REGISTRADO]:
        return JsonResponse(
            {'erro': f'REC {rec_id} ainda não foi enviada. Use o disparo normal.'},
            status=400
        )

    from aplicativos.comunicacao.services import disparar_email

    try:
        disparar_email(rec)
        # Mantém o status atual (não volta pra NOVO/ENVIADO) — é só um reenvio de e-mail.
        rec.data_envio   = timezone.now()
        rec.origem_envio = OrigemAcao.MANUAL
        rec.enviado_por  = str(request.user)
        rec.save(update_fields=['data_envio', 'origem_envio', 'enviado_por'])

        logger.warning(
            '[Arion] REENVIO manual (teste) da REC %s disparado por %s — status mantido em %s',
            rec_id, request.user, rec.status_envio
        )
    except Exception as e:
        logger.error('[Arion] Falha crítica ao REENVIAR REC %s: %s', rec_id, str(e), exc_info=True)
        return JsonResponse({'erro': f'Falha ao reenviar a REC {rec_id}.'}, status=500)

    return JsonResponse({
        'mensagem': f'REC {rec_id} reenviada com sucesso (uso manual/teste).',
        'rec_id':   rec_id,
    })
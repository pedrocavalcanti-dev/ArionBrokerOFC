import json
import logging
from datetime import datetime, time
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from aplicativos.chamados.models import Reincidencia
from aplicativos.chamados.reincidencias import services
from aplicativos.chamados.reincidencias.services import RegraReincidenciaError

logger = logging.getLogger(__name__)
User = get_user_model()


# ==============================================================================
# FUNÇÕES AUXILIARES INTERNAS
# ==============================================================================

def _json_sucesso(mensagem="", dados=None, status=200):
    resposta = {"ok": True}
    if mensagem:
        resposta["mensagem"] = mensagem
    if dados is not None:
        resposta["dados"] = dados
    return JsonResponse(resposta, status=status)


def _json_erro(mensagem, status=400, dados=None, campos=None):
    resposta = {"ok": False, "erro": mensagem}
    if dados is not None:
        resposta["dados"] = dados
    if campos is not None:
        resposta["campos"] = campos
    return JsonResponse(resposta, status=status)


def _obter_dados_request(request):
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            return json.loads(request.body)
        except json.JSONDecodeError:
            raise ValueError("JSON inválido.")
    return request.POST.dict()


def _parse_data_hora(valor):
    if not valor or str(valor).strip() == "":
        return None
    try:
        # Suporta formatos ISO e datetime-local nativo do HTML5
        dt = datetime.fromisoformat(str(valor).replace('Z', '+00:00'))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except ValueError:
        raise ValueError(f"Data inválida: {valor}")


def _obter_parametros_filtros(request):
    params = {
        "busca": request.GET.get("busca", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "classificacao": request.GET.get("classificacao", "").strip(),
        "responsavel": request.GET.get("responsavel", "").strip(),
        "operadora": request.GET.get("operadora", "").strip(),
        "projeto": request.GET.get("projeto", "").strip(),
        "data_inicio": None,
        "data_fim": None,
        "ordenacao": request.GET.get("ordenacao", "").strip(),
    }

    inicio_str = request.GET.get("data_inicio", "").strip()
    if inicio_str:
        try:
            dt_inicio = datetime.strptime(inicio_str, "%Y-%m-%d")
            dt_inicio = datetime.combine(dt_inicio, time.min)
            params["data_inicio"] = timezone.make_aware(dt_inicio)
        except ValueError:
            pass

    fim_str = request.GET.get("data_fim", "").strip()
    if fim_str:
        try:
            dt_fim = datetime.strptime(fim_str, "%Y-%m-%d")
            dt_fim = datetime.combine(dt_fim, time.max)
            params["data_fim"] = timezone.make_aware(dt_fim)
        except ValueError:
            pass

    return params


def _obter_opcoes_filtros():
    """Retorna listas de operadoras, projetos e choices para montar os selects."""
    operadoras = list(
        Reincidencia.objects.exclude(operadora="")
        .exclude(operadora__isnull=True)
        .values_list("operadora", flat=True)
        .distinct()
        .order_by("operadora")
    )
    
    projetos = list(
        Reincidencia.objects.exclude(projeto="")
        .exclude(projeto__isnull=True)
        .values_list("projeto", flat=True)
        .distinct()
        .order_by("projeto")
    )
    
    return {
        "operadoras": operadoras,
        "projetos": projetos,
        "status_choices": Reincidencia.STATUS_CHOICES,
        "classificacao_choices": Reincidencia.CLASSIFICACAO_CHOICES,
    }


def _tratar_excecao_api(exc, contexto):
    if isinstance(exc, RegraReincidenciaError):
        return _json_erro(str(exc), status=400)
    elif isinstance(exc, ValueError):
        return _json_erro(str(exc), status=400)
    elif isinstance(exc, PermissionDenied):
        return _json_erro("Você não tem permissão para realizar esta ação.", status=403)
    elif isinstance(exc, Reincidencia.DoesNotExist):
        return _json_erro("Reincidência não encontrada.", status=404)
    elif isinstance(exc, User.DoesNotExist):
        return _json_erro("Usuário não encontrado.", status=404)
    
    logger.exception(f"Erro inesperado em {contexto}: {str(exc)}")
    return _json_erro("Erro interno ao processar a solicitação.", status=500)


# ==============================================================================
# VIEWS DE PÁGINAS (HTML)
# ==============================================================================

@login_required
def tratamento(request):
    filtros = _obter_parametros_filtros(request)
    opcoes = _obter_opcoes_filtros()
    
    queryset = services.filtrar_reincidencias(
        fila="TRATAMENTO",
        busca=filtros["busca"],
        status=filtros["status"],
        classificacao=filtros["classificacao"],
        responsavel=filtros["responsavel"],
        usuario=request.user,
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"],
        ordenacao=filtros["ordenacao"],
        operadora=filtros["operadora"],
        projeto=filtros["projeto"],
    )
    
    contexto = {
        "reincidencias": queryset,
        "resumo": services.obter_resumo_reincidencias(),
        "filtros": {
            "busca": filtros["busca"],
            "status": filtros["status"],
            "classificacao": filtros["classificacao"],
            "responsavel": filtros["responsavel"],
            "operadora": filtros["operadora"],
            "projeto": filtros["projeto"],
            "data_inicio": request.GET.get("data_inicio", "").strip(),
            "data_fim": request.GET.get("data_fim", "").strip(),
            "ordenacao": filtros["ordenacao"],
        },
        "status_choices": Reincidencia.STATUS_CHOICES,
        "classificacao_choices": Reincidencia.CLASSIFICACAO_CHOICES,
        "fila_atual": "TRATAMENTO",
        "fila_atual_label": "Reincidências para Tratamento",
        "operadoras": opcoes["operadoras"],
        "projetos": opcoes["projetos"],
        "opcoes_filtros": opcoes,
    }
    return render(request, "chamados/reincidencias/tratamento.html", contexto)


@login_required
def monitoramento(request):
    filtros = _obter_parametros_filtros(request)
    opcoes = _obter_opcoes_filtros()
    
    queryset = services.filtrar_reincidencias(
        fila="MONITORAMENTO",
        busca=filtros["busca"],
        status=filtros["status"],
        classificacao=filtros["classificacao"],
        responsavel=filtros["responsavel"],
        usuario=request.user,
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"],
        ordenacao=filtros["ordenacao"],
        operadora=filtros["operadora"],
        projeto=filtros["projeto"],
    )
    
    contexto = {
        "reincidencias": queryset,
        "resumo": services.obter_resumo_reincidencias(),
        "filtros": {
            "busca": filtros["busca"],
            "status": filtros["status"],
            "classificacao": filtros["classificacao"],
            "responsavel": filtros["responsavel"],
            "operadora": filtros["operadora"],
            "projeto": filtros["projeto"],
            "data_inicio": request.GET.get("data_inicio", "").strip(),
            "data_fim": request.GET.get("data_fim", "").strip(),
            "ordenacao": filtros["ordenacao"],
        },
        "status_choices": Reincidencia.STATUS_CHOICES,
        "classificacao_choices": Reincidencia.CLASSIFICACAO_CHOICES,
        "fila_atual": "MONITORAMENTO",
        "fila_atual_label": "Monitoramento RREIP",
        "operadoras": opcoes["operadoras"],
        "projetos": opcoes["projetos"],
        "opcoes_filtros": opcoes,
    }
    return render(request, "chamados/reincidencias/monitoramento.html", contexto)


@login_required
def finalizados(request):
    filtros = _obter_parametros_filtros(request)
    opcoes = _obter_opcoes_filtros()
    
    queryset = services.filtrar_reincidencias(
        fila="FINALIZADO",
        busca=filtros["busca"],
        status=filtros["status"],
        classificacao=filtros["classificacao"],
        responsavel=filtros["responsavel"],
        usuario=request.user,
        data_inicio=filtros["data_inicio"],
        data_fim=filtros["data_fim"],
        ordenacao=filtros["ordenacao"],
        operadora=filtros["operadora"],
        projeto=filtros["projeto"],
    )
    
    contexto = {
        "reincidencias": queryset,
        "resumo": services.obter_resumo_reincidencias(),
        "filtros": {
            "busca": filtros["busca"],
            "status": filtros["status"],
            "classificacao": filtros["classificacao"],
            "responsavel": filtros["responsavel"],
            "operadora": filtros["operadora"],
            "projeto": filtros["projeto"],
            "data_inicio": request.GET.get("data_inicio", "").strip(),
            "data_fim": request.GET.get("data_fim", "").strip(),
            "ordenacao": filtros["ordenacao"],
        },
        "status_choices": Reincidencia.STATUS_CHOICES,
        "classificacao_choices": Reincidencia.CLASSIFICACAO_CHOICES,
        "fila_atual": "FINALIZADO",
        "fila_atual_label": "Finalizados",
        "operadoras": opcoes["operadoras"],
        "projetos": opcoes["projetos"],
        "opcoes_filtros": opcoes,
    }
    return render(request, "chamados/reincidencias/finalizados.html", contexto)


@login_required
def detalhes(request, pk):
    reincidencia = get_object_or_404(
        Reincidencia.objects.select_related("responsavel", "chamado"), pk=pk
    )
    historico = reincidencia.historico.select_related("usuario").all()
    historico_designacao = services.buscar_historico_designacao(
        reincidencia.designacao,
        excluir_id=reincidencia.id
    )
    
    reincidencia_dados = services.serializar_reincidencia(reincidencia, request.user)

    contexto = {
        "reincidencia": reincidencia,
        "reincidencia_dados": reincidencia_dados,
        "historico": historico,
        "historico_designacao": historico_designacao,
        "status_choices": Reincidencia.STATUS_CHOICES,
        "classificacao_choices": Reincidencia.CLASSIFICACAO_CHOICES,
        "pode_editar": reincidencia_dados["pode_editar"],
        "pode_solicitar_monitoramento": reincidencia_dados["pode_solicitar_monitoramento"],
        "pode_iniciar_monitoramento": reincidencia_dados["pode_iniciar_monitoramento"],
        "texto_otrs": reincidencia_dados["texto_otrs"],
        "email_monitoramento": reincidencia_dados.get("email_monitoramento", {}),
    }
    return render(request, "chamados/reincidencias/detalhes.html", contexto)


# ==============================================================================
# VIEWS DE API
# ==============================================================================

@login_required
@require_GET
def api_resumo(request):
    try:
        dados = services.obter_resumo_reincidencias()
        return _json_sucesso(dados=dados)
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_resumo")


@login_required
@require_POST
def api_criar(request):
    try:
        dados = _obter_dados_request(request)
        
        campos_data = ["data_ticket", "data_ticket_origem"]
        for campo in campos_data:
            if campo in dados:
                dados[campo] = _parse_data_hora(dados[campo])
                
        reincidencia = services.criar_reincidencia(dados, usuario=request.user)
        return _json_sucesso(
            mensagem="Reincidência criada com sucesso.",
            dados=services.serializar_reincidencia(reincidencia, request.user),
            status=201
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_criar")


@login_required
@require_POST
def api_editar(request, pk):
    try:
        dados = _obter_dados_request(request)
        
        campos_data = [
            "data_ticket", "data_ticket_origem", 
            "data_ticket_monitoramento", "data_encerramento_origem"
        ]
        for campo in campos_data:
            if campo in dados:
                dados[campo] = _parse_data_hora(dados[campo])
                
        reincidencia = services.editar_reincidencia(
            reincidencia_id=pk,
            dados=dados,
            usuario=request.user
        )
        return _json_sucesso(
            mensagem="Reincidência atualizada com sucesso.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_editar")


@login_required
@require_POST
def api_excluir(request, pk):
    try:
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("Apenas administradores podem excluir registros.")
            
        reincidencia = Reincidencia.objects.get(pk=pk)
        dados = services.serializar_reincidencia(reincidencia, request.user)
        reincidencia.delete()
        
        return _json_sucesso(
            mensagem="Reincidência excluída com sucesso (Ação Definitiva).",
            dados=dados
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_excluir")


@login_required
@require_POST
def api_apropriar(request, pk):
    try:
        reincidencia = services.apropriar_reincidencia(
            reincidencia_id=pk,
            usuario=request.user
        )
        return _json_sucesso(
            mensagem="Reincidência apropriada com sucesso.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_apropriar")


@login_required
@require_POST
def api_liberar(request, pk):
    try:
        reincidencia = services.liberar_reincidencia(
            reincidencia_id=pk,
            usuario=request.user
        )
        return _json_sucesso(
            mensagem="Responsável liberado com sucesso.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_liberar")


@login_required
@require_POST
def api_transferir(request, pk):
    try:
        dados = _obter_dados_request(request)
        responsavel_id = dados.get("responsavel_id")
        
        if not responsavel_id:
            raise RegraReincidenciaError("O ID do novo responsável é obrigatório.")
            
        reincidencia = services.transferir_reincidencia(
            reincidencia_id=pk,
            novo_responsavel_id=responsavel_id,
            usuario=request.user
        )
        return _json_sucesso(
            mensagem="Reincidência transferida com sucesso.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_transferir")


@login_required
@require_POST
def api_atualizar_status(request, pk):
    try:
        dados = _obter_dados_request(request)
        status = dados.get("status")
        
        if not status:
            raise RegraReincidenciaError("O status é obrigatório.")
            
        reincidencia = services.atualizar_status_reincidencia(
            reincidencia_id=pk,
            novo_status=status,
            usuario=request.user
        )
        return _json_sucesso(
            mensagem="Status atualizado com sucesso.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_atualizar_status")


@login_required
@require_POST
def api_salvar_analise(request, pk):
    try:
        dados = _obter_dados_request(request)
        campos_analise = {
            "motivo_identificado": dados.get("motivo_identificado"),
            "causa_raiz": dados.get("causa_raiz"),
            "acao_realizada": dados.get("acao_realizada"),
            "acao_preventiva": dados.get("acao_preventiva"),
            "conclusao": dados.get("conclusao")
        }
        
        reincidencia = services.atualizar_analise_reincidencia(
            reincidencia_id=pk,
            dados=campos_analise,
            usuario=request.user
        )
        
        reincidencia_serializada = services.serializar_reincidencia(reincidencia, request.user)
        return _json_sucesso(
            mensagem="Análise salva com sucesso.",
            dados={
                "reincidencia": reincidencia_serializada,
                "texto_otrs": reincidencia_serializada["texto_otrs"]
            }
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_salvar_analise")


@login_required
@require_POST
def api_classificar(request, pk):
    try:
        dados = _obter_dados_request(request)
        classificacao = dados.get("classificacao")
        motivo = dados.get("motivo", "")
        
        if classificacao in ["MASSIVA", "FALSO_POSITIVO", "FALHA_ISOLADA", "DUPLICADO", "NAO_SE_APLICA"]:
            if not str(motivo).strip():
                return _json_erro(
                    "Verifique os campos informados.", 
                    campos={"motivo": "O motivo é obrigatório para esta classificação."}
                )
                
        reincidencia = services.classificar_reincidencia(
            reincidencia_id=pk,
            classificacao=classificacao,
            motivo_classificacao=motivo,
            usuario=request.user
        )
        
        if classificacao == "REINCIDENCIA_CONFIRMADA":
            mensagem = "Reincidência confirmada com sucesso."
        else:
            mensagem = f"Registro classificado como {reincidencia.get_classificacao_display()} e movido para Finalizados."
            
        return _json_sucesso(
            mensagem=mensagem,
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_classificar")


@login_required
@require_GET
def api_texto_otrs(request, pk):
    try:
        reincidencia = Reincidencia.objects.get(pk=pk)
        texto = services.gerar_texto_otrs(reincidencia)
        return _json_sucesso(dados={"texto": texto})
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_texto_otrs")


@login_required
@require_GET
def api_previa_email_monitoramento(request, pk):
    try:
        reincidencia = Reincidencia.objects.get(pk=pk)
        email_dados = services.gerar_contexto_email_monitoramento(reincidencia)
        return _json_sucesso(dados=email_dados)
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_previa_email_monitoramento")


@login_required
@require_POST
def api_enviar_email_monitoramento(request, pk):
    try:
        reincidencia = Reincidencia.objects.get(pk=pk)
        
        # Validação de regras e permissão
        if not services.usuario_pode_editar(reincidencia, request.user):
            raise PermissionDenied("Você não tem permissão para solicitar monitoramento.")
            
        if not reincidencia.pode_solicitar_monitoramento():
            raise RegraReincidenciaError("Registro não atende aos critérios para solicitar monitoramento.")

        # Importação interna para evitar falhas caso o módulo comunicação esteja sendo carregado
        try:
            from aplicativos.comunicacao.services import disparar_email_monitoramento
        except ImportError:
            raise RegraReincidenciaError("Serviço de comunicação não encontrado ou inativo no momento.")

        # Dispara efetivamente via SMTP
        try:
            disparar_email_monitoramento(reincidencia, usuario=request.user)
        except Exception as e:
            logger.error(f"Falha de SMTP ao enviar email RREIP {pk}: {str(e)}")
            return _json_erro("Não foi possível enviar a solicitação de monitoramento via SMTP.", status=500)

        # Se passou sem exceptions, o e-mail foi entregue ao SMTP do sistema.
        dados_anteriores = {"status": reincidencia.status}
        
        reincidencia.status = "AGUARDANDO_TICKET_MONITORAMENTO"
        reincidencia.email_monitoramento_enviado = True
        reincidencia.data_envio_monitoramento = timezone.now()
        reincidencia.email_monitoramento_enviado_por = request.user
        reincidencia.save()

        services.registrar_historico(
            reincidencia=reincidencia,
            tipo_evento="SOLICITACAO_MONITORAMENTO",
            descricao="Solicitação de monitoramento enviada com sucesso ao sistema de tickets.",
            usuario=request.user,
            dados_anteriores=dados_anteriores,
            dados_novos={"status": reincidencia.status}
        )
        
        return _json_sucesso(
            mensagem="Solicitação enviada e status atualizado para aguardando ticket.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_enviar_email_monitoramento")


@login_required
@require_POST
def api_registrar_ticket_monitoramento(request, pk):
    try:
        dados = _obter_dados_request(request)
        
        ticket = dados.get("ticket_monitoramento") or dados.get("ticket", "")
        url = dados.get("url_ticket_monitoramento") or dados.get("url", "")
        data_str = dados.get("data_ticket_monitoramento") or dados.get("data", "")
        data = _parse_data_hora(data_str)

        reincidencia = services.registrar_ticket_monitoramento(
            reincidencia_id=pk,
            ticket=ticket,
            url=url,
            data=data,
            usuario=request.user
        )
        
        return _json_sucesso(
            mensagem="Ticket de monitoramento registrado com sucesso.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_registrar_ticket_monitoramento")


@login_required
@require_POST
def api_mover_monitoramento(request, pk):
    try:
        reincidencia = services.mover_para_monitoramento(
            reincidencia_id=pk,
            usuario=request.user
        )
        return _json_sucesso(
            mensagem="Monitoramento iniciado por 30 dias.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_mover_monitoramento")


@login_required
@require_POST
def api_reabrir(request, pk):
    """Usada exclusivamente quando o chamado RREIP reincide/falha."""
    try:
        dados = _obter_dados_request(request)
        data_ticket = dados.get("data_ticket")
        
        if data_ticket:
            data_ticket = _parse_data_hora(data_ticket)
            
        reincidencia = services.reabrir_para_tratamento(
            reincidencia_id=pk,
            usuario=request.user,
            novo_ticket=dados.get("novo_ticket", ""),
            url_ticket=dados.get("url_ticket", ""),
            data_ticket=data_ticket
        )
        return _json_sucesso(
            mensagem="Nova reincidência registrada e devolvida para Tratamento.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_reabrir")


@login_required
@require_POST
def api_reabrir_finalizado(request, pk):
    """Usada para trazer registros descartados ou finalizados incorretamente de volta ao tratamento."""
    try:
        dados = _obter_dados_request(request)
        motivo = dados.get("motivo", "")
        
        if not str(motivo).strip():
            return _json_erro("Verifique os campos informados.", campos={"motivo": "Motivo da reabertura é obrigatório."})
            
        reincidencia = services.reabrir_registro_finalizado(
            reincidencia_id=pk,
            usuario=request.user
        )
        return _json_sucesso(
            mensagem="Registro reaberto para análise e devolvido ao Tratamento.",
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_reabrir_finalizado")


@login_required
@require_POST
def api_concluir(request, pk):
    try:
        dados = _obter_dados_request(request)
        forcar_str = str(dados.get("forcar", "")).strip().lower()
        forcar = forcar_str in ["true", "1", "sim", "on"]
        
        reincidencia = services.concluir_monitoramento(
            reincidencia_id=pk,
            usuario=request.user,
            forcar=forcar
        )
        
        mensagem = "Monitoramento concluído com sucesso."
        if forcar:
            mensagem = "Monitoramento concluído antecipadamente (Ação Forçada)."
            
        return _json_sucesso(
            mensagem=mensagem,
            dados=services.serializar_reincidencia(reincidencia, request.user)
        )
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_concluir")


@login_required
@require_GET
def api_historico(request, pk):
    try:
        reincidencia = Reincidencia.objects.get(pk=pk)
        
        historico_qs = reincidencia.historico.select_related("usuario").all()
        historico_serializado = [services.serializar_historico(item) for item in historico_qs]
        
        anteriores_qs = services.buscar_historico_designacao(
            reincidencia.designacao,
            excluir_id=reincidencia.id
        )
        anteriores_serializados = [services.serializar_reincidencia(item, request.user) for item in anteriores_qs]
        
        return _json_sucesso(dados={
            "historico": historico_serializado,
            "reincidencias_anteriores": anteriores_serializados,
        })
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_historico")


@login_required
@require_GET
def api_detalhes(request, pk):
    try:
        reincidencia = Reincidencia.objects.select_related("responsavel").get(pk=pk)
        reincidencia_dados = services.serializar_reincidencia(reincidencia, request.user)
        
        historico_qs = reincidencia.historico.select_related("usuario").all()
        historico_serializado = [services.serializar_historico(item) for item in historico_qs]
        
        anteriores_qs = services.buscar_historico_designacao(
            reincidencia.designacao,
            excluir_id=reincidencia.id
        )
        anteriores_serializados = [services.serializar_reincidencia(item, request.user) for item in anteriores_qs]
        
        return _json_sucesso(dados={
            "reincidencia": reincidencia_dados,
            "historico": historico_serializado,
            "reincidencias_anteriores": anteriores_serializados,
        })
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_detalhes")


@login_required
@require_GET
def api_usuarios(request):
    try:
        usuarios_qs = User.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        lista_usuarios = []
        for usuario in usuarios_qs:
            nome = usuario.get_full_name() or usuario.username
            lista_usuarios.append({
                "id": usuario.id,
                "nome": nome,
                "username": usuario.username,
                "is_staff": usuario.is_staff,
            })
            
        return _json_sucesso(dados=lista_usuarios)
    except Exception as exc:
        return _tratar_excecao_api(exc, "api_usuarios")
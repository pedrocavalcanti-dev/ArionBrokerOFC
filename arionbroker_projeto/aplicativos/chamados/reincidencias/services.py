import logging
import re
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction, DatabaseError
from django.db.models import Q, Count
from django.utils import timezone
from aplicativos.chamados.models import (
    Chamado,
    Reincidencia,
    HistoricoReincidencia,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class RegraReincidenciaError(Exception):
    """Exceção customizada para violações de regra de negócio do módulo de Reincidências."""
    pass


# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

def normalizar_texto(valor):
    """Remove espaços laterais de um texto e trata valores nulos."""
    if not valor:
        return ""
    return str(valor).strip()


def normalizar_designacao(valor):
    """Normaliza a designação compatível com o model Reincidencia."""
    valor_limpo = normalizar_texto(valor)
    if not valor_limpo:
        return ""
    return re.sub(r"[^a-zA-Z0-9]", "", valor_limpo).upper()


def usuario_eh_admin(usuario):
    """Verifica se o usuário é staff ou superuser."""
    if not usuario:
        return False
    return usuario.is_staff or usuario.is_superuser


def usuario_pode_editar(reincidencia, usuario):
    """Verifica se o usuário pode editar a reincidência (responsável atual ou admin)."""
    if not usuario:
        return False
    return usuario == reincidencia.responsavel or usuario_eh_admin(usuario)


def registrar_historico(
    reincidencia,
    tipo_evento,
    descricao="",
    usuario=None,
    ticket_relacionado="",
    dados_anteriores=None,
    dados_novos=None,
):
    """Função auxiliar para registrar histórico de forma padronizada."""
    try:
        HistoricoReincidencia.objects.create(
            reincidencia=reincidencia,
            tipo_evento=tipo_evento,
            descricao=descricao,
            usuario=usuario,
            ticket_relacionado=ticket_relacionado,
            dados_anteriores=dados_anteriores or {},
            dados_novos=dados_novos or {}
        )
    except Exception as e:
        logger.error(f"Erro ao registrar histórico para reincidência {reincidencia.id}: {str(e)}")


# ==============================================================================
# SERVIÇOS PRINCIPAIS DE REGRA DE NEGÓCIO
# ==============================================================================

def criar_reincidencia(dados, usuario=None):
    ticket_atual = normalizar_texto(dados.get("ticket_atual"))
    ticket_origem = normalizar_texto(dados.get("ticket_origem", ticket_atual))
    designacao = normalizar_texto(dados.get("designacao"))
    chamado_id = dados.get("chamado_id")

    if not ticket_atual:
        raise RegraReincidenciaError("O ticket atual é obrigatório.")
    if not designacao:
        raise RegraReincidenciaError("A designação é obrigatória.")

    if Reincidencia.objects.filter(ticket_atual=ticket_atual).exists():
        raise RegraReincidenciaError(f"O ticket {ticket_atual} já está cadastrado no sistema.")

    chamado_obj = None
    if chamado_id:
        chamado_obj = Chamado.objects.filter(id=chamado_id).first()

    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.create(
                ticket_atual=ticket_atual,
                ticket_origem=ticket_origem,
                url_ticket=normalizar_texto(dados.get("url_ticket")),
                url_ticket_origem=normalizar_texto(dados.get("url_ticket_origem", dados.get("url_ticket"))),
                data_ticket=dados.get("data_ticket"),
                data_ticket_origem=dados.get("data_ticket_origem", dados.get("data_ticket")),
                data_encerramento_origem=dados.get("data_encerramento_origem"),
                designacao=designacao,
                cliente=normalizar_texto(dados.get("cliente")),
                projeto=normalizar_texto(dados.get("projeto")),
                identificador_projeto=normalizar_texto(dados.get("identificador_projeto")),
                operadora=normalizar_texto(dados.get("operadora")),
                isp=normalizar_texto(dados.get("isp")),
                chamado=chamado_obj,
                fila="TRATAMENTO",
                status="NOVO",
                classificacao="PENDENTE",
                quantidade_reincidencias=1
            )
        except IntegrityError:
            logger.error(f"IntegrityError ao criar reincidencia com ticket {ticket_atual}")
            raise RegraReincidenciaError("Conflito ao criar reincidência. Verifique se o ticket já existe.")
        except DatabaseError as e:
            logger.error(f"DatabaseError ao criar reincidencia: {e}")
            raise RegraReincidenciaError("Erro de banco de dados ao criar a reincidência.")

        dados_novos = {
            "ticket_atual": reincidencia.ticket_atual,
            "ticket_origem": reincidencia.ticket_origem,
            "designacao": reincidencia.designacao,
            "fila": reincidencia.fila,
            "status": reincidencia.status
        }

        registrar_historico(
            reincidencia=reincidencia,
            tipo_evento="CRIADO",
            descricao="Registro de reincidência criado manualmente.",
            usuario=usuario,
            dados_novos=dados_novos,
            ticket_relacionado=ticket_atual
        )

        return reincidencia


def apropriar_reincidencia(reincidencia_id, usuario):
    if not usuario or not usuario.is_authenticated:
        raise RegraReincidenciaError("Usuário precisa estar autenticado.")

    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if reincidencia.responsavel == usuario:
            return reincidencia

        if reincidencia.responsavel is not None:
            raise RegraReincidenciaError("Esta reincidência já está apropriada por outro usuário.")

        dados_anteriores = {"responsavel_id": None, "status": reincidencia.status}
        
        reincidencia.responsavel = usuario
        
        if reincidencia.status in ["NOVO", "REINCIDIU"]:
            reincidencia.status = "EM_ANALISE"

        reincidencia.save()

        dados_novos = {"responsavel_id": usuario.id, "status": reincidencia.status}

        registrar_historico(
            reincidencia=reincidencia,
            tipo_evento="APROPRIADO",
            descricao=f"Reincidência apropriada por {usuario.get_full_name() or usuario.username}.",
            usuario=usuario,
            dados_anteriores=dados_anteriores,
            dados_novos=dados_novos
        )

        return reincidencia


def liberar_reincidencia(reincidencia_id, usuario):
    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para liberar esta reincidência.")

        if not reincidencia.responsavel:
            return reincidencia

        dados_anteriores = {"responsavel_id": reincidencia.responsavel.id, "status": reincidencia.status}

        reincidencia.responsavel = None

        teve_analise = reincidencia.analise_completa() or any([
            reincidencia.motivo_identificado.strip(),
            reincidencia.causa_raiz.strip(),
            reincidencia.acao_realizada.strip(),
            reincidencia.acao_preventiva.strip(),
            reincidencia.conclusao.strip()
        ])

        if reincidencia.status == "EM_ANALISE" and not teve_analise:
            reincidencia.status = "NOVO"

        reincidencia.save()

        dados_novos = {"responsavel_id": None, "status": reincidencia.status}

        registrar_historico(
            reincidencia=reincidencia,
            tipo_evento="LIBERADO",
            descricao="Reincidência liberada.",
            usuario=usuario,
            dados_anteriores=dados_anteriores,
            dados_novos=dados_novos
        )

        return reincidencia


def transferir_reincidencia(reincidencia_id, novo_responsavel_id, usuario):
    if not usuario_eh_admin(usuario):
        raise RegraReincidenciaError("Somente administradores podem transferir reincidências.")

    try:
        novo_responsavel = User.objects.get(id=novo_responsavel_id)
    except User.DoesNotExist:
        raise RegraReincidenciaError("Novo responsável não encontrado.")

    if not novo_responsavel.is_active:
        raise RegraReincidenciaError("O novo responsável precisa ser um usuário ativo.")

    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if reincidencia.responsavel == novo_responsavel:
            raise RegraReincidenciaError("A reincidência já pertence a este responsável.")

        resp_antigo_id = reincidencia.responsavel.id if reincidencia.responsavel else None
        dados_anteriores = {"responsavel_id": resp_antigo_id, "status": reincidencia.status}

        reincidencia.responsavel = novo_responsavel

        if reincidencia.status in ["NOVO", "REINCIDIU"]:
            reincidencia.status = "EM_ANALISE"

        reincidencia.save()

        dados_novos = {"responsavel_id": novo_responsavel.id, "status": reincidencia.status}

        registrar_historico(
            reincidencia=reincidencia,
            tipo_evento="TRANSFERIDO",
            descricao=f"Transferido para {novo_responsavel.get_full_name() or novo_responsavel.username}.",
            usuario=usuario,
            dados_anteriores=dados_anteriores,
            dados_novos=dados_novos
        )

        return reincidencia


def editar_reincidencia(reincidencia_id, dados, usuario):
    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para editar esta reincidência.")

        novo_ticket = normalizar_texto(dados.get("ticket_atual", reincidencia.ticket_atual))
        if novo_ticket != reincidencia.ticket_atual:
            if Reincidencia.objects.filter(ticket_atual=novo_ticket).exclude(id=reincidencia.id).exists():
                raise RegraReincidenciaError(f"O ticket {novo_ticket} já está em uso em outro registro.")

        campos_editaveis = [
            "ticket_atual", "url_ticket", "data_ticket",
            "ticket_origem", "url_ticket_origem", "data_ticket_origem",
            "ticket_monitoramento", "url_ticket_monitoramento", "data_ticket_monitoramento",
            "designacao", "cliente", "projeto", "identificador_projeto",
            "operadora", "isp", "data_encerramento_origem"
        ]

        dados_anteriores = {}
        dados_novos = {}
        alterou = False

        for campo in campos_editaveis:
            if campo in dados:
                valor_novo = dados[campo]
                if campo not in ["data_ticket", "data_ticket_origem", "data_ticket_monitoramento", "data_encerramento_origem"]:
                    valor_novo = normalizar_texto(valor_novo)
                
                valor_antigo = getattr(reincidencia, campo)
                if valor_novo != valor_antigo:
                    dados_anteriores[campo] = str(valor_antigo)
                    dados_novos[campo] = str(valor_novo)
                    setattr(reincidencia, campo, valor_novo)
                    alterou = True

        if alterou:
            reincidencia.save()
            registrar_historico(
                reincidencia=reincidencia,
                tipo_evento="DADOS_EDITADOS",
                descricao="Dados cadastrais alterados.",
                usuario=usuario,
                dados_anteriores=dados_anteriores,
                dados_novos=dados_novos
            )

        return reincidencia


def atualizar_analise_reincidencia(reincidencia_id, dados, usuario):
    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para editar a análise.")

        campos_analise = ["motivo_identificado", "causa_raiz", "acao_realizada", "acao_preventiva", "conclusao"]
        dados_anteriores = {}
        dados_novos = {}
        alterou = False

        for campo in campos_analise:
            if campo in dados:
                valor_novo = normalizar_texto(dados[campo])
                valor_antigo = normalizar_texto(getattr(reincidencia, campo))
                if valor_novo != valor_antigo:
                    dados_anteriores[campo] = valor_antigo
                    dados_novos[campo] = valor_novo
                    setattr(reincidencia, campo, valor_novo)
                    alterou = True

        if alterou:
            if reincidencia.status not in ["MONITORANDO", "CONCLUIDO", "DESCARTADO"]:
                if reincidencia.status != "EM_ANALISE" and reincidencia.status != "AGUARDANDO_TICKET_MONITORAMENTO":
                    dados_anteriores["status"] = reincidencia.status
                    reincidencia.status = "EM_ANALISE"
                    dados_novos["status"] = "EM_ANALISE"
            
            reincidencia.save()
            registrar_historico(
                reincidencia=reincidencia,
                tipo_evento="ANALISE_ATUALIZADA",
                descricao="Campos da análise foram atualizados.",
                usuario=usuario,
                dados_anteriores=dados_anteriores,
                dados_novos=dados_novos
            )

        return reincidencia


def atualizar_status_reincidencia(reincidencia_id, novo_status, usuario):
    valid_choices = [c[0] for c in Reincidencia.STATUS_CHOICES]
    if novo_status not in valid_choices:
        raise RegraReincidenciaError("Status inválido.")

    status_protegidos = ["MONITORANDO", "CONCLUIDO", "DESCARTADO", "AGUARDANDO_TICKET_MONITORAMENTO"]
    if novo_status in status_protegidos:
        raise RegraReincidenciaError(f"O status '{novo_status}' faz parte do fluxo automatizado e não pode ser definido manualmente.")

    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para alterar o status.")

        if reincidencia.status == novo_status:
            return reincidencia

        dados_anteriores = {"status": reincidencia.status}
        reincidencia.status = novo_status
        reincidencia.save()
        dados_novos = {"status": reincidencia.status}

        registrar_historico(
            reincidencia=reincidencia,
            tipo_evento="STATUS_ALTERADO",
            descricao=f"Status alterado para {reincidencia.get_status_display()}.",
            usuario=usuario,
            dados_anteriores=dados_anteriores,
            dados_novos=dados_novos
        )

        return reincidencia


def classificar_reincidencia(reincidencia_id, classificacao, motivo_classificacao, usuario):
    valid_classificacoes = [c[0] for c in Reincidencia.CLASSIFICACAO_CHOICES]
    if classificacao not in valid_classificacoes:
        raise RegraReincidenciaError("Classificação inválida.")

    descartes = ["MASSIVA", "FALSO_POSITIVO", "FALHA_ISOLADA", "DUPLICADO", "NAO_SE_APLICA"]

    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para classificar a reincidência.")

        if reincidencia.fila not in ["TRATAMENTO", "NOVO"]:
            raise RegraReincidenciaError("Só é possível classificar chamados que ainda estão em tratamento.")

        dados_anteriores = {
            "classificacao": reincidencia.classificacao, 
            "motivo_classificacao": reincidencia.motivo_classificacao,
            "fila": reincidencia.fila,
            "status": reincidencia.status
        }

        # Se for um dos tipos que não geram monitoramento, usamos a model para descartar
        if classificacao in descartes:
            reincidencia.finalizar_triagem(classificacao, motivo_classificacao, usuario)
        else:
            reincidencia.classificacao = classificacao
            reincidencia.motivo_classificacao = motivo_classificacao
            if reincidencia.status == "NOVO":
                reincidencia.status = "EM_ANALISE"
            reincidencia.save()

            registrar_historico(
                reincidencia=reincidencia,
                tipo_evento="CLASSIFICADO",
                descricao=f"Classificado como {reincidencia.get_classificacao_display()}.",
                usuario=usuario,
                dados_anteriores=dados_anteriores,
                dados_novos={"classificacao": classificacao, "status": reincidencia.status}
            )

        return reincidencia


def preparar_monitoramento(reincidencia_id, usuario):
    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para executar esta ação.")

        try:
            reincidencia.preparar_solicitacao_monitoramento(usuario)
        except ValueError as e:
            raise RegraReincidenciaError(str(e))

        return reincidencia


def registrar_ticket_monitoramento(reincidencia_id, ticket, url, data, usuario):
    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para registrar o ticket de monitoramento.")

        try:
            reincidencia.registrar_ticket_monitoramento(ticket, url, data, usuario)
        except ValueError as e:
            raise RegraReincidenciaError(str(e))

        return reincidencia


def mover_para_monitoramento(reincidencia_id, usuario):
    """
    Inicia os 30 dias de monitoramento propriamente dito.
    Requer: Classificação OK, Análise completa, Ticket de monitoramento registrado.
    """
    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para iniciar o monitoramento.")

        try:
            reincidencia.iniciar_monitoramento(usuario)
        except ValueError as e:
            raise RegraReincidenciaError(str(e))

        return reincidencia


def reabrir_para_tratamento(reincidencia_id, usuario, novo_ticket=""):
    novo_ticket = normalizar_texto(novo_ticket)

    if not novo_ticket:
        raise RegraReincidenciaError("O novo ticket é obrigatório para registrar a reincidência.")

    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_pode_editar(reincidencia, usuario):
            raise RegraReincidenciaError("Você não tem permissão para reabrir esta reincidência.")

        # Valida se novo ticket não existe na base, exceto no registro atual
        if Reincidencia.objects.filter(ticket_atual=novo_ticket).exclude(id=reincidencia.id).exists() or \
           Reincidencia.objects.filter(ticket_origem=novo_ticket).exclude(id=reincidencia.id).exists():
            raise RegraReincidenciaError(f"O ticket {novo_ticket} já está registrado em outro chamado.")

        # Delega à model a atualização segura (não sobrescreve ticket_atual/origem/monitoramento)
        reincidencia.registrar_nova_reincidencia(novo_ticket, usuario)
        
        return reincidencia


def reabrir_registro_finalizado(reincidencia_id, usuario):
    """Permite trazer de volta para tratamento um registro que havia sido finalizado incorretamente."""
    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if not usuario_eh_admin(usuario) and reincidencia.responsavel != usuario:
            raise RegraReincidenciaError("Sem permissão para reabrir este registro.")

        if reincidencia.fila != "FINALIZADO":
            raise RegraReincidenciaError("O registro não está na fila finalizado.")

        dados_anteriores = {
            "fila": reincidencia.fila,
            "status": reincidencia.status,
            "classificacao": reincidencia.classificacao
        }

        reincidencia.fila = "TRATAMENTO"
        reincidencia.status = "EM_ANALISE"
        reincidencia.classificacao = "PENDENTE"
        reincidencia.data_finalizacao = None
        reincidencia.save()

        registrar_historico(
            reincidencia=reincidencia,
            tipo_evento="STATUS_ALTERADO",
            descricao="Registro reaberto para tratamento manualmente.",
            usuario=usuario,
            dados_anteriores=dados_anteriores,
            dados_novos={"fila": "TRATAMENTO", "status": "EM_ANALISE", "classificacao": "PENDENTE"}
        )

        return reincidencia


def concluir_monitoramento(reincidencia_id, usuario=None, forcar=False):
    with transaction.atomic():
        try:
            reincidencia = Reincidencia.objects.select_for_update().get(id=reincidencia_id)
        except Reincidencia.DoesNotExist:
            raise RegraReincidenciaError("Reincidência não encontrada.")

        if reincidencia.fila != "MONITORAMENTO":
            raise RegraReincidenciaError("Apenas registros em monitoramento podem ser concluídos.")

        if not forcar and reincidencia.data_fim_monitoramento and timezone.now() < reincidencia.data_fim_monitoramento:
            raise RegraReincidenciaError("O prazo de 30 dias ainda não expirou.")

        if forcar and not usuario_eh_admin(usuario):
            raise RegraReincidenciaError("Somente administradores podem forçar a conclusão antecipada.")

        reincidencia.concluir_monitoramento(usuario)

        return reincidencia


def processar_monitoramentos_expirados():
    agora = timezone.now()
    expirados = Reincidencia.objects.filter(
        fila="MONITORAMENTO",
        status="MONITORANDO",
        data_fim_monitoramento__lte=agora
    ).values_list('id', flat=True)

    resultado = {
        "processados": 0,
        "ids": [],
        "erros": []
    }

    for rid in expirados:
        try:
            with transaction.atomic():
                obj = Reincidencia.objects.select_for_update().get(id=rid)
                if obj.fila == "MONITORAMENTO" and obj.data_fim_monitoramento <= agora:
                    obj.concluir_monitoramento(usuario=None)
                    resultado["processados"] += 1
                    resultado["ids"].append(obj.id)
        except Exception as e:
            logger.error(f"Erro ao processar monitoramento expirado {rid}: {e}")
            resultado["erros"].append(f"ID {rid}: {str(e)}")

    return resultado


def buscar_historico_designacao(designacao, excluir_id=None):
    designacao_norm = normalizar_designacao(designacao)
    if not designacao_norm:
        return Reincidencia.objects.none()

    qs = Reincidencia.objects.filter(designacao_normalizada=designacao_norm)
    if excluir_id:
        qs = qs.exclude(id=excluir_id)
        
    return qs.order_by("-data_ticket_origem", "-criado_em")


def obter_resumo_reincidencias():
    agregado = Reincidencia.objects.aggregate(
        total=Count("id"),
        tratamento=Count("id", filter=Q(fila="TRATAMENTO")),
        novas=Count("id", filter=Q(status="NOVO")),
        em_analise=Count("id", filter=Q(status="EM_ANALISE")),
        aguardando=Count("id", filter=Q(status="AGUARDANDO_TICKET_MONITORAMENTO")),
        monitoramento=Count("id", filter=Q(fila="MONITORAMENTO")),
        reincidiram=Count("id", filter=Q(status="REINCIDIU")),
        concluidas=Count("id", filter=Q(fila="FINALIZADO")),
        massiva=Count("id", filter=Q(classificacao="MASSIVA")),
        falso_positivo=Count("id", filter=Q(classificacao="FALSO_POSITIVO")),
        falha_isolada=Count("id", filter=Q(classificacao="FALHA_ISOLADA")),
    )
    return agregado


def filtrar_reincidencias(
    fila=None,
    busca="",
    status="",
    classificacao="",
    responsavel="",
    usuario=None,
    data_inicio=None,
    data_fim=None,
    ordenacao="",
    operadora="",
    projeto=""
):
    qs = Reincidencia.objects.select_related("responsavel", "chamado").all()

    if fila:
        qs = qs.filter(fila=fila)

    if status:
        qs = qs.filter(status=status)

    if classificacao:
        qs = qs.filter(classificacao=classificacao)

    if busca:
        busca = normalizar_texto(busca)
        qs = qs.filter(
            Q(ticket_atual__icontains=busca) |
            Q(ticket_origem__icontains=busca) |
            Q(ticket_monitoramento__icontains=busca) |
            Q(designacao__icontains=busca) |
            Q(identificador_projeto__icontains=busca) |
            Q(cliente__icontains=busca) |
            Q(projeto__icontains=busca) |
            Q(operadora__icontains=busca) |
            Q(isp__icontains=busca)
        )

    if operadora:
        qs = qs.filter(operadora__iexact=operadora.strip())

    if projeto:
        qs = qs.filter(projeto__iexact=projeto.strip())

    if responsavel:
        if responsavel == "meus" and usuario:
            qs = qs.filter(responsavel=usuario)
        elif responsavel == "sem_responsavel":
            qs = qs.filter(responsavel__isnull=True)

    if data_inicio:
        qs = qs.filter(Q(data_ticket_origem__gte=data_inicio) | Q(data_ticket__gte=data_inicio))

    if data_fim:
        qs = qs.filter(Q(data_ticket_origem__lte=data_fim) | Q(data_ticket__lte=data_fim))

    if ordenacao == "antigos":
        qs = qs.order_by("criado_em")
    elif ordenacao == "recentes":
        qs = qs.order_by("-criado_em")
    elif ordenacao == "mais_reincidentes":
        qs = qs.order_by("-quantidade_reincidencias", "-criado_em")
    elif ordenacao == "fim_monitoramento":
        qs = qs.order_by("data_fim_monitoramento")
    else:
        qs = qs.order_by("-criado_em")

    return qs


def gerar_texto_otrs(reincidencia):
    """Gera o texto padronizado com os dados da análise para ser enviado ao OTRS."""
    return (
        f"Motivo Identificado:\n{reincidencia.motivo_identificado}\n\n"
        f"Causa Raiz:\n{reincidencia.causa_raiz}\n\n"
        f"Ação Realizada:\n{reincidencia.acao_realizada}\n\n"
        f"Ação Preventiva:\n{reincidencia.acao_preventiva}\n\n"
        f"Conclusão:\n{reincidencia.conclusao}"
    )


def gerar_contexto_email_monitoramento(reincidencia):
    """
    Monta a estrutura de assunto e corpo cru.
    Essa função é chamada tanto pela View do RREIP para a prévia em tela,
    quanto pelo serviço de comunicação para uso em render_to_string.
    O disparo em si é responsabilidade de aplicativos/comunicacao/services.py.
    """
    try:
        # Assunto seguindo o padrão de formalidade
        projeto = reincidencia.projeto or "PROJETO NÃO IDENTIFICADO"
        designacao = reincidencia.designacao or "SEM DESIGNAÇÃO"
        identificador = reincidencia.get_identificador_formatado()

        partes_assunto = [
            f"[{projeto.upper()}]",
            "SOLICITAÇÃO DE MONITORAMENTO RREIP",
            f"BL: {designacao}",
        ]
        if identificador:
            partes_assunto.append(identificador)

        assunto = " - ".join(partes_assunto)
        
        # Corpo de e-mail (usado apenas como fallback texto plano ou visualização simples, 
        # a comunicação enviará o HTML renderizado)
        corpo = "Prezados,\n\n"
        corpo += "A ocorrência encontra-se normalizada.\n"
        corpo += "Solicitamos a abertura de um novo ticket na fila de REINCIDÊNCIAS para monitoramento sistêmico por 30 dias.\n\n"
        
        corpo += "=== DADOS DA OCORRÊNCIA ORIGINAL ===\n"
        ticket_exibicao = reincidencia.ticket_origem or reincidencia.ticket_atual
        corpo += f"Ticket Original: {ticket_exibicao}\n"
        corpo += f"Designação: {reincidencia.designacao}\n"
        if reincidencia.data_ticket_origem:
            corpo += f"Data de abertura: {reincidencia.data_ticket_origem.strftime('%d/%m/%Y %H:%M')}\n"
        if reincidencia.data_encerramento_origem:
            corpo += f"Data de encerramento: {reincidencia.data_encerramento_origem.strftime('%d/%m/%Y %H:%M')}\n"
        corpo += "\n"
        
        corpo += "=== ANÁLISE REALIZADA ===\n"
        corpo += gerar_texto_otrs(reincidencia)
        
        return {
            "assunto": assunto,
            "corpo": corpo
        }
    except Exception as e:
        logger.error(f"Erro ao gerar dados prévios do e-mail de monitoramento: {e}")
        return {"assunto": "", "corpo": ""}


def serializar_reincidencia(reincidencia, usuario=None):
    nome_responsavel = None
    if reincidencia.responsavel:
        nome_responsavel = reincidencia.responsavel.get_full_name() or reincidencia.responsavel.username

    # Lógica de fallback para dados antigos que usavam os campos "ticket_atual", etc.
    ticket_origem_exibicao = reincidencia.ticket_origem or reincidencia.ticket_atual
    url_ticket_origem_exibicao = reincidencia.url_ticket_origem or reincidencia.url_ticket
    data_ticket_origem_exibicao = reincidencia.data_ticket_origem or reincidencia.data_ticket

    return {
        "id": reincidencia.id,
        "pode_editar": usuario_pode_editar(reincidencia, usuario),
        
        # Campos Legados (preservados por segurança)
        "ticket_atual": reincidencia.ticket_atual,
        "url_ticket": reincidencia.url_ticket,
        "data_ticket": reincidencia.data_ticket.isoformat() if reincidencia.data_ticket else None,
        
        # Classificação
        "classificacao": reincidencia.classificacao,
        "classificacao_display": reincidencia.get_classificacao_display(),
        "motivo_classificacao": reincidencia.motivo_classificacao,
        
        # Origem
        "ticket_origem": reincidencia.ticket_origem,
        "url_ticket_origem": reincidencia.url_ticket_origem,
        "data_ticket_origem": reincidencia.data_ticket_origem.isoformat() if reincidencia.data_ticket_origem else None,
        "ticket_origem_exibicao": ticket_origem_exibicao,
        "url_ticket_origem_exibicao": url_ticket_origem_exibicao,
        "data_ticket_origem_exibicao": data_ticket_origem_exibicao.isoformat() if data_ticket_origem_exibicao else None,
        "data_encerramento_origem": reincidencia.data_encerramento_origem.isoformat() if reincidencia.data_encerramento_origem else None,
        
        # Monitoramento
        "ticket_monitoramento": reincidencia.ticket_monitoramento,
        "url_ticket_monitoramento": reincidencia.url_ticket_monitoramento,
        "data_ticket_monitoramento": reincidencia.data_ticket_monitoramento.isoformat() if reincidencia.data_ticket_monitoramento else None,
        
        # Metadados 
        "designacao": reincidencia.designacao,
        "designacao_normalizada": reincidencia.designacao_normalizada,
        "cliente": reincidencia.cliente,
        "projeto": reincidencia.projeto,
        "identificador_projeto": reincidencia.identificador_projeto,
        "identificador_label": reincidencia.get_identificador_label(),
        "identificador_formatado": reincidencia.get_identificador_formatado(),
        "operadora": reincidencia.operadora,
        "isp": reincidencia.isp,
        
        # Fila e Status
        "fila": reincidencia.fila,
        "fila_display": reincidencia.get_fila_display(),
        "status": reincidencia.status,
        "status_display": reincidencia.get_status_display(),
        "quantidade_reincidencias": reincidencia.quantidade_reincidencias,
        
        # Envio de Email
        "email_monitoramento_enviado": reincidencia.email_monitoramento_enviado,
        "data_envio_monitoramento": reincidencia.data_envio_monitoramento.isoformat() if reincidencia.data_envio_monitoramento else None,
        
        # Análise
        "motivo_identificado": reincidencia.motivo_identificado,
        "causa_raiz": reincidencia.causa_raiz,
        "acao_realizada": reincidencia.acao_realizada,
        "acao_preventiva": reincidencia.acao_preventiva,
        "conclusao": reincidencia.conclusao,
        
        # Validações Processuais
        "analise_completa": reincidencia.analise_completa(),
        "pode_solicitar_monitoramento": reincidencia.pode_solicitar_monitoramento(),
        "pode_iniciar_monitoramento": reincidencia.pode_iniciar_monitoramento(),
        
        # Responsável
        "responsavel_id": reincidencia.responsavel_id,
        "responsavel": nome_responsavel,
        
        # Ciclo de Vida
        "data_inicio_monitoramento": reincidencia.data_inicio_monitoramento.isoformat() if reincidencia.data_inicio_monitoramento else None,
        "data_fim_monitoramento": reincidencia.data_fim_monitoramento.isoformat() if reincidencia.data_fim_monitoramento else None,
        "data_finalizacao": reincidencia.data_finalizacao.isoformat() if reincidencia.data_finalizacao else None,
        "dias_restantes": reincidencia.dias_restantes_monitoramento(),
        
        "criado_em": reincidencia.criado_em.isoformat() if reincidencia.criado_em else None,
        "atualizado_em": reincidencia.atualizado_em.isoformat() if reincidencia.atualizado_em else None,

        # Textos e E-mails Auxiliares
        "texto_otrs": gerar_texto_otrs(reincidencia),
        "email_monitoramento": gerar_contexto_email_monitoramento(reincidencia),
    }


def serializar_historico(item):
    nome_usuario = None
    if item.usuario:
        nome_usuario = item.usuario.get_full_name() or item.usuario.username

    return {
        "id": item.id,
        "tipo_evento": item.tipo_evento,
        "tipo_evento_display": item.get_tipo_evento_display(),
        "descricao": item.descricao,
        "usuario_id": item.usuario_id,
        "usuario": nome_usuario,
        "ticket_relacionado": item.ticket_relacionado,
        "dados_anteriores": item.dados_anteriores,
        "dados_novos": item.dados_novos,
        "criado_em": item.criado_em.isoformat() if item.criado_em else None,
    }
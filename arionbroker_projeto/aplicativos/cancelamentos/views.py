import json
import logging
import unicodedata

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from aplicativos.autenticacao.models import (
    UserPreference,
    VisualizacaoCancelamentos,
)

from .models import (
    Cancelamento,
    HistoricoCancelamento,
    HistoricoFila,
    ObservacaoCancelamento,
    PendenciaCancelamento,
)

from .excel import exportar_relatorio_excel

from .services import (
    OperacaoNaoPermitidaError,
    TransicaoInvalidaError,
    adicionar_observacao,
    alterar_status,
    apropriar_cancelamento,
    atualizar_financeiro,
    concluir_cancelamento,
    criar_pendencia,
    descartar_pendencia,
    editar_cancelamento,
    liberar_cancelamento,
    mover_cancelamento,
    resolver_pendencia,
    transferir_cancelamento,
)

User = get_user_model()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config auxiliar
# ---------------------------------------------------------------------------
# Novo fluxo operacional explícito
PROXIMA_FILA_OPERACIONAL = {
    Cancelamento.Fila.PEDIDO:      Cancelamento.Fila.SOLICITACAO,
    Cancelamento.Fila.SOLICITACAO: Cancelamento.Fila.PENDENCIA,
    Cancelamento.Fila.PENDENCIA:   None, # Conclusão não é automática via movimentação
    Cancelamento.Fila.CONCLUIDO:   None, # Fila terminal
    
    # Legado
    Cancelamento.Fila.FINANCEIRO:  None,
}

TEMPLATE_POR_FILA = {
    Cancelamento.Fila.PEDIDO:
        'cancelamentos/cancelamentos.html',

    Cancelamento.Fila.SOLICITACAO:
        'cancelamentos/filas/fila_solicitacao.html',

    Cancelamento.Fila.PENDENCIA:
        'cancelamentos/filas/fila_pendencia.html',

    # Legado temporário
    Cancelamento.Fila.FINANCEIRO:
        'cancelamentos/filas/fila_financeiro.html',

    Cancelamento.Fila.CONCLUIDO:
        'cancelamentos/filas/fila_concluidos.html',
}

def _proxima_fila(fila_atual):
    """Retorna a próxima fila permitida para movimentação operacional padrão."""
    return PROXIMA_FILA_OPERACIONAL.get(fila_atual)

def _kpis():
    kpis = {}
    for fila_valor, fila_label in Cancelamento.Fila.choices:
        kpis[fila_valor] = {
            'label': fila_label,
            'total': Cancelamento.objects.filter(fila=fila_valor).count(),
        }
    kpis['TOTAL_GERAL'] = Cancelamento.objects.count()
    return kpis
def _nome_usuario(usuario, vazio=None):
    """
    Retorna um nome seguro para qualquer relação de usuário opcional.

    Não cria usuário fake e não altera a FK do model.
    """
    if not usuario:
        return vazio

    nome = usuario.get_full_name()

    if nome:
        return nome

    return usuario.username or vazio


def _usuario_eh_admin(usuario) -> bool:
    """
    Verificação administrativa usada pelas APIs de correção de concluídos.
    """
    preferencias = getattr(
        usuario,
        'preferencias',
        None,
    )

    return bool(
        getattr(usuario, 'is_superuser', False)
        or getattr(usuario, 'is_staff', False)
        or getattr(preferencias, 'is_admin', False)
    )


def _bloqueio_concluido_para_nao_admin(
    cancelamento: Cancelamento,
    usuario,
):
    """
    Retorna JsonResponse 403 quando um usuário comum tenta editar concluído.
    """
    if (
        cancelamento.fila
        == Cancelamento.Fila.CONCLUIDO
        and not _usuario_eh_admin(usuario)
    ):
        return JsonResponse(
            {
                'ok': False,
                'erro': (
                    'Este cancelamento está concluído. '
                    'Somente administradores podem realizar correções.'
                ),
            },
            status=403,
        )

    return None


# ---------------------------------------------------------------------------
# Serialização
# ---------------------------------------------------------------------------
def _serializa(c: Cancelamento) -> dict:
    total_obs = c.observacoes.count() if hasattr(c, '_prefetched_objects_cache') or True else 0

    return {
        'id':                            c.id,
        'ticket_arion':                  c.ticket_arion,
        'ticket_url':                    c.ticket_url,
        'designacao_circuito':           c.designacao_circuito,
        'cod_cliente':                   c.cod_cliente,
        'protocolo':                     c.protocolo,
        'isp':                           c.isp,
        'contato_isp':                   c.contato_isp,
        'canal_contato':                 c.canal_contato,
        'cliente':                       c.cliente,
        'cliente_final':                 c.cliente_final,
        'endereco':                      c.endereco,
        'numero':                        c.numero,
        'complemento':                   c.complemento,
        'bairro':                        c.bairro,
        'cidade':                        c.cidade,
        'uf':                            c.uf,
        'cep':                           c.cep,
        'fila':                          c.fila,
        'fila_label':                    c.get_fila_display(),
        'status':                        c.status,
        'status_label':                  c.get_status_display(),
        'responsavel_id':                c.responsavel_id,
        'responsavel':                   _nome_usuario(c.responsavel, 'Sem responsável'),
        'apropriado_em':                 c.apropriado_em.isoformat() if c.apropriado_em else None,
        'data_criacao_chamado':          c.data_criacao_chamado.isoformat() if c.data_criacao_chamado else None,
        'data_primeiro_contato':         c.data_primeiro_contato.isoformat() if c.data_primeiro_contato else None,
        'data_ultima_interacao':         c.data_ultima_interacao.isoformat() if c.data_ultima_interacao else None,
        'data_cancelamento_confirmado':  c.data_cancelamento_confirmado.isoformat() if c.data_cancelamento_confirmado else None,
        'concluido_em':                  c.concluido_em.isoformat() if c.concluido_em else None,
        'proxima_acao':                  c.proxima_acao,
        'data_proxima_acao':             c.data_proxima_acao.isoformat() if c.data_proxima_acao else None,

        # -----------------------------------------------------------
        # Valores financeiros gravados no Cancelamento
        # -----------------------------------------------------------
        'valor_multa_rescisao':          str(c.valor_multa_rescisao) if c.valor_multa_rescisao is not None else None,
        'valor_equipamento':             str(c.valor_equipamento) if c.valor_equipamento is not None else None,
        'valor_outros':                  str(c.valor_outros) if c.valor_outros is not None else None,
        'valor_total_financeiro':        str(c.valor_total_financeiro),

        # -----------------------------------------------------------
        # Valores calculados diretamente das pendências
        #
        # São estes valores que o modal de conclusão deve mostrar
        # antes de concluir o cancelamento.
        #
        # Pendências DESCARTADAS não entram nos cálculos.
        # -----------------------------------------------------------
        'valor_pendencias_multa':        str(c.valor_pendencias_multa),
        'valor_pendencias_equipamento':  str(c.valor_pendencias_equipamento),
        'valor_pendencias_outros':       str(c.valor_pendencias_outros),
        'valor_pendencias_total':        str(c.valor_pendencias_total),
        'pendencias_ativas_count':       c.pendencias_ativas_count,

        # -----------------------------------------------------------
        # Financeiro legado / compatibilidade
        # -----------------------------------------------------------
        'ultima_competencia_faturada':   c.ultima_competencia_faturada,
        'data_baixa_financeira':         c.data_baixa_financeira.isoformat() if c.data_baixa_financeira else None,
        'confirmacao_sem_nova_cobranca': c.confirmacao_sem_nova_cobranca,
        'observacao_financeira':         c.observacao_financeira,

        # -----------------------------------------------------------
        # Controle
        # -----------------------------------------------------------
        'aging_dias':                    c.aging_dias,
        'pode_concluir':                 c.pode_concluir,
        'total_observacoes':             total_obs,
        'criado_em':                     c.criado_em.isoformat(),
        'atualizado_em':                 c.atualizado_em.isoformat(),
        'observacao':                    c.observacao,
        'agendamento':                   c.agendamento.isoformat() if c.agendamento else None,
        'atendente':                     c.atendente.username if c.atendente_id else None,
    }

def _serializa_obs(obs: ObservacaoCancelamento) -> dict:
    return {
        'id':         obs.id,
        'texto':      obs.texto,
        'criado_por': _nome_usuario(obs.criado_por, 'Sistema'),
        'criado_em':  obs.criado_em.isoformat(),
    }

def _serializa_pendencia(p) -> dict:
    # Garante que data_prevista é date/datetime, não string
    data_prevista_iso = None
    if p.data_prevista:
        if isinstance(p.data_prevista, str):
            # Se chegou como string, tenta parsear
            try:
                dt = datetime.fromisoformat(p.data_prevista.replace('Z', '+00:00'))
                data_prevista_iso = dt.date().isoformat()
            except (ValueError, AttributeError):
                # Se falhar, tenta como data no formato YYYY-MM-DD
                try:
                    data_prevista_iso = datetime.strptime(p.data_prevista, '%Y-%m-%d').date().isoformat()
                except:
                    data_prevista_iso = p.data_prevista  # mantém a string se não conseguir parsear
        else:
            # É date ou datetime, seguro chamar isoformat()
            data_prevista_iso = p.data_prevista.isoformat()
    
    return {
    'id': p.id,

    'tipo': p.tipo,
    'tipo_label': p.get_tipo_display(),

    'descricao': p.descricao,

    'valor': (
        str(p.valor)
        if p.valor is not None
        else None
    ),

    'status': p.status,
    'status_label': p.get_status_display(),

    # Uma pendência só deixa de participar do fechamento
    # quando for explicitamente descartada.
    'entra_no_calculo': (
        p.status
        != PendenciaCancelamento.StatusPendencia.DESCARTADA
    ),

    'data_prevista': data_prevista_iso,

    'resolvida_em': (
        p.resolvida_em.isoformat()
        if p.resolvida_em
        else None
    ),

    'criado_em': p.criado_em.isoformat(),
}

# ---------------------------------------------------------------------------
# Busca global
# ---------------------------------------------------------------------------
def _normalizar_texto_busca(valor):
    """
    Normaliza textos para comparação de labels.

    Exemplo:
        "Concluídos" -> "concluidos"
        "PENDÊNCIA"  -> "pendencia"
    """
    texto = str(valor or '').casefold()

    return ''.join(
        caractere
        for caractere in unicodedata.normalize('NFKD', texto)
        if not unicodedata.combining(caractere)
    )


def _choices_correspondentes(choices, termo):
    """
    Retorna os códigos internos de choices cujo código ou label
    corresponde ao texto pesquisado.

    Permite, por exemplo:
        "concluidos" -> CONCLUIDO
        "pendencia"  -> PENDENCIA
        "multa contrato" -> multa_contrato
    """
    termo_normalizado = _normalizar_texto_busca(termo)
    encontrados = []

    for valor, label in choices:
        valor_normalizado = _normalizar_texto_busca(valor)
        label_normalizado = _normalizar_texto_busca(label)

        if (
            termo_normalizado in valor_normalizado
            or termo_normalizado in label_normalizado
        ):
            encontrados.append(valor)

    return encontrados


def _montar_q_busca_global(termo):
    """
    Monta a pesquisa geral de Cancelamentos.

    A pesquisa não depende da fila atual.

    Pesquisa em:
    - ticket;
    - URL;
    - designação;
    - código do cliente;
    - cliente;
    - cliente final;
    - ISP;
    - contato ISP;
    - protocolo;
    - canal;
    - endereço;
    - número;
    - complemento;
    - bairro;
    - cidade;
    - UF;
    - CEP;
    - próxima ação;
    - observações;
    - observação financeira;
    - responsável;
    - atendente legado;
    - pendências;
    - histórico de atividades;
    - fila;
    - status;
    - valores;
    - datas.
    """
    termo = str(termo or '').strip()

    if not termo:
        return Q(pk__in=[])

    busca = (
        Q(ticket_arion__icontains=termo)
        | Q(ticket_url__icontains=termo)
        | Q(designacao_circuito__icontains=termo)
        | Q(cod_cliente__icontains=termo)
        | Q(cliente__icontains=termo)
        | Q(cliente_final__icontains=termo)
        | Q(isp__icontains=termo)
        | Q(contato_isp__icontains=termo)
        | Q(protocolo__icontains=termo)
        | Q(canal_contato__icontains=termo)
        | Q(endereco__icontains=termo)
        | Q(numero__icontains=termo)
        | Q(complemento__icontains=termo)
        | Q(bairro__icontains=termo)
        | Q(cidade__icontains=termo)
        | Q(uf__icontains=termo)
        | Q(cep__icontains=termo)
        | Q(proxima_acao__icontains=termo)
        | Q(observacao__icontains=termo)
        | Q(observacao_financeira__icontains=termo)

        # Responsável
        | Q(responsavel__username__icontains=termo)
        | Q(responsavel__first_name__icontains=termo)
        | Q(responsavel__last_name__icontains=termo)

        # Atendente legado
        | Q(atendente__username__icontains=termo)
        | Q(atendente__first_name__icontains=termo)
        | Q(atendente__last_name__icontains=termo)

        # Observações
        | Q(observacoes__texto__icontains=termo)
        | Q(observacoes__criado_por__username__icontains=termo)
        | Q(observacoes__criado_por__first_name__icontains=termo)
        | Q(observacoes__criado_por__last_name__icontains=termo)

        # Pendências
        | Q(pendencias__descricao__icontains=termo)
        | Q(pendencias__tipo__icontains=termo)
        | Q(pendencias__status__icontains=termo)

        # Histórico geral
        | Q(atividades__descricao__icontains=termo)
        | Q(atividades__realizado_por__username__icontains=termo)
        | Q(atividades__realizado_por__first_name__icontains=termo)
        | Q(atividades__realizado_por__last_name__icontains=termo)
    )

    # -----------------------------------------------------------------------
    # Fila por código ou nome exibido
    # -----------------------------------------------------------------------
    filas_encontradas = _choices_correspondentes(
        Cancelamento.Fila.choices,
        termo,
    )

    if filas_encontradas:
        busca |= Q(fila__in=filas_encontradas)

    # -----------------------------------------------------------------------
    # Status por código ou nome exibido
    # -----------------------------------------------------------------------
    status_encontrados = _choices_correspondentes(
        Cancelamento.Status.choices,
        termo,
    )

    if status_encontrados:
        busca |= Q(status__in=status_encontrados)

    # -----------------------------------------------------------------------
    # Tipo da pendência pelo nome exibido
    # -----------------------------------------------------------------------
    tipos_pendencia = _choices_correspondentes(
        PendenciaCancelamento.Tipo.choices,
        termo,
    )

    if tipos_pendencia:
        busca |= Q(
            pendencias__tipo__in=tipos_pendencia
        )

    # -----------------------------------------------------------------------
    # Status da pendência pelo nome exibido
    # -----------------------------------------------------------------------
    status_pendencia = _choices_correspondentes(
        PendenciaCancelamento.StatusPendencia.choices,
        termo,
    )

    if status_pendencia:
        busca |= Q(
            pendencias__status__in=status_pendencia
        )

    # -----------------------------------------------------------------------
    # Pesquisa por ID
    # -----------------------------------------------------------------------
    if termo.isdigit():
        busca |= Q(pk=int(termo))

    # -----------------------------------------------------------------------
    # Pesquisa por valor
    #
    # Aceita:
    # 800
    # 800,00
    # 800.00
    # 1.150,00
    # -----------------------------------------------------------------------
    valor_texto = termo.replace(' ', '')

    if ',' in valor_texto:
        valor_texto = (
            valor_texto
            .replace('.', '')
            .replace(',', '.')
        )

    try:
        valor_decimal = Decimal(valor_texto)

        busca |= (
            Q(valor_multa_rescisao=valor_decimal)
            | Q(valor_equipamento=valor_decimal)
            | Q(valor_outros=valor_decimal)
            | Q(pendencias__valor=valor_decimal)
        )

    except (InvalidOperation, ValueError):
        pass

    # -----------------------------------------------------------------------
    # Pesquisa por data
    #
    # Aceita:
    # 19/08/2026
    # 2026-08-19
    # -----------------------------------------------------------------------
    data_pesquisada = None

    for formato in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            data_pesquisada = datetime.strptime(
                termo,
                formato,
            ).date()

            break

        except ValueError:
            continue

    if data_pesquisada:
        busca |= (
            Q(data_criacao_chamado=data_pesquisada)
            | Q(data_primeiro_contato=data_pesquisada)
            | Q(data_ultima_interacao=data_pesquisada)
            | Q(data_cancelamento_confirmado=data_pesquisada)
            | Q(data_proxima_acao=data_pesquisada)
            | Q(data_baixa_financeira=data_pesquisada)
            | Q(agendamento=data_pesquisada)
            | Q(criado_em__date=data_pesquisada)
            | Q(atualizado_em__date=data_pesquisada)
            | Q(apropriado_em__date=data_pesquisada)
            | Q(concluido_em__date=data_pesquisada)
            | Q(pendencias__data_prevista=data_pesquisada)
            | Q(pendencias__resolvida_em__date=data_pesquisada)
            | Q(pendencias__criado_em__date=data_pesquisada)
            | Q(observacoes__criado_em__date=data_pesquisada)
            | Q(atividades__criado_em__date=data_pesquisada)
        )

    # -----------------------------------------------------------------------
    # Booleano
    # -----------------------------------------------------------------------
    termo_bool = _normalizar_texto_busca(termo)

    if termo_bool in ('sim', 'confirmado', 'confirmada'):
        busca |= Q(
            confirmacao_sem_nova_cobranca=True
        )

    elif termo_bool in ('nao', 'não'):
        busca |= Q(
            confirmacao_sem_nova_cobranca=False
        )

    return busca



def _valor_busca_data(valor):
    if not valor:
        return []
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return [valor.isoformat(), valor.strftime('%d/%m/%Y')]
    return [str(valor)]


def _texto_busca_cancelamento(c: Cancelamento) -> str:
    """Texto consolidado para busca global sem diferença de acento/caixa."""
    valores = [
        c.pk, c.ticket_arion, c.ticket_url, c.designacao_circuito, c.cod_cliente,
        c.protocolo, c.isp, c.contato_isp, c.canal_contato, c.cliente,
        c.cliente_final, c.endereco, c.numero, c.complemento, c.bairro,
        c.cidade, c.uf, c.cep, c.fila, c.get_fila_display(), c.status,
        c.get_status_display(), c.proxima_acao, c.observacao,
        c.observacao_financeira, c.ultima_competencia_faturada,
        c.valor_multa_rescisao, c.valor_equipamento, c.valor_outros,
        c.valor_total_financeiro,
    ]
    for campo in (
        c.data_criacao_chamado, c.data_primeiro_contato, c.data_ultima_interacao,
        c.data_cancelamento_confirmado, c.data_proxima_acao,
        c.data_baixa_financeira, c.agendamento, c.criado_em, c.atualizado_em,
        c.apropriado_em, c.concluido_em,
    ):
        valores.extend(_valor_busca_data(campo))
    if c.responsavel_id:
        valores.extend([c.responsavel.username, c.responsavel.first_name,
                        c.responsavel.last_name, c.responsavel.get_full_name()])
    if c.atendente_id:
        valores.extend([c.atendente.username, c.atendente.first_name,
                        c.atendente.last_name, c.atendente.get_full_name()])
    for o in c.observacoes.all():
        valores.extend([o.texto, *_valor_busca_data(o.criado_em)])
        if o.criado_por_id:
            valores.extend([o.criado_por.username, o.criado_por.first_name,
                            o.criado_por.last_name, o.criado_por.get_full_name()])
    for p in c.pendencias.all():
        valores.extend([p.tipo, p.get_tipo_display(), p.descricao, p.valor,
                        p.status, p.get_status_display(),
                        *_valor_busca_data(p.data_prevista),
                        *_valor_busca_data(p.resolvida_em),
                        *_valor_busca_data(p.criado_em)])
    for a in c.atividades.all():
        valores.extend([a.tipo, a.get_tipo_display(), a.descricao,
                        *_valor_busca_data(a.criado_em)])
        if a.realizado_por_id:
            valores.extend([a.realizado_por.username, a.realizado_por.first_name,
                            a.realizado_por.last_name, a.realizado_por.get_full_name()])
    return _normalizar_texto_busca(' '.join(str(v) for v in valores if v not in (None,'')))


def _corresponde_busca_global(c: Cancelamento, termo: str) -> bool:
    termo = _normalizar_texto_busca(termo).strip()
    return bool(termo and termo in _texto_busca_cancelamento(c))

# ---------------------------------------------------------------------------
# Preferência persistente — Visualizar Cancelamentos
# ---------------------------------------------------------------------------
def _preferencia_visualizacao_cancelamentos(request):
    """
    Retorna a preferência persistente do usuário para o filtro "Visualizar".

    Valores armazenados no backend:
    - todos
    - meus
    - sem_responsavel
    """
    prefs, _ = UserPreference.objects.get_or_create(
        user=request.user
    )

    valor = (
        prefs.cancelamentos_visualizar
        or VisualizacaoCancelamentos.TODOS
    )

    valores_validos = {
        escolha
        for escolha, _label
        in VisualizacaoCancelamentos.choices
    }

    if valor not in valores_validos:
        return VisualizacaoCancelamentos.TODOS

    return valor


def _sincronizar_preferencia_visualizacao_cancelamentos(request):
    """
    Sincroniza a preferência pelo parâmetro GET quando ele vier explicitamente.

    Isso deixa o backend como fonte de verdade e também serve de fallback:
    mesmo que o POST AJAX do frontend seja bloqueado/cacheado, navegar com
    ?responsavel=meus / sem_responsavel / todos atualiza a preferência.

    Retorna a preferência persistida após a sincronização.
    """
    prefs, _ = UserPreference.objects.get_or_create(
        user=request.user
    )

    if 'responsavel' not in request.GET:
        return prefs.cancelamentos_visualizar

    valor_url = request.GET.get(
        'responsavel',
        '',
    ).strip()

    mapa = {
        '': VisualizacaoCancelamentos.TODOS,
        'todos': VisualizacaoCancelamentos.TODOS,
        'meus': VisualizacaoCancelamentos.MEUS,
        'sem_responsavel': VisualizacaoCancelamentos.SEM_RESPONSAVEL,
    }

    if valor_url not in mapa:
        return prefs.cancelamentos_visualizar

    novo_valor = mapa[valor_url]

    if prefs.cancelamentos_visualizar != novo_valor:
        prefs.cancelamentos_visualizar = novo_valor
        prefs.save(
            update_fields=[
                'cancelamentos_visualizar',
            ]
        )

    return prefs.cancelamentos_visualizar


def _visualizacao_cancelamentos_contexto(request):
    """
    Valor usado somente para o estado visual dos botões no template.

    Diferente do filtro efetivo:
    - "todos" fica explicitamente como "todos" no HTML;
    - "meus" fica "meus";
    - "sem_responsavel" fica "sem_responsavel".
    """
    preferencia = _preferencia_visualizacao_cancelamentos(
        request
    )

    if (
        preferencia
        == VisualizacaoCancelamentos.MEUS
    ):
        return 'meus'

    if (
        preferencia
        == VisualizacaoCancelamentos.SEM_RESPONSAVEL
    ):
        return 'sem_responsavel'

    return 'todos'


def _filtro_responsavel_efetivo(request):
    """
    Resolve o filtro de responsável que deve ser aplicado.

    O backend é a fonte de verdade:
    - se vier ?responsavel=... na URL, primeiro sincroniza o UserPreference;
    - depois usa a preferência persistida;
    - IDs numéricos continuam suportados como filtro pontual e não viram preferência.

    Retorno:
    - ''                -> Todos
    - 'meus'            -> Meus Cancelamentos
    - 'sem_responsavel' -> Sem responsável
    - '<id>'            -> responsável específico
    """
    if 'responsavel' in request.GET:
        valor_url = request.GET.get(
            'responsavel',
            '',
        ).strip()

        if valor_url.isdigit():
            return valor_url

        _sincronizar_preferencia_visualizacao_cancelamentos(
            request
        )

    preferencia = _preferencia_visualizacao_cancelamentos(
        request
    )

    if (
        preferencia
        == VisualizacaoCancelamentos.MEUS
    ):
        return 'meus'

    if (
        preferencia
        == VisualizacaoCancelamentos.SEM_RESPONSAVEL
    ):
        return 'sem_responsavel'

    return ''


# ---------------------------------------------------------------------------
# Filtros da query string
# ---------------------------------------------------------------------------
def _aplicar_filtros(qs, request, fila: str):
    filtro_resp = _filtro_responsavel_efetivo(request)

    if filtro_resp == 'meus':
        qs = qs.filter(responsavel=request.user)
    elif filtro_resp == 'sem_responsavel':
        qs = qs.filter(responsavel__isnull=True)
    elif filtro_resp.isdigit():
        qs = qs.filter(responsavel_id=int(filtro_resp))

    filtro_status = request.GET.get('status', '').strip()

    if filtro_status:
        qs = qs.filter(status=filtro_status)

    busca = request.GET.get('busca', '').strip()

    if busca:
        qs = qs.filter(
            _montar_q_busca_global(busca)
        ).distinct()

    data_inicio = request.GET.get('data_inicio', '').strip()

    if data_inicio:
        try:
            data_inicio_obj = datetime.strptime(
                data_inicio,
                '%Y-%m-%d',
            ).date()

            qs = qs.filter(
                data_criacao_chamado__gte=data_inicio_obj
            )

        except ValueError:
            pass

    data_fim = request.GET.get('data_fim', '').strip()

    if data_fim:
        try:
            data_fim_obj = datetime.strptime(
                data_fim,
                '%Y-%m-%d',
            ).date()

            qs = qs.filter(
                data_criacao_chamado__lte=data_fim_obj
            )

        except ValueError:
            pass

    ordenacao = request.GET.get('ordenacao', '').strip()

    if ordenacao == 'antigos':
        qs = qs.order_by(
            'data_criacao_chamado',
            'id',
        )

    elif ordenacao == 'recentes':
        qs = qs.order_by(
            '-data_criacao_chamado',
            '-id',
        )

    elif ordenacao == 'ultima_interacao':
        qs = qs.order_by(
            '-data_ultima_interacao',
            '-atualizado_em',
        )

    elif fila == Cancelamento.Fila.PEDIDO and not ordenacao:
        qs = qs.order_by(
            'data_criacao_chamado',
            'id',
        )

    elif fila == Cancelamento.Fila.CONCLUIDO and not ordenacao:
        qs = qs.order_by(
            '-concluido_em',
            '-atualizado_em',
            '-id',
        )

    else:
        qs = qs.order_by(
            '-atualizado_em',
            '-id',
        )

    return qs

# ---------------------------------------------------------------------------
# Páginas (uma por fila)
# ---------------------------------------------------------------------------

@login_required
def _view_fila(request, fila: str):
    qs = (
        Cancelamento.objects
        .filter(fila=fila)
        .select_related('responsavel', 'atendente')
        .prefetch_related('observacoes', 'pendencias')
    )
    qs = _aplicar_filtros(qs, request, fila)

    filtro_responsavel_efetivo = (
        _filtro_responsavel_efetivo(request)
    )

    visualizacao_cancelamentos = (
        _visualizacao_cancelamentos_contexto(request)
    )

    proxima = _proxima_fila(fila)
    analistas = User.objects.filter(is_active=True).order_by('first_name', 'username')

    contexto = {
        'fila_atual':         fila,
        'fila_atual_label':   dict(Cancelamento.Fila.choices)[fila],
        'proxima_fila':       proxima,
        'proxima_fila_label': dict(Cancelamento.Fila.choices).get(proxima),
        'cancelamentos':      qs,
        'cancelamentos_json': json.dumps([_serializa(c) for c in qs]),
        'kpis':               _kpis(),
        'status_choices':     Cancelamento.Status.choices,
        'fila_choices':       Cancelamento.Fila.choices,
        'tipo_pendencia_choices': PendenciaCancelamento.Tipo.choices,
        'analistas':          analistas,
        'filtros': {
            'responsavel':  visualizacao_cancelamentos,
            'status':       request.GET.get('status', ''),
            'busca':        request.GET.get('busca', ''),
            'data_inicio':  request.GET.get('data_inicio', ''),
            'data_fim':     request.GET.get('data_fim', ''),
            'ordenacao':    request.GET.get('ordenacao', ''),
        },
    }
    return render(request, TEMPLATE_POR_FILA[fila], contexto)

def pedido(request):
    return _view_fila(request, Cancelamento.Fila.PEDIDO)

def solicitacao(request):
    return _view_fila(request, Cancelamento.Fila.SOLICITACAO)

def pendencia(request):
    return _view_fila(request, Cancelamento.Fila.PENDENCIA)

def financeiro(request):
    # Compatibilidade temporária com a rota antiga.
    # Remover após migração de urls.py e dos registros legados.
    return _view_fila(request, Cancelamento.Fila.FINANCEIRO)

def concluido(request):
    return _view_fila(request, Cancelamento.Fila.CONCLUIDO)

# ---------------------------------------------------------------------------
# Página de detalhes do cancelamento
# ---------------------------------------------------------------------------
@login_required
def detalhe(request, pk: int):
    c = get_object_or_404(
        Cancelamento.objects
        .select_related('responsavel', 'atendente')
        .prefetch_related(
            'observacoes__criado_por',
            'pendencias__criada_por',
            'historico__movido_por',
            'atividades__realizado_por',
        ),
        pk=pk,
    )

    # Relações de usuário são opcionais.
    # Nunca substituímos a FK por objetos fake: isso preserva o estado real
    # do model e permite abrir normalmente chamados sem responsável.
    historico_filas = (
        c.historico
        .select_related('movido_por')
        .order_by('movido_em')
    )

    atividades = (
        c.atividades
        .select_related('realizado_por')
        .order_by('criado_em')
    )

    pendencias_ativas = (
        c.pendencias
        .exclude(status='DESCARTADA')
        .order_by('criado_em')
    )

    analistas = (
        User.objects
        .filter(is_active=True)
        .order_by('first_name', 'username')
    )

    contexto = {
        'cancelamento': c,
        'responsavel_nome': _nome_usuario(
            c.responsavel,
            'Sem responsável',
        ),
        'historico_filas': historico_filas,
        'atividades': atividades,
        'pendencias': pendencias_ativas,
        'analistas': analistas,
        'status_choices': Cancelamento.Status.choices,
        'fila_choices': Cancelamento.Fila.choices,
        'tipo_pendencia_choices': PendenciaCancelamento.Tipo.choices,
        'pode_concluir': c.pode_concluir,
    }
    return render(request, 'cancelamentos/detalhe.html', contexto)
# ---------------------------------------------------------------------------
# API — Criação
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_criar(request):
    dados = request.POST

    campos_obrigatorios = ['ticket_arion', 'data_criacao_chamado']
    faltando = [campo for campo in campos_obrigatorios if not dados.get(campo)]
    if faltando:
        return JsonResponse(
            {'ok': False, 'erro': f'Campos obrigatórios faltando: {", ".join(faltando)}'},
            status=400,
        )

    ticket_arion_str = dados.get('ticket_arion', '').strip()
    if Cancelamento.objects.filter(ticket_arion=ticket_arion_str).exists():
        return JsonResponse(
            {'ok': False, 'erro': 'Já existe um chamado com esse Ticket Arion.'},
            status=400,
        )

    observacao_texto = dados.get('observacao', '').strip()

    try:
        with transaction.atomic():
            c = Cancelamento.objects.create(
                ticket_arion        = ticket_arion_str,
                ticket_url          = dados.get('ticket_url', '').strip(),
                designacao_circuito = dados.get('designacao_circuito', '').strip(),
                cod_cliente         = dados.get('cod_cliente', '').strip(),
                protocolo           = dados.get('protocolo', '').strip(),
                isp                 = dados.get('isp', '').strip(),
                contato_isp         = dados.get('contato_isp', '').strip(),
                canal_contato       = dados.get('canal_contato', '').strip(),
                cliente             = dados.get('cliente', '').strip(),
                cliente_final       = dados.get('cliente_final', '').strip(),
                cidade              = dados.get('cidade', '').strip(),
                uf                  = dados.get('uf', '').strip(),
                observacao          = observacao_texto,
                data_criacao_chamado= dados.get('data_criacao_chamado') or None,
                agendamento         = dados.get('agendamento') or None,
                fila                = Cancelamento.Fila.PEDIDO,
                status              = Cancelamento.Status.NOVO,
                
                
                responsavel         = request.user,
                apropriado_em       = timezone.now(),
               
            )

            HistoricoFila.objects.create(
                cancelamento=c,
                fila_origem='',
                fila_destino=Cancelamento.Fila.PEDIDO,
                movido_por=request.user,
            )

            HistoricoCancelamento.objects.create(
                cancelamento=c,
                tipo=HistoricoCancelamento.Tipo.CRIACAO,
                descricao=f'Chamado criado e assumido por {request.user.get_full_name() or request.user.username}.',
                realizado_por=request.user,
            )

            if observacao_texto:
                ObservacaoCancelamento.objects.create(
                    cancelamento=c,
                    texto=observacao_texto,
                    criado_por=request.user
                )

        c.refresh_from_db()

        return JsonResponse({'ok': True, 'cancelamento': _serializa(c)})

    except Exception as e:
        return JsonResponse({'ok': False, 'erro': f'Falha interna no banco: {str(e)}'}, status=500)


# ---------------------------------------------------------------------------
# API — Busca global
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['GET'])
def api_busca_global(request):
    """Busca em todas as filas, sem redirecionar a tela atual."""
    termo = request.GET.get('q', '').strip()
    if len(termo) < 2:
        return JsonResponse({'ok': True, 'termo': termo, 'total': 0, 'resultados': [], 'por_fila': {}})

    qs = (Cancelamento.objects
          .select_related('responsavel', 'atendente')
          .prefetch_related('observacoes__criado_por', 'pendencias', 'atividades__realizado_por'))

    responsavel = _filtro_responsavel_efetivo(request)
    if responsavel == 'meus':
        qs = qs.filter(responsavel=request.user)
    elif responsavel == 'sem_responsavel':
        qs = qs.filter(responsavel__isnull=True)
    elif responsavel.isdigit():
        qs = qs.filter(responsavel_id=int(responsavel))

    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)

    data_inicio = request.GET.get('data_inicio', '').strip()
    if data_inicio:
        try:
            qs = qs.filter(data_criacao_chamado__gte=datetime.strptime(data_inicio, '%Y-%m-%d').date())
        except ValueError:
            pass
    data_fim = request.GET.get('data_fim', '').strip()
    if data_fim:
        try:
            qs = qs.filter(data_criacao_chamado__lte=datetime.strptime(data_fim, '%Y-%m-%d').date())
        except ValueError:
            pass

    ordenacao = request.GET.get('ordenacao', '').strip()
    if ordenacao == 'antigos':
        qs = qs.order_by('data_criacao_chamado', 'id')
    elif ordenacao == 'recentes':
        qs = qs.order_by('-data_criacao_chamado', '-id')
    elif ordenacao == 'ultima_interacao':
        qs = qs.order_by('-data_ultima_interacao', '-atualizado_em')
    else:
        qs = qs.order_by('-atualizado_em', '-id')

    limite = 200
    encontrados = []
    for c in qs:
        if _corresponde_busca_global(c, termo):
            encontrados.append(c)
            if len(encontrados) >= limite:
                break

    resultados = []
    for c in encontrados:
        responsavel_nome = _nome_usuario(
            c.responsavel,
            'Sem responsável',
        )
        resultados.append({
            'id': c.id,
            'detalhe_url': reverse('cancelamentos:detalhe', args=[c.id]),
            'ticket_arion': c.ticket_arion,
            'ticket_url': c.ticket_url,
            'designacao_circuito': c.designacao_circuito,
            'cliente': c.cliente,
            'cliente_final': c.cliente_final,
            'cidade': c.cidade,
            'uf': c.uf,
            'isp': c.isp,
            'protocolo': c.protocolo,
            'fila': c.fila,
            'fila_label': c.get_fila_display(),
            'status': c.status,
            'status_label': c.get_status_display(),
            'responsavel_id': c.responsavel_id,
            'responsavel': responsavel_nome,
            'data_criacao_chamado': c.data_criacao_chamado.isoformat() if c.data_criacao_chamado else None,
            'total_observacoes': len(c.observacoes.all()),
        })

    por_fila = {}
    for item in resultados:
        por_fila[item['fila']] = por_fila.get(item['fila'], 0) + 1

    return JsonResponse({
        'ok': True,
        'termo': termo,
        'total': len(resultados),
        'limite': limite,
        'por_fila': por_fila,
        'resultados': resultados,
    })



# ---------------------------------------------------------------------------
# API — Detalhes (GET)
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['GET'])
def api_detalhe(request, pk: int):
    c = get_object_or_404(
        Cancelamento.objects
        .select_related('responsavel', 'atendente')
        .prefetch_related('observacoes', 'pendencias'),
        pk=pk,
    )
    dados = _serializa(c)
    dados['observacoes'] = [_serializa_obs(o) for o in c.observacoes.order_by('criado_em')]
    dados['pendencias']  = [_serializa_pendencia(p) for p in c.pendencias.order_by('criado_em')]
    return JsonResponse({'ok': True, 'cancelamento': dados})

# ---------------------------------------------------------------------------
# API — Mover fila
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_mover(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)
    fila_destino = request.POST.get('fila_destino', '').strip()
    motivo       = request.POST.get('motivo', '').strip()

    try:
        c = mover_cancelamento(c, fila_destino, request.user, motivo)
    except TransicaoInvalidaError as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=400)

    return JsonResponse({'ok': True, 'cancelamento': _serializa(c)})

# ---------------------------------------------------------------------------
# API — Alterar status
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_status(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)
    novo_status = request.POST.get('status', '').strip()

    try:
        c = alterar_status(c, novo_status, request.user)
    except OperacaoNaoPermitidaError as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=400)

    return JsonResponse({'ok': True, 'cancelamento': _serializa(c)})

# ---------------------------------------------------------------------------
# API — Observações
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_obs(request, pk: int):
    c    = get_object_or_404(Cancelamento, pk=pk)

    bloqueio = _bloqueio_concluido_para_nao_admin(
        c,
        request.user,
    )
    if bloqueio:
        return bloqueio
    texto = request.POST.get('texto', '').strip()

    if not texto:
        return JsonResponse({'ok': False, 'erro': 'O texto da observação não pode ser vazio.'}, status=400)

    try:
        obs = adicionar_observacao(
            c,
            texto,
            request.user,
        )
    except OperacaoNaoPermitidaError as e:
        return JsonResponse(
            {
                'ok': False,
                'erro': str(e),
            },
            status=403,
        )

    return JsonResponse(
        {
            'ok': True,
            'observacao': _serializa_obs(obs),
        }
    )

@login_required
@require_http_methods(['GET'])
def api_obs_listar(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)
    observacoes = c.observacoes.select_related('criado_por').order_by('criado_em')
    return JsonResponse({'ok': True, 'observacoes': [_serializa_obs(o) for o in observacoes]})

# ---------------------------------------------------------------------------
# API — Apropriar / Liberar / Transferir
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_apropriar(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)
    try:
        c = apropriar_cancelamento(c, request.user)
    except OperacaoNaoPermitidaError as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=400)
    return JsonResponse({'ok': True, 'cancelamento': _serializa(c)})

@login_required
@require_http_methods(['POST'])
def api_liberar(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)
    try:
        c = liberar_cancelamento(c, request.user)
    except OperacaoNaoPermitidaError as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=400)
    return JsonResponse({'ok': True, 'cancelamento': _serializa(c)})

@login_required
@require_http_methods(['POST'])
def api_transferir(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)
    novo_resp_id = request.POST.get('responsavel_id')

    if not novo_resp_id or not novo_resp_id.isdigit():
        return JsonResponse({'ok': False, 'erro': 'responsavel_id inválido.'}, status=400)

    novo_responsavel = get_object_or_404(User, pk=int(novo_resp_id))

    try:
        c = transferir_cancelamento(c, novo_responsavel, request.user)
    except OperacaoNaoPermitidaError as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=403)

    return JsonResponse({'ok': True, 'cancelamento': _serializa(c)})

# ---------------------------------------------------------------------------
# API — Pendências
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_pendencia_criar(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)

    bloqueio = _bloqueio_concluido_para_nao_admin(
        c,
        request.user,
    )
    if bloqueio:
        return bloqueio
    tipo = request.POST.get('tipo', '').strip()
 
    if tipo not in dict(PendenciaCancelamento.Tipo.choices):
        return JsonResponse({'ok': False, 'erro': 'Tipo de pendência inválido.'}, status=400)
 
    # Parse da data_prevista (string → datetime.date)
    data_prevista = None
    data_prevista_str = request.POST.get('data_prevista', '').strip()
    if data_prevista_str:
        try:
            data_prevista = datetime.strptime(data_prevista_str, '%Y-%m-%d').date()
        except ValueError:
            try:
                data_prevista = datetime.fromisoformat(data_prevista_str.replace('Z', '+00:00')).date()
            except (ValueError, AttributeError):
                return JsonResponse(
                    {'ok': False, 'erro': f'Data inválida: {data_prevista_str}. Use formato YYYY-MM-DD.'},
                    status=400,
                )
 
    # Parse do valor (string → Decimal)
    valor = None
    valor_str = request.POST.get('valor', '').strip()
    if valor_str:
        try:
            valor = Decimal(valor_str)
        except:
            return JsonResponse(
                {'ok': False, 'erro': f'Valor inválido: {valor_str}'},
                status=400,
            )
 
    # Cria a pendência
    try:
        p = criar_pendencia(
            cancelamento=c,
            tipo=tipo,
            descricao=request.POST.get('descricao', '').strip(),
            valor=valor,
            data_prevista=data_prevista,  
            usuario=request.user,
        )
    except Exception as e:
        return JsonResponse(
            {'ok': False, 'erro': f'Erro ao criar pendência: {str(e)}'},
            status=400,
        )
 
    # NOVO: Opção de mover para fila de pendências automaticamente
    mover_para_pendencia = request.POST.get('mover_para_pendencia', 'false').lower() in ('true', '1', 'on', 'yes')
    if mover_para_pendencia and c.fila != Cancelamento.Fila.PENDENCIA:
        try:
            c = mover_cancelamento(
                c,
                Cancelamento.Fila.PENDENCIA,
                request.user,
                motivo=f'Pendência criada: {tipo}'
            )
        except Exception as e:
            print(f'Aviso: Não foi possível mover para PENDENCIA: {str(e)}')
 
    return JsonResponse({'ok': True, 'pendencia': _serializa_pendencia(p)})

@login_required
@require_http_methods(['POST'])
def api_pendencia_resolver(request, pendencia_pk: int):
    p = get_object_or_404(PendenciaCancelamento, pk=pendencia_pk)

    bloqueio = _bloqueio_concluido_para_nao_admin(
        p.cancelamento,
        request.user,
    )
    if bloqueio:
        return bloqueio
    try:
        p = resolver_pendencia(
            p,
            request.user,
        )
    except OperacaoNaoPermitidaError as e:
        return JsonResponse(
            {
                'ok': False,
                'erro': str(e),
            },
            status=403,
        )

    return JsonResponse(
        {
            'ok': True,
            'pendencia': _serializa_pendencia(p),
        }
    )

@login_required
@require_http_methods(['POST'])
def api_pendencia_descartar(request, pendencia_pk: int):
    p = get_object_or_404(
        PendenciaCancelamento.objects.select_related(
            'cancelamento'
        ),
        pk=pendencia_pk,
    )

    bloqueio = _bloqueio_concluido_para_nao_admin(
        p.cancelamento,
        request.user,
    )
    if bloqueio:
        return bloqueio

    try:
        p = descartar_pendencia(
            p,
            request.user,
        )
    except OperacaoNaoPermitidaError as e:
        return JsonResponse(
            {
                'ok': False,
                'erro': str(e),
            },
            status=403,
        )

    return JsonResponse(
        {
            'ok': True,
            'pendencia': _serializa_pendencia(p),
        }
    )

# ---------------------------------------------------------------------------
# API — Financeiro
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_financeiro(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)

    bloqueio = _bloqueio_concluido_para_nao_admin(
        c,
        request.user,
    )
    if bloqueio:
        return bloqueio

    def _decimal(key):
        val = request.POST.get(key)
        return val if val not in (None, '') else None

    def _date(key):
        val = request.POST.get(key)
        return val if val not in (None, '') else None

    confirmacao = request.POST.get('confirmacao_sem_nova_cobranca')
    confirmacao_bool = None
    if confirmacao is not None:
        confirmacao_bool = confirmacao.lower() in ('true', '1', 'on', 'yes')

    try:
        c = atualizar_financeiro(
            cancelamento=c,
            usuario=request.user,
            valor_multa_rescisao=_decimal('valor_multa_rescisao'),
            valor_equipamento=_decimal('valor_equipamento'),
            valor_outros=_decimal('valor_outros'),
            ultima_competencia_faturada=request.POST.get('ultima_competencia_faturada', ''),
            data_baixa_financeira=_date('data_baixa_financeira'),
            confirmacao_sem_nova_cobranca=confirmacao_bool,
            observacao_financeira=request.POST.get('observacao_financeira', ''),
            data_cancelamento_confirmado=_date('data_cancelamento_confirmado'),
        )
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=400)

    return JsonResponse({'ok': True, 'cancelamento': _serializa(c)})


 # ---------------------------------------------------------------------------
# API — Conclusão
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_concluir(request, pk: int):
    """
    Conclui definitivamente um cancelamento.

    Regras:
    - recebe a data do cancelamento;
    - observação final é opcional;
    - se a data não vier, usa a data local atual;
    - os valores financeiros não vêm do frontend;
    - o service calcula o snapshot financeiro;
    - se já estiver realmente em CONCLUIDO, retorna sucesso sem duplicar histórico.
    """

    # -----------------------------------------------------------------------
    # DATA DO CANCELAMENTO
    # -----------------------------------------------------------------------
    data_str = request.POST.get(
        'data_cancelamento_confirmado',
        '',
    ).strip()

    if data_str:
        try:
            data_cancelamento = datetime.strptime(
                data_str,
                '%Y-%m-%d',
            ).date()

        except ValueError:
            return JsonResponse(
                {
                    'ok': False,
                    'erro': (
                        'Data do cancelamento inválida. '
                        'Utilize o formato AAAA-MM-DD.'
                    ),
                },
                status=400,
            )
    else:
        data_cancelamento = timezone.localdate()

    # -----------------------------------------------------------------------
    # OBSERVAÇÃO FINAL
    # -----------------------------------------------------------------------
    observacao_foi_enviada = (
        'observacao_financeira' in request.POST
    )

    observacao_final = request.POST.get(
        'observacao_financeira',
        '',
    ).strip()

    try:
        with transaction.atomic():

            # ----------------------------------------------------------------
            # BLOQUEIA O REGISTRO DURANTE A CONCLUSÃO
            # ----------------------------------------------------------------
            c = get_object_or_404(
                Cancelamento.objects.select_for_update(),
                pk=pk,
            )

            # ----------------------------------------------------------------
            # IDEMPOTÊNCIA
            #
            # IMPORTANTE:
            # somente a FILA CONCLUIDO define que o fluxo de conclusão
            # realmente terminou.
            #
            # Não usamos apenas o status, pois existem registros antigos
            # que podem possuir CONCLUIDO_CANCELAMENTO ainda em PENDENCIA.
            # ----------------------------------------------------------------
            if c.fila == Cancelamento.Fila.CONCLUIDO:
                c.refresh_from_db()

                return JsonResponse(
                    {
                        'ok': True,
                        'ja_concluido': True,
                        'cancelamento': _serializa(c),
                    }
                )

            # ----------------------------------------------------------------
            # SALVA DATA E OBSERVAÇÃO
            # ----------------------------------------------------------------
            campos_atualizados = [
                'data_cancelamento_confirmado',
                'atualizado_em',
            ]

            c.data_cancelamento_confirmado = data_cancelamento

            if observacao_foi_enviada:
                c.observacao_financeira = observacao_final

                campos_atualizados.append(
                    'observacao_financeira'
                )

            c.save(
                update_fields=campos_atualizados
            )

            # ----------------------------------------------------------------
            # CONCLUSÃO
            #
            # O service é responsável por:
            # - validar fila de origem;
            # - calcular as pendências;
            # - salvar snapshot financeiro;
            # - mover para CONCLUIDO;
            # - alterar status;
            # - preencher concluido_em;
            # - criar os históricos.
            # ----------------------------------------------------------------
            c = concluir_cancelamento(
                c,
                request.user,
            )

    except OperacaoNaoPermitidaError as e:
        return JsonResponse(
            {
                'ok': False,
                'erro': str(e),
            },
            status=400,
        )

    except Exception as e:
        logger.exception(
            '[CANCELAMENTOS] Erro ao concluir cancelamento ID %s',
            pk,
        )

        return JsonResponse(
            {
                'ok': False,
                'erro': (
                    f'Erro ao concluir cancelamento: '
                    f'{type(e).__name__}: {str(e)}'
                ),
            },
            status=500,
        )

    # -----------------------------------------------------------------------
    # ATUALIZA O OBJETO APÓS A TRANSAÇÃO
    # -----------------------------------------------------------------------
    c.refresh_from_db()

    return JsonResponse(
        {
            'ok': True,
            'ja_concluido': False,
            'cancelamento': _serializa(c),
        }
    )


# ---------------------------------------------------------------------------
# API — Excluir
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_excluir(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)
    c.delete()
    return JsonResponse({'ok': True})



# ---------------------------------------------------------------------------
# API — Edição
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_editar(request, pk: int):
    c = get_object_or_404(Cancelamento, pk=pk)
    
    bloqueio = _bloqueio_concluido_para_nao_admin(
        c,
        request.user,
    )
    if bloqueio:
        return bloqueio

    # Verifica se Ticket Arion foi enviado e já existe em OUTRO ID
    ticket_arion = request.POST.get('ticket_arion')
    if ticket_arion and Cancelamento.objects.filter(ticket_arion=ticket_arion).exclude(pk=pk).exists():
        return JsonResponse({'ok': False, 'erro': 'Já existe outro chamado com esse Ticket Arion.'}, status=400)

    # Passamos o dicionário completo do POST para o service validar os campos permitidos
    try:
        c = editar_cancelamento(c, request.POST, request.user)
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': f'Falha ao editar: {str(e)}'}, status=400)

    c.refresh_from_db()
    return JsonResponse({'ok': True, 'cancelamento': _serializa(c)})




# ---------------------------------------------------------------------------
# API — Mover fila em lote
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(['POST'])
def api_mover_lote(request):
    """
    Move vários cancelamentos para a mesma fila de destino.

    Regras:
    - reutiliza mover_cancelamento() para cada registro;
    - mantém as mesmas validações da movimentação individual;
    - mantém histórico individual por cancelamento;
    - mantém a regra especial de status ao entrar em Pendência;
    - uma falha não impede os demais registros de serem processados;
    - Concluídos continua protegido pelas regras do service.
    """
    fila_destino = request.POST.get(
        'fila_destino',
        '',
    ).strip()

    motivo = request.POST.get(
        'motivo',
        '',
    ).strip() or 'Movimentação em lote.'

    # requestApi envia cada ID repetindo a chave "ids".
    ids_recebidos = request.POST.getlist(
        'ids'
    )

    # Compatibilidade caso algum cliente envie "ids[]".
    if not ids_recebidos:
        ids_recebidos = request.POST.getlist(
            'ids[]'
        )

    # Compatibilidade com JSON/comma-separated em um único campo.
    if not ids_recebidos:
        ids_brutos = request.POST.get(
            'ids',
            '',
        ).strip()

        if ids_brutos:
            try:
                ids_json = json.loads(
                    ids_brutos
                )

                if isinstance(ids_json, list):
                    ids_recebidos = ids_json

            except (
                json.JSONDecodeError,
                TypeError,
            ):
                ids_recebidos = [
                    item.strip()
                    for item in ids_brutos.split(',')
                    if item.strip()
                ]

    ids = []
    ids_vistos = set()

    for valor in ids_recebidos:
        valor_str = str(
            valor
        ).strip()

        if not valor_str.isdigit():
            continue

        pk = int(valor_str)

        if pk in ids_vistos:
            continue

        ids_vistos.add(pk)
        ids.append(pk)

    if not ids:
        return JsonResponse(
            {
                'ok': False,
                'erro': (
                    'Nenhum cancelamento válido foi '
                    'selecionado.'
                ),
            },
            status=400,
        )

    if len(ids) > 200:
        return JsonResponse(
            {
                'ok': False,
                'erro': (
                    'O limite é de 200 cancelamentos '
                    'por movimentação em lote.'
                ),
            },
            status=400,
        )

    filas_validas = {
        valor
        for valor, _label
        in Cancelamento.Fila.choices
    }

    if fila_destino not in filas_validas:
        return JsonResponse(
            {
                'ok': False,
                'erro': 'Fila de destino inválida.',
            },
            status=400,
        )

    cancelamentos = {
        c.pk: c
        for c in (
            Cancelamento.objects
            .filter(pk__in=ids)
            .select_related(
                'responsavel',
                'atendente',
            )
        )
    }

    movidos = []
    falhas = []

    for pk in ids:
        cancelamento = cancelamentos.get(
            pk
        )

        if not cancelamento:
            falhas.append(
                {
                    'id': pk,
                    'ticket_arion': None,
                    'erro': (
                        'Cancelamento não encontrado.'
                    ),
                }
            )

            continue

        try:
            # O service já utiliza transaction.atomic() e registra
            # os históricos necessários para cada cancelamento.
            cancelamento = mover_cancelamento(
                cancelamento,
                fila_destino,
                request.user,
                motivo=motivo,
            )

            movidos.append(
                {
                    'id': cancelamento.pk,
                    'ticket_arion': (
                        cancelamento.ticket_arion
                    ),
                    'fila': cancelamento.fila,
                    'fila_label': (
                        cancelamento.get_fila_display()
                    ),
                    'status': (
                        cancelamento.status
                    ),
                    'status_label': (
                        cancelamento.get_status_display()
                    ),
                }
            )

        except (
            TransicaoInvalidaError,
            OperacaoNaoPermitidaError,
        ) as e:
            falhas.append(
                {
                    'id': cancelamento.pk,
                    'ticket_arion': (
                        cancelamento.ticket_arion
                    ),
                    'erro': str(e),
                }
            )

        except Exception as e:
            logger.exception(
                (
                    '[CANCELAMENTOS] Erro ao mover '
                    'cancelamento %s em lote.'
                ),
                cancelamento.pk,
            )

            falhas.append(
                {
                    'id': cancelamento.pk,
                    'ticket_arion': (
                        cancelamento.ticket_arion
                    ),
                    'erro': (
                        f'{type(e).__name__}: {str(e)}'
                    ),
                }
            )

    return JsonResponse(
        {
            'ok': True,
            'fila_destino': fila_destino,
            'fila_destino_label': dict(
                Cancelamento.Fila.choices
            ).get(
                fila_destino,
                fila_destino,
            ),
            'solicitados': len(ids),
            'movidos': len(movidos),
            'falharam': len(falhas),
            'resultados': movidos,
            'falhas': falhas,
        }
    )
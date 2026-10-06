"""
services.py — Regras de negócio do módulo de cancelamentos.

Centraliza aqui tudo que não é simples CRUD:
- movimentação de filas;
- apropriação / liberação / transferência;
- observações;
- pendências;
- alteração de status;
- financeiro legado;
- conclusão;
- edição com auditoria.

Todas as operações que alteram estado usam transação atômica e registram
HistoricoFila e/ou HistoricoCancelamento quando aplicável.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import (
    Cancelamento,
    HistoricoCancelamento,
    HistoricoFila,
    ObservacaoCancelamento,
    PendenciaCancelamento,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Mapa de transições permitidas
# ---------------------------------------------------------------------------
TRANSICOES_PERMITIDAS: dict[str, list[str]] = {
    Cancelamento.Fila.PEDIDO: [
        Cancelamento.Fila.SOLICITACAO,
    ],
    Cancelamento.Fila.SOLICITACAO: [
        Cancelamento.Fila.PENDENCIA,
    ],
    Cancelamento.Fila.PENDENCIA: [
        Cancelamento.Fila.SOLICITACAO,
    ],

    # Legado temporário.
    # Nenhuma fila nova deve ter FINANCEIRO como destino.
    Cancelamento.Fila.FINANCEIRO: [],

    # Estado terminal.
    Cancelamento.Fila.CONCLUIDO: [],
}



# ---------------------------------------------------------------------------
# Regra de status x fila
# ---------------------------------------------------------------------------
# IMPORTANTE:
# A fila representa onde o chamado está no fluxo operacional.
# O status representa a situação atual do chamado.
#
# Regra geral:
# - mover entre filas preserva o status atual;
# - EXCEÇÃO: ao entrar na fila PENDENCIA, o status principal
#   passa automaticamente para PENDENCIA_IDENTIFICADA;
# - a conclusão definitiva continua sendo tratada por concluir_cancelamento().
#
# Os status próprios de PendenciaCancelamento continuam independentes
# (ABERTA, EM_TRATATIVA, RESOLVIDA e DESCARTADA).


# ---------------------------------------------------------------------------
# Exceções de domínio
# ---------------------------------------------------------------------------
class TransicaoInvalidaError(Exception):
    """Tentativa de mover para uma fila não permitida."""


class OperacaoNaoPermitidaError(Exception):
    """Ação bloqueada pelas regras de negócio."""


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------
def _registrar_historico(
    cancelamento: Cancelamento,
    tipo: str,
    descricao: str,
    usuario=None,
) -> HistoricoCancelamento:
    return HistoricoCancelamento.objects.create(
        cancelamento=cancelamento,
        tipo=tipo,
        descricao=descricao,
        realizado_por=usuario,
    )


def _usuario_eh_admin(usuario) -> bool:
    """
    Regra única de administrador para o módulo de Cancelamentos.

    Aceita:
    - superuser Django;
    - staff Django;
    - preferência/cargo administrativo do ARION Broker.
    """
    if not usuario:
        return False

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


def _validar_edicao_concluido(
    cancelamento: Cancelamento,
    usuario,
    mensagem: str,
) -> None:
    """
    Chamados concluídos continuam terminais para o fluxo normal.

    A única exceção é administrativa: administradores podem corrigir
    dados, observações, pendências e financeiro sem reabrir ou mudar a fila.
    """
    if (
        cancelamento.fila
        == Cancelamento.Fila.CONCLUIDO
        and not _usuario_eh_admin(usuario)
    ):
        raise OperacaoNaoPermitidaError(
            mensagem
        )


def _recalcular_snapshot_financeiro_pendencias(
    cancelamento: Cancelamento,
) -> Cancelamento:
    """
    Recalcula o snapshot financeiro a partir das pendências não descartadas.

    Usado nas correções administrativas de chamados já concluídos para evitar
    inconsistências do tipo:
        pendência = R$ 500,00
        total final = R$ 0,00

    A fila, o status e a data de conclusão NÃO são alterados.
    """
    valor_multa = Decimal('0.00')
    valor_equipamento = Decimal('0.00')
    valor_outros = Decimal('0.00')

    pendencias = (
        cancelamento.pendencias
        .exclude(
            status=(
                PendenciaCancelamento
                .StatusPendencia
                .DESCARTADA
            )
        )
    )

    for pendencia in pendencias:
        valor = (
            pendencia.valor
            if pendencia.valor is not None
            else Decimal('0.00')
        )

        if (
            pendencia.tipo
            == PendenciaCancelamento.Tipo.MULTA_CONTRATO
        ):
            valor_multa += valor

        elif (
            pendencia.tipo
            == PendenciaCancelamento.Tipo.MULTA_EQUIPAMENTO
        ):
            valor_equipamento += valor

        else:
            valor_outros += valor

    cancelamento.valor_multa_rescisao = valor_multa
    cancelamento.valor_equipamento = valor_equipamento
    cancelamento.valor_outros = valor_outros

    cancelamento.save(
        update_fields=[
            'valor_multa_rescisao',
            'valor_equipamento',
            'valor_outros',
            'atualizado_em',
        ]
    )

    return cancelamento


# ---------------------------------------------------------------------------
# Movimentação de filas
# ---------------------------------------------------------------------------
def mover_cancelamento(
    cancelamento: Cancelamento,
    fila_destino: str,
    usuario,
    motivo: str = '',
) -> Cancelamento:
    """
    Move o cancelamento para uma fila permitida.

    Regras:
    - a fila CONCLUIDO não pode ser acessada manualmente;
    - a mudança de fila preserva o status atual do cancelamento;
    - exceção: ao entrar na fila PENDENCIA, o status passa para
      PENDENCIA_IDENTIFICADA;
    - o status também pode ser alterado separadamente por alterar_status();
    - a conclusão definitiva continua responsável pelo status terminal.
    """

    if fila_destino == Cancelamento.Fila.CONCLUIDO:
        raise TransicaoInvalidaError(
            'A fila Concluídos somente pode ser acessada '
            'pela operação de conclusão.'
        )

    fila_origem = cancelamento.fila

    destinos_permitidos = TRANSICOES_PERMITIDAS.get(
        fila_origem,
        [],
    )

    if fila_destino not in destinos_permitidos:
        raise TransicaoInvalidaError(
            f'Não é possível mover de {fila_origem} '
            f'para {fila_destino}. '
            f'Destinos permitidos: '
            f'{destinos_permitidos or "nenhum"}'
        )

    with transaction.atomic():
        # Fila e status são independentes.
        # Regra especial: ao ENTRAR na fila de Pendências,
        # o status passa automaticamente para PENDENCIA_IDENTIFICADA.
        cancelamento.fila = fila_destino

        campos_atualizados = [
            'fila',
            'atualizado_em',
        ]

        if fila_destino == Cancelamento.Fila.PENDENCIA:
            cancelamento.status = (
                Cancelamento.Status.PENDENCIA_IDENTIFICADA
            )
            campos_atualizados.append('status')

        cancelamento.save(
            update_fields=campos_atualizados
        )

        HistoricoFila.objects.create(
            cancelamento=cancelamento,
            fila_origem=fila_origem,
            fila_destino=fila_destino,
            movido_por=usuario,
        )

        fila_origem_label = dict(
            Cancelamento.Fila.choices
        ).get(
            fila_origem,
            fila_origem,
        )

        fila_destino_label = dict(
            Cancelamento.Fila.choices
        ).get(
            fila_destino,
            fila_destino,
        )

        descricao = (
            f'Movido de "{fila_origem_label}" '
            f'para "{fila_destino_label}"'
        )

        if motivo:
            descricao += f'. Motivo: {motivo}'

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.MUDANCA_FILA,
            descricao,
            usuario,
        )

    return cancelamento


# ---------------------------------------------------------------------------
# Apropriação
# ---------------------------------------------------------------------------
def apropriar_cancelamento(
    cancelamento: Cancelamento,
    usuario,
) -> Cancelamento:
    if cancelamento.fila == Cancelamento.Fila.CONCLUIDO:
        raise OperacaoNaoPermitidaError(
            'Não é possível apropriar um cancelamento concluído.'
        )

    if cancelamento.responsavel_id:
        raise OperacaoNaoPermitidaError(
            f'Este chamado já está com '
            f'{cancelamento.responsavel}. '
            f'Use a transferência para mudar o responsável.'
        )

    with transaction.atomic():
        cancelamento.responsavel = usuario
        cancelamento.apropriado_em = timezone.now()

        cancelamento.save(
            update_fields=[
                'responsavel',
                'apropriado_em',
                'atualizado_em',
            ]
        )

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.APROPRIACAO,
            f'{usuario} apropriou-se do cancelamento.',
            usuario,
        )

    return cancelamento


def liberar_cancelamento(
    cancelamento: Cancelamento,
    usuario,
) -> Cancelamento:
    if cancelamento.fila == Cancelamento.Fila.CONCLUIDO:
        raise OperacaoNaoPermitidaError(
            'Não é possível liberar um cancelamento concluído.'
        )

    if not cancelamento.responsavel_id:
        return cancelamento

    eh_responsavel = (
        cancelamento.responsavel_id == usuario.pk
    )

    eh_admin = getattr(
        usuario,
        'is_staff',
        False,
    )

    if not (
        eh_responsavel
        or eh_admin
    ):
        raise OperacaoNaoPermitidaError(
            'Somente o próprio responsável ou um '
            'administrador pode liberar o chamado.'
        )

    with transaction.atomic():
        responsavel_anterior = str(
            cancelamento.responsavel
        )

        cancelamento.responsavel = None
        cancelamento.apropriado_em = None

        cancelamento.save(
            update_fields=[
                'responsavel',
                'apropriado_em',
                'atualizado_em',
            ]
        )

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.LIBERACAO,
            (
                f'{responsavel_anterior} liberou '
                f'o cancelamento '
                f'(ação de {usuario}).'
            ),
            usuario,
        )

    return cancelamento


def transferir_cancelamento(
    cancelamento: Cancelamento,
    novo_responsavel,
    usuario,
) -> Cancelamento:
    if cancelamento.fila == Cancelamento.Fila.CONCLUIDO:
        raise OperacaoNaoPermitidaError(
            'Não é possível transferir um '
            'cancelamento concluído.'
        )

    if not getattr(
        usuario,
        'is_staff',
        False,
    ):
        raise OperacaoNaoPermitidaError(
            'Somente administradores podem transferir '
            'a responsabilidade de um chamado.'
        )

    with transaction.atomic():
        responsavel_anterior = (
            str(cancelamento.responsavel)
            if cancelamento.responsavel_id
            else 'sem responsável'
        )

        cancelamento.responsavel = novo_responsavel
        cancelamento.apropriado_em = timezone.now()

        cancelamento.save(
            update_fields=[
                'responsavel',
                'apropriado_em',
                'atualizado_em',
            ]
        )

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.TRANSFERENCIA,
            (
                f'Responsável alterado de '
                f'"{responsavel_anterior}" para '
                f'"{novo_responsavel}" por {usuario}.'
            ),
            usuario,
        )

    return cancelamento


# ---------------------------------------------------------------------------
# Observações
# ---------------------------------------------------------------------------
def adicionar_observacao(
    cancelamento: Cancelamento,
    texto: str,
    usuario,
) -> ObservacaoCancelamento:
    _validar_edicao_concluido(
        cancelamento,
        usuario,
        (
            'Somente administradores podem adicionar observações '
            'a um cancelamento concluído.'
        ),
    )

    texto = str(
        texto or ''
    ).strip()

    if not texto:
        raise OperacaoNaoPermitidaError(
            'O texto da observação não pode ser vazio.'
        )

    with transaction.atomic():
        observacao = ObservacaoCancelamento.objects.create(
            cancelamento=cancelamento,
            texto=texto,
            criado_por=usuario,
        )

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.OBSERVACAO,
            f'Observação adicionada por {usuario}.',
            usuario,
        )

    return observacao


# ---------------------------------------------------------------------------
# Pendências
# ---------------------------------------------------------------------------
def criar_pendencia(
    cancelamento: Cancelamento,
    tipo: str,
    descricao: str = '',
    valor=None,
    data_prevista=None,
    usuario=None,
) -> PendenciaCancelamento:
    _validar_edicao_concluido(
        cancelamento,
        usuario,
        (
            'Somente administradores podem criar pendências '
            'em um cancelamento concluído.'
        ),
    )

    with transaction.atomic():
        pendencia = PendenciaCancelamento.objects.create(
            cancelamento=cancelamento,
            tipo=tipo,
            descricao=descricao,
            valor=valor,
            data_prevista=data_prevista,
            criada_por=usuario,
        )

        tipo_label = dict(
            PendenciaCancelamento.Tipo.choices
        ).get(
            tipo,
            tipo,
        )

        descricao_historico = (
            f'Pendência criada: {tipo_label}'
        )

        if descricao:
            descricao_historico += (
                f' — {descricao}'
            )

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.PENDENCIA_CRIADA,
            descricao_historico,
            usuario,
        )

        if (
            cancelamento.fila
            == Cancelamento.Fila.CONCLUIDO
        ):
            _recalcular_snapshot_financeiro_pendencias(
                cancelamento
            )

            _registrar_historico(
                cancelamento,
                HistoricoCancelamento.Tipo.VALOR_ALTERADO,
                (
                    'Snapshot financeiro recalculado automaticamente '
                    'após inclusão administrativa de pendência '
                    'em chamado concluído.'
                ),
                usuario,
            )

    return pendencia


def resolver_pendencia(
    pendencia: PendenciaCancelamento,
    usuario,
) -> PendenciaCancelamento:
    _validar_edicao_concluido(
        pendencia.cancelamento,
        usuario,
        (
            'Somente administradores podem alterar pendências '
            'de um cancelamento concluído.'
        ),
    )

    with transaction.atomic():
        pendencia.marcar_resolvida()

        tipo_label = dict(
            PendenciaCancelamento.Tipo.choices
        ).get(
            pendencia.tipo,
            pendencia.tipo,
        )

        _registrar_historico(
            pendencia.cancelamento,
            HistoricoCancelamento.Tipo.PENDENCIA_RESOLVIDA,
            f'Pendência resolvida: {tipo_label}.',
            usuario,
        )

        if (
            pendencia.cancelamento.fila
            == Cancelamento.Fila.CONCLUIDO
        ):
            _recalcular_snapshot_financeiro_pendencias(
                pendencia.cancelamento
            )

    return pendencia


def descartar_pendencia(
    pendencia: PendenciaCancelamento,
    usuario,
) -> PendenciaCancelamento:
    """
    Descarta uma pendência com auditoria.

    Em chamados concluídos, somente Admin pode executar a correção.
    Pendência descartada deixa de participar do snapshot financeiro.
    """
    cancelamento = pendencia.cancelamento

    _validar_edicao_concluido(
        cancelamento,
        usuario,
        (
            'Somente administradores podem descartar pendências '
            'de um cancelamento concluído.'
        ),
    )

    with transaction.atomic():
        pendencia.status = (
            PendenciaCancelamento
            .StatusPendencia
            .DESCARTADA
        )

        pendencia.save(
            update_fields=[
                'status',
            ]
        )

        tipo_label = dict(
            PendenciaCancelamento.Tipo.choices
        ).get(
            pendencia.tipo,
            pendencia.tipo,
        )

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.EDICAO,
            f'Pendência descartada: {tipo_label}.',
            usuario,
        )

        if (
            cancelamento.fila
            == Cancelamento.Fila.CONCLUIDO
        ):
            _recalcular_snapshot_financeiro_pendencias(
                cancelamento
            )

            _registrar_historico(
                cancelamento,
                HistoricoCancelamento.Tipo.VALOR_ALTERADO,
                (
                    'Snapshot financeiro recalculado automaticamente '
                    'após descarte administrativo de pendência '
                    'em chamado concluído.'
                ),
                usuario,
            )

    return pendencia


# ---------------------------------------------------------------------------
# Alteração de status
# ---------------------------------------------------------------------------
def alterar_status(
    cancelamento: Cancelamento,
    novo_status: str,
    usuario,
) -> Cancelamento:
    """
    Altera manualmente o status.

    CONCLUIDO_CANCELAMENTO é reservado exclusivamente
    para concluir_cancelamento().
    """

    if cancelamento.fila == Cancelamento.Fila.CONCLUIDO:
        raise OperacaoNaoPermitidaError(
            'Não é possível alterar o status '
            'de um cancelamento concluído.'
        )

    if novo_status not in dict(
        Cancelamento.Status.choices
    ):
        raise OperacaoNaoPermitidaError(
            f'Status inválido: {novo_status}'
        )

    if (
        novo_status
        == Cancelamento.Status.CONCLUIDO_CANCELAMENTO
    ):
        raise OperacaoNaoPermitidaError(
            'O status "Cancelamento concluído" '
            'não pode ser aplicado manualmente. '
            'Utilize a operação Concluir.'
        )

    if cancelamento.status == novo_status:
        return cancelamento

    with transaction.atomic():
        status_anterior = (
            cancelamento.get_status_display()
        )

        cancelamento.status = novo_status

        cancelamento.save(
            update_fields=[
                'status',
                'atualizado_em',
            ]
        )

        novo_status_label = dict(
            Cancelamento.Status.choices
        ).get(
            novo_status,
            novo_status,
        )

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.ALTERACAO_STATUS,
            (
                f'Status alterado de '
                f'"{status_anterior}" para '
                f'"{novo_status_label}".'
            ),
            usuario,
        )

    return cancelamento


# ---------------------------------------------------------------------------
# Atualização de valores financeiros
# ---------------------------------------------------------------------------
def atualizar_financeiro(
    cancelamento: Cancelamento,
    usuario,
    valor_multa_rescisao=None,
    valor_equipamento=None,
    valor_outros=None,
    ultima_competencia_faturada: str = '',
    data_baixa_financeira=None,
    confirmacao_sem_nova_cobranca: bool | None = None,
    observacao_financeira: str = '',
    data_cancelamento_confirmado=None,
) -> Cancelamento:
    """
    Mantido para compatibilidade com registros legados.

    Não deve ser usado como etapa obrigatória do novo fluxo.
    """

    _validar_edicao_concluido(
        cancelamento,
        usuario,
        (
            'Somente administradores podem alterar dados financeiros '
            'de um cancelamento concluído.'
        ),
    )

    campos = []

    if valor_multa_rescisao is not None:
        cancelamento.valor_multa_rescisao = (
            valor_multa_rescisao
        )
        campos.append(
            'valor_multa_rescisao'
        )

    if valor_equipamento is not None:
        cancelamento.valor_equipamento = (
            valor_equipamento
        )
        campos.append(
            'valor_equipamento'
        )

    if valor_outros is not None:
        cancelamento.valor_outros = valor_outros
        campos.append(
            'valor_outros'
        )

    if ultima_competencia_faturada:
        cancelamento.ultima_competencia_faturada = (
            ultima_competencia_faturada
        )
        campos.append(
            'ultima_competencia_faturada'
        )

    if data_baixa_financeira is not None:
        cancelamento.data_baixa_financeira = (
            data_baixa_financeira
        )
        campos.append(
            'data_baixa_financeira'
        )

    if confirmacao_sem_nova_cobranca is not None:
        cancelamento.confirmacao_sem_nova_cobranca = (
            confirmacao_sem_nova_cobranca
        )
        campos.append(
            'confirmacao_sem_nova_cobranca'
        )

    if observacao_financeira:
        cancelamento.observacao_financeira = (
            observacao_financeira
        )
        campos.append(
            'observacao_financeira'
        )

    if data_cancelamento_confirmado is not None:
        cancelamento.data_cancelamento_confirmado = (
            data_cancelamento_confirmado
        )
        campos.append(
            'data_cancelamento_confirmado'
        )

    if not campos:
        return cancelamento

    campos.append(
        'atualizado_em'
    )

    with transaction.atomic():
        cancelamento.save(
            update_fields=campos
        )

        _registrar_historico(
            cancelamento,
            HistoricoCancelamento.Tipo.VALOR_ALTERADO,
            f'Dados financeiros atualizados por {usuario}.',
            usuario,
        )

    return cancelamento


# ---------------------------------------------------------------------------
# Conclusão
# ---------------------------------------------------------------------------
def concluir_cancelamento(
    cancelamento: Cancelamento,
    usuario,
) -> Cancelamento:
    """
    Conclui definitivamente o cancelamento.

    Regras:
    - PENDENCIA é a origem normal;
    - FINANCEIRO é aceito apenas para legado;
    - pendências ABERTA / EM_TRATATIVA não bloqueiam;
    - pendências DESCARTADAS não entram no cálculo;
    - valores financeiros são derivados das pendências;
    - FINANCEIRO legado preserva o snapshot existente;
    - CONCLUIDO é terminal.
    """

    if cancelamento.fila == Cancelamento.Fila.CONCLUIDO:
        raise OperacaoNaoPermitidaError(
            'Este cancelamento já está concluído.'
        )

    with transaction.atomic():
        cancelamento_locked = (
            Cancelamento.objects
            .select_for_update()
            .get(pk=cancelamento.pk)
        )

        # ---------------------------------------------------------------
        # Revalidação após lock
        # ---------------------------------------------------------------
        if (
            cancelamento_locked.fila
            == Cancelamento.Fila.CONCLUIDO
        ):
            raise OperacaoNaoPermitidaError(
                'Este cancelamento já está concluído.'
            )

        fila_origem = (
            cancelamento_locked.fila
        )

        # ---------------------------------------------------------------
        # Origem permitida
        # ---------------------------------------------------------------
        if fila_origem not in (
            Cancelamento.Fila.PENDENCIA,
            Cancelamento.Fila.FINANCEIRO,
        ):
            raise OperacaoNaoPermitidaError(
                'O cancelamento somente pode ser '
                'concluído a partir da fila de Pendências.'
            )

        # ---------------------------------------------------------------
        # Data
        # ---------------------------------------------------------------
        if (
            not cancelamento_locked
            .data_cancelamento_confirmado
        ):
            raise OperacaoNaoPermitidaError(
                'Informe a data do cancelamento '
                'antes de concluir.'
            )

        campos_financeiros = []

        # ---------------------------------------------------------------
        # Snapshot financeiro
        # ---------------------------------------------------------------
        if (
            fila_origem
            == Cancelamento.Fila.PENDENCIA
        ):
            valor_multa = Decimal(
                '0.00'
            )

            valor_equipamento = Decimal(
                '0.00'
            )

            valor_outros = Decimal(
                '0.00'
            )

            pendencias = (
                cancelamento_locked
                .pendencias
                .select_for_update()
                .exclude(
                    status=(
                        PendenciaCancelamento
                        .StatusPendencia
                        .DESCARTADA
                    )
                )
            )

            for pendencia in pendencias:
                valor = (
                    pendencia.valor
                    if pendencia.valor is not None
                    else Decimal('0.00')
                )

                if (
                    pendencia.tipo
                    == PendenciaCancelamento
                    .Tipo
                    .MULTA_CONTRATO
                ):
                    valor_multa += valor

                elif (
                    pendencia.tipo
                    == PendenciaCancelamento
                    .Tipo
                    .MULTA_EQUIPAMENTO
                ):
                    valor_equipamento += valor

                else:
                    valor_outros += valor

            cancelamento_locked.valor_multa_rescisao = (
                valor_multa
            )

            cancelamento_locked.valor_equipamento = (
                valor_equipamento
            )

            cancelamento_locked.valor_outros = (
                valor_outros
            )

            campos_financeiros = [
                'valor_multa_rescisao',
                'valor_equipamento',
                'valor_outros',
            ]

        # ---------------------------------------------------------------
        # Estado terminal
        # ---------------------------------------------------------------
        cancelamento_locked.fila = (
            Cancelamento.Fila.CONCLUIDO
        )

        cancelamento_locked.status = (
            Cancelamento.Status
            .CONCLUIDO_CANCELAMENTO
        )

        cancelamento_locked.concluido_em = (
            timezone.now()
        )

        cancelamento_locked.save(
            update_fields=[
                *campos_financeiros,
                'fila',
                'status',
                'concluido_em',
                'atualizado_em',
            ]
        )

        # ---------------------------------------------------------------
        # Histórico de fila
        # ---------------------------------------------------------------
        HistoricoFila.objects.create(
            cancelamento=cancelamento_locked,
            fila_origem=fila_origem,
            fila_destino=Cancelamento.Fila.CONCLUIDO,
            movido_por=usuario,
        )

        # ---------------------------------------------------------------
        # Histórico da conclusão
        # ---------------------------------------------------------------
        fila_origem_label = dict(
            Cancelamento.Fila.choices
        ).get(
            fila_origem,
            fila_origem,
        )

        _registrar_historico(
            cancelamento_locked,
            HistoricoCancelamento.Tipo.CONCLUSAO,
            (
                f'Cancelamento concluído por {usuario}. '
                f'Movimentado de '
                f'"{fila_origem_label}" '
                f'para "Concluídos".'
            ),
            usuario,
        )

        # ---------------------------------------------------------------
        # Sincroniza objeto original
        # ---------------------------------------------------------------
        cancelamento.fila = (
            cancelamento_locked.fila
        )

        cancelamento.status = (
            cancelamento_locked.status
        )

        cancelamento.concluido_em = (
            cancelamento_locked.concluido_em
        )

        cancelamento.data_cancelamento_confirmado = (
            cancelamento_locked
            .data_cancelamento_confirmado
        )

        cancelamento.valor_multa_rescisao = (
            cancelamento_locked
            .valor_multa_rescisao
        )

        cancelamento.valor_equipamento = (
            cancelamento_locked
            .valor_equipamento
        )

        cancelamento.valor_outros = (
            cancelamento_locked
            .valor_outros
        )

    return cancelamento


# ---------------------------------------------------------------------------
# Edição de Dados (Com Auditoria)
# ---------------------------------------------------------------------------
def editar_cancelamento(
    cancelamento: Cancelamento,
    dados_novos: dict,
    usuario,
) -> Cancelamento:
    """
    Atualiza os dados cadastrais permitidos e registra
    auditoria detalhada das alterações.
    """

    _validar_edicao_concluido(
        cancelamento,
        usuario,
        (
            'Somente administradores podem editar '
            'um cancelamento concluído.'
        ),
    )

    campos_permitidos = [
        'ticket_arion',
        'ticket_url',
        'designacao_circuito',
        'cod_cliente',
        'cliente',
        'cliente_final',
        'isp',
        'contato_isp',
        'protocolo',
        'canal_contato',
        'endereco',
        'numero',
        'complemento',
        'bairro',
        'cidade',
        'uf',
        'cep',
        'data_criacao_chamado',
        'agendamento',
        'proxima_acao',
        'data_proxima_acao',
        'observacao',
    ]

    campos_data = {
        'data_criacao_chamado',
        'agendamento',
        'data_proxima_acao',
    }

    alteracoes = []

    with transaction.atomic():
        cancelamento_locked = (
            Cancelamento.objects
            .select_for_update()
            .get(pk=cancelamento.pk)
        )

        _validar_edicao_concluido(
            cancelamento_locked,
            usuario,
            (
                'Somente administradores podem editar '
                'um cancelamento concluído.'
            ),
        )

        campos_alterados = []

        for campo in campos_permitidos:
            if campo not in dados_novos:
                continue

            valor_antigo = getattr(
                cancelamento_locked,
                campo,
            )

            valor_novo = dados_novos[
                campo
            ]

            str_antigo = (
                str(valor_antigo).strip()
                if valor_antigo is not None
                else ''
            )

            str_novo = (
                str(valor_novo).strip()
                if valor_novo is not None
                else ''
            )

            if str_antigo == str_novo:
                continue

            if (
                str_novo == ''
                and campo in campos_data
            ):
                valor_final = None
            else:
                valor_final = valor_novo

            setattr(
                cancelamento_locked,
                campo,
                valor_final,
            )

            campos_alterados.append(
                campo
            )

            alteracoes.append(
                (
                    f'- {campo}: '
                    f'de "{str_antigo}" '
                    f'para "{str_novo}"'
                )
            )

        if not campos_alterados:
            return cancelamento_locked

        cancelamento_locked.save(
            update_fields=[
                *campos_alterados,
                'atualizado_em',
            ]
        )

        descricao_auditoria = (
            'Dados do cancelamento editados:\n'
            + '\n'.join(alteracoes)
        )

        _registrar_historico(
            cancelamento_locked,
            HistoricoCancelamento.Tipo.EDICAO,
            descricao_auditoria,
            usuario,
        )

        for campo in campos_permitidos:
            setattr(
                cancelamento,
                campo,
                getattr(
                    cancelamento_locked,
                    campo,
                ),
            )

        cancelamento.atualizado_em = (
            cancelamento_locked.atualizado_em
        )

    return cancelamento
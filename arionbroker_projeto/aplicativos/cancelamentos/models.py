from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Model principal
# ---------------------------------------------------------------------------
class Cancelamento(models.Model):

    class Fila(models.TextChoices):
        PEDIDO = 'PEDIDO', 'Pedido de Cancelamento'
        SOLICITACAO = 'SOLICITACAO', 'Solicitação de Cancelamento'
        PENDENCIA = 'PENDENCIA', 'Pendências de Cancelamento'

        # Compatibilidade temporária durante a migração do fluxo
        FINANCEIRO = 'FINANCEIRO', 'Financeiro - Cancelamento'

        CONCLUIDO = 'CONCLUIDO', 'Concluídos'

    class Status(models.TextChoices):
        NOVO = 'NOVO', 'Novo'
        SEM_RESPONSAVEL = 'SEM_RESPONSAVEL', 'Sem responsável'
        EM_TRIAGEM = 'EM_TRIAGEM', 'Em triagem'
        EM_ATENDIMENTO = 'EM_ATENDIMENTO', 'Em Atendimento'
        AG_CONTATO = 'AG_CONTATO', 'Aguardando contato'
        SOLICITACAO_ENVIADA = 'SOLICITACAO_ENVIADA', 'Solicitação enviada'
        AG_RETORNO_ISP = 'AG_RETORNO_ISP', 'Aguardando retorno da ISP'
        CANCELAMENTO_CONFIRMADO = (
            'CANCELAMENTO_CONFIRMADO',
            'Cancelamento confirmado',
        )
        PENDENCIA_IDENTIFICADA = (
            'PENDENCIA_IDENTIFICADA',
            'Pendência identificada',
        )
        AG_ANALISE_FINANCEIRA = (
            'AG_ANALISE_FINANCEIRA',
            'Aguardando análise',
        )
        EM_ANALISE_FINANCEIRA = (
            'EM_ANALISE_FINANCEIRA',
            'Em análise financeira',
        )
        AG_BAIXA = 'AG_BAIXA', 'Aguardando baixa'
        BAIXA_CONCLUIDA = 'BAIXA_CONCLUIDA', 'Baixa concluída'
        CONCLUIDO_CANCELAMENTO = (
            'CONCLUIDO_CANCELAMENTO',
            'Concluído Cancelamento',
        )
        CANCELADO = 'CANCELADO', 'Cancelado'
        AG_VISITA_TECNICA = 'AG_VISITA_TECNICA', 'Ag. Visita Técnica'
        PENDENTE_CANCELAMENTO = (
            'PENDENTE_CANCELAMENTO',
            'Pendente de Cancelamento',
        )

    class CanalContato(models.TextChoices):
        EMAIL = 'EMAIL', 'E-mail'
        TELEFONE = 'TELEFONE', 'Telefone'
        PORTAL = 'PORTAL', 'Portal'
        WHATSAPP = 'WHATSAPP', 'WhatsApp'
        OUTRO = 'OUTRO', 'Outro'

    # -----------------------------------------------------------------------
    # OTRS
    # -----------------------------------------------------------------------
    ticket_arion = models.CharField(
        'Ticket Arion',
        max_length=50,
        unique=True,
    )

    ticket_url = models.URLField(
        'Link do chamado no OTRS',
        max_length=500,
        blank=True,
    )

    # -----------------------------------------------------------------------
    # Link / circuito
    # -----------------------------------------------------------------------
    designacao_circuito = models.CharField(
        'Designação/Circuito',
        max_length=100,
        blank=True,
    )

    cod_cliente = models.CharField(
        'Cód. Cliente',
        max_length=50,
        blank=True,
    )

    # -----------------------------------------------------------------------
    # Clientes
    # -----------------------------------------------------------------------
    cliente = models.CharField(
        'Cliente (Operadora)',
        max_length=100,
        blank=True,
    )

    cliente_final = models.CharField(
        'Cliente Final',
        max_length=150,
        blank=True,
    )

    # -----------------------------------------------------------------------
    # ISP
    # -----------------------------------------------------------------------
    isp = models.CharField(
        'ISP',
        max_length=100,
        blank=True,
    )

    contato_isp = models.CharField(
        'Contato da ISP',
        max_length=100,
        blank=True,
    )

    protocolo = models.CharField(
        'Protocolo',
        max_length=100,
        blank=True,
    )

    canal_contato = models.CharField(
        'Canal de contato',
        max_length=20,
        choices=CanalContato.choices,
        blank=True,
    )

    # -----------------------------------------------------------------------
    # Localização
    # -----------------------------------------------------------------------
    endereco = models.CharField(
        'Endereço',
        max_length=200,
        blank=True,
    )

    numero = models.CharField(
        'Número',
        max_length=20,
        blank=True,
    )

    complemento = models.CharField(
        'Complemento',
        max_length=100,
        blank=True,
    )

    bairro = models.CharField(
        'Bairro',
        max_length=100,
        blank=True,
    )

    cidade = models.CharField(
        'Cidade',
        max_length=100,
        blank=True,
    )

    uf = models.CharField(
        'UF',
        max_length=2,
        blank=True,
    )

    cep = models.CharField(
        'CEP',
        max_length=9,
        blank=True,
    )

    # -----------------------------------------------------------------------
    # Fluxo
    # -----------------------------------------------------------------------
    fila = models.CharField(
        'Fila',
        max_length=20,
        choices=Fila.choices,
        default=Fila.PEDIDO,
    )

    status = models.CharField(
        'Status',
        max_length=30,
        choices=Status.choices,
        default=Status.NOVO,
    )

    # -----------------------------------------------------------------------
    # Responsável
    # -----------------------------------------------------------------------
    atendente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelamentos_atendente',
        verbose_name='Atendente (legado)',
    )

    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelamentos',
        verbose_name='Responsável',
    )

    apropriado_em = models.DateTimeField(
        'Apropriado em',
        null=True,
        blank=True,
    )

    # -----------------------------------------------------------------------
    # Datas
    # -----------------------------------------------------------------------
    data_criacao_chamado = models.DateField(
        'Data de Criação do Chamado',
        null=True,
        blank=True,
    )

    data_primeiro_contato = models.DateField(
        'Data do primeiro contato',
        null=True,
        blank=True,
    )

    data_ultima_interacao = models.DateField(
        'Data da última interação',
        null=True,
        blank=True,
    )

    data_cancelamento_confirmado = models.DateField(
        'Data do cancelamento confirmado',
        null=True,
        blank=True,
    )

    concluido_em = models.DateTimeField(
        'Concluído em',
        null=True,
        blank=True,
    )

    # -----------------------------------------------------------------------
    # Próxima ação
    # -----------------------------------------------------------------------
    proxima_acao = models.CharField(
        'Próxima ação',
        max_length=255,
        blank=True,
    )

    data_proxima_acao = models.DateField(
        'Data da próxima ação',
        null=True,
        blank=True,
    )

    # -----------------------------------------------------------------------
    # Financeiro
    #
    # Estes campos permanecem no model.
    #
    # No novo fluxo os valores finais são preenchidos automaticamente
    # pelo services.py no momento da conclusão, a partir das pendências.
    #
    # Eles representam uma fotografia financeira do encerramento.
    # -----------------------------------------------------------------------
    valor_multa_rescisao = models.DecimalField(
        'Valor da Multa/Rescisão',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    valor_equipamento = models.DecimalField(
        'Valor do Equipamento',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    valor_outros = models.DecimalField(
        'Outros valores',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    ultima_competencia_faturada = models.CharField(
        'Última competência faturada',
        max_length=20,
        blank=True,
    )

    data_baixa_financeira = models.DateField(
        'Data da baixa financeira',
        null=True,
        blank=True,
    )

    confirmacao_sem_nova_cobranca = models.BooleanField(
        'Confirmado sem nova cobrança',
        default=False,
    )

    observacao_financeira = models.TextField(
        'Observação financeira',
        blank=True,
    )

    # -----------------------------------------------------------------------
    # Controle
    # -----------------------------------------------------------------------
    observacao = models.TextField(
        'Observação (legado)',
        blank=True,
    )

    agendamento = models.DateField(
        'Agendamento',
        null=True,
        blank=True,
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = 'Cancelamento'
        verbose_name_plural = 'Cancelamentos'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.ticket_arion} - {self.cliente_final}'

    # -----------------------------------------------------------------------
    # Properties calculadas
    # -----------------------------------------------------------------------
    @property
    def pendencias_ativas(self):
        """
        Retorna todas as pendências que não foram descartadas.

        Uma pendência ABERTA ou EM_TRATATIVA continua sendo considerada
        para fins de registro e valor.

        Somente DESCARTADA é ignorada.
        """
        return self.pendencias.exclude(
            status='DESCARTADA'
        )

    @property
    def pendencias_ativas_count(self):
        return self.pendencias_ativas.count()

    @property
    def valor_pendencias_multa(self):
        """
        Soma todas as multas de contrato não descartadas.
        """
        return sum(
            (
                p.valor or 0
                for p in self.pendencias_ativas.filter(
                    tipo='multa_contrato'
                )
            ),
            0,
        )

    @property
    def valor_pendencias_equipamento(self):
        """
        Soma todas as multas de equipamento não descartadas.
        """
        return sum(
            (
                p.valor or 0
                for p in self.pendencias_ativas.filter(
                    tipo='multa_equipamento'
                )
            ),
            0,
        )

    @property
    def valor_pendencias_outros(self):
        """
        Soma os valores das demais pendências não descartadas.

        Tudo que não for multa de contrato ou multa de equipamento
        entra em Outros.
        """
        return sum(
            (
                p.valor or 0
                for p in self.pendencias_ativas.exclude(
                    tipo__in=[
                        'multa_contrato',
                        'multa_equipamento',
                    ]
                )
            ),
            0,
        )

    @property
    def valor_pendencias_total(self):
        """
        Soma todos os valores das pendências não descartadas.
        """
        return sum(
            (
                p.valor or 0
                for p in self.pendencias_ativas
            ),
            0,
        )

    @property
    def valor_total_financeiro(self):
        """
        Total financeiro gravado no Cancelamento.

        Após a conclusão representa a fotografia dos valores
        existentes naquele momento.
        """
        return (
            (self.valor_multa_rescisao or 0)
            + (self.valor_equipamento or 0)
            + (self.valor_outros or 0)
        )

    @property
    def aging_dias(self):
        """
        Quantidade de dias desde a criação do chamado.
        """
        from datetime import date

        if self.data_criacao_chamado:
            return (
                date.today()
                - self.data_criacao_chamado
            ).days

        return None

    @property
    def pode_concluir(self):
        """
        Regra de negócio para conclusão.

        No novo fluxo, as pendências funcionam como registros
        operacionais/financeiros.

        Elas NÃO precisam estar resolvidas para permitir a conclusão.

        Pendências ABERTAS ou EM_TRATATIVA continuam registradas e seus
        valores entram normalmente no fechamento.

        Apenas pendências DESCARTADAS são ignoradas nos cálculos.

        Para concluir é necessário somente possuir a data em que o
        cancelamento foi confirmado.

        A validação da fila de origem permitida é responsabilidade
        do services.py.
        """
        return bool(
            self.data_cancelamento_confirmado
        )


# ---------------------------------------------------------------------------
# Histórico de filas
# ---------------------------------------------------------------------------
class HistoricoFila(models.Model):

    cancelamento = models.ForeignKey(
        Cancelamento,
        on_delete=models.CASCADE,
        related_name='historico',
    )

    fila_origem = models.CharField(
        'Fila de Origem',
        max_length=20,
        choices=Cancelamento.Fila.choices,
        null=True,
        blank=True,
    )

    fila_destino = models.CharField(
        'Fila de Destino',
        max_length=20,
        choices=Cancelamento.Fila.choices,
    )

    movido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    movido_em = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = 'Histórico de Fila'
        verbose_name_plural = 'Históricos de Fila'
        ordering = ['-movido_em']

    def __str__(self):
        return (
            f'{self.cancelamento.ticket_arion}: '
            f'{self.fila_origem} → {self.fila_destino}'
        )


# ---------------------------------------------------------------------------
# Observações
# ---------------------------------------------------------------------------
class ObservacaoCancelamento(models.Model):

    cancelamento = models.ForeignKey(
        Cancelamento,
        on_delete=models.CASCADE,
        related_name='observacoes',
    )

    texto = models.TextField(
        'Observação',
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = 'Observação'
        verbose_name_plural = 'Observações'
        ordering = ['criado_em']

    def __str__(self):
        return (
            f'Obs. {self.cancelamento.ticket_arion} — '
            f'{self.criado_em:%d/%m/%Y %H:%M}'
        )


# ---------------------------------------------------------------------------
# Pendências
# ---------------------------------------------------------------------------
class PendenciaCancelamento(models.Model):

    class Tipo(models.TextChoices):
        MENSALIDADES_ATRASADAS = (
            'mensalidades_atrasadas',
            'Mensalidades Atrasadas',
        )

        MULTA_EQUIPAMENTO = (
            'multa_equipamento',
            'Multa Equipamento',
        )

        MULTA_CONTRATO = (
            'multa_contrato',
            'Multa Contrato',
        )

        AGUARDANDO_DISTRATO = (
            'aguardando_distrato',
            'Aguardando Distrato',
        )

        AGUARDANDO_TERMO = (
            'aguardando_termo',
            'Aguardando Termo para Baixa',
        )

        OUTROS = (
            'outros',
            'Outros (digitar)',
        )

    class StatusPendencia(models.TextChoices):
        ABERTA = (
            'ABERTA',
            'Aberta',
        )

        EM_TRATATIVA = (
            'EM_TRATATIVA',
            'Em tratativa',
        )

        RESOLVIDA = (
            'RESOLVIDA',
            'Resolvida',
        )

        DESCARTADA = (
            'DESCARTADA',
            'Descartada',
        )

    cancelamento = models.ForeignKey(
        Cancelamento,
        on_delete=models.CASCADE,
        related_name='pendencias',
    )

    tipo = models.CharField(
        'Tipo',
        max_length=30,
        choices=Tipo.choices,
    )

    descricao = models.TextField(
        'Descrição',
        blank=True,
    )

    valor = models.DecimalField(
        'Valor',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    status = models.CharField(
        'Status',
        max_length=20,
        choices=StatusPendencia.choices,
        default=StatusPendencia.ABERTA,
    )

    data_prevista = models.DateField(
        'Data prevista',
        null=True,
        blank=True,
    )

    resolvida_em = models.DateTimeField(
        'Resolvida em',
        null=True,
        blank=True,
    )

    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pendencias_criadas',
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = 'Pendência'
        verbose_name_plural = 'Pendências'
        ordering = ['criado_em']

    def __str__(self):
        return (
            f'{self.get_tipo_display()} — '
            f'{self.cancelamento.ticket_arion}'
        )

    def marcar_resolvida(self):
        self.status = self.StatusPendencia.RESOLVIDA
        self.resolvida_em = timezone.now()

        self.save(
            update_fields=[
                'status',
                'resolvida_em',
            ]
        )


# ---------------------------------------------------------------------------
# Histórico geral de atividades
# ---------------------------------------------------------------------------
class HistoricoCancelamento(models.Model):

    class Tipo(models.TextChoices):
        CRIACAO = (
            'CRIACAO',
            'Criação',
        )

        APROPRIACAO = (
            'APROPRIACAO',
            'Apropriação',
        )

        LIBERACAO = (
            'LIBERACAO',
            'Liberação',
        )

        TRANSFERENCIA = (
            'TRANSFERENCIA',
            'Transferência de responsável',
        )

        ALTERACAO_STATUS = (
            'ALTERACAO_STATUS',
            'Alteração de status',
        )

        MUDANCA_FILA = (
            'MUDANCA_FILA',
            'Mudança de fila',
        )

        OBSERVACAO = (
            'OBSERVACAO',
            'Observação adicionada',
        )

        PENDENCIA_CRIADA = (
            'PENDENCIA_CRIADA',
            'Pendência criada',
        )

        PENDENCIA_RESOLVIDA = (
            'PENDENCIA_RESOLVIDA',
            'Pendência resolvida',
        )

        VALOR_ALTERADO = (
            'VALOR_ALTERADO',
            'Valor alterado',
        )

        CONCLUSAO = (
            'CONCLUSAO',
            'Conclusão',
        )

        EDICAO = (
            'EDICAO',
            'Edição de dados',
        )

    cancelamento = models.ForeignKey(
        Cancelamento,
        on_delete=models.CASCADE,
        related_name='atividades',
    )

    tipo = models.CharField(
        'Tipo',
        max_length=30,
        choices=Tipo.choices,
    )

    descricao = models.TextField(
        'Descrição',
    )

    realizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = 'Histórico'
        verbose_name_plural = 'Históricos'
        ordering = ['criado_em']

    def __str__(self):
        return (
            f'{self.get_tipo_display()} — '
            f'{self.cancelamento.ticket_arion} — '
            f'{self.criado_em:%d/%m/%Y %H:%M}'
        )
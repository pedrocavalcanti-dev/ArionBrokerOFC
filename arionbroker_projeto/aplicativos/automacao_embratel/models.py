from django.db import models
from django.utils import timezone


# ══════════════════════════════════════════════════════════════
#  ENUMS / STATUS
# ══════════════════════════════════════════════════════════════

class StatusProcessamentoEmbratel(models.TextChoices):
    """
    Status INTERNO de processamento da tarefa (não confundir com
    status_portal, que é o status vindo do Modos Web).
    """
    NOVO = 'NOVO', 'Novo'
    PENDENTE_ENVIO = 'PENDENTE_ENVIO', 'Pendente de envio'
    ENVIANDO = 'ENVIANDO', 'Enviando'
    ENVIADO = 'ENVIADO', 'E-mail enviado'
    REVISAO = 'REVISAO', 'Revisão'
    ERRO = 'ERRO', 'Erro'
    IGNORADO = 'IGNORADO', 'Ignorado'
    FINALIZADO = 'FINALIZADO', 'Finalizado no portal'


class OrigemColetaEmbratel(models.TextChoices):
    MANUAL = 'MANUAL', 'Manual'
    AUTOMATICO = 'AUTOMATICO', 'Automático'


class StatusExecucaoEmbratel(models.TextChoices):
    EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em andamento'
    SUCESSO = 'SUCESSO', 'Sucesso'
    SUCESSO_COM_ERROS = 'SUCESSO_COM_ERROS', 'Sucesso com erros'
    FALHA = 'FALHA', 'Falha'


# ══════════════════════════════════════════════════════════════
#  TAREFA EMBRATEL
# ══════════════════════════════════════════════════════════════

class TarefaEmbratel(models.Model):
    """
    Representa uma tarefa coletada do módulo de Recuperação do
    portal Modos Web (Embratel).
    """

    # --- Identificação no portal ---------------------------------
    id_portal = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='ID no portal',
        help_text='Identificador único da tarefa no Modos Web. Primeira barreira contra duplicidade.',
    )
    id_processo = models.CharField(max_length=50, blank=True, null=True, verbose_name='ID do processo')
    id_workflow = models.CharField(max_length=50, blank=True, null=True, verbose_name='ID do workflow')
    id_tarefa_anterior = models.CharField(max_length=50, blank=True, null=True, verbose_name='ID da tarefa anterior')

    # --- Dados do portal --------------------------------------------
    status_portal = models.CharField(max_length=100, blank=True, null=True, verbose_name='Status no portal')
    tipo_tarefa = models.CharField(max_length=100, blank=True, null=True, verbose_name='Tipo de tarefa')
    cliente = models.CharField(max_length=255, blank=True, null=True)
    provedor = models.CharField(max_length=100, blank=True, null=True)
    designacao = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    circuito = models.CharField(max_length=100, blank=True, null=True)
    projeto = models.CharField(max_length=255, blank=True, null=True)
    sintoma = models.CharField(max_length=255, blank=True, null=True)
    descricao = models.TextField(blank=True, null=True)
    dados_tecnicos = models.JSONField(blank=True, null=True, help_text='Payload técnico bruto/estruturado da tarefa.')

    # --- Datas do portal ----------------------------------------------
    data_criacao_portal = models.DateTimeField(blank=True, null=True)
    data_atualizacao_portal = models.DateTimeField(blank=True, null=True)
    data_finalizacao_portal = models.DateTimeField(blank=True, null=True)

    # --- SLA / aging ----------------------------------------------------
    dentro_sla = models.BooleanField(blank=True, null=True)
    aging_minutos = models.IntegerField(blank=True, null=True)

    # --- Acesso -----------------------------------------------------------
    url_tarefa = models.URLField(max_length=500, blank=True, null=True)

    # --- Controle interno de processamento --------------------------------
    status_processamento = models.CharField(
        max_length=20,
        choices=StatusProcessamentoEmbratel.choices,
        default=StatusProcessamentoEmbratel.NOVO,
        db_index=True,
    )
    data_coleta = models.DateTimeField(blank=True, null=True)
    data_envio = models.DateTimeField(blank=True, null=True)
    origem_coleta = models.CharField(
        max_length=20,
        choices=OrigemColetaEmbratel.choices,
        blank=True,
        null=True,
    )
    coletado_por = models.CharField(max_length=150, blank=True, null=True)
    enviado_por = models.CharField(max_length=150, blank=True, null=True)
    erro_processamento = models.TextField(blank=True, null=True)
    tentativas = models.PositiveIntegerField(default=0)

    # --- Metadados -----------------------------------------------------
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tarefa Embratel'
        verbose_name_plural = 'Tarefas Embratel'
        ordering = ['-data_criacao_portal', '-criado_em']
        indexes = [
            models.Index(fields=['status_processamento']),
            models.Index(fields=['designacao']),
        ]

    def __str__(self):
        return f'Tarefa {self.id_portal} — {self.cliente or "sem cliente"}'

    def marcar_erro(self, mensagem):
        self.status_processamento = StatusProcessamentoEmbratel.ERRO
        self.erro_processamento = mensagem
        self.tentativas = models.F('tentativas') + 1
        self.save(update_fields=['status_processamento', 'erro_processamento', 'tentativas', 'atualizado_em'])

    def marcar_enviado(self, enviado_por=None):
        self.status_processamento = StatusProcessamentoEmbratel.ENVIADO
        self.data_envio = timezone.now()
        if enviado_por:
            self.enviado_por = enviado_por
        self.save(update_fields=['status_processamento', 'data_envio', 'enviado_por', 'atualizado_em'])


# ══════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO DO ROBÔ
# ══════════════════════════════════════════════════════════════

class ConfiguracaoRoboEmbratel(models.Model):
    """
    Configuração única (singleton) controlando o comportamento
    do robô Embratel. Usado para pausar/retomar sem mexer em código.
    """

    ativo = models.BooleanField(default=True)
    intervalo_minutos = models.PositiveIntegerField(default=5)

    ultima_execucao = models.DateTimeField(blank=True, null=True)
    ultimo_sucesso = models.DateTimeField(blank=True, null=True)
    ultima_falha = models.DateTimeField(blank=True, null=True)

    alterado_por = models.CharField(max_length=150, blank=True, null=True)
    alterado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração do Robô Embratel'
        verbose_name_plural = 'Configuração do Robô Embratel'

    def __str__(self):
        return f'Configuração Embratel — {"Ativo" if self.ativo else "Pausado"}'

    def save(self, *args, **kwargs):
        # Garante padrão singleton (sempre pk=1)
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config


# ══════════════════════════════════════════════════════════════
#  EXECUÇÃO DO ROBÔ (histórico de ciclos)
# ══════════════════════════════════════════════════════════════

class ExecucaoRoboEmbratel(models.Model):
    """
    Registra cada ciclo executado pelo robô (manual ou automático).
    """

    iniciado_em = models.DateTimeField(default=timezone.now)
    finalizado_em = models.DateTimeField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=StatusExecucaoEmbratel.choices,
        default=StatusExecucaoEmbratel.EM_ANDAMENTO,
    )

    origem = models.CharField(
        max_length=20,
        choices=OrigemColetaEmbratel.choices,
        blank=True,
        null=True,
    )
    executor = models.CharField(max_length=150, blank=True, null=True)

    tarefas_encontradas = models.PositiveIntegerField(default=0)
    tarefas_novas = models.PositiveIntegerField(default=0)
    tarefas_atualizadas = models.PositiveIntegerField(default=0)
    emails_enviados = models.PositiveIntegerField(default=0)

    erros = models.JSONField(blank=True, null=True, default=list)
    duracao_segundos = models.FloatField(blank=True, null=True)

    class Meta:
        verbose_name = 'Execução do Robô Embratel'
        verbose_name_plural = 'Execuções do Robô Embratel'
        ordering = ['-iniciado_em']

    def __str__(self):
        return f'Execução {self.id} — {self.status} ({self.iniciado_em:%d/%m/%Y %H:%M})'

    def finalizar(self, status, erros=None):
        self.finalizado_em = timezone.now()
        self.status = status
        if erros:
            self.erros = erros
        if self.iniciado_em:
            self.duracao_segundos = (self.finalizado_em - self.iniciado_em).total_seconds()
        self.save()


# ══════════════════════════════════════════════════════════════
#  HISTÓRICO DE MUDANÇAS DA TAREFA (opcional)
# ══════════════════════════════════════════════════════════════

class HistoricoTarefaEmbratel(models.Model):
    """
    Guarda mudanças relevantes de uma tarefa ao longo do tempo.
    Útil para auditoria — opcional, pode ser desativado se não for
    necessário nas primeiras fases.
    """

    tarefa = models.ForeignKey(
        TarefaEmbratel,
        on_delete=models.CASCADE,
        related_name='historico',
    )
    status_anterior = models.CharField(max_length=100, blank=True, null=True)
    status_novo = models.CharField(max_length=100, blank=True, null=True)
    dados_anteriores = models.JSONField(blank=True, null=True)
    dados_novos = models.JSONField(blank=True, null=True)
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico de Tarefa Embratel'
        verbose_name_plural = 'Históricos de Tarefas Embratel'
        ordering = ['-registrado_em']

    def __str__(self):
        return f'Histórico da tarefa {self.tarefa.id_portal} em {self.registrado_em:%d/%m/%Y %H:%M}'
from django.db import models
from aplicativos.core_broker.models import Projeto

import re
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone


class KpiOtrs(models.Model):
    """
    Armazena o valor atual de cada KPI do dashboard OTRS.
    Atualizado a cada 1 minuto pelo scraper de KPIs.
    """

    kpi_id = models.CharField(max_length=50, unique=True, db_index=True)
    titulo = models.CharField(max_length=200)
    grupo = models.CharField(max_length=200, default='', blank=True)
    valor = models.IntegerField(default=0)
    brad_por_operadora = models.JSONField(default=dict, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    coletado_ok = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'KPI OTRS'
        verbose_name_plural = 'KPIs OTRS'
        ordering = ['grupo', 'titulo']

    def __str__(self):
        return f'[{self.grupo}] {self.titulo} = {self.valor}'


class ConfiguracaoSLA(models.Model):
    """
    Prazo de SLA configurado por operadora + projeto.
    Editável pelo Django Admin. Suporta minutos, horas ou dias.
    """
    UNIDADES_CHOICES = [
        ('minutos', 'Minutos'),
        ('horas', 'Horas'),
        ('dias', 'Dias'),
    ]

    operadora_slug = models.CharField(max_length=50, db_index=True)
    projeto_slug   = models.CharField(max_length=50, db_index=True)

    sla_valor = models.PositiveIntegerField(
        default=5,
        help_text='Valor numérico do prazo de SLA (combine com a unidade abaixo).'
    )
    sla_unidade = models.CharField(
        max_length=10,
        choices=UNIDADES_CHOICES,
        default='dias',
    )

    criado_em     = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de SLA'
        verbose_name_plural = 'Configurações de SLA'
        unique_together = ('operadora_slug', 'projeto_slug')
        ordering = ['operadora_slug', 'projeto_slug']

    def duracao_em_segundos(self):
        """Converte sla_valor + sla_unidade num total de segundos. Usado no cálculo de % restante."""
        if self.sla_unidade == 'minutos':
            return self.sla_valor * 60
        elif self.sla_unidade == 'horas':
            return self.sla_valor * 3600
        return self.sla_valor * 86400

    def __str__(self):
        return f'{self.operadora_slug}/{self.projeto_slug} — {self.sla_valor} {self.sla_unidade}'


class Chamado(models.Model):
    """
    Chamado cadastrado manualmente enquanto não há acesso ao banco do OTRS.
    Data de abertura é automática (auto_now_add) e o analista é sempre
    o usuário logado no momento do cadastro.
    """

    STATUS_CHOICES = [
        ('aberto',        'Em Aberto'),
        ('resolvido',     'Resolvido'),
        ('atendimento',   'Em atendimento pela ISP'),
        ('pendente',      'Pendente financeira'),
        ('ag_visita',     'AG. VISITA TECNICA'),
        ('analise',       'Em analise pelo POS VENDAS'),
        ('troca',         'Troca de titularidade'),
        ('cancelamento',  'Cancelamento do Link'),
        ('aguardando',    'Aguardando validação'),
        ('cgnat',         'CGNAT'),
        ('tunel',         'Túneis'),
        ('massiva',       'Massiva'),
    ]

    operadora_slug = models.CharField(max_length=50, db_index=True)
    projeto_slug   = models.CharField(max_length=50, db_index=True)

    # Identificador próprio do cliente — label muda conforme o projeto (BRAD/SIGLA/CI)
    id_personalizado = models.CharField(max_length=50, blank=True, default='')

    ticket_arion = models.CharField(max_length=50)

    # URL do chamado no OTRS.
    # Alterado para CharField para aceitar links copiados sem 'https://' ou textos soltos sem travar o form.
    url_ticket = models.CharField(max_length=500, blank=True, default='')

    designacao   = models.CharField(max_length=150)
    isp          = models.CharField(max_length=100, blank=True, default='')
    contato      = models.CharField(max_length=150, blank=True, default='')
    local        = models.CharField(max_length=150, blank=True, default='')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aberto')
    obs    = models.TextField(blank=True, default='')

    # Grava a hora certa automaticamente; no template exibimos só dd/mm/aaaa
    data_abertura = models.DateTimeField(auto_now_add=True)

    analista = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chamados_registrados',
        help_text='Usuário logado no momento do cadastro.'
    )

    criado_em     = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Chamado'
        verbose_name_plural = 'Chamados'
        ordering = ['-data_abertura']
        indexes = [
            models.Index(fields=['operadora_slug', 'projeto_slug']),
        ]

    def __str__(self):
        return f'{self.ticket_arion} — {self.designacao}'


class FiltroProjeto(models.Model):
    """
    Filtro ÚNICO e COMPARTILHADO por operadora + projeto.
    Não é mais por usuário: quem mudar, muda pra todo mundo que acessar
    aquele projeto, e o valor fica salvo no banco até alguém alterar de novo
    (sobrevive a F5, logout, outro navegador, reinício do servidor, etc).
    """
    operadora_slug = models.CharField(max_length=50, db_index=True)
    projeto_slug   = models.CharField(max_length=50, db_index=True)

    # Estado salvo dos botões e inputs
    status = models.CharField(max_length=50, default='aberto')
    busca  = models.CharField(max_length=200, blank=True, default='')
    aging  = models.CharField(max_length=20, blank=True, default='')

    atualizado_em  = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='filtros_projetos_alterados',
        help_text='Último usuário que alterou o filtro (apenas informativo).'
    )

    class Meta:
        verbose_name = 'Filtro do Projeto'
        verbose_name_plural = 'Filtros dos Projetos'
        # Garante que existe apenas UM registro de filtro por operadora+projeto (compartilhado)
        unique_together = ('operadora_slug', 'projeto_slug')

    def __str__(self):
        return f'Filtro compartilhado — {self.operadora_slug}/{self.projeto_slug}'


# ==============================================================================
# MÓDULO RREIP - REINCIDÊNCIAS
# ==============================================================================

class Reincidencia(models.Model):
    FILA_CHOICES = [
        ("TRATAMENTO", "Reincidências para Tratamento"),
        ("MONITORAMENTO", "Monitoramento RREIP"),
        ("FINALIZADO", "Finalizado"),
    ]

    STATUS_CHOICES = [
        ("NOVO", "Novo"),
        ("EM_ANALISE", "Em análise"),
        ("EM_TRATATIVA", "Em tratativa"),
        ("AGUARDANDO_ISP", "Aguardando ISP"),
        ("AGUARDANDO_CLIENTE", "Aguardando cliente"),
        ("AGUARDANDO_TICKET_MONITORAMENTO", "Aguardando ticket de monitoramento"),
        ("MONITORANDO", "Em monitoramento"),
        ("REINCIDIU", "Reincidiu novamente"),
        ("CONCLUIDO", "Concluído"),
        ("DESCARTADO", "Finalizado sem monitoramento"),
    ]

    CLASSIFICACAO_CHOICES = [
        ("PENDENTE", "Pendente de classificação"),
        ("REINCIDENCIA_CONFIRMADA", "Reincidência confirmada"),
        ("MASSIVA", "Massiva"),
        ("FALSO_POSITIVO", "Falso positivo"),
        ("FALHA_ISOLADA", "Falha isolada"),
        ("DUPLICADO", "Registro duplicado"),
        ("NAO_SE_APLICA", "Não se aplica"),
    ]

    # Campos de Classificação da Triagem
    classificacao = models.CharField(
        max_length=30, 
        choices=CLASSIFICACAO_CHOICES, 
        default="PENDENTE"
    )
    motivo_classificacao = models.TextField(blank=True, default="")

    # Campos Legados (Mantidos para retrocompatibilidade. Serão migrados gradualmente para os campos de origem)
    ticket_atual = models.CharField(max_length=50, unique=True, db_index=True)
    url_ticket = models.CharField(max_length=500, blank=True, default="")
    data_ticket = models.DateTimeField(null=True, blank=True)
    
    # 1. Ticket de Origem (Chamado original tratado)
    ticket_origem = models.CharField(max_length=50, blank=True, default="", db_index=True)
    url_ticket_origem = models.CharField(max_length=500, blank=True, default="")
    data_ticket_origem = models.DateTimeField(null=True, blank=True)

    # 2. Ticket de Monitoramento (Segundo chamado para a fila REINCIDENTES do OTRS)
    ticket_monitoramento = models.CharField(max_length=50, blank=True, default="", db_index=True)
    url_ticket_monitoramento = models.CharField(max_length=500, blank=True, default="")
    data_ticket_monitoramento = models.DateTimeField(null=True, blank=True)
    
    designacao = models.CharField(max_length=150, db_index=True)
    designacao_normalizada = models.CharField(max_length=150, db_index=True, blank=True)
    
    cliente = models.CharField(max_length=150, blank=True, default="")
    projeto = models.CharField(max_length=150, blank=True, default="")
    
    identificador_projeto = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Identificador do projeto: BRAD, CI, SIGLA ou equivalente.",
    )
    
    operadora = models.CharField(max_length=150, blank=True, default="")
    isp = models.CharField(max_length=150, blank=True, default="")
    
    fila = models.CharField(max_length=20, choices=FILA_CHOICES, default="TRATAMENTO")
    status = models.CharField(max_length=35, choices=STATUS_CHOICES, default="NOVO")
    quantidade_reincidencias = models.PositiveIntegerField(default=1)
    
    # Campos de Análise
    motivo_identificado = models.TextField(blank=True, default="")
    causa_raiz = models.TextField(blank=True, default="")
    acao_realizada = models.TextField(blank=True, default="")
    acao_preventiva = models.TextField(blank=True, default="")
    conclusao = models.TextField(blank=True, default="")
    
    # Controle de Envio de E-mail de Monitoramento
    email_monitoramento_enviado = models.BooleanField(default=False)
    data_envio_monitoramento = models.DateTimeField(null=True, blank=True)
    email_monitoramento_enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emails_monitoramento_rreip_enviados"
    )
    email_monitoramento_destinatarios = models.TextField(blank=True, default="")

    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reincidencias_responsaveis"
    )
    
    chamado = models.ForeignKey(
        Chamado,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reincidencias"
    )

    data_encerramento_origem = models.DateTimeField(null=True, blank=True)
    data_inicio_monitoramento = models.DateTimeField(null=True, blank=True)
    data_fim_monitoramento = models.DateTimeField(null=True, blank=True)
    data_finalizacao = models.DateTimeField(null=True, blank=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Reincidência"
        verbose_name_plural = "Reincidências"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(
                fields=["fila", "status"],
                name="rreip_fila_status_idx",
            ),
            models.Index(
                fields=["operadora", "projeto"],
                name="rreip_oper_proj_idx",
            ),
            models.Index(
                fields=["designacao_normalizada", "data_ticket_origem"],
                name="rreip_design_dtorig_idx",
            ),
            models.Index(
                fields=["classificacao"],
                name="rreip_classificacao_idx",
            ),
            models.Index(
                fields=["ticket_origem"],
                name="rreip_ticket_origem_idx",
            ),
            models.Index(
                fields=["ticket_monitoramento"],
                name="rreip_ticket_mon_idx",
            ),
        ]

    def get_identificador_label(self):
        projeto = (self.projeto or "").strip().lower()
        operadora = (self.operadora or "").strip().lower()

        if "bradesco" in projeto:
            return "BRAD"
        
        projetos_sigla = ["mcdonalds", "mc donalds", "mcdonald's", "arcos dourados"]
        for p in projetos_sigla:
            if p in projeto:
                return "SIGLA"
                
        return "CI"

    def get_identificador_formatado(self):
        if not self.identificador_projeto:
            return ""
        return f"{self.get_identificador_label()}: {self.identificador_projeto}"

    def normalizar_designacao(self):
        """Remove espaços extras, caracteres especiais e converte para maiúsculas."""
        if not self.designacao:
            return ""
        # Mantém apenas letras e números, converte para maiúsculo
        valor_limpo = re.sub(r'[^a-zA-Z0-9]', '', self.designacao)
        return valor_limpo.upper()

    def analise_completa(self):
        """Retorna True quando todos os campos obrigatórios da análise estão preenchidos."""
        return all([
            self.motivo_identificado.strip(),
            self.causa_raiz.strip(),
            self.acao_realizada.strip(),
            self.acao_preventiva.strip(),
            self.conclusao.strip()
        ])

    def pode_mover_para_monitoramento(self):
        """(Legado/Alias) Valida se os campos obrigatórios da análise estão preenchidos."""
        return self.analise_completa()

    def pode_solicitar_monitoramento(self):
        """Valida se o analista já pode gerar a solicitação de abertura do ticket de monitoramento."""
        return (
            self.classificacao == "REINCIDENCIA_CONFIRMADA"
            and self.analise_completa()
            and self.fila == "TRATAMENTO"
            and self.fila != "FINALIZADO"
        )

    def preparar_solicitacao_monitoramento(self, usuario=None):
        """Prepara o registro informando que a análise terminou e o e-mail será enviado."""
        if not self.pode_solicitar_monitoramento():
            raise ValueError("Registro não atende aos critérios para solicitar monitoramento.")
        
        self.status = "AGUARDANDO_TICKET_MONITORAMENTO"
        self.save()

        if usuario:
            self.historico.create(
                tipo_evento="SOLICITACAO_MONITORAMENTO",
                descricao="Solicitação de monitoramento preparada.",
                usuario=usuario
            )

    def registrar_ticket_monitoramento(self, ticket, url="", data=None, usuario=None):
        """Registra o segundo ticket originado no OTRS para a fila REINCIDENTES."""
        if not ticket:
            raise ValueError("É obrigatório informar o número do ticket de monitoramento.")
        
        self.ticket_monitoramento = ticket
        self.url_ticket_monitoramento = url
        self.data_ticket_monitoramento = data or timezone.now()
        self.save()

        if usuario:
            self.historico.create(
                tipo_evento="TICKET_MONITORAMENTO_REGISTRADO",
                descricao=f"Ticket de monitoramento {ticket} registrado no sistema.",
                usuario=usuario,
                ticket_relacionado=ticket
            )

    def pode_iniciar_monitoramento(self):
        """Valida se todas as exigências (inclusive segundo ticket) estão prontas para contagem de prazo."""
        return (
            self.classificacao == "REINCIDENCIA_CONFIRMADA"
            and self.analise_completa()
            and bool(self.ticket_monitoramento.strip())
            and self.fila == "TRATAMENTO"
        )

    def iniciar_monitoramento(self, usuario=None):
        """Inicia os 30 dias de monitoramento propriamente dito."""
        if not self.pode_iniciar_monitoramento():
            raise ValueError("Preencha todos os campos da análise e garanta que o ticket de monitoramento está inserido antes de iniciar.")
        
        self.fila = "MONITORAMENTO"
        self.status = "MONITORANDO"
        self.data_inicio_monitoramento = timezone.now()
        self.data_fim_monitoramento = self.data_inicio_monitoramento + timedelta(days=30)
        self.save()
        
        if usuario:
            self.historico.create(
                tipo_evento="MONITORAMENTO_INICIADO",
                descricao="Chamado movido para a fila de monitoramento por 30 dias.",
                usuario=usuario
            )

    def concluir_monitoramento(self, usuario=None):
        """Finaliza com sucesso após os 30 dias de monitoramento."""
        self.fila = "FINALIZADO"
        self.status = "CONCLUIDO"
        self.data_finalizacao = timezone.now()
        self.save()
        
        if usuario:
            self.historico.create(
                tipo_evento="CONCLUIDO",
                descricao="Período de monitoramento de 30 dias concluído com sucesso.",
                usuario=usuario
            )

    def finalizar_triagem(self, classificacao, motivo="", usuario=None):
        """Descarta o registro enviando-o para a fila FINALIZADO em casos onde não há monitoramento."""
        classificacoes_permitidas = ["MASSIVA", "FALSO_POSITIVO", "FALHA_ISOLADA", "DUPLICADO", "NAO_SE_APLICA"]
        
        if classificacao not in classificacoes_permitidas:
            raise ValueError(f"Classificação não permitida para este método. Use: {', '.join(classificacoes_permitidas)}")
            
        self.classificacao = classificacao
        self.motivo_classificacao = motivo
        self.fila = "FINALIZADO"
        self.status = "DESCARTADO"
        self.data_finalizacao = timezone.now()
        self.save()

        if usuario:
            self.historico.create(
                tipo_evento="TRIAGEM_FINALIZADA",
                descricao=f"Triagem finalizada sem monitoramento. Classificação: {self.get_classificacao_display()}.",
                usuario=usuario
            )

    def registrar_nova_reincidencia(self, novo_ticket, usuario=None):
        """Registra uma ocorrência caso ocorra falha dentro dos 30 dias (ou tratativas pendentes)."""
        # Futuramente, os tickets adicionais serão armazenados em uma model própria de Ocorrencias
        self.fila = "TRATAMENTO"
        self.status = "REINCIDIU"
        self.quantidade_reincidencias += 1
        
        self.data_inicio_monitoramento = None
        self.data_fim_monitoramento = None
        self.save()

        if usuario:
            self.historico.create(
                tipo_evento="REINCIDIU",
                descricao=f"Nova reincidência identificada através do ticket {novo_ticket}.",
                usuario=usuario,
                ticket_relacionado=novo_ticket,
                dados_novos={"novo_ticket": novo_ticket, "quantidade_reincidencias": self.quantidade_reincidencias}
            )

    def dias_restantes_monitoramento(self):
        if self.fila != "MONITORAMENTO" or not self.data_fim_monitoramento:
            return 0
        restantes = (self.data_fim_monitoramento - timezone.now()).days
        return max(0, restantes)

    def esta_monitorando(self):
        return self.fila == "MONITORAMENTO" and self.status == "MONITORANDO"

    def save(self, *args, **kwargs):
        self.designacao_normalizada = self.normalizar_designacao()
        super().save(*args, **kwargs)

    def __str__(self):
        # Prioriza o ticket de monitoramento, depois o de origem e por último o legado.
        ticket = self.ticket_monitoramento or self.ticket_origem or self.ticket_atual
        return f"{ticket} - {self.designacao}"


class HistoricoReincidencia(models.Model):
    TIPO_EVENTO_CHOICES = [
        ("CRIADO", "Registro criado"),
        ("APROPRIADO", "Responsável assumiu"),
        ("LIBERADO", "Responsável liberou"),
        ("TRANSFERIDO", "Responsável transferido"),
        ("STATUS_ALTERADO", "Status alterado"),
        ("ANALISE_ATUALIZADA", "Análise atualizada"),
        ("MOVIDO_MONITORAMENTO", "Movido para monitoramento"),
        ("REINCIDIU", "Reincidiu novamente"),
        ("CONCLUIDO", "Monitoramento concluído"),
        ("OBSERVACAO", "Observação adicionada"),
        # Novos tipos de evento adicionados para o fluxo atual:
        ("CLASSIFICADO", "Classificação alterada"),
        ("TRIAGEM_FINALIZADA", "Triagem finalizada"),
        ("SOLICITACAO_MONITORAMENTO", "Solicitação de monitoramento preparada"),
        ("TICKET_MONITORAMENTO_REGISTRADO", "Ticket de monitoramento registrado"),
        ("MONITORAMENTO_INICIADO", "Monitoramento iniciado"),
        ("DADOS_EDITADOS", "Dados editados"),
    ]

    reincidencia = models.ForeignKey(
        Reincidencia,
        on_delete=models.CASCADE,
        related_name="historico"
    )
    tipo_evento = models.CharField(max_length=35, choices=TIPO_EVENTO_CHOICES)
    descricao = models.TextField(blank=True, default="")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    ticket_relacionado = models.CharField(max_length=50, blank=True, default="")
    
    dados_anteriores = models.JSONField(default=dict, blank=True)
    dados_novos = models.JSONField(default=dict, blank=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Histórico de Reincidência"
        verbose_name_plural = "Históricos de Reincidência"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.reincidencia.ticket_atual} - {self.get_tipo_evento_display()}"
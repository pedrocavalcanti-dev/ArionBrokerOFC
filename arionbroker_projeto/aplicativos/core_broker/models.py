from django.db import models


# ── CHOICES ───────────────────────────────────────────────────
class StatusEnvio(models.TextChoices):
    NOVO       = 'NOVO',       'Novo'
    ENVIADO    = 'ENVIADO',    'Aguardando OTRS'         # Antes era 'Enviado'
    REVISAO    = 'REVISAO',    'Revisão'
    REGISTRADO = 'REGISTRADO', 'Concluído'               # Antes era 'Registrado no Broker'
    ERRO_OTRS  = 'ERRO_OTRS',  'Erro — Ticket não encontrado'


class Projeto(models.TextChoices):
    CORREIOS   = 'CORREIOS',   'Correios (ECT)'
    CAIXA      = 'CAIXA',      'Caixa Econômica (CEF)'
    BB         = 'BB',         'Banco do Brasil'
    CARREFOUR  = 'CARREFOUR',  'Carrefour'
    DIVERSOS   = 'DIVERSOS',   'Diversos / Revisão'


class OrigemAcao(models.TextChoices):
    MANUAL     = 'MANUAL',     'Manual'
    AUTOMATICA = 'AUTOMATICA', 'Automática'


# ── MAPEAMENTO CLIENTE → PROJETO ──────────────────────────────
MAPA_CLIENTE_PROJETO = {
    'ECT':        Projeto.CORREIOS,
    'CEF':        Projeto.CAIXA,
    'BCO BRASIL': Projeto.BB,
    'CARREFOUR':  Projeto.CARREFOUR,
}


def identificar_projeto(nome_cliente: str) -> str:
    if not nome_cliente:
        return Projeto.DIVERSOS
    cliente_upper = nome_cliente.strip().upper()
    return MAPA_CLIENTE_PROJETO.get(cliente_upper, Projeto.DIVERSOS)


# ── MODEL PRINCIPAL ───────────────────────────────────────────
class TicketREC(models.Model):

    rec_id           = models.CharField(max_length=20, unique=True, verbose_name='Número da REC')
    designacao_claro = models.CharField(max_length=100, blank=True, verbose_name='Designação Claro')
    bl_dados         = models.CharField(max_length=100, blank=True, verbose_name='BL / Designação Operadora')
    cliente          = models.CharField(max_length=100, blank=True, verbose_name='Cliente')

    # Campo onde fica o chamado que o scraper da claro captura
    chamado_operadora = models.CharField(max_length=50, blank=True, verbose_name='Chamado Arion')

    # Campo onde vai o número do Ticket que o otrs_scraper vai achar
    ticket_otrs = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name='Ticket OTRS',
        db_index=True,
    )

    data_abertura_portal    = models.DateTimeField(null=True, blank=True, verbose_name='Data de Abertura (Portal)')
    data_registro_operadora = models.DateTimeField(null=True, blank=True, verbose_name='Data de Registro (Operadora)')
    data_atualizacao_portal = models.DateTimeField(null=True, blank=True, verbose_name='Data de Atualização (Portal)')

    projeto = models.CharField(
        max_length=20,
        choices=Projeto.choices,
        default=Projeto.DIVERSOS,
        verbose_name='Projeto',
    )

    status_interface = models.CharField(max_length=20, blank=True, verbose_name='Status Interface')
    status_equip     = models.CharField(max_length=20, blank=True, verbose_name='Status Equipamento')
    sintoma          = models.TextField(blank=True, verbose_name='Sintoma')

    screenshot = models.ImageField(
        upload_to='screenshots/',
        null=True,
        blank=True,
        verbose_name='Screenshot',
    )

    status_envio = models.CharField(
        max_length=15,
        choices=StatusEnvio.choices,
        default=StatusEnvio.NOVO,
        verbose_name='Status de Envio',
        db_index=True,
    )
    data_coleta = models.DateTimeField(auto_now_add=True, verbose_name='Data de Coleta')
    data_envio  = models.DateTimeField(null=True, blank=True, verbose_name='Data de Envio')

    origem_coleta = models.CharField(
        max_length=15,
        choices=OrigemAcao.choices,
        default=OrigemAcao.MANUAL,
        verbose_name='Origem da Coleta',
    )
    origem_envio = models.CharField(
        max_length=15,
        choices=OrigemAcao.choices,
        blank=True,
        default='',
        verbose_name='Origem do Envio',
    )
    coletado_por = models.CharField(max_length=150, blank=True, verbose_name='Coletado por')
    enviado_por  = models.CharField(max_length=150, blank=True, verbose_name='Enviado por')

    class Meta:
        verbose_name        = 'Ticket REC'
        verbose_name_plural = 'Tickets REC'
        ordering = ['-data_abertura_portal', '-data_coleta']

    def __str__(self):
        return f'REC {self.rec_id} — {self.projeto} [{self.status_envio}]'

    @property
    def ja_enviado(self):
        return self.status_envio in [StatusEnvio.ENVIADO, StatusEnvio.REGISTRADO]

    @property
    def em_revisao(self):
        return self.status_envio == StatusEnvio.REVISAO

    @property
    def concluido(self):
        return self.status_envio == StatusEnvio.REGISTRADO

    @property
    def erro_otrs(self):
        return self.status_envio == StatusEnvio.ERRO_OTRS

    @property
    def interface_down(self):
        return (self.status_interface or '').lower() == 'down'

    @property
    def tem_chamado_arion(self):
        return bool(self.chamado_operadora and self.chamado_operadora.strip())

    @property
    def tem_ticket_otrs(self):
        return bool(self.ticket_otrs and self.ticket_otrs.strip())

    @property
    def data_principal_ordenacao(self):
        return (
            self.data_abertura_portal or
            self.data_registro_operadora or
            self.data_atualizacao_portal or
            self.data_coleta
        )

    @classmethod
    def criar_ou_ignorar(cls, dados: dict):
        rec_id  = dados.get('rec_id', '').strip()
        cliente = dados.get('cliente', '').strip()

        if not rec_id:
            return None, False

        projeto = identificar_projeto(cliente)
        status  = StatusEnvio.NOVO

        obj, criado = cls.objects.get_or_create(
            rec_id=rec_id,
            defaults={
                'designacao_claro':        dados.get('designacao_claro', ''),
                'bl_dados':                dados.get('bl_dados', ''),
                'cliente':                 cliente,
                'projeto':                 projeto,
                'status_interface':        dados.get('status_interface', ''),
                'status_equip':            dados.get('status_equip', ''),
                'sintoma':                 dados.get('sintoma', ''),
                'status_envio':            status,
                'chamado_operadora':       dados.get('chamado_operadora', ''),
                'ticket_otrs':             '',
                'data_abertura_portal':    dados.get('data_abertura_portal'),
                'data_registro_operadora': dados.get('data_registro_operadora'),
                'data_atualizacao_portal': dados.get('data_atualizacao_portal'),
                'origem_coleta':           dados.get('origem_coleta', OrigemAcao.MANUAL),
                'coletado_por':            dados.get('coletado_por', ''),
            },
        )
        return obj, criado


# ── CONFIGURAÇÃO DO ROBÔ ──────────────────────────────────────
class ConfiguracaoRobo(models.Model):
    ativo = models.BooleanField(
        default=True,
        verbose_name='Modo Automático Ativo',
    )
    alterado_por = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Último alterado por',
    )
    alterado_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Alterado em',
    )

    class Meta:
        verbose_name        = 'Configuração do Robô'
        verbose_name_plural = 'Configuração do Robô'

    def __str__(self):
        return f'Robô — {"ATIVO" if self.ativo else "PAUSADO"}'

    @classmethod
    def get_ou_criar(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
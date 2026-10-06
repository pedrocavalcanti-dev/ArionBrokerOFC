from django.contrib import admin
from django.utils.html import format_html

from .models import (
    TarefaEmbratel,
    ConfiguracaoRoboEmbratel,
    ExecucaoRoboEmbratel,
    HistoricoTarefaEmbratel,
)


# ══════════════════════════════════════════════════════════════
#  TAREFA EMBRATEL
# ══════════════════════════════════════════════════════════════

@admin.register(TarefaEmbratel)
class TarefaEmbratelAdmin(admin.ModelAdmin):
    list_display = (
        'id_portal',
        'cliente',
        'designacao',
        'status_portal',
        'status_processamento',
        'dentro_sla',
        'tentativas',
        'data_coleta',
        'data_envio',
        'link_portal',
    )
    list_display_links = ('id_portal', 'cliente')
    list_filter = (
        'status_processamento',
        'status_portal',
        'origem_coleta',
        'dentro_sla',
        'provedor',
    )
    search_fields = (
        'id_portal',
        'id_processo',
        'id_workflow',
        'designacao',
        'cliente',
        'circuito',
        'projeto',
    )
    date_hierarchy = 'data_coleta'
    ordering = ('-data_criacao_portal',)
    list_per_page = 50

    readonly_fields = (
        'criado_em',
        'atualizado_em',
        'link_portal',
    )

    fieldsets = (
        ('Identificação no portal', {
            'fields': (
                'id_portal', 'id_processo', 'id_workflow', 'id_tarefa_anterior',
                'link_portal',
            )
        }),
        ('Dados da tarefa', {
            'fields': (
                'status_portal', 'tipo_tarefa', 'cliente', 'provedor',
                'designacao', 'circuito', 'projeto', 'sintoma', 'descricao',
                'dados_tecnicos',
            )
        }),
        ('Datas do portal', {
            'fields': (
                'data_criacao_portal', 'data_atualizacao_portal', 'data_finalizacao_portal',
            )
        }),
        ('SLA', {
            'fields': ('dentro_sla', 'aging_minutos')
        }),
        ('Processamento interno', {
            'fields': (
                'status_processamento', 'origem_coleta',
                'data_coleta', 'data_envio',
                'coletado_por', 'enviado_por',
                'tentativas', 'erro_processamento',
            )
        }),
        ('Metadados', {
            'fields': ('criado_em', 'atualizado_em'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Portal')
    def link_portal(self, obj):
        if obj.url_tarefa:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">Abrir no Modos Web ↗</a>',
                obj.url_tarefa,
            )
        return '—'

    actions = ['marcar_para_revisao']

    @admin.action(description='Marcar selecionadas para revisão')
    def marcar_para_revisao(self, request, queryset):
        from .models import StatusProcessamentoEmbratel
        atualizadas = queryset.update(status_processamento=StatusProcessamentoEmbratel.REVISAO)
        self.message_user(request, f'{atualizadas} tarefa(s) marcada(s) para revisão.')


# ══════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO DO ROBÔ (singleton)
# ══════════════════════════════════════════════════════════════

@admin.register(ConfiguracaoRoboEmbratel)
class ConfiguracaoRoboEmbratelAdmin(admin.ModelAdmin):
    list_display = (
        'ativo',
        'intervalo_minutos',
        'ultima_execucao',
        'ultimo_sucesso',
        'ultima_falha',
        'alterado_por',
        'alterado_em',
    )
    readonly_fields = ('alterado_em',)

    def has_add_permission(self, request):
        # Singleton: impede criar mais de um registro
        return not ConfiguracaoRoboEmbratel.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Nunca permite excluir a configuração
        return False


# ══════════════════════════════════════════════════════════════
#  EXECUÇÕES DO ROBÔ
# ══════════════════════════════════════════════════════════════

@admin.register(ExecucaoRoboEmbratel)
class ExecucaoRoboEmbratelAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'status',
        'origem',
        'executor',
        'iniciado_em',
        'finalizado_em',
        'duracao_segundos',
        'tarefas_encontradas',
        'tarefas_novas',
        'tarefas_atualizadas',
        'emails_enviados',
    )
    list_filter = ('status', 'origem')
    search_fields = ('executor',)
    date_hierarchy = 'iniciado_em'
    ordering = ('-iniciado_em',)
    readonly_fields = (
        'iniciado_em', 'finalizado_em', 'duracao_segundos',
        'tarefas_encontradas', 'tarefas_novas', 'tarefas_atualizadas',
        'emails_enviados', 'erros',
    )

    def has_add_permission(self, request):
        # Execuções são criadas apenas pelo robô/serviço, não manualmente
        return False


# ══════════════════════════════════════════════════════════════
#  HISTÓRICO DE TAREFAS
# ══════════════════════════════════════════════════════════════

@admin.register(HistoricoTarefaEmbratel)
class HistoricoTarefaEmbratelAdmin(admin.ModelAdmin):
    list_display = ('tarefa', 'status_anterior', 'status_novo', 'registrado_em')
    list_filter = ('status_novo',)
    search_fields = ('tarefa__id_portal', 'tarefa__cliente')
    date_hierarchy = 'registrado_em'
    ordering = ('-registrado_em',)
    readonly_fields = ('tarefa', 'status_anterior', 'status_novo', 'dados_anteriores', 'dados_novos', 'registrado_em')

    def has_add_permission(self, request):
        # Histórico é gerado automaticamente, não manualmente
        return False
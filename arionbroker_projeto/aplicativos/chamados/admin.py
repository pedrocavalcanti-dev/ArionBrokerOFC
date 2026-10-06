from datetime import timedelta
from django.contrib import admin, messages
from django.utils import timezone
from .models import (
    KpiOtrs,
    ConfiguracaoSLA,
    Chamado,
    Reincidencia,
    HistoricoReincidencia,
)

@admin.register(KpiOtrs)
class KpiOtrsAdmin(admin.ModelAdmin):
    list_display   = ('kpi_id', 'titulo', 'grupo', 'valor', 'coletado_ok', 'atualizado_em')
    list_filter    = ('grupo', 'coletado_ok')
    search_fields  = ('kpi_id', 'titulo', 'grupo')
    ordering       = ('grupo', 'titulo')


@admin.register(ConfiguracaoSLA)
class ConfiguracaoSLAAdmin(admin.ModelAdmin):
    list_display   = ('operadora_slug', 'projeto_slug', 'sla_valor', 'sla_unidade', 'atualizado_em')
    list_filter    = ('operadora_slug', 'sla_unidade')
    search_fields  = ('operadora_slug', 'projeto_slug')
    ordering       = ('operadora_slug', 'projeto_slug')


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    list_display     = (
        'ticket_arion', 'designacao', 'operadora_slug', 'projeto_slug',
        'status', 'analista', 'data_abertura',
    )
    list_filter      = ('operadora_slug', 'projeto_slug', 'status')
    search_fields    = ('ticket_arion', 'designacao', 'isp', 'local', 'id_personalizado')
    date_hierarchy   = 'data_abertura'
    ordering         = ('-data_abertura',)
    readonly_fields  = ('data_abertura', 'criado_em', 'atualizado_em')
    autocomplete_fields = ('analista',)


@admin.register(Reincidencia)
class ReincidenciaAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_atual",
        "designacao",
        "identificador_formatado",
        "cliente",
        "operadora",
        "projeto",
        "fila",
        "status",
        "quantidade_reincidencias",
        "responsavel",
        "data_inicio_monitoramento",
        "data_fim_monitoramento",
        "atualizado_em",
    )
    list_filter = (
        "fila",
        "status",
        "operadora",
        "projeto",
        "responsavel",
    )
    search_fields = (
        "ticket_atual",
        "designacao",
        "designacao_normalizada",
        "identificador_projeto",
        "cliente",
        "projeto",
        "operadora",
        "isp",
    )
    ordering = ("-criado_em",)
    readonly_fields = (
        "designacao_normalizada",
        "criado_em",
        "atualizado_em",
        "data_inicio_monitoramento",
        "data_fim_monitoramento",
    )
    autocomplete_fields = (
        "responsavel",
        "chamado",
    )
    date_hierarchy = "criado_em"

    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "ticket_atual",
                    "url_ticket",
                    "designacao",
                    "designacao_normalizada",
                    "cliente",
                    "projeto",
                    "identificador_projeto",
                    "operadora",
                    "isp",
                    "chamado",
                )
            },
        ),
        (
            "Fluxo RREIP",
            {
                "fields": (
                    "fila",
                    "status",
                    "quantidade_reincidencias",
                    "responsavel",
                )
            },
        ),
        (
            "Análise",
            {
                "fields": (
                    "motivo_identificado",
                    "causa_raiz",
                    "acao_preventiva",
                    "conclusao",
                )
            },
        ),
        (
            "Datas",
            {
                "fields": (
                    "data_ticket",
                    "data_inicio_monitoramento",
                    "data_fim_monitoramento",
                    "criado_em",
                    "atualizado_em",
                )
            },
        ),
    )

    actions = (
        "marcar_como_tratamento",
        "marcar_como_monitoramento",
        "marcar_como_concluido",
    )

    @admin.display(
        description="Identificador",
        ordering="identificador_projeto",
    )
    def identificador_formatado(self, obj):
        return obj.get_identificador_formatado() or "—"

    @admin.action(description="Mover selecionadas para Tratamento")
    def marcar_como_tratamento(self, request, queryset):
        queryset.update(
            fila="TRATAMENTO",
            status="EM_ANALISE",
            data_inicio_monitoramento=None,
            data_fim_monitoramento=None
        )
        self.message_user(request, "Registros movidos para Tratamento com sucesso.", messages.SUCCESS)

    @admin.action(description="Mover selecionadas para Monitoramento RREIP")
    def marcar_como_monitoramento(self, request, queryset):
        movidos = 0
        for obj in queryset:
            if obj.pode_mover_para_monitoramento():
                obj.fila = "MONITORAMENTO"
                obj.status = "MONITORANDO"
                obj.data_inicio_monitoramento = timezone.now()
                obj.data_fim_monitoramento = timezone.now() + timedelta(days=30)
                obj.save()
                movidos += 1
        
        if movidos > 0:
            self.message_user(request, f"{movidos} registro(s) movido(s) para Monitoramento RREIP.", messages.SUCCESS)
        else:
            self.message_user(request, "Nenhum registro movido. Verifique se as análises estão preenchidas.", messages.WARNING)

    @admin.action(description="Marcar selecionadas como concluídas")
    def marcar_como_concluido(self, request, queryset):
        queryset.update(
            fila="CONCLUIDO",
            status="CONCLUIDO"
        )
        self.message_user(request, "Registros marcados como concluídos com sucesso.", messages.SUCCESS)


@admin.register(HistoricoReincidencia)
class HistoricoReincidenciaAdmin(admin.ModelAdmin):
    list_display = (
        'reincidencia',
        'tipo_evento',
        'usuario',
        'ticket_relacionado',
        'criado_em',
    )
    list_filter = (
        'tipo_evento',
        'criado_em',
    )
    search_fields = (
        'reincidencia__ticket_atual',
        'reincidencia__designacao',
        'descricao',
        'ticket_relacionado',
        'usuario__username',
        'usuario__first_name',
        'usuario__last_name',
    )
    ordering = ('-criado_em',)
    readonly_fields = (
        'reincidencia',
        'tipo_evento',
        'descricao',
        'usuario',
        'ticket_relacionado',
        'dados_anteriores',
        'dados_novos',
        'criado_em',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
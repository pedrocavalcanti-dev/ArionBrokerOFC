from django.contrib import admin
from .models import Cancelamento, HistoricoFila


class HistoricoFilaInline(admin.TabularInline):
    model = HistoricoFila
    extra = 0
    readonly_fields = ('fila_origem', 'fila_destino', 'movido_por', 'movido_em')
    can_delete = False


@admin.register(Cancelamento)
class CancelamentoAdmin(admin.ModelAdmin):
    list_display = ('ticket_arion', 'cliente_final', 'fila', 'status', 'atendente', 'criado_em')
    list_filter = ('fila', 'status', 'cliente')
    search_fields = ('ticket_arion', 'designacao_circuito', 'cliente_final', 'protocolo')
    inlines = [HistoricoFilaInline]
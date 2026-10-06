from django.contrib import admin
from .models import TicketREC


@admin.register(TicketREC)
class TicketRECAdmin(admin.ModelAdmin):
    list_display  = ('rec_id', 'cliente', 'projeto', 'bl_dados', 'status_interface', 'status_envio', 'data_coleta')
    list_filter   = ('status_envio', 'projeto', 'status_interface')
    search_fields = ('rec_id', 'bl_dados', 'designacao_claro', 'cliente')
    readonly_fields = ('data_coleta', 'data_envio')
    ordering      = ('-data_coleta',)
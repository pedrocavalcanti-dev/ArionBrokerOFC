from django.contrib import admin
from .models import ConfigEmailProjeto

@admin.register(ConfigEmailProjeto)
class ConfigEmailProjetoAdmin(admin.ModelAdmin):
    list_display = ('projeto', 'destinatarios', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('destinatarios', 'cc')
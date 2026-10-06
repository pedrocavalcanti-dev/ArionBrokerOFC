from django.apps import AppConfig

class ChamadosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'aplicativos.chamados'  # <--- Tem que ter o "aplicativos." na frente
    verbose_name = 'Gestão de Projetos e Chamados'
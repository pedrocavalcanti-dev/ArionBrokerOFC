from django.apps import AppConfig

class AutenticacaoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'aplicativos.autenticacao' # <-- O SEGREDO ESTÁ AQUI (adicione o aplicativos.)
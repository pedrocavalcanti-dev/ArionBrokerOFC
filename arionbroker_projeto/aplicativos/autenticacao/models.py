# aplicativos/autenticacao/models.py

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Cargo(models.TextChoices):
    ADMIN = 'ADMIN', 'Administrador'
    OPERADOR = 'OPERADOR', 'Operador'


class VisualizacaoCancelamentos(models.TextChoices):
    """
    Preferência persistente do filtro "Visualizar" do módulo Cancelamentos.

    Os valores foram mantidos compatíveis com os parâmetros já utilizados
    pelo módulo de Cancelamentos:
    - todos
    - meus
    - sem_responsavel
    """
    TODOS = 'todos', 'Todos'
    MEUS = 'meus', 'Meus Cancelamentos'
    SEM_RESPONSAVEL = 'sem_responsavel', 'Sem responsável'


class UserPreference(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='preferencias',
    )

    tema = models.CharField(
        max_length=10,
        default='dark',
        verbose_name='Tema',
    )

    sidebar_aberta = models.BooleanField(
        default=True,
        verbose_name='Sidebar Aberta',
    )

    cargo = models.CharField(
        max_length=10,
        choices=Cargo.choices,
        default=Cargo.OPERADOR,
        verbose_name='Cargo',
    )

    cancelamentos_visualizar = models.CharField(
        max_length=20,
        choices=VisualizacaoCancelamentos.choices,
        default=VisualizacaoCancelamentos.TODOS,
        verbose_name='Visualização padrão de Cancelamentos',
    )

    class Meta:
        verbose_name = 'Preferência de Usuário'
        verbose_name_plural = 'Preferências de Usuários'

    def __str__(self):
        return f'{self.user.username} — {self.cargo}'

    @property
    def is_admin(self):
        return self.cargo == Cargo.ADMIN


@receiver(post_save, sender=User)
def criar_user_preference(sender, instance, created, **kwargs):
    """
    Garante que todo usuário tenha UserPreference.

    Regras existentes preservadas:
    - superusuário / staff nasce como ADMIN;
    - usuário comum nasce como OPERADOR;
    - não rebaixa um ADMIN definido manualmente;
    - cria preferências caso um usuário antigo ainda não possua registro.

    A preferência de Cancelamentos usa o default "todos".
    """
    if created:
        cargo_inicial = (
            Cargo.ADMIN
            if (instance.is_superuser or instance.is_staff)
            else Cargo.OPERADOR
        )

        UserPreference.objects.create(
            user=instance,
            cargo=cargo_inicial,
        )

        return

    try:
        prefs = instance.preferencias

        if (
            (instance.is_superuser or instance.is_staff)
            and not prefs.is_admin
        ):
            prefs.cargo = Cargo.ADMIN
            prefs.save(update_fields=['cargo'])

    except UserPreference.DoesNotExist:
        cargo_inicial = (
            Cargo.ADMIN
            if (instance.is_superuser or instance.is_staff)
            else Cargo.OPERADOR
        )

        UserPreference.objects.create(
            user=instance,
            cargo=cargo_inicial,
        )

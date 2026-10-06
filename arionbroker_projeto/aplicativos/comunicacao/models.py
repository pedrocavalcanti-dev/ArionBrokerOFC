from django.db import models

from aplicativos.core_broker.models import Projeto


class ConfigEmailProjeto(models.Model):

    projeto = models.CharField(
        max_length=20,
        choices=Projeto.choices,
        unique=True,
        verbose_name="Projeto",
    )

    destinatarios = models.TextField(
        help_text=(
            "Separe múltiplos e-mails "
            "por vírgula ou ponto e vírgula."
        ),
        verbose_name="Destinatários (Para)",
    )

    cc = models.TextField(
        blank=True,
        help_text=(
            "Opcional. Separe múltiplos e-mails "
            "por vírgula ou ponto e vírgula."
        ),
        verbose_name="Cópia (CC)",
    )

    ativo = models.BooleanField(
        default=True,
        verbose_name="Ativo",
    )

    class Meta:
        verbose_name = "Configuração de E-mail por Projeto"
        verbose_name_plural = (
            "Configurações de E-mail por Projeto"
        )

    def __str__(self):

        return (
            f"Configuração: "
            f"{self.get_projeto_display()}"
        )

    @staticmethod
    def _separar_emails(valor):

        if not valor:
            return []

        valor = valor.replace(";", ",")

        return [
            email.strip()
            for email in valor.split(",")
            if email.strip()
        ]

    def lista_destinatarios(self):

        return self._separar_emails(
            self.destinatarios
        )

    def lista_cc(self):

        return self._separar_emails(
            self.cc
        )
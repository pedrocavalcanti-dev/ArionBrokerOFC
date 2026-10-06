from django.core.management.base import BaseCommand
from aplicativos.chamados.models import ConfiguracaoSLA


class Command(BaseCommand):
    help = 'Popula os SLAs padrão de cada projeto conhecido. Não sobrescreve o que já existe (get_or_create).'

    # (operadora_slug, projeto_slug, valor, unidade)
    # Ajuste os valores à vontade depois no Admin — esse seed nunca vai sobrescrever
    # o que você já tiver editado lá.
    PROJETOS = [
        ('claro', 'bradesco',           4,  'horas'),
        ('claro', 'correios',           12, 'horas'),
        ('claro', 'caixa',              2,  'dias'),
        ('claro', 'banco-do-brasil',    5,  'dias'),
        ('claro', 'diversos',           5,  'dias'),
        ('vivo',  'bradesco',           4,  'horas'),
        ('vivo',  'mcdonalds',          24, 'horas'),
        ('vivo',  'lan-to-lan',         2,  'dias'),
        ('algar', 'escolas-conectadas', 7,  'dias'),
    ]

    def handle(self, *args, **options):
        criados    = 0
        existentes = 0

        for op_slug, proj_slug, valor, unidade in self.PROJETOS:
            config, created = ConfiguracaoSLA.objects.get_or_create(
                operadora_slug=op_slug,
                projeto_slug=proj_slug,
                defaults={'sla_valor': valor, 'sla_unidade': unidade},
            )

            if created:
                criados += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  Criado   : {op_slug.upper()} / {proj_slug}  →  {valor} {unidade}'
                ))
            else:
                existentes += 1
                self.stdout.write(self.style.WARNING(
                    f'  Já existe: {op_slug.upper()} / {proj_slug}  →  {config.sla_valor} {config.sla_unidade} (não alterado)'
                ))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Finalizado: {criados} criado(s), {existentes} já existente(s) e preservado(s).'
        ))
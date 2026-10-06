# cancelamentos/migrations/0006_dados_financeiro_para_concluido.py

from django.db import migrations

def migrar_financeiro_para_concluido(apps, schema_editor):
    Cancelamento = apps.get_model('cancelamentos', 'Cancelamento')
    HistoricoCancelamento = apps.get_model('cancelamentos', 'HistoricoCancelamento')

    cancelamentos_legados = Cancelamento.objects.filter(fila='FINANCEIRO')

    for cancelamento in cancelamentos_legados:
        cancelamento.fila = 'CONCLUIDO'

        if cancelamento.status == 'CONCLUIDO_CANCELAMENTO':
            evento_conclusao = HistoricoCancelamento.objects.filter(
                cancelamento_id=cancelamento.id,
                tipo='CONCLUSAO'
            ).order_by('criado_em').first()

            if evento_conclusao:
                cancelamento.concluido_em = evento_conclusao.criado_em
            else:
                cancelamento.concluido_em = None
        else:
            cancelamento.concluido_em = None

        cancelamento.save(update_fields=['fila', 'concluido_em'])


class Migration(migrations.Migration):

    dependencies = [
        # Aponta para a migration de schema que acabamos de criar
        ('cancelamentos', '0005_schema_concluido'), 
    ]

    operations = [
        migrations.RunPython(
            code=migrar_financeiro_para_concluido,
            reverse_code=migrations.RunPython.noop 
        ),
    ]
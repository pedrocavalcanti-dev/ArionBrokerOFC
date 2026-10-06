# cancelamentos/migrations/0005_schema_concluido.py

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        # Aponta exatamente para a última migration que você listou
        ('cancelamentos', '0004_alter_pendenciacancelamento_tipo'), 
    ]

    operations = [
        migrations.AddField(
            model_name='cancelamento',
            name='concluido_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Concluído em'),
        ),
        migrations.AlterField(
            model_name='cancelamento',
            name='fila',
            field=models.CharField(choices=[('PEDIDO', 'Pedido de Cancelamento'), ('SOLICITACAO', 'Solicitação de Cancelamento'), ('PENDENCIA', 'Pendências de Cancelamento'), ('FINANCEIRO', 'Financeiro - Cancelamento'), ('CONCLUIDO', 'Concluídos')], default='PEDIDO', max_length=20, verbose_name='Fila'),
        ),
        migrations.AlterField(
            model_name='historicofila',
            name='fila_origem',
            field=models.CharField(blank=True, choices=[('PEDIDO', 'Pedido de Cancelamento'), ('SOLICITACAO', 'Solicitação de Cancelamento'), ('PENDENCIA', 'Pendências de Cancelamento'), ('FINANCEIRO', 'Financeiro - Cancelamento'), ('CONCLUIDO', 'Concluídos')], max_length=20, null=True, verbose_name='Fila de Origem'),
        ),
        migrations.AlterField(
            model_name='historicofila',
            name='fila_destino',
            field=models.CharField(choices=[('PEDIDO', 'Pedido de Cancelamento'), ('SOLICITACAO', 'Solicitação de Cancelamento'), ('PENDENCIA', 'Pendências de Cancelamento'), ('FINANCEIRO', 'Financeiro - Cancelamento'), ('CONCLUIDO', 'Concluídos')], max_length=20, verbose_name='Fila de Destino'),
        ),
    ]
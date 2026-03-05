from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_add_fallback_channel_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventposition',
            name='allowed_time_blocks',
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    'Deixe em branco para permitir todos os blocos do evento. '
                    'Se preenchido, apenas os blocos selecionados estarão disponíveis para esta posição.'
                ),
                related_name='restricted_positions',
                to='core.timeblock',
                verbose_name='Blocos Permitidos',
            ),
        ),
    ]

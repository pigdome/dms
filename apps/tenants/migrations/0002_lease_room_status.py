import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
        ('rooms', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='lease',
            name='room',
            field=models.ForeignKey(
                blank=True,
                help_text='Room assigned under this lease',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='leases',
                to='rooms.room',
            ),
        ),
        migrations.AddField(
            model_name='lease',
            name='status',
            field=models.CharField(
                choices=[('active', 'Active'), ('ended', 'Ended'), ('pending', 'Pending')],
                default='active',
                max_length=10,
            ),
        ),
    ]

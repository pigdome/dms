from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_initial'),
        ('core', '0002_dormitory_invoice_prefix_userdormitoryrole'),
    ]

    operations = [
        migrations.AddField(
            model_name='bill',
            name='invoice_number',
            field=models.CharField(blank=True, default=None, max_length=30, null=True, unique=True),
        ),
    ]

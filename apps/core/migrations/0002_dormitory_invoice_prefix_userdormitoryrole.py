import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dormitory',
            name='invoice_prefix',
            field=models.CharField(blank=True, help_text='Prefix for invoice numbers, e.g. H01', max_length=5),
        ),
        migrations.CreateModel(
            name='UserDormitoryRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[('superadmin', 'Superadmin'), ('owner', 'Owner'), ('staff', 'Staff'), ('tenant', 'Tenant')],
                    default='staff',
                    max_length=20,
                )),
                ('is_primary', models.BooleanField(default=False)),
                ('dormitory', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.dormitory')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='dormitory_memberships',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'unique_together': {('user', 'dormitory')},
            },
        ),
        migrations.AddField(
            model_name='customuser',
            name='dormitories',
            field=models.ManyToManyField(
                blank=True,
                related_name='members',
                through='core.UserDormitoryRole',
                to='core.dormitory',
            ),
        ),
    ]

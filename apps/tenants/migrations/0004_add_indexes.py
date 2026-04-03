# I6: Migration เพิ่ม db_index บน:
# - Lease.status, Lease.end_date
# - TenantProfile.is_deleted

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_idcard_encryption'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lease',
            name='status',
            field=models.CharField(
                choices=[('active', 'Active'), ('ended', 'Ended'), ('pending', 'Pending')],
                db_index=True,
                default='active',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='lease',
            name='end_date',
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='tenantprofile',
            name='is_deleted',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Soft delete flag (PDPA)',
            ),
        ),
    ]

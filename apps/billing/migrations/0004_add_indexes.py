# I6: Migration เพิ่ม database indexes บน Bill fields ที่ใช้ filter/query บ่อย
# Bill.status, Bill.month, Bill.due_date

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_sms_notification_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bill',
            name='status',
            field=models.CharField(
                choices=[('draft', 'Draft'), ('sent', 'Sent'), ('paid', 'Paid'), ('overdue', 'Overdue')],
                db_index=True,
                default='draft',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='bill',
            name='month',
            field=models.DateField(
                db_index=True,
                help_text='First day of billing month',
            ),
        ),
        migrations.AlterField(
            model_name='bill',
            name='due_date',
            field=models.DateField(db_index=True),
        ),
    ]

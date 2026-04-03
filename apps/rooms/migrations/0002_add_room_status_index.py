# I6: Migration เพิ่ม db_index บน Room.status
# ใช้ filter บ่อยใน generate_bills_for_dormitory() และ room list views

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rooms', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='room',
            name='status',
            field=models.CharField(
                choices=[
                    ('occupied', 'Occupied'),
                    ('vacant', 'Vacant'),
                    ('cleaning', 'Cleaning'),
                    ('maintenance', 'Maintenance'),
                ],
                db_index=True,
                default='vacant',
                max_length=20,
            ),
        ),
    ]

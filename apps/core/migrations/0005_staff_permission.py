# I2: Migration สำหรับ StaffPermission model
# เพิ่ม granular permission matrix สำหรับ staff user

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_add_line_user_id_to_customuser'),
    ]

    operations = [
        migrations.CreateModel(
            name='StaffPermission',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('can_view_billing', models.BooleanField(default=False, help_text='ดูบิลและการชำระเงิน')),
                ('can_record_meter', models.BooleanField(default=False, help_text='บันทึกมิเตอร์น้ำ/ไฟ')),
                ('can_manage_maintenance', models.BooleanField(default=False, help_text='จัดการงานแจ้งซ่อม')),
                ('can_log_parcels', models.BooleanField(default=False, help_text='บันทึกพัสดุ')),
                ('can_view_tenants', models.BooleanField(default=False, help_text='ดูข้อมูลผู้เช่า')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('dormitory', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='staff_permissions',
                    to='core.dormitory',
                )),
                ('user', models.OneToOneField(
                    help_text='Staff user ที่ permission นี้เป็นของ',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='staff_permission',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Staff Permission',
                'verbose_name_plural': 'Staff Permissions',
            },
        ),
    ]

# I5: Migration สำหรับ CustomUser.must_change_password field
# บังคับผู้เช่าเปลี่ยน password เมื่อ login ครั้งแรก

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_staff_permission'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='must_change_password',
            field=models.BooleanField(
                default=False,
                help_text='Force user to change password on next login',
            ),
        ),
    ]

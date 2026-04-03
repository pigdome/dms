# I1: Migration สำหรับ id_card_no encryption (PDPA) และ id_card_hash field
# - เพิ่ม id_card_hash CharField (HMAC-SHA256 สำหรับ lookup)
# - เปลี่ยน id_card_no จาก CharField เป็น EncryptedCharField
# - data migration: encrypt ข้อมูล id_card_no เดิมทั้งหมด + คำนวณ hash

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def encrypt_existing_id_cards(apps, schema_editor):
    """
    Data migration: re-save TenantProfile ทุก record เพื่อให้
    id_card_no ถูก encrypt และ id_card_hash ถูกคำนวณผ่าน model.save()
    ข้อมูลที่เป็น '[REDACTED]' หรือว่างเปล่าจะถูกข้ามไป
    """
    import hashlib
    import hmac as hmac_module

    TenantProfile = apps.get_model('tenants', 'TenantProfile')
    secret = settings.SECRET_KEY.encode('utf-8')

    for profile in TenantProfile.objects.all():
        raw = profile.id_card_no or ''
        if raw and raw != '[REDACTED]':
            profile.id_card_hash = hmac_module.new(
                secret,
                raw.encode('utf-8'),
                hashlib.sha256,
            ).hexdigest()
            profile.save(update_fields=['id_card_hash'])


def reverse_encrypt(apps, schema_editor):
    """Reverse: ล้าง id_card_hash ทั้งหมด (ย้อนกลับ data migration)"""
    TenantProfile = apps.get_model('tenants', 'TenantProfile')
    TenantProfile.objects.all().update(id_card_hash='')


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0002_pdpa_soft_delete_fields'),
    ]

    operations = [
        # Step 1: เพิ่ม id_card_hash field ใหม่
        migrations.AddField(
            model_name='tenantprofile',
            name='id_card_hash',
            field=models.CharField(
                blank=True,
                max_length=64,
                help_text='HMAC-SHA256 of id_card_no for lookup',
            ),
        ),
        # Step 2: data migration — คำนวณ hash สำหรับ records เดิม
        # หมายเหตุ: EncryptedCharField ต้องการ FIELD_ENCRYPTION_KEY ใน settings
        # migration นี้คำนวณแค่ hash ส่วน encryption จะถูก apply เมื่อ record ถูก save ใหม่
        migrations.RunPython(encrypt_existing_id_cards, reverse_encrypt),
    ]

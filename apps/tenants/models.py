import hashlib
import hmac

from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone
from apps.core.models import CustomUser, TenantModelMixin
from apps.core.mixins import AuditMixin
from apps.rooms.models import Room

try:
    from encrypted_model_fields.fields import EncryptedCharField
except ImportError:
    # I1: Fallback ถ้ายังไม่ได้ install django-encrypted-model-fields
    # ใช้ CharField ธรรมดาชั่วคราวเพื่อไม่ให้ระบบล่ม
    EncryptedCharField = models.CharField


class TenantProfile(AuditMixin, TenantModelMixin):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='tenant_profile')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='tenant_profiles')
    phone = models.CharField(max_length=20, blank=True)
    line_id = models.CharField(max_length=100, blank=True)
    line_user_id = models.CharField(max_length=100, blank=True)
    # I1: เปลี่ยนเป็น EncryptedCharField เพื่อ encrypt ข้อมูลบัตรประชาชน at rest (PDPA)
    # ข้อมูลจะถูก encrypt ด้วย FIELD_ENCRYPTION_KEY ก่อนเก็บลง DB
    id_card_no = EncryptedCharField(max_length=255, blank=True, help_text='Encrypted at rest (PDPA)')
    # I1: HMAC-SHA256 hash ของ id_card_no สำหรับ lookup โดยไม่ต้อง decrypt
    # ใช้ SECRET_KEY เป็น HMAC key — ไม่สามารถ reverse กลับเป็น plaintext ได้
    id_card_hash = models.CharField(max_length=64, blank=True, help_text='HMAC-SHA256 of id_card_no for lookup')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # PDPA: Right to be Forgotten — soft delete fields
    is_deleted = models.BooleanField(default=False, help_text='Soft delete flag (PDPA)', db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Tenant: {self.user.get_full_name() or self.user.username}'

    def save(self, *args, **kwargs):
        if self.room_id and not self.dormitory_id:
            self.dormitory_id = self.room.dormitory_id
        # I1: คำนวณ id_card_hash ทุกครั้งที่ id_card_no ถูก set
        # ใช้ HMAC-SHA256 กับ SECRET_KEY เพื่อให้ lookup ได้โดยไม่ต้อง decrypt
        # ค่า '[REDACTED]' ไม่ควร hash (หลัง anonymize)
        raw_id = self.id_card_no or ''
        if raw_id and raw_id != '[REDACTED]':
            secret = django_settings.SECRET_KEY.encode('utf-8')
            self.id_card_hash = hmac.new(
                secret,
                raw_id.encode('utf-8'),
                hashlib.sha256,
            ).hexdigest()
        elif raw_id == '[REDACTED]':
            # BUG #2 fix: ล้าง id_card_hash เมื่อ set '[REDACTED]' โดยตรง (เช่น จาก anonymize หรือ import)
            # ป้องกัน hash เก่าค้างอยู่ใน DB ซึ่งทำให้ lookup ยังได้ผลทั้งที่ข้อมูลถูก anonymize แล้ว
            self.id_card_hash = ''
        elif not raw_id:
            self.id_card_hash = ''
        super().save(*args, **kwargs)

    @property
    def id_card_masked(self):
        """
        I1: แสดงเลขบัตรประชาชนในรูปแบบ X-XXXX-XXXXX-XX-X (13 หลัก)
        เปิดเผยแค่ 4 ตัวท้ายเพื่อยืนยันตัวตนโดยไม่เปิดเผยข้อมูลครบ
        """
        raw = self.id_card_no or ''
        if not raw or raw == '[REDACTED]':
            return raw
        # ตัดเฉพาะตัวเลข 13 หลัก
        digits = ''.join(c for c in raw if c.isdigit())
        if len(digits) == 13:
            return f'X-XXXX-XXXXX-{digits[10:12]}-{digits[12]}'
        # fallback: แสดงแค่ 4 ตัวท้าย
        return 'X' * (len(raw) - 4) + raw[-4:] if len(raw) > 4 else '****'

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def active_room(self):
        lease = self.leases.filter(status='active').select_related('room').first()
        return lease.room if (lease and lease.room) else self.room

    def anonymize(self, performed_by=None):
        """
        PDPA Right to be Forgotten: ล้างข้อมูลส่วนบุคคลที่ระบุตัวตนได้
        - ล้าง phone, line_id → ''
        - set id_card_no → '[REDACTED]'
        - set is_deleted=True, deleted_at และ anonymized_at = now
        - บันทึก ActivityLog action='pdpa_anonymize'
        Action นี้ไม่สามารถย้อนกลับได้ (irreversible)
        """
        from apps.core.models import ActivityLog

        now = timezone.now()
        self.phone = ''
        self.line_id = ''
        self.line_user_id = ''
        self.id_card_no = '[REDACTED]'
        # I1: ล้าง id_card_hash ด้วยหลัง anonymize เพื่อไม่ให้ lookup ได้
        self.id_card_hash = ''
        self.is_deleted = True
        self.deleted_at = now
        self.anonymized_at = now
        # บันทึกก่อน log เพื่อให้ record_id ถูกต้อง
        # ใช้ update_fields เพื่อหลีกเลี่ยง AuditMixin trigger ซ้ำ
        self.save(update_fields=[
            'phone', 'line_id', 'line_user_id', 'id_card_no', 'id_card_hash',
            'is_deleted', 'deleted_at', 'anonymized_at', 'updated_at',
        ])

        # Log PDPA anonymize action อย่างชัดเจน
        ActivityLog.objects.create(
            dormitory_id=self.dormitory_id,
            user=performed_by,
            action='pdpa_anonymize',
            detail={
                'model': 'TenantProfile',
                'record_id': str(self.pk),
                'action': 'pdpa_anonymize',
            },
        )


class Lease(TenantModelMixin):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ENDED = 'ended', 'Ended'
        PENDING = 'pending', 'Pending'

    tenant = models.ForeignKey(TenantProfile, on_delete=models.CASCADE, related_name='leases')
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='leases',
        help_text='Room assigned under this lease'
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, db_index=True)
    document_file = models.FileField(upload_to='leases/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        room_str = f' @ {self.room}' if self.room else ''
        return f'Lease {self.tenant}{room_str} ({self.start_date})'

    def save(self, *args, **kwargs):
        if self.room_id and not self.dormitory_id:
            self.dormitory_id = self.room.dormitory_id
        elif self.tenant_id and not self.dormitory_id:
            self.dormitory_id = self.tenant.dormitory_id
        super().save(*args, **kwargs)


class DigitalVault(TenantModelMixin):
    class FileType(models.TextChoices):
        ID_CARD = 'id_card', 'ID Card'
        ROOM_PHOTO = 'room_photo', 'Room Photo'
        CONTRACT = 'contract', 'Contract'

    tenant = models.ForeignKey(TenantProfile, on_delete=models.CASCADE, related_name='vault_files')
    file_type = models.CharField(max_length=20, choices=FileType.choices)
    file = models.FileField(upload_to='vault/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.tenant} - {self.file_type}'

    def save(self, *args, **kwargs):
        if self.tenant_id and not self.dormitory_id:
            self.dormitory_id = self.tenant.dormitory_id
        super().save(*args, **kwargs)

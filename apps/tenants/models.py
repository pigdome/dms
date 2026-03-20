from django.db import models
from apps.core.models import CustomUser, TenantModelMixin
from apps.rooms.models import Room


class TenantProfile(TenantModelMixin):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='tenant_profile')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='tenant_profiles')
    phone = models.CharField(max_length=20, blank=True)
    line_id = models.CharField(max_length=100, blank=True)
    line_user_id = models.CharField(max_length=100, blank=True)
    id_card_no = models.CharField(max_length=255, blank=True, help_text='Encrypted at rest (PDPA)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Tenant: {self.user.get_full_name() or self.user.username}'

    def save(self, *args, **kwargs):
        if self.room_id and not self.dormitory_id:
            self.dormitory_id = self.room.dormitory_id
        super().save(*args, **kwargs)

    @property
    def active_room(self):
        lease = self.leases.filter(status='active').select_related('room').first()
        return lease.room if (lease and lease.room) else self.room


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
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
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

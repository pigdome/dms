from django.db import models
from apps.core.models import CustomUser
from apps.rooms.models import Room


class TenantProfile(models.Model):
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

    @property
    def dormitory(self):
        active = self.leases.filter(status='active').select_related('room__floor__building__dormitory').first()
        if active and active.room:
            return active.room.floor.building.dormitory
        return self.room.floor.building.dormitory if self.room else None

    @property
    def active_room(self):
        lease = self.leases.filter(status='active').select_related('room').first()
        return lease.room if (lease and lease.room) else self.room


class Lease(models.Model):
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


class DigitalVault(models.Model):
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

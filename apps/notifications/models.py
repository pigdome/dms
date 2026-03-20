from django.db import models
from apps.core.models import Dormitory, CustomUser, TenantModelMixin
from apps.rooms.models import Room
from apps.billing.models import Bill


class Parcel(TenantModelMixin):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='parcels')
    photo = models.ImageField(upload_to='parcels/')
    carrier = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    logged_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Parcel for Room {self.room.number} - {self.carrier}'

    def save(self, *args, **kwargs):
        if self.room_id and not getattr(self, 'dormitory_id', None):
            self.dormitory_id = self.room.dormitory_id
        super().save(*args, **kwargs)


class Broadcast(TenantModelMixin):
    class AudienceType(models.TextChoices):
        ALL = 'all', 'All Tenants'
        BUILDING = 'building', 'By Building'
        FLOOR = 'floor', 'By Floor'

    audience_type = models.CharField(max_length=20, choices=AudienceType.choices, default=AudienceType.ALL)
    audience_ref = models.CharField(max_length=100, blank=True, help_text='Building name or Floor number if targeted')
    title = models.CharField(max_length=200)
    body = models.TextField()
    attachment = models.FileField(upload_to='broadcasts/', blank=True, null=True)
    sent_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        dorm_name = self.dormitory.name if getattr(self, 'dormitory_id', None) else "No Dorm"
        return f'Broadcast: {self.title} ({dorm_name})'


class DunningLog(TenantModelMixin):
    class TriggerType(models.TextChoices):
        PRE_7D = 'pre_7d', '7 Days Before Due'
        PRE_3D = 'pre_3d', '3 Days Before Due'
        PRE_1D = 'pre_1d', '1 Day Before Due'
        DUE = 'due', 'Due Date'
        POST_1D = 'post_1d', '1 Day Overdue'
        POST_7D = 'post_7d', '7 Days Overdue'
        POST_15D = 'post_15d', '15 Days Overdue'

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='dunning_logs')
    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices)
    sent_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    class Meta:
        unique_together = ['bill', 'trigger_type']
        ordering = ['sent_at']

    def __str__(self):
        return f'Dunning {self.trigger_type} for {self.bill}'

    def save(self, *args, **kwargs):
        if self.bill_id and not getattr(self, 'dormitory_id', None):
            self.dormitory_id = self.bill.dormitory_id
        super().save(*args, **kwargs)

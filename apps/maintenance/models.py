from django.db import models
from apps.core.models import CustomUser
from apps.rooms.models import Room


class MaintenanceTicket(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        IN_PROGRESS = 'in_progress', 'In Progress'
        WAITING_PARTS = 'waiting_parts', 'Waiting for Parts'
        COMPLETED = 'completed', 'Completed'

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='maintenance_tickets')
    reported_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='reported_tickets')
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    technician = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Ticket #{self.pk} - Room {self.room.number} ({self.status})'

    @property
    def dormitory(self):
        return self.room.dormitory


class TicketPhoto(models.Model):
    class Stage(models.TextChoices):
        ISSUE = 'issue', 'Issue'
        COMPLETION = 'completion', 'Completion'

    ticket = models.ForeignKey(MaintenanceTicket, on_delete=models.CASCADE, related_name='photos')
    photo = models.ImageField(upload_to='maintenance/')
    stage = models.CharField(max_length=20, choices=Stage.choices)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class TicketStatusHistory(models.Model):
    ticket = models.ForeignKey(MaintenanceTicket, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=20, choices=MaintenanceTicket.Status.choices)
    changed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    note = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['changed_at']

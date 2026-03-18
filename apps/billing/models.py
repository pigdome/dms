from django.db import models, transaction
from apps.core.models import Dormitory
from apps.rooms.models import Room


class BillingSettings(models.Model):
    class BillDay(models.IntegerChoices):
        FIRST = 1, '1st'
        FIFTH = 5, '5th'
        TENTH = 10, '10th'
        TWENTY_FIFTH = 25, '25th'

    dormitory = models.OneToOneField(Dormitory, on_delete=models.CASCADE, related_name='billing_settings')
    bill_day = models.IntegerField(choices=BillDay.choices, default=BillDay.FIRST)
    grace_days = models.PositiveIntegerField(default=5)
    elec_rate = models.DecimalField(max_digits=6, decimal_places=2, default=7.00)
    water_rate = models.DecimalField(max_digits=6, decimal_places=2, default=18.00)
    tmr_api_key = models.CharField(max_length=255, blank=True)
    tmr_secret = models.CharField(max_length=255, blank=True)
    dunning_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f'Billing Settings - {self.dormitory.name}'


class Bill(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SENT = 'sent', 'Sent'
        PAID = 'paid', 'Paid'
        OVERDUE = 'overdue', 'Overdue'

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bills')
    month = models.DateField(help_text='First day of billing month')
    invoice_number = models.CharField(max_length=30, unique=True, null=True, blank=True, default=None)
    base_rent = models.DecimalField(max_digits=10, decimal_places=2)
    water_amt = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    elec_amt = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['room', 'month']
        ordering = ['-month']

    def save(self, *args, **kwargs):
        if not self.invoice_number and self.room_id:
            dorm = self.room.floor.building.dormitory
            prefix = dorm.invoice_prefix or 'INV'
            ym = self.month.strftime('%y%m')
            with transaction.atomic():
                seq = (
                    Bill.objects.select_for_update()
                    .filter(room__floor__building__dormitory=dorm, month=self.month)
                    .exclude(pk=self.pk)
                    .count()
                ) + 1
                self.invoice_number = f'{prefix}-{ym}-{seq:03d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Bill {self.room} - {self.month.strftime("%Y-%m")} ({self.status})'

    @property
    def dormitory(self):
        return self.room.dormitory


class Payment(models.Model):
    bill = models.OneToOneField(Bill, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    tmr_ref = models.CharField(max_length=255, unique=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    webhook_payload = models.JSONField(default=dict)
    paid_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Payment {self.bill} - {self.amount}'

from decimal import Decimal

from django.db import models, transaction
from apps.core.models import Dormitory, TenantModelMixin, UUIDEncoder
from apps.core.mixins import AuditMixin
from apps.rooms.models import Room


class BillingSettings(TenantModelMixin):
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

    # SMS notification channel settings
    class NotificationChannel(models.TextChoices):
        LINE_ONLY = 'line_only', 'LINE Only'
        SMS_ONLY = 'sms_only', 'SMS Only'
        BOTH = 'both', 'LINE + SMS'

    notification_channel = models.CharField(
        max_length=20,
        choices=NotificationChannel.choices,
        default=NotificationChannel.LINE_ONLY,
    )
    sms_enabled = models.BooleanField(default=False)
    sms_api_key = models.CharField(max_length=255, blank=True)
    # Sender ID ที่แสดงบนมือถือผู้รับ — จำกัด 11 ตัวอักษรตามมาตรฐาน GSM
    sms_sender_name = models.CharField(max_length=11, blank=True)

    def __str__(self):
        return f'Billing Settings - {self.dormitory.name if self.dormitory_id else "No Dorm"}'


class ExtraChargeType(TenantModelMixin):
    """
    Owner-defined recurring charge types, e.g. Internet, Parking, Equipment rental.
    Acts as a catalog — each dormitory can have its own list.
    """
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    default_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Bill(AuditMixin, TenantModelMixin):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SENT = 'sent', 'Sent'
        PAID = 'paid', 'Paid'
        OVERDUE = 'overdue', 'Overdue'

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bills')
    # Link to the MeterReading that generated the utility amounts (nullable for manual bills)
    meter_reading = models.ForeignKey(
        'rooms.MeterReading', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bills',
    )
    month = models.DateField(help_text='First day of billing month')
    invoice_number = models.CharField(max_length=30, unique=True, null=True, blank=True, default=None)
    base_rent = models.DecimalField(max_digits=10, decimal_places=2)
    water_amt = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    elec_amt = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_amt = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                     help_text='Sum of BillLineItem amounts (auto-updated by refresh_total)')
    total = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['room', 'month']
        ordering = ['-month']

    # ------------------------------------------------------------------
    # Meter reading snapshot properties (read-through to linked reading)
    # ------------------------------------------------------------------

    @property
    def water_prev(self):
        return self.meter_reading.water_prev if self.meter_reading_id else Decimal('0')

    @property
    def water_curr(self):
        return self.meter_reading.water_curr if self.meter_reading_id else Decimal('0')

    @property
    def elec_prev(self):
        return self.meter_reading.elec_prev if self.meter_reading_id else Decimal('0')

    @property
    def elec_curr(self):
        return self.meter_reading.elec_curr if self.meter_reading_id else Decimal('0')

    @property
    def water_units(self):
        return self.water_curr - self.water_prev

    @property
    def elec_units(self):
        return self.elec_curr - self.elec_prev

    # ------------------------------------------------------------------
    # Total management
    # ------------------------------------------------------------------

    def refresh_total(self):
        """Recompute other_amt from line_items and update total. Call after adding/removing BillLineItems."""
        from django.db.models import Sum
        self.other_amt = self.line_items.aggregate(s=Sum('amount'))['s'] or Decimal('0')
        self.total = self.base_rent + self.water_amt + self.elec_amt + self.other_amt
        self.save(update_fields=['other_amt', 'total', 'updated_at'])

    def save(self, *args, **kwargs):
        if self.room_id and not getattr(self, 'dormitory_id', None):
            self.dormitory_id = self.room.dormitory_id

        if not self.invoice_number and self.room_id:
            dorm = self.dormitory or self.room.floor.building.dormitory
            prefix = dorm.invoice_prefix or 'INV'
            ym = self.month.strftime('%y%m')
            with transaction.atomic():
                seq = (
                    Bill.unscoped_objects.select_for_update()
                    .filter(room__floor__building__dormitory=dorm, month=self.month)
                    .exclude(pk=self.pk)
                    .count()
                ) + 1
                self.invoice_number = f'{prefix}-{ym}-{seq:03d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Bill {self.room} - {self.month.strftime("%Y-%m")} ({self.status})'


class BillLineItem(TenantModelMixin):
    """
    An extra charge line item attached to a bill.
    Created from ExtraChargeType catalog or added manually.
    After adding/removing line items, call bill.refresh_total().
    """
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='line_items')
    charge_type = models.ForeignKey(
        ExtraChargeType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bill_items',
    )
    # Snapshot of charge name at billing time (so renaming ExtraChargeType won't change history)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f'{self.description}: ฿{self.amount}'

    def save(self, *args, **kwargs):
        if self.bill_id and not getattr(self, 'dormitory_id', None):
            self.dormitory_id = self.bill.dormitory_id
        super().save(*args, **kwargs)


class Payment(AuditMixin, TenantModelMixin):
    bill = models.OneToOneField(Bill, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    tmr_ref = models.CharField(max_length=255, unique=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    webhook_payload = models.JSONField(default=dict, encoder=UUIDEncoder)
    paid_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Payment {self.bill} - {self.amount}'

    def save(self, *args, **kwargs):
        if self.bill_id and not getattr(self, 'dormitory_id', None):
            self.dormitory_id = self.bill.dormitory_id
        super().save(*args, **kwargs)

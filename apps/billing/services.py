from decimal import Decimal
from datetime import date, timedelta
import calendar


def calculate_bill(base_rent, water_units, elec_units, water_rate, elec_rate, extra_amt=0):
    """
    Calculate total bill amount.

    Args:
        base_rent:   monthly rent
        water_units: units consumed (curr - prev)
        elec_units:  units consumed (curr - prev)
        water_rate:  rate per unit
        elec_rate:   rate per unit
        extra_amt:   sum of extra charge line items (default 0)
    """
    water_amt = Decimal(str(water_units)) * Decimal(str(water_rate))
    elec_amt = Decimal(str(elec_units)) * Decimal(str(elec_rate))
    other_amt = Decimal(str(extra_amt))
    total = Decimal(str(base_rent)) + water_amt + elec_amt + other_amt
    return {
        'base_rent': Decimal(str(base_rent)),
        'water_amt': water_amt,
        'elec_amt': elec_amt,
        'other_amt': other_amt,
        'total': total,
    }


def calculate_prorated_rent(base_rent, move_in_date, billing_month):
    """Calculate pro-rated rent for partial month occupancy."""
    days_in_month = calendar.monthrange(billing_month.year, billing_month.month)[1]
    if billing_month.month == 12:
        month_end = date(billing_month.year + 1, 1, 1)
    else:
        month_end = date(billing_month.year, billing_month.month + 1, 1)
    month_start = date(billing_month.year, billing_month.month, 1)

    occupied_from = max(move_in_date, month_start)
    days_occupied = (month_end - occupied_from).days
    days_occupied = max(0, min(days_occupied, days_in_month))

    prorated = Decimal(str(base_rent)) * Decimal(days_occupied) / Decimal(days_in_month)
    return prorated.quantize(Decimal('0.01'))


def generate_bills_for_dormitory(dormitory, month: date) -> list:
    """
    Create draft bills for all occupied rooms in *dormitory* for *month*.

    - Skips rooms that already have a bill for this month.
    - Links the latest MeterReading for that month to Bill.meter_reading.
    - Uses water_units / elec_units from the linked MeterReading.
    - Returns the list of newly created Bill objects.
    """
    from django.db import transaction
    from apps.billing.models import Bill, BillingSettings
    from apps.rooms.models import MeterReading, Room

    try:
        settings = dormitory.billing_settings
    except BillingSettings.DoesNotExist:
        return []

    bill_date = date(month.year, month.month, settings.bill_day)
    due_date = bill_date + timedelta(days=settings.grace_days)

    from apps.tenants.models import Lease

    rooms = Room.objects.filter(
        floor__building__dormitory=dormitory,
        status=Room.Status.OCCUPIED,
    )

    created = []
    for room in rooms:
        if Bill.objects.filter(room=room, month=month).exists():
            continue

        meter = (
            MeterReading.unscoped_objects
            .filter(room=room, reading_date__year=month.year, reading_date__month=month.month)
            .order_by('-reading_date')
            .first()
        )

        water_amt = Decimal('0')
        elec_amt = Decimal('0')
        if meter:
            water_amt = Decimal(str(meter.water_units)) * settings.water_rate
            elec_amt = Decimal(str(meter.elec_units)) * settings.elec_rate

        # I3: ตรวจสอบว่า lease ของห้องนี้เริ่มต้นในเดือนที่กำลัง generate bill
        # ถ้า start_date อยู่ในเดือนเดียวกัน → คำนวณ pro-rated rent แทนราคาเต็ม
        base_rent = room.base_rent
        active_lease = (
            Lease.unscoped_objects
            .filter(room=room, status='active')
            .order_by('-start_date')
            .first()
        )
        if active_lease and active_lease.start_date:
            lease_start = active_lease.start_date
            if lease_start.year == month.year and lease_start.month == month.month:
                # ผู้เช่าเข้าอยู่กลางเดือน → คำนวณค่าเช่าตามจำนวนวันที่พักจริง
                base_rent = calculate_prorated_rent(room.base_rent, lease_start, month)

        total = base_rent + water_amt + elec_amt

        with transaction.atomic():
            bill = Bill.objects.create(
                room=room,
                month=month,
                base_rent=base_rent,
                meter_reading=meter,
                water_amt=water_amt,
                elec_amt=elec_amt,
                other_amt=Decimal('0'),
                total=total,
                due_date=due_date,
                status=Bill.Status.DRAFT,
            )
        created.append(bill)

    return created


def mark_overdue_bills() -> int:
    """
    Mark all sent/draft bills whose due_date has passed as overdue.
    Returns the number of bills updated.
    """
    from django.utils import timezone
    from apps.billing.models import Bill

    today = timezone.localdate()
    return Bill.objects.filter(
        status__in=[Bill.Status.DRAFT, Bill.Status.SENT],
        due_date__lt=today,
    ).update(status=Bill.Status.OVERDUE)


def get_dunning_trigger_dates(due_date):
    """Return all dunning trigger dates for a bill."""
    return {
        'pre_7d': due_date - timedelta(days=7),
        'pre_3d': due_date - timedelta(days=3),
        'pre_1d': due_date - timedelta(days=1),
        'due': due_date,
        'post_1d': due_date + timedelta(days=1),
        'post_7d': due_date + timedelta(days=7),
        'post_15d': due_date + timedelta(days=15),
    }

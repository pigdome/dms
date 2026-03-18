"""
Celery tasks for billing automation.

Periodic schedule (configured via Django Celery Beat in admin):
  - generate_monthly_bills_task  → run daily at 00:05
  - mark_overdue_bills_task      → run daily at 00:10
  - check_dunning_task           → run daily at 09:00
"""
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def generate_monthly_bills_task(self):
    """
    Generate bills for dormitories whose bill_day matches today.
    Safe to run daily — skips rooms that already have a bill for the month.
    """
    from datetime import date

    from django.utils import timezone

    from apps.billing.services import generate_bills_for_dormitory
    from apps.core.models import Dormitory

    today = timezone.localdate()
    month = date(today.year, today.month, 1)
    total_created = 0

    for dormitory in Dormitory.objects.prefetch_related('billing_settings'):
        try:
            if dormitory.billing_settings.bill_day != today.day:
                continue
        except Exception:
            continue
        try:
            bills = generate_bills_for_dormitory(dormitory, month)
            total_created += len(bills)
            logger.info('Generated %d bills for %s (%s)', len(bills), dormitory.name, month)
        except Exception as exc:
            logger.error('Bill generation failed for %s: %s', dormitory.name, exc)
            raise self.retry(exc=exc)

    return {'bills_created': total_created, 'date': str(today)}


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def mark_overdue_bills_task(self):
    """Mark all unpaid bills past their due date as overdue."""
    from apps.billing.services import mark_overdue_bills

    try:
        updated = mark_overdue_bills()
        logger.info('Marked %d bills as overdue', updated)
        return {'bills_marked_overdue': updated}
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def check_dunning_task(self):
    """
    Send dunning notifications for unpaid bills at the configured trigger dates.
    Uses DunningLog unique_together to prevent duplicate sends.
    """
    from django.utils import timezone

    from apps.billing.models import Bill
    from apps.billing.services import get_dunning_trigger_dates
    from apps.notifications.models import DunningLog
    from apps.notifications.tasks import send_dunning_notification_task

    today = timezone.localdate()
    sent = 0

    unpaid_bills = Bill.objects.filter(
        status__in=[Bill.Status.SENT, Bill.Status.OVERDUE],
    ).select_related('room__floor__building__dormitory__billing_settings')

    for bill in unpaid_bills:
        try:
            dorm_settings = bill.room.floor.building.dormitory.billing_settings
            if not dorm_settings.dunning_enabled:
                continue
        except Exception:
            continue

        trigger_dates = get_dunning_trigger_dates(bill.due_date)

        for trigger_type, trigger_date in trigger_dates.items():
            if trigger_date != today:
                continue
            if DunningLog.objects.filter(bill=bill, trigger_type=trigger_type).exists():
                continue

            send_dunning_notification_task.delay(bill.pk, trigger_type)
            sent += 1

    return {'dunning_tasks_queued': sent}

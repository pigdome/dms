"""
Celery tasks for notifications (dunning messages, parcel alerts, broadcasts).
Actual delivery channel (LINE Messaging API, SMS, etc.) is plugged in here.
"""
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_dunning_notification_task(self, bill_pk: int, trigger_type: str):
    """
    Send a dunning notification for *bill_pk* at *trigger_type* stage.
    Creates a DunningLog entry to prevent duplicates.
    """
    from apps.billing.models import Bill
    from apps.notifications.models import DunningLog

    try:
        bill = Bill.objects.select_related(
            'room__floor__building__dormitory',
        ).get(pk=bill_pk)
    except Bill.DoesNotExist:
        logger.error('send_dunning: Bill %s not found', bill_pk)
        return

    if DunningLog.objects.filter(bill=bill, trigger_type=trigger_type).exists():
        return  # already sent — idempotent

    success = True
    error_message = ''

    try:
        _deliver_dunning(bill, trigger_type)
    except Exception as exc:
        success = False
        error_message = str(exc)[:500]
        logger.warning('Dunning delivery failed bill=%s trigger=%s: %s', bill_pk, trigger_type, exc)
        # Record failure before retrying so the log exists
        DunningLog.objects.get_or_create(
            bill=bill,
            trigger_type=trigger_type,
            defaults={'success': False, 'error_message': error_message},
        )
        raise self.retry(exc=exc)

    DunningLog.objects.get_or_create(
        bill=bill,
        trigger_type=trigger_type,
        defaults={'success': success, 'error_message': error_message},
    )


def _deliver_dunning(bill, trigger_type: str):
    """Deliver a dunning message via LINE Messaging API."""
    from apps.notifications.line import push_dunning_message
    sent = push_dunning_message(bill, trigger_type)
    logger.info(
        'Dunning %s for bill %s (room %s, due %s) — LINE sent: %s',
        trigger_type, bill.invoice_number, bill.room, bill.due_date, sent,
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_parcel_notification_task(self, parcel_pk: int):
    """Notify a tenant that a parcel has arrived."""
    from django.utils import timezone
    from apps.notifications.models import Parcel

    try:
        parcel = Parcel.objects.select_related('room').get(pk=parcel_pk)
    except Parcel.DoesNotExist:
        logger.error('send_parcel_notification: Parcel %s not found', parcel_pk)
        return

    try:
        from apps.notifications.line import push_parcel_notification
        push_parcel_notification(parcel)
        logger.info('Parcel notification sent for room %s', parcel.room)
        parcel.notified_at = timezone.now()
        parcel.save(update_fields=['notified_at'])
    except Exception as exc:
        logger.warning('Parcel notification failed parcel=%s: %s', parcel_pk, exc)
        raise self.retry(exc=exc)

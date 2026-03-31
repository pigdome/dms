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
    """
    ส่ง dunning message ตาม notification_channel ที่ตั้งค่าไว้ใน BillingSettings:
      - line_only  → ส่ง LINE เท่านั้น
      - sms_only   → ส่ง SMS เท่านั้น
      - both       → ส่งทั้ง LINE และ SMS
                     ถ้า LINE ล้มเหลว → ลอง SMS (fallback)
    """
    from apps.billing.models import BillingSettings
    from apps.notifications.line import push_dunning_message
    from apps.notifications.sms import SMSService

    # อ่าน notification channel จาก BillingSettings ของ dormitory นั้น
    dormitory = bill.room.floor.building.dormitory
    try:
        settings_obj = BillingSettings.objects.get(dormitory=dormitory)
        channel = settings_obj.notification_channel
        sms_api_key = settings_obj.sms_api_key
        sms_sender_name = settings_obj.sms_sender_name
    except BillingSettings.DoesNotExist:
        # ถ้าไม่มี BillingSettings ให้ fallback เป็น LINE เหมือนเดิม
        channel = 'line_only'
        sms_api_key = ''
        sms_sender_name = ''

    line_sent = False
    sms_sent = False

    if channel == 'line_only':
        line_sent = push_dunning_message(bill, trigger_type)
        logger.info(
            'Dunning %s for bill %s (room %s, due %s) — LINE sent: %s',
            trigger_type, bill.invoice_number, bill.room, bill.due_date, line_sent,
        )

    elif channel == 'sms_only':
        sms_sent = _send_sms_dunning(bill, trigger_type, sms_api_key, sms_sender_name)
        logger.info(
            'Dunning %s for bill %s (room %s, due %s) — SMS sent: %s',
            trigger_type, bill.invoice_number, bill.room, bill.due_date, sms_sent,
        )

    elif channel == 'both':
        line_sent = push_dunning_message(bill, trigger_type)
        logger.info(
            'Dunning %s for bill %s (room %s, due %s) — LINE sent: %s',
            trigger_type, bill.invoice_number, bill.room, bill.due_date, line_sent,
        )
        # ถ้า LINE ล้มเหลว ให้ fallback ไปส่ง SMS แทน
        if not line_sent:
            logger.warning(
                'LINE ล้มเหลว — fallback to SMS for dunning %s bill %s',
                trigger_type, bill.invoice_number,
            )
        sms_sent = _send_sms_dunning(bill, trigger_type, sms_api_key, sms_sender_name)
        logger.info(
            'Dunning %s for bill %s (room %s, due %s) — SMS sent: %s',
            trigger_type, bill.invoice_number, bill.room, bill.due_date, sms_sent,
        )


def _send_sms_dunning(bill, trigger_type: str, sms_api_key: str, sms_sender_name: str) -> bool:
    """
    ส่ง SMS dunning ไปยังผู้เช่าในห้องนั้น.
    คืน True ถ้าส่งสำเร็จอย่างน้อย 1 คน.
    """
    from apps.notifications.sms import SMSService

    try:
        tenant_profiles = bill.room.tenant_profiles.filter(
            leases__status='active'
        ).select_related('user')
    except Exception:
        return False

    label_map = {
        'pre_7d': 'อีก 7 วัน',
        'pre_3d': 'อีก 3 วัน',
        'pre_1d': 'พรุ่งนี้',
        'due': 'วันนี้',
        'post_1d': 'เลยกำหนด 1 วัน',
        'post_7d': 'เลยกำหนด 7 วัน',
        'post_15d': 'เลยกำหนด 15 วัน',
    }
    when = label_map.get(trigger_type, trigger_type)
    due = bill.due_date.strftime('%d/%m/%Y') if bill.due_date else '-'
    total = f'{bill.total:,.2f}'

    svc = SMSService(api_key=sms_api_key, sender_name=sms_sender_name)
    sent = False
    for profile in tenant_profiles:
        phone = getattr(profile, 'phone', None)
        if not phone:
            continue
        message = (
            f'แจ้งเตือนค่าเช่า ห้อง {bill.room.number} '
            f'ยอด {total} บ. ครบกำหนด {due} ({when}) '
            f'กรุณาชำระก่อนครบกำหนด'
        )
        if svc.send_sms(phone=phone, message=message):
            sent = True
    return sent


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
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_broadcast_task(self, broadcast_pk: int):
    """Send a broadcast message to all targeted tenants via LINE."""
    from apps.notifications.models import Broadcast
    from apps.notifications.line import push_broadcast

    try:
        broadcast = Broadcast.objects.select_related('dormitory').get(pk=broadcast_pk)
    except Broadcast.DoesNotExist:
        logger.error('send_broadcast: Broadcast %s not found', broadcast_pk)
        return

    try:
        sent_count = push_broadcast(broadcast)
        logger.info('Broadcast %s sent to %d tenants', broadcast_pk, sent_count)
    except Exception as exc:
        logger.warning('Broadcast delivery failed broadcast=%s: %s', broadcast_pk, exc)
        raise self.retry(exc=exc) from exc

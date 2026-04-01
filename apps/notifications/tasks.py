"""
Celery tasks for notifications (dunning messages, parcel alerts, broadcasts,
lease expiry warnings, and PDPA auto-purge).
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
def send_payment_receipt_task(self, bill_pk: int):
    """
    Send a digital receipt LINE message to the tenant after payment.
    Called from the TMR webhook handler after bill is marked as paid.
    """
    from apps.billing.models import Bill

    try:
        bill = Bill.objects.select_related(
            'room__floor__building__dormitory',
            'payment',
        ).get(pk=bill_pk)
    except Bill.DoesNotExist:
        logger.error('send_payment_receipt: Bill %s not found', bill_pk)
        return

    payment = getattr(bill, 'payment', None)
    if not payment:
        logger.warning('send_payment_receipt: Bill %s has no payment', bill_pk)
        return

    try:
        from apps.notifications.line import push_payment_receipt
        success = push_payment_receipt(bill, payment)
        logger.info('Payment receipt sent for bill %s: %s', bill_pk, success)
    except Exception as exc:
        logger.warning('Payment receipt failed bill=%s: %s', bill_pk, exc)
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_owner_notification_task(self, bill_pk: int):
    """
    Push LINE notification to dormitory owner(s) when a payment is received.
    Called from the TMR webhook handler after bill is marked as paid.
    """
    from apps.billing.models import Bill

    try:
        bill = Bill.objects.select_related(
            'room__floor__building__dormitory',
            'payment',
        ).get(pk=bill_pk)
    except Bill.DoesNotExist:
        logger.error('send_payment_owner_notification: Bill %s not found', bill_pk)
        return

    payment = getattr(bill, 'payment', None)
    if not payment:
        logger.warning('send_payment_owner_notification: Bill %s has no payment', bill_pk)
        return

    try:
        from apps.notifications.line import push_payment_owner_notification
        success = push_payment_owner_notification(bill, payment)
        logger.info('Payment owner notification sent for bill %s: %s', bill_pk, success)
    except Exception as exc:
        logger.warning('Payment owner notification failed bill=%s: %s', bill_pk, exc)
        raise self.retry(exc=exc) from exc


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


# ---------------------------------------------------------------------------
# P1-1: Lease Expiry Warning — Celery scheduled task
# ---------------------------------------------------------------------------

@shared_task
def check_lease_expiry_task():
    """
    Daily check for leases expiring in 30 or 7 days.
    Sends LINE notifications to both tenant and owner(s).

    Runs once per day (scheduled via celery beat).
    Uses a simple "already notified" check via ActivityLog to prevent duplicates.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.tenants.models import Lease
    from apps.core.models import ActivityLog, CustomUser, UserDormitoryRole

    today = timezone.now().date()
    warning_days = [30, 7]

    for days in warning_days:
        target_date = today + timedelta(days=days)
        # Find active leases expiring on exactly target_date
        leases = Lease.unscoped_objects.filter(
            status='active',
            end_date=target_date,
        ).select_related(
            'tenant__user',
            'room__floor__building__dormitory',
        )

        for lease in leases:
            if not lease.room or not lease.tenant:
                continue

            dormitory = lease.room.floor.building.dormitory if lease.room else None
            if not dormitory:
                continue

            # Idempotency: check if we already sent this exact warning
            log_action = f'lease_expiry_{days}d'
            already_sent = ActivityLog.unscoped_objects.filter(
                action=log_action,
                record_id=str(lease.pk),
            ).exists()
            if already_sent:
                continue

            tenant_sent = False
            owner_sent = False

            # Send to tenant
            try:
                from apps.notifications.line import push_lease_expiry_tenant
                tenant_sent = push_lease_expiry_tenant(lease.tenant, lease, days)
            except Exception as exc:
                logger.warning(
                    'Lease expiry tenant notification failed lease=%s: %s',
                    lease.pk, exc,
                )

            # Send to owner(s) of this dormitory
            try:
                from apps.notifications.line import push_lease_expiry_owner
                # Find owners: first check direct dormitory FK, then UserDormitoryRole
                owners = CustomUser.objects.filter(
                    dormitory=dormitory,
                    role=CustomUser.Role.OWNER,
                ).exclude(line_user_id='')

                if not owners.exists():
                    owner_ids = UserDormitoryRole.objects.filter(
                        dormitory=dormitory,
                        role=CustomUser.Role.OWNER,
                    ).values_list('user_id', flat=True)
                    owners = CustomUser.objects.filter(
                        pk__in=owner_ids,
                    ).exclude(line_user_id='')

                for owner in owners:
                    if push_lease_expiry_owner(owner, lease, days):
                        owner_sent = True
            except Exception as exc:
                logger.warning(
                    'Lease expiry owner notification failed lease=%s: %s',
                    lease.pk, exc,
                )

            # Log to prevent duplicate notifications
            ActivityLog.unscoped_objects.create(
                dormitory=dormitory,
                action=log_action,
                record_id=str(lease.pk),
                detail={
                    'model': 'Lease',
                    'lease_id': str(lease.pk),
                    'days_remaining': days,
                    'tenant_notified': tenant_sent,
                    'owner_notified': owner_sent,
                },
            )

            logger.info(
                'Lease expiry warning (%dd) sent for lease %s room %s: '
                'tenant=%s owner=%s',
                days, lease.pk,
                lease.room.number if lease.room else '?',
                tenant_sent, owner_sent,
            )


# ---------------------------------------------------------------------------
# P1-2: PDPA Auto-Purge — anonymize tenant data 90 days after lease ends
# ---------------------------------------------------------------------------

@shared_task
def pdpa_auto_purge_task():
    """
    Daily task: find tenants whose ALL leases have ended and the most recent
    end_date is more than 90 days ago. Auto-anonymize their personal data
    per PDPA Data Retention policy.

    Only processes TenantProfiles that have NOT yet been anonymized
    (anonymized_at is NULL and is_deleted is False).
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.db.models import Max, Q
    from apps.tenants.models import TenantProfile

    cutoff_date = timezone.now().date() - timedelta(days=90)

    # Find profiles that:
    # 1. Are NOT already anonymized
    # 2. Have NO active/pending leases
    # 3. Have at least one ended lease with max(end_date) <= cutoff_date
    candidates = TenantProfile.unscoped_objects.filter(
        is_deleted=False,
        anonymized_at__isnull=True,
    ).exclude(
        # Exclude profiles with any active or pending lease
        leases__status__in=['active', 'pending'],
    ).filter(
        # Must have at least one ended lease
        leases__status='ended',
    ).annotate(
        latest_end_date=Max('leases__end_date'),
    ).filter(
        latest_end_date__lte=cutoff_date,
    ).distinct()

    purged_count = 0
    for profile in candidates:
        try:
            profile.anonymize()
            purged_count += 1
            logger.info(
                'PDPA auto-purge: anonymized TenantProfile %s (latest lease end: %s)',
                profile.pk, profile.leases.aggregate(Max('end_date'))['end_date__max'],
            )
        except Exception as exc:
            logger.error(
                'PDPA auto-purge failed for TenantProfile %s: %s',
                profile.pk, exc,
            )

    logger.info('PDPA auto-purge completed: %d profiles anonymized', purged_count)
    return purged_count

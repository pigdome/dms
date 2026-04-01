"""
LINE Messaging API client (push messages only, no LIFF).
Uses stdlib urllib — no extra dependencies required.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

LINE_API_URL = 'https://api.line.me/v2/bot/message/push'


def _access_token() -> str:
    return getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '')


def push_text(line_user_id: str, text: str) -> bool:
    """Push a plain-text message to a single LINE user. Returns True on success."""
    token = _access_token()
    if not token:
        logger.warning('LINE_CHANNEL_ACCESS_TOKEN not configured — skipping push.')
        return False
    if not line_user_id:
        return False

    payload = json.dumps({
        'to': line_user_id,
        'messages': [{'type': 'text', 'text': text}],
    }).encode()

    req = urllib.request.Request(
        LINE_API_URL,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        logger.error('LINE push failed (%s): %s', e.code, body)
        return False
    except Exception as exc:
        logger.error('LINE push error: %s', exc)
        return False


def push_parcel_notification(parcel) -> bool:
    """Notify the tenant of a parcel using their LINE ID."""
    try:
        tenant_profiles = parcel.room.tenant_profiles.filter(
            leases__status='active'
        ).select_related('user')
    except Exception:
        return False

    sent = False
    for profile in tenant_profiles:
        line_id = profile.line_id
        if not line_id:
            continue
        carrier = parcel.carrier or 'ไม่ระบุ'
        text = (
            f'📦 มีพัสดุมาให้คุณแล้ว!\n'
            f'ห้อง {parcel.room.number} · ผู้ส่ง: {carrier}\n'
            f'กรุณารับที่สำนักงานหอพัก'
        )
        if push_text(line_id, text):
            sent = True
    return sent


def push_dunning_message(bill, trigger_type: str) -> bool:
    """Send a dunning message to the tenant(s) in the bill's room."""
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

    sent = False
    for profile in tenant_profiles:
        if not profile.line_id:
            continue
        text = (
            f'💰 แจ้งเตือนค่าเช่า\n'
            f'ห้อง {bill.room.number} · {bill.month.strftime("%B %Y") if bill.month else ""}\n'
            f'ยอด: ฿{total} · ครบกำหนด: {due} ({when})\n'
            f'กรุณาชำระเพื่อหลีกเลี่ยงค่าปรับ'
        )
        if push_text(profile.line_id, text):
            sent = True
    return sent


def push_payment_receipt(bill, payment) -> bool:
    """
    Send a digital receipt to the tenant(s) in the bill's room after payment.
    Returns True if at least one message was sent successfully.
    """
    try:
        tenant_profiles = bill.room.tenant_profiles.filter(
            leases__status='active'
        ).select_related('user')
    except Exception:
        return False

    total = f'{payment.amount:,.2f}'
    paid_at = payment.paid_at.strftime('%d/%m/%Y %H:%M') if payment.paid_at else '-'
    room_number = bill.room.number
    invoice = bill.invoice_number or '-'
    month_str = bill.month.strftime('%B %Y') if bill.month else '-'

    sent = False
    for profile in tenant_profiles:
        if not profile.line_id:
            continue
        text = (
            f'Receipt / ใบเสร็จรับเงิน\n'
            f'Invoice: {invoice}\n'
            f'Room {room_number} - {month_str}\n'
            f'Amount: {total} THB\n'
            f'Paid: {paid_at}\n'
            f'Thank you for your payment!'
        )
        if push_text(profile.line_id, text):
            sent = True
    return sent


def push_payment_owner_notification(bill, payment) -> bool:
    """
    Notify the dormitory owner(s) when a payment is received.
    Looks up users with role=owner who have a line_user_id and belong to
    the dormitory of the bill.
    Returns True if at least one message was sent successfully.
    """
    from apps.core.models import CustomUser
    dormitory = bill.room.floor.building.dormitory

    owners = CustomUser.objects.filter(
        dormitory=dormitory,
        role=CustomUser.Role.OWNER,
    ).exclude(line_user_id='')

    if not owners.exists():
        # Also check UserDormitoryRole for owners assigned to this dormitory
        from apps.core.models import UserDormitoryRole
        owner_ids = UserDormitoryRole.objects.filter(
            dormitory=dormitory,
            role=CustomUser.Role.OWNER,
        ).values_list('user_id', flat=True)
        owners = CustomUser.objects.filter(
            pk__in=owner_ids,
        ).exclude(line_user_id='')

    total = f'{payment.amount:,.2f}'
    room_number = bill.room.number
    invoice = bill.invoice_number or '-'

    sent = False
    for owner in owners:
        text = (
            f'Payment received!\n'
            f'Invoice: {invoice}\n'
            f'Room {room_number} - {total} THB\n'
            f'Bill status: Paid'
        )
        if push_text(owner.line_user_id, text):
            sent = True
    return sent


def push_broadcast(broadcast) -> int:
    """Send broadcast message to tenants. Returns number of messages sent."""
    from apps.tenants.models import TenantProfile
    from apps.rooms.models import Room
    from django.db.models import Q

    dorm = broadcast.dormitory
    rooms_qs = Room.objects.filter(floor__building__dormitory=dorm)

    if broadcast.audience_type == 'building' and broadcast.audience_ref:
        rooms_qs = rooms_qs.filter(floor__building__name=broadcast.audience_ref)
    elif broadcast.audience_type == 'floor' and broadcast.audience_ref:
        rooms_qs = rooms_qs.filter(floor__pk=broadcast.audience_ref)

    profiles = TenantProfile.objects.filter(
        Q(leases__room__in=rooms_qs, leases__status='active') |
        Q(room__in=rooms_qs)
    ).distinct().select_related('user')

    sent = 0
    text = f'📢 {broadcast.title}\n\n{broadcast.body}'
    for profile in profiles:
        if profile.line_id and push_text(profile.line_id, text):
            sent += 1
    return sent


def push_lease_expiry_tenant(tenant_profile, lease, days_remaining: int) -> bool:
    """
    Notify a tenant that their lease is expiring soon.
    Called by the check_lease_expiry_task for 30-day and 7-day warnings.
    """
    line_id = tenant_profile.line_id
    if not line_id:
        return False

    room_number = lease.room.number if lease.room else '-'
    end_date = lease.end_date.strftime('%d/%m/%Y') if lease.end_date else '-'

    if days_remaining <= 7:
        urgency = 'URGENT'
    else:
        urgency = ''

    text = (
        f'{"[" + urgency + "] " if urgency else ""}'
        f'Lease Expiry Notice / แจ้งเตือนสัญญาใกล้หมด\n'
        f'Room {room_number}\n'
        f'End date: {end_date} (in {days_remaining} days)\n'
        f'Please contact the office to renew your lease.'
    )
    return push_text(line_id, text)


def push_lease_expiry_owner(owner_user, lease, days_remaining: int) -> bool:
    """
    Notify an owner that a tenant's lease is expiring soon.
    Uses the owner's line_user_id field (not line_id).
    """
    line_user_id = owner_user.line_user_id
    if not line_user_id:
        return False

    room_number = lease.room.number if lease.room else '-'
    tenant_name = lease.tenant.full_name if lease.tenant else '-'
    end_date = lease.end_date.strftime('%d/%m/%Y') if lease.end_date else '-'

    text = (
        f'Lease Expiry Alert\n'
        f'Tenant: {tenant_name}\n'
        f'Room {room_number}\n'
        f'End date: {end_date} (in {days_remaining} days)\n'
        f'Action needed: renew or prepare vacancy.'
    )
    return push_text(line_user_id, text)

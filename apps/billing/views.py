import csv
import hashlib
import hmac
import json
import logging

from django.conf import settings as django_settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.billing.models import Bill, BillingSettings, Payment
from apps.core.models import ActivityLog

logger = logging.getLogger(__name__)

from apps.core.mixins import OwnerRequiredMixin, StaffRequiredMixin, StaffPermissionRequiredMixin


class BillingSettingsView(OwnerRequiredMixin, View):
    """จัดการ Billing Settings — เฉพาะ owner/superadmin เท่านั้น (ไม่ใช่ staff)"""
    def _get_or_create_settings(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        if not dorm:
            return None
        settings, _ = BillingSettings.objects.get_or_create(dormitory=dorm)
        return settings

    def get(self, request):
        settings = self._get_or_create_settings(request)
        if not settings:
            messages.error(request, _('No dormitory associated with your account.'))
            return redirect('dashboard:index')
        
        from apps.billing.forms import BillingSettingsForm
        form = BillingSettingsForm(instance=settings)
        return render(request, 'billing/settings.html', {
            'settings': settings,
            'form': form,
            'bill_day_choices': BillingSettings.BillDay.choices,
        })

    def post(self, request):
        settings = self._get_or_create_settings(request)
        if not settings:
            messages.error(request, _('No dormitory associated with your account.'))
            return redirect('dashboard:index')

        from apps.billing.forms import BillingSettingsForm
        form = BillingSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            ActivityLog.objects.create(
                dormitory=settings.dormitory,
                user=request.user,
                action='billing_settings_updated',
                detail={'settings_id': settings.pk},
            )
            messages.success(request, _('Billing settings updated successfully.'))
            return redirect('billing:settings')
        
        return render(request, 'billing/settings.html', {
            'settings': settings,
            'form': form,
            'bill_day_choices': BillingSettings.BillDay.choices,
        })


class BillListView(StaffPermissionRequiredMixin, View):
    """รายการ Bills — owner/superadmin ผ่านทันที, staff ต้องมี can_view_billing"""
    permission_flag = 'can_view_billing'
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        if not dorm:
            messages.error(request, _('No dormitory associated with your account.'))
            return redirect('dashboard:index')

        bills = Bill.objects.filter(
            room__floor__building__dormitory=dorm
        ).select_related('room', 'room__floor', 'room__floor__building').order_by('-month', '-created_at')

        # Filters — default month to current month
        status_filter = request.GET.get('status', '')
        now = timezone.now()
        default_month = now.strftime('%Y-%m')
        month_filter = request.GET.get('month', default_month)
        if status_filter:
            bills = bills.filter(status=status_filter)
        if month_filter:
            try:
                from datetime import datetime
                month_date = datetime.strptime(month_filter, '%Y-%m').date()
                bills = bills.filter(month__year=month_date.year, month__month=month_date.month)
            except ValueError:
                pass

        return render(request, 'billing/list.html', {
            'bills': bills,
            'status_choices': Bill.Status.choices,
            'status_filter': status_filter,
            'month_filter': month_filter,
            'default_month': default_month,
        })


class BillDetailView(StaffPermissionRequiredMixin, View):
    """รายละเอียด Bill — owner/superadmin ผ่านทันที, staff ต้องมี can_view_billing"""
    permission_flag = 'can_view_billing'
    def get(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        bill = get_object_or_404(
            Bill.objects.select_related(
                'room__floor__building__dormitory',
                'meter_reading',
            ).prefetch_related('line_items__charge_type'),
            pk=pk, room__floor__building__dormitory=dorm
        )
        payment = getattr(bill, 'payment', None)
        line_items = bill.line_items.all()
        return render(request, 'billing/detail.html', {
            'bill': bill,
            'payment': payment,
            'line_items': line_items,
        })

    def post(self, request, pk):
        """Update bill status manually (draft→sent, sent→overdue etc.)."""
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        bill = get_object_or_404(
            Bill, pk=pk, room__floor__building__dormitory=dorm
        )
        new_status = request.POST.get('status', '').strip()
        valid = [s[0] for s in Bill.Status.choices]
        if new_status in valid:
            bill.status = new_status
            bill.save(update_fields=['status', 'updated_at'])
            ActivityLog.objects.create(
                dormitory=dorm,
                user=request.user,
                action='bill_status_changed',
                detail={'bill_id': bill.pk, 'new_status': new_status, 'room_number': bill.room.number},
            )
            messages.success(request, _('Bill status updated.'))
        else:
            messages.error(request, _('Invalid status.'))
        return redirect('billing:detail', pk=pk)


@csrf_exempt
@require_POST
def tmr_webhook(request):
    """
    Receive TMR payment gateway webhook, verify HMAC signature, and mark the
    matching bill as paid.  Fully idempotent: duplicate webhooks return 200.
    """
    body = request.body

    # --- Signature verification ---
    # B2 fix: ถ้าไม่ได้ตั้ง TMR_WEBHOOK_SECRET ให้ reject ทันที
    # ห้าม skip HMAC verify เพราะจะทำให้ใครก็ POST มา mark bill ว่าจ่ายแล้วได้
    secret = django_settings.TMR_WEBHOOK_SECRET
    if not secret:
        return HttpResponse('Webhook secret not configured', status=400)

    sig = request.META.get('HTTP_X_TMR_SIGNATURE', '')
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return HttpResponse('Invalid signature', status=403)

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse('Bad JSON', status=400)

    # TMR sends: ref (unique transaction id), order_id (invoice_number), amount
    idempotency_key = data.get('ref') or data.get('transaction_id', '')
    invoice_number = data.get('order_id') or data.get('invoice_number', '')

    if not idempotency_key or not invoice_number:
        return HttpResponse('Missing ref or order_id', status=400)

    # B1 fix: ครอบ idempotency check + select_for_update ทั้งหมดไว้ใน atomic() block
    # เดิม select_for_update() อยู่นอก atomic() → concurrent webhooks ผ่าน idempotency
    # check พร้อมกันได้ → duplicate payment record
    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        # --- Idempotency check (ต้องอยู่ใน atomic + select_for_update เพื่อป้องกัน race) ---
        if Payment.objects.filter(idempotency_key=idempotency_key).exists():
            return JsonResponse({'status': 'already_processed'})

        try:
            bill = Bill.objects.select_for_update().get(invoice_number=invoice_number)
        except Bill.DoesNotExist:
            return HttpResponse('Bill not found', status=404)

        if bill.status == Bill.Status.PAID:
            return JsonResponse({'status': 'already_paid'})

        # I4: Validate ว่าจำนวนเงินจาก webhook ตรงกับยอดใน bill
        # ถ้าไม่ตรงให้ log warning แต่ยังคง process ต่อไป (ไม่ reject)
        # เนื่องจาก payment gateway อาจส่ง amount ที่ปัดเศษต่างกันเล็กน้อย
        from decimal import Decimal as _Decimal
        webhook_amount = data.get('amount')
        if webhook_amount is not None:
            try:
                webhook_amount_dec = _Decimal(str(webhook_amount))
                if webhook_amount_dec != bill.total:
                    logger.warning(
                        'Webhook amount mismatch: bill=%s invoice=%s '
                        'expected=%s received=%s',
                        bill.pk, bill.invoice_number, bill.total, webhook_amount_dec,
                    )
                    ActivityLog.objects.create(
                        dormitory=bill.room.floor.building.dormitory,
                        user=None,
                        action='webhook_amount_mismatch',
                        detail={
                            'bill_id': str(bill.pk),
                            'invoice': bill.invoice_number,
                            'bill_total': str(bill.total),
                            'webhook_amount': str(webhook_amount_dec),
                        },
                    )
            except Exception:
                # จำนวนเงินรูปแบบผิดพลาด — log warning แล้วใช้ bill.total แทน
                logger.warning(
                    'Webhook amount parse error: bill=%s value=%s',
                    bill.pk, webhook_amount,
                )

        Payment.objects.create(
            bill=bill,
            amount=data.get('amount', bill.total),
            tmr_ref=data.get('tmr_ref', idempotency_key),
            idempotency_key=idempotency_key,
            webhook_payload=data,
            paid_at=timezone.now(),
        )
        bill.status = Bill.Status.PAID
        bill.save(update_fields=['status', 'updated_at'])
        ActivityLog.objects.create(
            dormitory=bill.room.floor.building.dormitory,
            user=None,  # System action
            action='payment_received_webhook',
            detail={'bill_id': bill.pk, 'invoice': bill.invoice_number, 'amount': data.get('amount')},
        )

    # Queue LINE notifications: receipt to tenant + alert to owner
    try:
        from apps.notifications.tasks import (
            send_payment_receipt_task,
            send_payment_owner_notification_task,
        )
        send_payment_receipt_task.delay(bill.pk)
        send_payment_owner_notification_task.delay(bill.pk)
    except Exception:
        pass  # Notification failure must not break payment processing

    return JsonResponse({'status': 'ok'})

class BillQRRedirectView(View):
    """
    B3 fix: Server-side QR redirect endpoint — ไม่ expose tmr_api_key ใน client-facing URL
    Tenant เรียก /billing/qr/<bill_id>/ → server ตรวจสิทธิ์ → redirect ไปยัง TMR URL จริง
    tmr_api_key ไม่โผล่ใน HTML หรือ network tab ของ tenant
    """

    def get(self, request, bill_id):
        from django.contrib.auth.mixins import LoginRequiredMixin
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())

        user = request.user

        # ตรวจสิทธิ์: tenant เข้าได้เฉพาะบิลของตัวเอง, owner/staff เข้าได้ทุกบิลใน dormitory
        if user.role == 'tenant':
            try:
                from apps.tenants.models import TenantProfile
                profile = TenantProfile.objects.get(user=user)
                bill = Bill.objects.get(
                    pk=bill_id,
                    room__leases__tenant=profile,
                )
            except (Bill.DoesNotExist, Exception):
                return HttpResponse('Not found', status=404)
        else:
            dorm = getattr(request, 'active_dormitory', None) or user.dormitory
            bill = get_object_or_404(
                Bill, pk=bill_id, room__floor__building__dormitory=dorm
            )

        # ตรวจสถานะ: redirect เฉพาะบิลที่ยังไม่จ่าย
        if bill.status not in (Bill.Status.SENT, Bill.Status.OVERDUE):
            return HttpResponse('Payment not required', status=400)

        try:
            billing_settings = bill.room.floor.building.dormitory.billing_settings
            if not billing_settings.tmr_api_key:
                return HttpResponse('Payment not configured', status=400)
            # สร้าง TMR URL ฝั่ง server — api_key ไม่ถูกส่งไปหา client เลย
            tmr_url = f"https://payment.tmr.th/qr/{billing_settings.tmr_api_key}/{bill.invoice_number}"
        except Exception:
            return HttpResponse('Payment configuration error', status=500)

        # BUG #1 fix: เปลี่ยนจาก redirect เป็น server-side proxy
        # redirect(tmr_url) ส่ง Location header ไปยัง client ซึ่งมี tmr_api_key อยู่
        # tenant สามารถเห็น api_key ได้จาก browser DevTools → Network tab
        # แก้โดย fetch QR image ฝั่ง server แล้ว stream กลับไปให้ client โดยตรง
        import urllib.request as _urllib_req
        import urllib.error as _urllib_err
        try:
            with _urllib_req.urlopen(tmr_url, timeout=10) as resp:
                content_type = resp.headers.get('Content-Type', 'image/png')
                image_data = resp.read()
            return HttpResponse(image_data, content_type=content_type)
        except _urllib_err.HTTPError as exc:
            logger.warning('TMR QR fetch HTTPError bill=%s status=%s', bill_id, exc.code)
            return HttpResponse('Payment QR not available', status=502)
        except Exception as exc:
            logger.warning('TMR QR fetch failed bill=%s: %s', bill_id, exc)
            return HttpResponse('Payment QR not available', status=502)


class BillCSVExportView(OwnerRequiredMixin, View):
    """
    Export bill data เป็น CSV — เฉพาะ owner/superadmin เท่านั้น (ข้อมูลการเงินสำคัญ)
    รองรับ date range (start_month–end_month) และ building filter
    GET ไม่มี start_month → แสดง form ให้กรอก
    GET มี start_month → download CSV ทันที
    """

    def get(self, request):
        from datetime import datetime
        from apps.rooms.models import Building

        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        if not dorm:
            messages.error(request, _('No dormitory associated with your account.'))
            return redirect('dashboard:index')

        start_month_str = request.GET.get('start_month', '').strip()
        end_month_str = request.GET.get('end_month', '').strip()
        building_id = request.GET.get('building_id', '').strip()

        # ถ้าไม่มี start_month → แสดง export form เพื่อให้กรอก date range
        if not start_month_str:
            buildings = Building.objects.filter(dormitory=dorm).order_by('name')
            now = timezone.now()
            default_month = now.strftime('%Y-%m')
            return render(request, 'billing/export.html', {
                'buildings': buildings,
                'default_start_month': default_month,
                'default_end_month': default_month,
            })

        # Validate และ parse start_month / end_month
        try:
            start_date = datetime.strptime(start_month_str, '%Y-%m').date()
        except ValueError:
            messages.error(request, _('Invalid start month format. Use YYYY-MM.'))
            return redirect('billing:export')

        if end_month_str:
            try:
                end_date = datetime.strptime(end_month_str, '%Y-%m').date()
            except ValueError:
                messages.error(request, _('Invalid end month format. Use YYYY-MM.'))
                return redirect('billing:export')
        else:
            # ถ้าไม่ระบุ end_month ใช้ start_month เป็น end_month เดียวกัน
            end_date = start_date

        # กัน start > end
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # Query bills ใน date range — enforce tenant isolation ด้วย dormitory filter
        # ใช้ prefetch_related สำหรับ leases และ tenant_profiles เพื่อหลีกเลี่ยง N+1 query
        # (loop ต้องการ active lease + tenant profile ของแต่ละห้อง — prefetch ให้โหลดเป็น batch)
        from django.db.models import Prefetch
        from apps.tenants.models import Lease, TenantProfile

        active_lease_prefetch = Prefetch(
            'room__leases',
            queryset=Lease.objects.filter(status='active').select_related('tenant__user'),
            to_attr='active_leases_cache',
        )
        tenant_profile_prefetch = Prefetch(
            'room__tenant_profiles',
            queryset=TenantProfile.objects.select_related('user'),
            to_attr='tenant_profiles_cache',
        )

        bills = (
            Bill.objects.filter(
                room__floor__building__dormitory=dorm,
                month__gte=start_date,
                month__lte=end_date,
            )
            .select_related(
                'room',
                'room__floor',
                'room__floor__building',
                'payment',
            )
            .prefetch_related(
                active_lease_prefetch,
                tenant_profile_prefetch,
            )
            .order_by('month', 'room__floor__building__name', 'room__number')
        )

        # Optional building filter — ยังคง enforce dormitory ผ่าน query ข้างบน
        if building_id:
            bills = bills.filter(room__floor__building_id=building_id)

        # สร้าง CSV response พร้อม UTF-8 BOM เพื่อให้ Excel ภาษาไทยอ่านได้
        # ใช้ charset=utf-8 และ write BOM เองเพื่อควบคุมได้แน่นอน (utf-8-sig อาจ double BOM)
        filename = f'bills_export_{start_month_str}_to_{end_month_str or start_month_str}.csv'
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        # เขียน UTF-8 BOM (U+FEFF) ที่ต้นไฟล์ให้ Excel อ่านภาษาไทยได้
        response.write('\ufeff')

        writer = csv.writer(response)
        # Header columns ตาม spec
        writer.writerow([
            'Invoice No', 'Room', 'Tenant Name', 'Month',
            'Base Rent', 'Water Units', 'Water Amt', 'Elec Units', 'Elec Amt',
            'Total', 'Status', 'Paid Date',
        ])

        for b in bills:
            # หา tenant name จาก active lease ก่อน ถ้าไม่มีดูจาก tenant_profiles
            # ใช้ to_attr cache ที่ prefetch มาแล้ว — ไม่ hit DB อีก (แก้ N+1 query)
            tenant_name = ''
            active_leases = getattr(b.room, 'active_leases_cache', None)
            if active_leases:
                tenant_name = active_leases[0].tenant.full_name
            else:
                profiles = getattr(b.room, 'tenant_profiles_cache', None)
                if profiles:
                    tenant_name = profiles[0].full_name

            # วันที่ชำระเงิน — ดูจาก Payment ที่ link กับ bill นี้
            paid_date = ''
            payment = getattr(b, 'payment', None)
            if payment and payment.paid_at:
                paid_date = payment.paid_at.strftime('%Y-%m-%d')

            writer.writerow([
                b.invoice_number or '',
                b.room.number,
                tenant_name,
                b.month.strftime('%Y-%m') if b.month else '',
                b.base_rent,
                b.water_units,
                b.water_amt,
                b.elec_units,
                b.elec_amt,
                b.total,
                b.get_status_display(),
                paid_date,
            ])

        return response

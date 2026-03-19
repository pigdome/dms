import csv
import hashlib
import hmac
import json

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django.shortcuts import get_object_or_404

from apps.billing.models import Bill, BillingSettings, Payment
from apps.core.models import ActivityLog

from apps.core.decorators import staff_required


@method_decorator([login_required, staff_required], name='dispatch')
class BillingSettingsView(View):
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
        return render(request, 'billing/settings.html', {
            'settings': settings,
            'bill_day_choices': BillingSettings.BillDay.choices,
        })

    def post(self, request):
        settings = self._get_or_create_settings(request)
        if not settings:
            messages.error(request, _('No dormitory associated with your account.'))
            return redirect('dashboard:index')

        data = request.POST
        settings.tmr_api_key = data.get('tmr_api_key', '').strip()
        settings.tmr_secret = data.get('tmr_secret', '').strip()

        bill_day = data.get('bill_day', '1')
        valid_days = [str(d[0]) for d in BillingSettings.BillDay.choices]
        if bill_day in valid_days:
            settings.bill_day = int(bill_day)

        try:
            settings.grace_days = max(0, int(data.get('grace_days', 5) or 5))
        except (ValueError, TypeError):
            settings.grace_days = 5

        try:
            settings.elec_rate = float(data.get('elec_rate', 7.00) or 7.00)
        except (ValueError, TypeError):
            settings.elec_rate = 7.00

        try:
            settings.water_rate = float(data.get('water_rate', 18.00) or 18.00)
        except (ValueError, TypeError):
            settings.water_rate = 18.00

        settings.dunning_enabled = bool(data.get('dunning_enabled'))
        settings.save()

        messages.success(request, _('Billing settings saved successfully.'))
        return redirect('billing:settings')


@method_decorator([login_required, staff_required], name='dispatch')
class BillListView(View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        if not dorm:
            messages.error(request, _('No dormitory associated with your account.'))
            return redirect('dashboard:index')

        bills = Bill.objects.filter(
            room__floor__building__dormitory=dorm
        ).select_related('room', 'room__floor', 'room__floor__building').order_by('-month', '-created_at')

        # Filters
        status_filter = request.GET.get('status', '')
        month_filter = request.GET.get('month', '')
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
        })


@method_decorator([login_required, staff_required], name='dispatch')
class BillDetailView(View):
    def get(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        bill = get_object_or_404(
            Bill.objects.select_related('room__floor__building__dormitory'),
            pk=pk, room__floor__building__dormitory=dorm
        )
        payment = getattr(bill, 'payment', None)
        return render(request, 'billing/detail.html', {
            'bill': bill,
            'payment': payment,
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
    secret = django_settings.TMR_WEBHOOK_SECRET
    if secret:
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

    # --- Idempotency check ---
    if Payment.objects.filter(idempotency_key=idempotency_key).exists():
        return JsonResponse({'status': 'already_processed'})

    try:
        bill = Bill.objects.select_for_update().get(invoice_number=invoice_number)
    except Bill.DoesNotExist:
        return HttpResponse('Bill not found', status=404)

    if bill.status == Bill.Status.PAID:
        return JsonResponse({'status': 'already_paid'})

    from django.db import transaction as db_transaction
    with db_transaction.atomic():
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

    return JsonResponse({'status': 'ok'})

@method_decorator([login_required, staff_required], name='dispatch')
class BillCSVExportView(View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        if not dorm:
            return HttpResponse(status=403)

        bills = Bill.objects.filter(
            room__floor__building__dormitory=dorm
        ).select_related('room', 'room__floor', 'room__floor__building').order_by('-month', '-created_at')

        # Reuse filters (simplified)
        status = request.GET.get('status')
        if status:
            bills = bills.filter(status=status)
        month = request.GET.get('month')
        if month:
            try:
                from datetime import datetime
                d = datetime.strptime(month, '%Y-%m').date()
                bills = bills.filter(month=d)
            except Exception:
                pass

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="bills_{dorm.pk}_{timezone.now().date()}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Invoice', 'Month', 'Room', 'Building', 'Tenant',
            'Base Rent', 'Elec (Used)', 'Elec (Amt)', 'Water (Used)', 'Water (Amt)',
            'Others', 'Total', 'Status', 'Due Date'
        ])

        for b in bills:
            # Try to get active tenant via Lease
            from apps.tenants.models import TenantProfile
            tenant = "N/A"
            active_lease = b.room.leases.filter(status='active').first()
            if active_lease:
                tenant = active_lease.tenant.full_name
            elif b.room.tenant_profiles.exists():
                tenant = b.room.tenant_profiles.first().full_name

            writer.writerow([
                b.invoice_number,
                b.month.strftime('%Y-%m') if b.month else '',
                b.room.number,
                b.room.floor.building.name,
                tenant,
                b.base_rent,
                b.elec_curr - (b.elec_prev or 0),
                b.elec_amt,
                b.water_curr - (b.water_prev or 0),
                b.water_amt,
                b.other_amt,
                b.total,
                b.get_status_display(),
                b.due_date.strftime('%Y-%m-%d') if b.due_date else ''
            ])

        return response

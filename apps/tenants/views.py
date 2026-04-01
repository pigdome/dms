from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from apps.tenants.models import TenantProfile, Lease

from apps.core.mixins import StaffRequiredMixin, OwnerRequiredMixin
from apps.core.utils import SimpleForm
from apps.core.models import ActivityLog


def _dorm_profiles(user, dormitory=None):
    """Return TenantProfiles scoped to the user's (or given) dormitory.

    Looks up profiles via active Lease.room first; falls back to the legacy
    TenantProfile.room FK so existing data still surfaces correctly.
    """
    from django.db.models import Q
    dorm = dormitory or user.dormitory
    return TenantProfile.objects.filter(
        Q(leases__room__floor__building__dormitory=dorm, leases__status='active') |
        Q(room__floor__building__dormitory=dorm)
    ).distinct().select_related('user', 'room', 'room__floor', 'room__floor__building')


class TenantListView(StaffRequiredMixin, View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        profiles = _dorm_profiles(request.user, dormitory=dorm)
        search_query = request.GET.get('q', '')
        if search_query:
            profiles = profiles.filter(
                user__first_name__icontains=search_query
            ) | profiles.filter(
                user__last_name__icontains=search_query
            ) | profiles.filter(
                user__username__icontains=search_query
            ) | profiles.filter(
                room__number__icontains=search_query
            )
        return render(request, 'tenants/list.html', {
            'tenants': profiles,
            'search_query': search_query,
        })


class TenantDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        # Tenants may only view their own profile; staff/owners see any profile in their dorm
        if request.user.role == 'tenant':
            try:
                own_profile = request.user.tenant_profile
            except TenantProfile.DoesNotExist:
                return redirect('tenant:home')
            if own_profile.pk != pk:
                return redirect('tenants:detail', pk=own_profile.pk)
            profile = own_profile
        else:
            dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
            profile = get_object_or_404(_dorm_profiles(request.user, dormitory=dorm), pk=pk)
        leases = profile.leases.select_related('room').all()
        # Collect bills from all rooms this tenant has leased
        from apps.billing.models import Bill
        bills = Bill.objects.filter(
            room__leases__tenant=profile
        ).order_by('-month').distinct()[:12]
        return render(request, 'tenants/detail.html', {
            'profile': profile,
            'leases': leases,
            'bills': bills,
        })


class TenantCreateView(StaffRequiredMixin, View):
    def _context(self, user, data=None, dormitory=None):
        from apps.rooms.models import Room
        dorm = dormitory or user.dormitory
        available_rooms = Room.objects.filter(
            floor__building__dormitory=dorm,
            status__in=['vacant', 'cleaning'],
        ).select_related('floor', 'floor__building')
        return {
            'available_rooms': available_rooms,
            'form': SimpleForm(data or {}),
        }

    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        return render(request, 'tenants/form.html', self._context(request.user, dormitory=dorm))

    def post(self, request):
        from apps.core.models import CustomUser
        from apps.rooms.models import Room

        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        data = request.POST
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        phone = data.get('phone', '').strip()
        room_id = data.get('room', '')
        start_date = data.get('start_date', '')

        if not username:
            messages.error(request, _('Username is required.'))
            return render(request, 'tenants/form.html', self._context(request.user, data, dormitory=dorm))

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, _('Username already exists.'))
            return render(request, 'tenants/form.html', self._context(request.user, data, dormitory=dorm))

        # Create user
        user = CustomUser.objects.create_user(
            username=username,
            password=password or username,  # fallback to username if no password
            first_name=first_name,
            last_name=last_name,
            role='tenant',
            dormitory=dorm,
        )

        # Assign room if specified
        room = None
        if room_id:
            room = get_object_or_404(
                Room, pk=room_id, floor__building__dormitory=dorm
            )
            room.status = 'occupied'
            room.save()

        profile = TenantProfile.objects.create(
            user=user,
            room=room,
            phone=phone,
        )

        # Create initial lease with room assignment (canonical multi-unit path)
        if start_date and room:
            Lease.objects.create(
                tenant=profile,
                room=room,
                start_date=start_date,
                status='active',
            )

        # Add activity log
        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='tenant_added',
            detail={'profile_id': profile.pk, 'name': profile.full_name},
        )
        messages.success(request, _('Tenant added successfully.'))
        return redirect('tenants:detail', pk=profile.pk)



class TenantUpdateView(StaffRequiredMixin, View):
    def get(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        profile = get_object_or_404(_dorm_profiles(request.user, dormitory=dorm), pk=pk)
        from apps.rooms.models import Room
        available_rooms = Room.objects.filter(
            floor__building__dormitory=dorm,
        ).select_related('floor', 'floor__building')
        active_room = profile.active_room
        data = {
            'username': profile.user.username,
            'first_name': profile.user.first_name,
            'last_name': profile.user.last_name,
            'phone': profile.phone,
            'room': str(active_room.pk) if active_room else '',
        }
        return render(request, 'tenants/form.html', {
            'object': profile,
            'available_rooms': available_rooms,
            'form': SimpleForm(data),
        })

    def post(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        profile = get_object_or_404(_dorm_profiles(request.user, dormitory=dorm), pk=pk)
        data = request.POST
        profile.user.first_name = data.get('first_name', '').strip()
        profile.user.last_name = data.get('last_name', '').strip()
        profile.user.save()
        profile.phone = data.get('phone', '').strip()

        room_id = data.get('room', '')
        if room_id:
            from apps.rooms.models import Room
            room = get_object_or_404(
                Room, pk=room_id, floor__building__dormitory=dorm
            )
            profile.room = room
        profile.save()

        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='tenant_updated',
            detail={'profile_id': profile.pk, 'name': profile.full_name},
        )
        messages.success(request, _('Tenant updated successfully.'))
        return redirect('tenants:detail', pk=profile.pk)


class AnonymizeTenantView(OwnerRequiredMixin, View):
    """
    POST /tenants/<pk>/anonymize/ — PDPA Right to be Forgotten
    ล้างข้อมูลส่วนบุคคลของผู้เช่า (irreversible action)
    ต้อง POST พร้อม confirm=true เพื่อยืนยัน
    เฉพาะ owner/superadmin เท่านั้น — ไม่ให้ staff ทำ
    """

    def get(self, request, pk):
        """แสดง confirm dialog ก่อน anonymize"""
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        profile = get_object_or_404(_dorm_profiles(request.user, dormitory=dorm), pk=pk)
        return render(request, 'tenants/anonymize_confirm.html', {'profile': profile})

    def post(self, request, pk):
        """
        ดำเนินการ anonymize — ต้องส่ง confirm=true
        ถ้าไม่มี confirm → 400 Bad Request
        ถ้า tenant ไม่อยู่ใน dormitory ของ owner → 404 (IDOR protection)
        """
        from django.http import HttpResponseBadRequest

        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        # tenant isolation: เฉพาะ profile ที่อยู่ใน dormitory ของ owner เท่านั้น
        profile = get_object_or_404(_dorm_profiles(request.user, dormitory=dorm), pk=pk)

        if request.POST.get('confirm') != 'true':
            return HttpResponseBadRequest('Confirmation required. Send confirm=true to proceed.')

        # ดำเนินการ anonymize — irreversible
        profile.anonymize(performed_by=request.user)

        messages.success(
            request,
            _('Personal data for %(name)s has been anonymized (PDPA).') % {'name': str(pk)},
        )
        return redirect('tenants:list')


class TenantHomeView(LoginRequiredMixin, View):
    """Tenant self-service home page (accessible at /tenant/home/)."""

    def get(self, request):
        user = request.user
        if user.role not in ('tenant',):
            return redirect('dashboard:index')

        try:
            profile = user.tenant_profile
        except TenantProfile.DoesNotExist:
            messages.info(request, _('No tenant profile found. Please contact your dormitory manager.'))
            return render(request, 'tenants/tenant_home.html', {'profile': None})

        from apps.notifications.models import Parcel
        from apps.maintenance.models import MaintenanceTicket
        from apps.billing.models import Bill

        active_leases = list(
            profile.leases.filter(status='active').select_related('room').order_by('-start_date')
        )
        leases = profile.leases.select_related('room').order_by('-start_date')
        active_rooms = [lease.room for lease in active_leases if lease.room]

        # Primary room is the most recent active lease's room (fallback to legacy FK)
        primary_room = active_rooms[0] if active_rooms else profile.room

        current_bill = None
        latest_meter = None
        pending_parcel = None
        maintenance_tickets = []

        if primary_room:
            current_bill = primary_room.bills.order_by('-month').first()
            latest_meter = primary_room.meter_readings.order_by('-reading_date').first()
            pending_parcel = primary_room.parcels.filter(
                notified_at__isnull=False
            ).order_by('-notified_at').first()
            maintenance_tickets = MaintenanceTicket.objects.filter(
                room__in=active_rooms or [primary_room]
            ).order_by('-created_at')[:5]

        # All bills across all leased rooms
        all_bills = Bill.objects.filter(
            room__leases__tenant=profile
        ).order_by('-month').distinct()[:12]

        return render(request, 'tenants/tenant_home.html', {
            'profile': profile,
            'active_leases': active_leases,
            'active_rooms': active_rooms,
            'primary_room': primary_room,
            'current_bill': current_bill,
            'latest_meter': latest_meter,
            'pending_parcel': pending_parcel,
            'leases': leases,
            'all_bills': all_bills,
            'maintenance_tickets': maintenance_tickets,
        })


class TenantBillDetailView(LoginRequiredMixin, View):
    """Tenant bill detail with payment QR."""

    def get(self, request, pk):
        user = request.user
        if user.role not in ('tenant',):
            return redirect('dashboard:index')

        try:
            profile = user.tenant_profile
        except TenantProfile.DoesNotExist:
            return redirect('tenant:home')

        from apps.billing.models import Bill
        bill = get_object_or_404(
            Bill.objects.select_related(
                'room__floor__building__dormitory',
                'meter_reading',
            ).prefetch_related('line_items__charge_type'),
            pk=pk, room__leases__tenant=profile
        )
        payment = getattr(bill, 'payment', None)
        line_items = bill.line_items.all()

        # TMR QR URL (if bill is unpaid and dormitory has TMR configured)
        tmr_qr_url = None
        try:
            billing_settings = bill.room.floor.building.dormitory.billing_settings
            if billing_settings.tmr_api_key and bill.status in ('sent', 'overdue'):
                tmr_qr_url = f"https://payment.tmr.th/qr/{billing_settings.tmr_api_key}/{bill.invoice_number}"
        except Exception:
            pass

        return render(request, 'tenants/tenant_bill_detail.html', {
            'bill': bill,
            'payment': payment,
            'line_items': line_items,
            'tmr_qr_url': tmr_qr_url,
        })


class TenantBillsView(LoginRequiredMixin, View):
    """Tenant bill history page."""

    def get(self, request):
        user = request.user
        if user.role not in ('tenant',):
            return redirect('dashboard:index')

        try:
            profile = user.tenant_profile
        except TenantProfile.DoesNotExist:
            return redirect('tenant:home')

        from apps.billing.models import Bill
        all_bills = Bill.objects.filter(
            room__leases__tenant=profile
        ).order_by('-month').distinct()

        return render(request, 'tenants/tenant_bills.html', {
            'profile': profile,
            'all_bills': all_bills,
        })


class TenantParcelsView(LoginRequiredMixin, View):
    """Tenant parcel history page."""

    def get(self, request):
        user = request.user
        if user.role not in ('tenant',):
            return redirect('dashboard:index')

        try:
            profile = user.tenant_profile
        except TenantProfile.DoesNotExist:
            return redirect('tenant:home')

        from apps.notifications.models import Parcel
        active_rooms = list(
            profile.leases.filter(status='active').values_list('room', flat=True)
        )
        if not active_rooms and profile.room:
            active_rooms = [profile.room.pk]

        parcels = Parcel.objects.filter(room__in=active_rooms).order_by('-created_at')

        return render(request, 'tenants/tenant_parcels.html', {
            'profile': profile,
            'parcels': parcels,
        })


class TenantProfileView(LoginRequiredMixin, View):
    """Tenant profile page."""

    def get(self, request):
        user = request.user
        if user.role not in ('tenant',):
            return redirect('dashboard:index')

        try:
            profile = user.tenant_profile
        except TenantProfile.DoesNotExist:
            return redirect('tenant:home')

        leases = profile.leases.select_related('room').order_by('-start_date')

        return render(request, 'tenants/tenant_profile.html', {
            'profile': profile,
            'leases': leases,
        })



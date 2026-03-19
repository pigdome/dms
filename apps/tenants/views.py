from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from apps.tenants.models import TenantProfile, Lease

from apps.core.decorators import staff_required
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


@method_decorator([login_required, staff_required], name='dispatch')
class TenantListView(View):
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


@method_decorator(login_required, name='dispatch')
class TenantDetailView(View):
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


@method_decorator([login_required, staff_required], name='dispatch')
class TenantCreateView(View):
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


@method_decorator([login_required, staff_required], name='dispatch')
class TenantImportView(View):
    """Import tenants from CSV or Excel (xlsx) file."""

    REQUIRED_COLS = {'username', 'first_name', 'last_name'}

    def get(self, request):
        return render(request, 'tenants/import.html', {
            'sample_headers': 'username,first_name,last_name,phone,room_number,start_date,password',
        })

    def post(self, request):
        from apps.core.models import CustomUser
        from apps.rooms.models import Room

        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        upload = request.FILES.get('file')
        if not upload:
            messages.error(request, _('Please upload a CSV or Excel file.'))
            return redirect('tenants:import')

        ext = upload.name.rsplit('.', 1)[-1].lower()
        try:
            rows = self._parse_file(upload, ext)
        except Exception as e:
            messages.error(request, _('Could not read file: %(err)s') % {'err': str(e)})
            return redirect('tenants:import')

        created, skipped, errors = 0, 0, []
        for i, row in enumerate(rows, start=2):
            username = str(row.get('username', '')).strip()
            if not username:
                skipped += 1
                continue
            if CustomUser.objects.filter(username=username).exists():
                errors.append(_('Row %(n)s: username "%(u)s" already exists.') % {'n': i, 'u': username})
                skipped += 1
                continue

            user = CustomUser.objects.create_user(
                username=username,
                password=str(row.get('password', username)).strip() or username,
                first_name=str(row.get('first_name', '')).strip(),
                last_name=str(row.get('last_name', '')).strip(),
                role='tenant',
                dormitory=dorm,
            )
            room = None
            room_number = str(row.get('room_number', '')).strip()
            if room_number:
                room = Room.objects.filter(
                    number=room_number, floor__building__dormitory=dorm
                ).first()
                if room:
                    room.status = 'occupied'
                    room.save(update_fields=['status'])

            profile = TenantProfile.objects.create(
                user=user,
                room=room,
                phone=str(row.get('phone', '')).strip(),
            )
            start_date = str(row.get('start_date', '')).strip()
            if start_date and room:
                try:
                    Lease.objects.create(tenant=profile, room=room, start_date=start_date, status='active')
                except Exception:
                    pass
            created += 1

        if errors:
            for err in errors[:5]:
                messages.warning(request, err)
        messages.success(request, _('Import complete: %(c)s created, %(s)s skipped.') % {'c': created, 's': skipped})
        return redirect('tenants:list')

    def _parse_file(self, upload, ext):
        if ext == 'csv':
            import csv, io
            text = upload.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(text))
            return [dict(row) for row in reader]
        else:
            import openpyxl
            wb = openpyxl.load_workbook(upload, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return []
            headers = [str(h).strip().lower() if h else '' for h in rows[0]]
            result = []
            for row in rows[1:]:
                if not any(row):
                    continue
                result.append({headers[i]: (str(v).strip() if v is not None else '') for i, v in enumerate(row)})
            return result


@method_decorator([login_required, staff_required], name='dispatch')
class TenantUpdateView(View):
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


@method_decorator(login_required, name='dispatch')
class TenantHomeView(View):
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


@method_decorator(login_required, name='dispatch')
class TenantBillDetailView(View):
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
            Bill.objects.select_related('room__floor__building__dormitory'),
            pk=pk, room__leases__tenant=profile
        )
        payment = getattr(bill, 'payment', None)

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
            'tmr_qr_url': tmr_qr_url,
        })


@method_decorator(login_required, name='dispatch')
class TenantBillsView(View):
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


@method_decorator(login_required, name='dispatch')
class TenantParcelsView(View):
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


@method_decorator(login_required, name='dispatch')
class TenantProfileView(View):
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



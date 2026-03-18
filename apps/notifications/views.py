from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.notifications.models import Parcel, Broadcast


def staff_required(view_func):
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:login')
        if request.user.role == 'tenant':
            return redirect('tenant:home')
        return view_func(request, *args, **kwargs)

    return wrapper


def _dorm_rooms(user, dormitory=None):
    from apps.rooms.models import Room
    dorm = dormitory or user.dormitory
    return Room.objects.filter(
        floor__building__dormitory=dorm
    ).select_related('floor', 'floor__building').prefetch_related('tenant_profiles__user')


@method_decorator([login_required, staff_required], name='dispatch')
class ParcelCreateView(View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        return render(request, 'notifications/parcel_log.html', {
            'rooms': _dorm_rooms(request.user, dormitory=dorm),
            'form': _SimpleForm({}),
        })

    def post(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        data = request.POST
        room_id = data.get('room')
        carrier = data.get('carrier', '').strip()
        notes = data.get('notes', '').strip()

        if not room_id or not carrier:
            messages.error(request, _('Please fill in all required fields.'))
            return render(request, 'notifications/parcel_log.html', {
                'rooms': _dorm_rooms(request.user, dormitory=dorm),
                'form': _SimpleForm(data),
            })

        if 'photo' not in request.FILES:
            messages.error(request, _('Please upload a photo of the parcel.'))
            return render(request, 'notifications/parcel_log.html', {
                'rooms': _dorm_rooms(request.user, dormitory=dorm),
                'form': _SimpleForm(data),
            })

        from apps.rooms.models import Room
        room = get_object_or_404(Room, pk=room_id, floor__building__dormitory=dorm)

        parcel = Parcel.objects.create(
            room=room,
            photo=request.FILES['photo'],
            carrier=carrier,
            notes=notes,
            logged_by=request.user,
            notified_at=timezone.now(),  # mark as notified immediately
        )

        messages.success(request, _('Parcel logged and tenant notified.'))
        return redirect('notifications:parcel_list')


@method_decorator([login_required, staff_required], name='dispatch')
class ParcelListView(View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        parcels = Parcel.objects.filter(
            room__floor__building__dormitory=dorm
        ).select_related('room', 'room__floor__building').order_by('-notified_at')[:100]
        return render(request, 'notifications/parcel_list.html', {'parcels': parcels})


@method_decorator([login_required, staff_required], name='dispatch')
class BroadcastCreateView(View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        recent_broadcasts = Broadcast.objects.filter(dormitory=dorm)[:5] if dorm else []
        return render(request, 'notifications/broadcast.html', {
            'form': _SimpleForm({}),
            'recent_broadcasts': recent_broadcasts,
        })

    def post(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        data = request.POST
        title = data.get('title', '').strip()
        body = data.get('body', '').strip()
        audience_type = data.get('audience_type', 'all')
        audience_ref = data.get('audience_ref', '').strip()

        if not title or not body:
            messages.error(request, _('Title and body are required.'))
            return render(request, 'notifications/broadcast.html', {
                'form': _SimpleForm(data),
                'recent_broadcasts': Broadcast.objects.filter(dormitory=dorm)[:5] if dorm else [],
            })

        if not dorm:
            messages.error(request, _('No dormitory associated with your account.'))
            return redirect('dashboard:index')

        bc = Broadcast(
            dormitory=dorm,
            title=title,
            body=body,
            audience_type=audience_type,
            audience_ref=audience_ref,
            sent_by=request.user,
            sent_at=timezone.now(),
        )
        if 'attachment' in request.FILES:
            bc.attachment = request.FILES['attachment']
        bc.save()

        messages.success(request, _('Broadcast sent successfully.'))
        return redirect('notifications:broadcast')


class _SimpleForm:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        class _Field:
            def __init__(self, val):
                self._val = val
                self.errors = []

            def value(self):
                return self._val

        return _Field(self._data.get(name, ''))

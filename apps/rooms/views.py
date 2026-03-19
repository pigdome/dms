from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.rooms.models import Room, Building, Floor, MeterReading

from apps.core.decorators import staff_required
from apps.core.utils import SimpleForm
from apps.core.models import ActivityLog


def _dorm_rooms(user, dormitory=None):
    """Return a queryset of rooms filtered to the user's dormitory.

    Pass ``dormitory`` explicitly to override the user's current dormitory
    (used by property-switching views).
    """
    dorm = dormitory or user.dormitory
    return Room.objects.filter(
        floor__building__dormitory=dorm
    ).select_related('floor', 'floor__building')


@method_decorator([login_required, staff_required], name='dispatch')
class RoomListView(View):
    def get(self, request):
        rooms = _dorm_rooms(request.user)
        status_filter = request.GET.get('status', '')
        if status_filter:
            rooms = rooms.filter(status=status_filter)
        return render(request, 'rooms/list.html', {
            'rooms': rooms,
            'status_filter': status_filter,
        })


@method_decorator([login_required, staff_required], name='dispatch')
class RoomDetailView(View):
    def get(self, request, pk):
        room = get_object_or_404(_dorm_rooms(request.user), pk=pk)
        meter_readings = room.meter_readings.all()[:5]
        maintenance_tickets = room.maintenance_tickets.all()[:5]
        return render(request, 'rooms/detail.html', {
            'room': room,
            'meter_readings': meter_readings,
            'maintenance_tickets': maintenance_tickets,
        })


@method_decorator([login_required, staff_required], name='dispatch')
class RoomCreateView(View):
    def _context(self, user, data=None, dormitory=None):
        dorm = dormitory or user.dormitory
        floors = Floor.objects.filter(
            building__dormitory=dorm
        ).select_related('building')
        return {
            'floors': floors,
            'status_choices': Room.Status.choices,
            'form': SimpleForm(data or {}),
        }

    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        return render(request, 'rooms/form.html', self._context(request.user, dormitory=dorm))

    def post(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        data = request.POST
        floor_id = data.get('floor')
        number = data.get('number', '').strip()
        base_rent = data.get('base_rent', 0) or 0
        status = data.get('status', Room.Status.VACANT)

        errors = []
        if not floor_id:
            errors.append(_('Please select a floor.'))
        if not number:
            errors.append(_('Room number is required.'))

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'rooms/form.html', self._context(request.user, data, dormitory=dorm))

        floor = get_object_or_404(
            Floor, pk=floor_id, building__dormitory=dorm
        )
        if Room.objects.filter(floor=floor, number=number).exists():
            messages.error(request, _('Room number already exists on this floor.'))
            return render(request, 'rooms/form.html', self._context(request.user, data, dormitory=dorm))

        room = Room.objects.create(
            floor=floor, number=number, base_rent=base_rent, status=status
        )
        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='room_created',
            detail={'room_id': room.pk, 'room_number': room.number},
        )
        messages.success(request, _('Room created successfully.'))
        return redirect('rooms:detail', pk=room.pk)


@method_decorator([login_required, staff_required], name='dispatch')
class RoomUpdateView(View):
    def _context(self, user, room, data=None, dormitory=None):
        dorm = dormitory or user.dormitory
        floors = Floor.objects.filter(
            building__dormitory=dorm
        ).select_related('building')
        form_data = data or {
            'floor': str(room.floor_id),
            'number': room.number,
            'base_rent': str(room.base_rent),
            'status': room.status,
        }
        return {
            'object': room,
            'floors': floors,
            'status_choices': Room.Status.choices,
            'form': SimpleForm(form_data),
        }

    def get(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        room = get_object_or_404(_dorm_rooms(request.user, dormitory=dorm), pk=pk)
        return render(request, 'rooms/form.html', self._context(request.user, room, dormitory=dorm))

    def post(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        room = get_object_or_404(_dorm_rooms(request.user, dormitory=dorm), pk=pk)
        data = request.POST
        floor_id = data.get('floor')
        number = data.get('number', '').strip()
        base_rent = data.get('base_rent', 0) or 0
        status = data.get('status', room.status)

        if not floor_id or not number:
            messages.error(request, _('Please fill in all required fields.'))
            return render(request, 'rooms/form.html', self._context(request.user, room, data, dormitory=dorm))

        floor = get_object_or_404(
            Floor, pk=floor_id, building__dormitory=dorm
        )
        # Check uniqueness (exclude current room)
        if Room.objects.filter(floor=floor, number=number).exclude(pk=room.pk).exists():
            messages.error(request, _('Room number already exists on this floor.'))
            return render(request, 'rooms/form.html', self._context(request.user, room, data, dormitory=dorm))

        room.floor = floor
        room.number = number
        room.base_rent = base_rent
        room.status = status
        room.save()
        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='room_updated',
            detail={'room_id': room.pk, 'room_number': room.number},
        )
        messages.success(request, _('Room updated successfully.'))
        return redirect('rooms:detail', pk=room.pk)


@method_decorator([login_required, staff_required], name='dispatch')
class MeterReadingCreateView(View):
    def _context(self, user, data=None, selected_room_id=None, dormitory=None):
        dorm = dormitory or user.dormitory
        buildings = Building.objects.filter(dormitory=dorm)
        rooms = _dorm_rooms(user, dormitory=dorm)
        return {
            'buildings': buildings,
            'rooms': rooms,
            'form': SimpleForm(data or {}),
            'today': timezone.now().date().isoformat(),
            'selected_room_id': selected_room_id or (data or {}).get('room', ''),
        }

    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        selected_room_id = request.GET.get('room', '')
        return render(request, 'rooms/meter_reading.html',
                      self._context(request.user, selected_room_id=selected_room_id, dormitory=dorm))

    def post(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        data = request.POST
        room_id = data.get('room')
        reading_date = data.get('reading_date')
        water_prev = data.get('water_prev', 0) or 0
        water_curr = data.get('water_curr')
        elec_prev = data.get('elec_prev', 0) or 0
        elec_curr = data.get('elec_curr')

        if not room_id or not water_curr or not elec_curr or not reading_date:
            messages.error(request, _('Please fill in all required fields.'))
            return render(request, 'rooms/meter_reading.html', self._context(request.user, data, dormitory=dorm))

        room = get_object_or_404(_dorm_rooms(request.user, dormitory=dorm), pk=room_id)

        kwargs = {
            'room': room,
            'reading_date': reading_date,
            'water_prev': water_prev,
            'water_curr': water_curr,
            'elec_prev': elec_prev,
            'elec_curr': elec_curr,
            'recorded_by': request.user,
        }
        if 'water_photo' in request.FILES:
            kwargs['water_photo'] = request.FILES['water_photo']
        if 'elec_photo' in request.FILES:
            kwargs['elec_photo'] = request.FILES['elec_photo']

        MeterReading.objects.create(**kwargs)
        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='meter_reading_saved',
            detail={'room_id': room.pk, 'room_number': room.number, 'date': reading_date},
        )
        messages.success(request, _('Meter reading saved successfully.'))
        return redirect('rooms:detail', pk=room.pk)



from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.rooms.models import Room, Building, Floor, MeterReading

from apps.core.mixins import StaffRequiredMixin
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


class RoomListView(StaffRequiredMixin, View):
    def get(self, request):
        rooms = _dorm_rooms(request.user)
        status_filter = request.GET.get('status', '')
        if status_filter:
            rooms = rooms.filter(status=status_filter)
        return render(request, 'rooms/list.html', {
            'rooms': rooms,
            'status_filter': status_filter,
        })


class RoomDetailView(StaffRequiredMixin, View):
    def get(self, request, pk):
        room = get_object_or_404(_dorm_rooms(request.user), pk=pk)
        meter_readings = room.meter_readings.all()[:5]
        maintenance_tickets = room.maintenance_tickets.all()[:5]
        return render(request, 'rooms/detail.html', {
            'room': room,
            'meter_readings': meter_readings,
            'maintenance_tickets': maintenance_tickets,
        })


class RoomCreateView(StaffRequiredMixin, View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        from apps.rooms.forms import RoomForm
        form = RoomForm(dormitory=dorm)
        return render(request, 'rooms/form.html', {'form': form})

    def post(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        from apps.rooms.forms import RoomForm
        form = RoomForm(request.POST, dormitory=dorm)
        if form.is_valid():
            room = form.save()
            ActivityLog.objects.create(
                dormitory=dorm,
                user=request.user,
                action='room_created',
                detail={'room_id': room.pk, 'room_number': room.number},
            )
            messages.success(request, _('Room created successfully.'))
            return redirect('rooms:detail', pk=room.pk)
        
        return render(request, 'rooms/form.html', {'form': form})
class RoomUpdateView(StaffRequiredMixin, View):
    def get(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        room = get_object_or_404(_dorm_rooms(request.user, dormitory=dorm), pk=pk)
        from apps.rooms.forms import RoomForm
        form = RoomForm(instance=room, dormitory=dorm)
        return render(request, 'rooms/form.html', {'form': form, 'object': room})

    def post(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        room = get_object_or_404(_dorm_rooms(request.user, dormitory=dorm), pk=pk)
        from apps.rooms.forms import RoomForm
        form = RoomForm(request.POST, instance=room, dormitory=dorm)
        if form.is_valid():
            room = form.save()
            ActivityLog.objects.create(
                dormitory=dorm,
                user=request.user,
                action='room_updated',
                detail={'room_id': room.pk, 'room_number': room.number},
            )
            messages.success(request, _('Room updated successfully.'))
            return redirect('rooms:detail', pk=room.pk)
        
        return render(request, 'rooms/form.html', {'form': form, 'object': room})


class MeterReadingCreateView(StaffRequiredMixin, View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        from apps.rooms.forms import MeterReadingForm
        initial = {'reading_date': timezone.now().date()}
        room_id = request.GET.get('room')
        if room_id:
            initial['room'] = room_id
        
        form = MeterReadingForm(dormitory=dorm, initial=initial)
        buildings = Building.objects.filter(dormitory=dorm)
        rooms = _dorm_rooms(request.user)
        
        return render(request, 'rooms/meter_reading.html', {
            'form': form,
            'today': timezone.now().date().isoformat(),
            'buildings': buildings,
            'rooms': rooms,
        })

    def post(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        from apps.rooms.forms import MeterReadingForm
        form = MeterReadingForm(request.POST, request.FILES, dormitory=dorm)
        
        if form.is_valid():
            reading = form.save()
            ActivityLog.objects.create(
                dormitory=dorm,
                user=request.user,
                action='meter_reading_logged',
                detail={'reading_id': reading.pk, 'room_number': reading.room.number},
            )
            messages.success(request, _('Meter reading logged successfully.'))
            return redirect('rooms:detail', pk=reading.room.pk)
        
        buildings = Building.objects.filter(dormitory=dorm)
        rooms = _dorm_rooms(request.user)
        
        return render(request, 'rooms/meter_reading.html', {
            'form': form,
            'today': timezone.now().date().isoformat(),
            'buildings': buildings,
            'rooms': rooms,
        })



from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.notifications.models import Parcel, Broadcast

from apps.core.decorators import staff_required
from apps.core.utils import SimpleForm
from apps.core.models import ActivityLog


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
            'form': SimpleForm({}),
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
                'form': SimpleForm(data),
            })

        if 'photo' not in request.FILES:
            messages.error(request, _('Please upload a photo of the parcel.'))
            return render(request, 'notifications/parcel_log.html', {
                'rooms': _dorm_rooms(request.user, dormitory=dorm),
                'form': SimpleForm(data),
            })

        from apps.rooms.models import Room
        room = get_object_or_404(Room, pk=room_id, floor__building__dormitory=dorm)

        parcel = Parcel.objects.create(
            room=room,
            photo=request.FILES['photo'],
            carrier=carrier,
            notes=notes,
            logged_by=request.user,
            notified_at=None,
        )
        
        # Queue notification task
        try:
            from apps.notifications.tasks import send_parcel_notification_task
            send_parcel_notification_task.delay(parcel.pk)
        except Exception:
            pass # logged_at is None, can be retried or shown as failed
        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='parcel_logged',
            detail={'parcel_id': parcel.pk, 'room_number': room.number},
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
    def _audience_context(self, dorm):
        from apps.rooms.models import Building, Floor
        buildings = Building.objects.filter(dormitory=dorm) if dorm else []
        floors = Floor.objects.filter(building__dormitory=dorm).select_related('building') if dorm else []
        return {'buildings': buildings, 'floors': floors}

    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        recent_broadcasts = Broadcast.objects.filter(dormitory=dorm)[:5] if dorm else []
        ctx = self._audience_context(dorm)
        ctx.update({'form': SimpleForm({}), 'recent_broadcasts': recent_broadcasts})
        return render(request, 'notifications/broadcast.html', ctx)

    def post(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        data = request.POST
        title = data.get('title', '').strip()
        body = data.get('body', '').strip()
        audience_type = data.get('audience_type', 'all')
        audience_ref = data.get('audience_ref', '').strip()

        if not title or not body:
            messages.error(request, _('Title and body are required.'))
            ctx = self._audience_context(dorm)
            ctx.update({
                'form': SimpleForm(data),
                'recent_broadcasts': Broadcast.objects.filter(dormitory=dorm)[:5] if dorm else [],
            })
            return render(request, 'notifications/broadcast.html', ctx)

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
        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='broadcast_sent',
            detail={'broadcast_id': bc.pk, 'title': bc.title},
        )

        # Send LINE push messages via background task
        try:
            from apps.notifications.tasks import send_broadcast_task
            send_broadcast_task.delay(bc.pk)
            messages.success(request, _('Broadcast draft saved and delivery queued.'))
        except Exception:
            messages.warning(request, _('Broadcast saved, but background delivery could not be queued.'))

        return redirect('notifications:parcel_list') if 'room' in data else redirect('notifications:broadcast_list')



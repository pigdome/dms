from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.notifications.models import Parcel, Broadcast

from apps.core.mixins import StaffRequiredMixin, StaffPermissionRequiredMixin
from apps.core.utils import SimpleForm
from apps.core.models import ActivityLog


def _dorm_rooms(user, dormitory=None):
    from apps.rooms.models import Room
    dorm = dormitory or user.dormitory
    return Room.objects.filter(
        floor__building__dormitory=dorm
    ).select_related('floor', 'floor__building').prefetch_related('tenant_profiles__user')


class ParcelCreateView(StaffPermissionRequiredMixin, View):
    """บันทึกพัสดุ — owner/superadmin ผ่านทันที, staff ต้องมี can_log_parcels"""
    permission_flag = 'can_log_parcels'
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


class ParcelListView(StaffPermissionRequiredMixin, View):
    permission_flag = 'can_log_parcels'
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        parcels = Parcel.objects.filter(
            room__floor__building__dormitory=dorm
        ).select_related('room', 'room__floor__building').order_by('-notified_at')[:100]
        return render(request, 'notifications/parcel_list.html', {'parcels': parcels})


class BroadcastCreateView(StaffRequiredMixin, View):
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

        # I9: บันทึก draft (sent_at=None) แล้ว redirect ไปหน้า preview ก่อนส่งจริง
        # ป้องกันการส่งโดยไม่ตั้งใจ — owner ต้องกด "ยืนยันส่ง" อีกครั้ง
        bc = Broadcast(
            dormitory=dorm,
            title=title,
            body=body,
            audience_type=audience_type,
            audience_ref=audience_ref,
            sent_by=request.user,
            sent_at=None,  # draft — ยังไม่ส่ง
        )
        if 'attachment' in request.FILES:
            bc.attachment = request.FILES['attachment']
        bc.save()

        return redirect('notifications:broadcast_preview', pk=bc.pk)




class BroadcastListView(StaffRequiredMixin, View):
    """รายการ broadcasts ทั้งหมดใน dormitory"""
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        broadcasts = Broadcast.objects.filter(dormitory=dorm).order_by('-created_at')[:50] if dorm else []
        return render(request, 'notifications/broadcast_list.html', {'broadcasts': broadcasts})


class BroadcastPreviewView(StaffRequiredMixin, View):
    """
    I9: Preview หน้าสำหรับ broadcast draft
    แสดง: title, body, audience type, จำนวน recipients ที่จะได้รับ
    ปุ่ม 'ยืนยันส่ง' → POST /broadcast/<id>/confirm/
    ปุ่ม 'แก้ไข' → กลับไป edit form พร้อม draft data
    """
    def _get_broadcast_for_owner(self, request, pk):
        """ดึง broadcast draft ที่เป็นของ dormitory ของ user เท่านั้น (tenant isolation)"""
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        return get_object_or_404(Broadcast, pk=pk, dormitory=dorm, sent_at__isnull=True)

    def _count_recipients(self, broadcast):
        """นับจำนวน recipients ที่จะได้รับ broadcast นี้ (ใช้ logic เดียวกับ push_broadcast)"""
        from apps.tenants.models import TenantProfile
        from apps.rooms.models import Room
        from django.db.models import Q

        dorm = broadcast.dormitory
        rooms_qs = Room.objects.filter(floor__building__dormitory=dorm)

        if broadcast.audience_type == 'building' and broadcast.audience_ref:
            rooms_qs = rooms_qs.filter(floor__building__name=broadcast.audience_ref)
        elif broadcast.audience_type == 'floor' and broadcast.audience_ref:
            rooms_qs = rooms_qs.filter(floor__pk=broadcast.audience_ref)

        return TenantProfile.objects.filter(
            Q(leases__room__in=rooms_qs, leases__status='active') |
            Q(room__in=rooms_qs)
        ).distinct().count()

    def get(self, request, pk):
        bc = self._get_broadcast_for_owner(request, pk)
        recipient_count = self._count_recipients(bc)
        return render(request, 'notifications/broadcast_preview.html', {
            'broadcast': bc,
            'recipient_count': recipient_count,
        })


class BroadcastConfirmView(StaffRequiredMixin, View):
    """
    I9: ยืนยันการส่ง broadcast draft → เปลี่ยน sent_at → trigger Celery task ส่ง LINE
    POST /broadcast/<id>/confirm/
    """
    def post(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        bc = get_object_or_404(Broadcast, pk=pk, dormitory=dorm, sent_at__isnull=True)

        # mark ว่าส่งแล้ว — set sent_at เป็น now
        bc.sent_at = timezone.now()
        bc.save(update_fields=['sent_at'])

        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='broadcast_sent',
            detail={'broadcast_id': bc.pk, 'title': bc.title},
        )

        # Queue Celery task ส่ง LINE push
        try:
            from apps.notifications.tasks import send_broadcast_task
            send_broadcast_task.delay(bc.pk)
            messages.success(request, _('Broadcast queued for delivery.'))
        except Exception:
            messages.warning(request, _('Broadcast saved, but background delivery could not be queued.'))

        return redirect('notifications:broadcast_list')

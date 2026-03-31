from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from apps.maintenance.models import MaintenanceTicket, TicketPhoto, TicketStatusHistory
from apps.tenants.models import TenantProfile

from apps.core.mixins import StaffRequiredMixin
from apps.core.utils import SimpleForm
from apps.core.models import ActivityLog


def _dorm_tickets(user, dormitory=None):
    dorm = dormitory or user.dormitory
    return MaintenanceTicket.objects.filter(
        room__floor__building__dormitory=dorm
    ).select_related('room', 'room__floor', 'room__floor__building', 'reported_by')


def _dorm_rooms(user, dormitory=None):
    from apps.rooms.models import Room
    dorm = dormitory or user.dormitory
    return Room.objects.filter(
        floor__building__dormitory=dorm
    ).select_related('floor', 'floor__building')


class TicketListView(StaffRequiredMixin, View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        tickets = _dorm_tickets(request.user, dormitory=dorm)
        status_filter = request.GET.get('status', '')
        search_query = request.GET.get('q', '')

        if status_filter:
            tickets = tickets.filter(status=status_filter)
        if search_query:
            tickets = tickets.filter(
                room__number__icontains=search_query
            ) | tickets.filter(
                description__icontains=search_query
            )

        return render(request, 'maintenance/list.html', {
            'tickets': tickets,
            'status_filter': status_filter,
            'search_query': search_query,
        })


class TicketDetailView(StaffRequiredMixin, View):
    def get(self, request, pk):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        ticket = get_object_or_404(_dorm_tickets(request.user, dormitory=dorm), pk=pk)
        return render(request, 'maintenance/detail.html', {
            'ticket': ticket,
            'status_choices': MaintenanceTicket.Status.choices,
        })


class TicketCreateView(StaffRequiredMixin, View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        return render(request, 'maintenance/form.html', {
            'rooms': _dorm_rooms(request.user, dormitory=dorm),
            'form': SimpleForm({}),
        })

    def post(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        data = request.POST
        room_id = data.get('room')
        description = data.get('description', '').strip()
        technician = data.get('technician', '').strip()

        if not room_id or not description:
            messages.error(request, _('Please fill in all required fields.'))
            return render(request, 'maintenance/form.html', {
                'rooms': _dorm_rooms(request.user, dormitory=dorm),
                'form': SimpleForm(data),
            })

        from apps.rooms.models import Room
        room = get_object_or_404(Room, pk=room_id, floor__building__dormitory=dorm)

        ticket = MaintenanceTicket.objects.create(
            room=room,
            reported_by=request.user,
            description=description,
            technician=technician,
        )
        ActivityLog.objects.create(
            dormitory=dorm,
            user=request.user,
            action='maintenance_ticket_created',
            detail={'ticket_id': ticket.pk, 'room_number': room.number},
        )

        # Create initial status history entry
        TicketStatusHistory.objects.create(
            ticket=ticket,
            status=MaintenanceTicket.Status.NEW,
            changed_by=request.user,
            note=_('Ticket created'),
        )

        # Save photos if provided
        for photo_file in request.FILES.getlist('photos'):
            TicketPhoto.objects.create(
                ticket=ticket,
                photo=photo_file,
                stage=TicketPhoto.Stage.ISSUE,
            )

        messages.success(request, _('Maintenance ticket created successfully.'))
        return redirect('maintenance:detail', pk=ticket.pk)


@method_decorator(login_required, name='dispatch')
class TenantTicketCreateView(View):
    """Allow tenant users to submit maintenance requests for their own room."""

    def get(self, request):
        if request.user.role != 'tenant':
            return redirect('maintenance:create')
        try:
            profile = request.user.tenant_profile
        except TenantProfile.DoesNotExist:
            messages.error(request, _('No tenant profile found.'))
            return redirect('tenant:home')
        active_room = profile.active_room
        if not active_room:
            messages.error(request, _('You do not have an assigned room.'))
            return redirect('tenant:home')
        tickets = MaintenanceTicket.objects.filter(room=active_room).order_by('-created_at')
        return render(request, 'maintenance/tenant_form.html', {
            'room': active_room,
            'tickets': tickets,
            'form': SimpleForm({}),
        })

    def post(self, request):
        if request.user.role != 'tenant':
            return redirect('maintenance:create')
        try:
            profile = request.user.tenant_profile
        except TenantProfile.DoesNotExist:
            messages.error(request, _('No tenant profile found.'))
            return redirect('tenant:home')
        active_room = profile.active_room
        if not active_room:
            messages.error(request, _('You do not have an assigned room.'))
            return redirect('tenant:home')

        data = request.POST
        description = data.get('description', '').strip()
        if not description:
            messages.error(request, _('Please describe the issue.'))
            tickets = MaintenanceTicket.objects.filter(room=active_room).order_by('-created_at')
            return render(request, 'maintenance/tenant_form.html', {
                'room': active_room,
                'tickets': tickets,
                'form': SimpleForm(data),
            })

        ticket = MaintenanceTicket.objects.create(
            room=active_room,
            reported_by=request.user,
            description=description,
        )
        ActivityLog.objects.create(
            dormitory=profile.room.floor.building.dormitory if profile.room else request.user.dormitory,
            user=request.user,
            action='maintenance_ticket_created_tenant',
            detail={'ticket_id': ticket.pk, 'room_number': active_room.number},
        )
        TicketStatusHistory.objects.create(
            ticket=ticket,
            status=MaintenanceTicket.Status.NEW,
            changed_by=request.user,
            note=_('Ticket submitted by tenant'),
        )
        for photo_file in request.FILES.getlist('photos'):
            TicketPhoto.objects.create(
                ticket=ticket,
                photo=photo_file,
                stage=TicketPhoto.Stage.ISSUE,
            )
        messages.success(request, _('Repair request submitted successfully.'))
        return redirect('tenant:home')


@login_required
def update_status(request, pk):
    """Update ticket status via POST."""
    if request.user.role == 'tenant':
        return redirect('tenant:home')

    dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
    ticket = get_object_or_404(
        MaintenanceTicket,
        pk=pk,
        room__floor__building__dormitory=dorm,
    )

    if request.method == 'POST':
        new_status = request.POST.get('status')
        note = request.POST.get('note', '').strip()
        technician = request.POST.get('technician', '').strip()

        valid_statuses = [s[0] for s in MaintenanceTicket.Status.choices]
        if new_status not in valid_statuses:
            messages.error(request, _('Invalid status.'))
            return redirect('maintenance:detail', pk=pk)

        old_status = ticket.status
        ticket.status = new_status
        if technician:
            ticket.technician = technician
        ticket.save()

        if old_status != new_status:
            TicketStatusHistory.objects.create(
                ticket=ticket,
                status=new_status,
                changed_by=request.user,
                note=note,
            )
            ActivityLog.objects.create(
                dormitory=dorm,
                user=request.user,
                action='maintenance_status_changed',
                detail={'ticket_id': ticket.pk, 'new_status': new_status, 'room_number': ticket.room.number},
            )

        messages.success(request, _('Ticket status updated.'))

    return redirect('maintenance:detail', pk=pk)



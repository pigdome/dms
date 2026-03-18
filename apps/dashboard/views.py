from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.db.models import Sum
from django.utils import timezone


def staff_required(view_func):
    """Decorator: must be owner or staff (not a tenant user)."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:login')
        if request.user.role == 'tenant':
            return redirect('tenant:home')
        return view_func(request, *args, **kwargs)

    return wrapper


@method_decorator([login_required, staff_required], name='dispatch')
class DashboardView(View):
    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory
        owned_dormitories = request.user.owned_dormitories if request.user.is_owner else []
        context = {
            'total_income': 0,
            'overdue_count': 0,
            'vacant_count': 0,
            'pending_maintenance': 0,
            'recent_activity': [],
            'active_dormitory': dorm,
            'owned_dormitories': owned_dormitories,
        }

        if dorm:
            from apps.rooms.models import Room
            from apps.billing.models import Bill
            from apps.maintenance.models import MaintenanceTicket
            from apps.core.models import ActivityLog

            now = timezone.now()

            rooms_qs = Room.objects.filter(floor__building__dormitory=dorm)

            # Total income this month (paid bills)
            total_income = Bill.objects.filter(
                room__in=rooms_qs,
                status='paid',
                month__year=now.year,
                month__month=now.month,
            ).aggregate(total=Sum('total'))['total'] or 0

            # Overdue rooms
            overdue_count = Bill.objects.filter(
                room__in=rooms_qs,
                status='overdue',
            ).values('room').distinct().count()

            # Vacant rooms
            vacant_count = rooms_qs.filter(status='vacant').count()

            # Pending maintenance tickets
            pending_maintenance = MaintenanceTicket.objects.filter(
                room__in=rooms_qs,
                status__in=['new', 'in_progress', 'waiting_parts'],
            ).count()

            # Recent activity logs
            recent_activity = ActivityLog.objects.filter(dormitory=dorm)[:10]

            context.update({
                'total_income': total_income,
                'overdue_count': overdue_count,
                'vacant_count': vacant_count,
                'pending_maintenance': pending_maintenance,
                'recent_activity': recent_activity,
            })

        return render(request, 'dashboard/index.html', context)

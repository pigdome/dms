from datetime import date

from django.shortcuts import render, redirect
from django.views import View
from django.db.models import Sum, Count, Q
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from apps.core.mixins import OwnerRequiredMixin, StaffRequiredMixin


class DashboardView(StaffRequiredMixin, View):
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
            last_month = now - relativedelta(months=1)

            rooms_qs = Room.objects.filter(floor__building__dormitory=dorm)

            # Total income this month (paid bills)
            total_income = Bill.objects.filter(
                room__in=rooms_qs,
                status='paid',
                month__year=now.year,
                month__month=now.month,
            ).aggregate(total=Sum('total'))['total'] or 0

            # Total income last month (for trend)
            last_month_income = Bill.objects.filter(
                room__in=rooms_qs,
                status='paid',
                month__year=last_month.year,
                month__month=last_month.month,
            ).aggregate(total=Sum('total'))['total'] or 0

            # Income trend: positive = up, negative = down, None = no data
            if last_month_income > 0:
                income_trend = round((total_income - last_month_income) / last_month_income * 100, 1)
            else:
                income_trend = None

            # Overdue bills: count + total amount
            overdue_bills = Bill.objects.filter(room__in=rooms_qs, status='overdue')
            overdue_count = overdue_bills.values('room').distinct().count()
            overdue_amount = overdue_bills.aggregate(total=Sum('total'))['total'] or 0

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
                'last_month_income': last_month_income,
                'income_trend': income_trend,
                'overdue_count': overdue_count,
                'overdue_amount': overdue_amount,
                'vacant_count': vacant_count,
                'pending_maintenance': pending_maintenance,
                'recent_activity': recent_activity,
            })

        return render(request, 'dashboard/index.html', context)


class ReportView(OwnerRequiredMixin, View):
    """
    รายงานสรุปต่อ Building:
    - revenue: ยอดรวม Bill.total ที่ status=paid ในเดือนที่เลือก
    - occupancy %: จำนวนห้อง occupied / ห้องทั้งหมด ใน building
    - outstanding: ยอดรวม Bill.total ที่ status=overdue ใน building

    URL: /reports/?month=YYYY-MM
    Enforce tenant scope: ดู dormitory ของ active session เสมอ
    """

    def get(self, request):
        dorm = getattr(request, 'active_dormitory', None) or request.user.dormitory

        # Default filter = เดือนปัจจุบัน
        now = timezone.now()
        default_month = now.strftime('%Y-%m')
        month_filter = request.GET.get('month', default_month)

        # แปลง month string → date object สำหรับ query
        try:
            filter_date = date.fromisoformat(f'{month_filter}-01')
        except ValueError:
            filter_date = date(now.year, now.month, 1)
            month_filter = default_month

        buildings_data = []

        if dorm:
            from apps.rooms.models import Building
            from django.db.models import Count, Q

            # ดึง buildings พร้อม annotate ทุก metric ใน query เดียว (หลีกเลี่ยง N+1)
            buildings = Building.objects.filter(dormitory=dorm).order_by('name').annotate(
                total_rooms=Count('floors__rooms', distinct=True),
                occupied_rooms=Count(
                    'floors__rooms',
                    filter=Q(floors__rooms__status='occupied'),
                    distinct=True,
                ),
                revenue=Sum(
                    'floors__rooms__bills__total',
                    filter=Q(
                        floors__rooms__bills__status='paid',
                        floors__rooms__bills__month__year=filter_date.year,
                        floors__rooms__bills__month__month=filter_date.month,
                    ),
                ),
                outstanding=Sum(
                    'floors__rooms__bills__total',
                    filter=Q(floors__rooms__bills__status='overdue'),
                ),
            )

            for bldg in buildings:
                total_rooms = bldg.total_rooms or 0
                occupied_rooms = bldg.occupied_rooms or 0
                occupancy_pct = round(occupied_rooms / total_rooms * 100, 1) if total_rooms else 0.0

                buildings_data.append({
                    'building': bldg,
                    'total_rooms': total_rooms,
                    'occupied_rooms': occupied_rooms,
                    'occupancy_pct': occupancy_pct,
                    'revenue': bldg.revenue or 0,
                    'outstanding': bldg.outstanding or 0,
                })

        context = {
            'buildings_data': buildings_data,
            'month_filter': month_filter,
            'default_month': default_month,
            'active_dormitory': dorm,
        }
        return render(request, 'dashboard/reports.html', context)

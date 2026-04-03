from datetime import date

from django.shortcuts import render, redirect
from django.views import View
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.cache import cache
from dateutil.relativedelta import relativedelta

from apps.core.mixins import OwnerRequiredMixin, StaffRequiredMixin


def _dashboard_cache_key(dormitory_id):
    """Cache key สำหรับ dashboard stats แยกตาม dormitory (tenant isolation)"""
    return f'dashboard:stats:{dormitory_id}'


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

            # S8-4: ดึง stats จาก cache ก่อน — TTL 5 นาที, key แยกตาม dormitory
            cache_key = _dashboard_cache_key(dorm.pk)
            stats = cache.get(cache_key)

            if stats is None:
                # Cache miss — run queries และเก็บผลลัพธ์ลง cache
                # รวม Bill stats เป็น query เดียวด้วย conditional aggregation (N5)
                bill_stats = Bill.objects.filter(
                    room__floor__building__dormitory=dorm,
                ).aggregate(
                    total_income=Sum('total', filter=Q(
                        status='paid',
                        month__year=now.year,
                        month__month=now.month,
                    )),
                    last_month_income=Sum('total', filter=Q(
                        status='paid',
                        month__year=last_month.year,
                        month__month=last_month.month,
                    )),
                    overdue_amount=Sum('total', filter=Q(status='overdue')),
                )
                total_income = bill_stats['total_income'] or 0
                last_month_income = bill_stats['last_month_income'] or 0
                overdue_amount = bill_stats['overdue_amount'] or 0

                # Income trend: positive = up, negative = down, None = no data
                if last_month_income > 0:
                    income_trend = round((total_income - last_month_income) / last_month_income * 100, 1)
                else:
                    income_trend = None

                # Overdue room count (distinct rooms)
                overdue_count = Bill.objects.filter(
                    room__floor__building__dormitory=dorm,
                    status='overdue',
                ).values('room').distinct().count()

                # Vacant rooms
                vacant_count = rooms_qs.filter(status='vacant').count()

                # Pending maintenance tickets
                pending_maintenance = MaintenanceTicket.objects.filter(
                    room__in=rooms_qs,
                    status__in=['new', 'in_progress', 'waiting_parts'],
                ).count()

                stats = {
                    'total_income': total_income,
                    'last_month_income': last_month_income,
                    'income_trend': income_trend,
                    'overdue_count': overdue_count,
                    'overdue_amount': overdue_amount,
                    'vacant_count': vacant_count,
                    'pending_maintenance': pending_maintenance,
                }
                # บันทึกลง cache 5 นาที (300 วินาที)
                cache.set(cache_key, stats, timeout=300)

            # Recent activity logs ไม่ cache — ต้องแสดง realtime
            recent_activity = ActivityLog.objects.filter(
                dormitory=dorm,
            ).select_related('user')[:10]

            context.update(stats)
            context['recent_activity'] = recent_activity

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

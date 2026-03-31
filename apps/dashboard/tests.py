from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.core.models import Dormitory, CustomUser, UserDormitoryRole
from apps.rooms.models import Building, Floor, Room
from apps.billing.models import Bill, BillingSettings
from apps.maintenance.models import MaintenanceTicket


def _make_room(dorm, number):
    b = Building.objects.create(dormitory=dorm, name=f'B-{number}')
    f = Floor.objects.create(building=b, number=1)
    return Room.objects.create(floor=f, number=number, base_rent=5000, status='occupied')


class DashboardViewTests(TestCase):
    """DashboardView KPI aggregation with single and multi-property context."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm_a = Dormitory.objects.create(name='Dash A', address='A')
        cls.dorm_b = Dormitory.objects.create(name='Dash B', address='B')

        cls.room_a1 = _make_room(cls.dorm_a, '101')
        cls.room_a2 = _make_room(cls.dorm_a, '102')
        cls.room_b1 = _make_room(cls.dorm_b, '101')
        # Make room_a2 vacant so vacant_count > 0
        cls.room_a2.status = 'vacant'
        cls.room_a2.save()

        today = date.today()
        cls.paid_bill = Bill.objects.create(
            room=cls.room_a1, month=date(today.year, today.month, 1),
            base_rent=5000, total=5000, due_date=date(today.year, today.month, 25),
            status='paid',
        )
        cls.overdue_bill = Bill.objects.create(
            room=cls.room_a1, month=date(today.year, today.month - 1 or 12, 1),
            base_rent=5000, total=5000,
            due_date=date(today.year, today.month - 1 or 12, 25),
            status='overdue',
        )
        MaintenanceTicket.objects.create(
            room=cls.room_a1, description='Broken light', status='new'
        )

        cls.owner = CustomUser.objects.create_user(
            'dash_owner', password='pass', role='owner', dormitory=cls.dorm_a
        )

    def test_dashboard_200(self):
        self.client.force_login(self.owner)
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_vacant_count_for_dorm_a(self):
        self.client.force_login(self.owner)
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.context['vacant_count'], 1)

    def test_dashboard_overdue_count_for_dorm_a(self):
        self.client.force_login(self.owner)
        resp = self.client.get('/dashboard/')
        self.assertGreaterEqual(resp.context['overdue_count'], 1)

    def test_dashboard_pending_maintenance_count(self):
        self.client.force_login(self.owner)
        resp = self.client.get('/dashboard/')
        self.assertGreaterEqual(resp.context['pending_maintenance'], 1)

    def test_dashboard_includes_owned_dormitories_for_owner(self):
        UserDormitoryRole.objects.create(
            user=self.owner, dormitory=self.dorm_a, role='owner'
        )
        UserDormitoryRole.objects.create(
            user=self.owner, dormitory=self.dorm_b, role='owner'
        )
        self.client.force_login(self.owner)
        resp = self.client.get('/dashboard/')
        owned = list(resp.context['owned_dormitories'])
        self.assertIn(self.dorm_a, owned)
        self.assertIn(self.dorm_b, owned)

    def test_dashboard_active_dormitory_in_context(self):
        self.client.force_login(self.owner)
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.context['active_dormitory'], self.dorm_a)

    def test_tenant_user_redirected_from_dashboard(self):
        # StaffRequiredMixin คืน 403 PermissionDenied สำหรับ tenant — ไม่ redirect
        user = CustomUser.objects.create_user(
            'dash_tenant', password='pass', role='tenant', dormitory=self.dorm_a
        )
        self.client.force_login(user)
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_with_property_switch_uses_session_dorm(self):
        """After switching to dorm_b, dashboard should reflect dorm_b context."""
        UserDormitoryRole.objects.create(
            user=self.owner, dormitory=self.dorm_a, role='owner', is_primary=True
        )
        UserDormitoryRole.objects.create(
            user=self.owner, dormitory=self.dorm_b, role='owner'
        )
        self.client.force_login(self.owner)
        # Switch to dorm_b
        self.client.post('/property/switch/', {'dormitory_id': self.dorm_b.pk})
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.context['active_dormitory'], self.dorm_b)
        # dorm_b has no vacant rooms → vacant_count = 0
        self.assertEqual(resp.context['vacant_count'], 0)


# ---------------------------------------------------------------------------
# ReportView tests (Task 2.2)
# ---------------------------------------------------------------------------

def _make_building_with_rooms(dorm, bldg_name, room_specs):
    """
    Helper: สร้าง building + rooms ใน dormitory
    room_specs: list of (number, status) tuples
    คืน (building, list of rooms)
    """
    bldg = Building.objects.create(dormitory=dorm, name=bldg_name)
    floor = Floor.objects.create(building=bldg, number=1, dormitory=dorm)
    rooms = []
    for number, status in room_specs:
        r = Room.objects.create(
            floor=floor, number=number, base_rent=5000, status=status, dormitory=dorm
        )
        rooms.append(r)
    return bldg, rooms


class ReportViewTests(TestCase):
    """
    ทดสอบ ReportView (/reports/):
    - revenue คำนวณถูก (sum paid bills เดือนที่ filter)
    - occupancy % คำนวณถูก
    - outstanding คำนวณถูก
    - tenant isolation: owner A ไม่เห็นข้อมูล dorm B
    """

    @classmethod
    def setUpTestData(cls):
        cls.dorm_a = Dormitory.objects.create(name='Report Dorm A', address='A', invoice_prefix='RA')
        cls.dorm_b = Dormitory.objects.create(name='Report Dorm B', address='B', invoice_prefix='RB')

        cls.owner_a = CustomUser.objects.create_user(
            'report_owner_a', password='pass', role='owner', dormitory=cls.dorm_a
        )
        cls.owner_b = CustomUser.objects.create_user(
            'report_owner_b', password='pass', role='owner', dormitory=cls.dorm_b
        )

        # dorm_a: 1 building, 3 rooms (2 occupied, 1 vacant)
        today = date.today()
        cls.this_month = date(today.year, today.month, 1)

        cls.bldg_a, cls.rooms_a = _make_building_with_rooms(
            cls.dorm_a, 'Block A',
            [('R101', 'occupied'), ('R102', 'occupied'), ('R103', 'vacant')]
        )

        # Paid bill ในเดือนนี้ — ควรนับเป็น revenue
        cls.paid_bill = Bill.objects.create(
            room=cls.rooms_a[0],
            month=cls.this_month,
            base_rent=Decimal('5000'),
            total=Decimal('5500'),
            due_date=date(today.year, today.month, 25),
            status='paid',
        )
        # Paid bill อีกใบในเดือนนี้
        cls.paid_bill2 = Bill.objects.create(
            room=cls.rooms_a[1],
            month=cls.this_month,
            base_rent=Decimal('5000'),
            total=Decimal('5200'),
            due_date=date(today.year, today.month, 25),
            status='paid',
        )
        # Overdue bill — ควรนับเป็น outstanding
        cls.overdue_bill = Bill.objects.create(
            room=cls.rooms_a[0],
            month=date(today.year, today.month - 1 if today.month > 1 else 12, 1),
            base_rent=Decimal('5000'),
            total=Decimal('5000'),
            due_date=date(today.year, today.month - 1 if today.month > 1 else 12, 25),
            status='overdue',
        )

        # dorm_b: 1 building, 1 room — สำหรับ isolation test
        cls.bldg_b, cls.rooms_b = _make_building_with_rooms(
            cls.dorm_b, 'Block B',
            [('R201', 'occupied')]
        )
        Bill.objects.create(
            room=cls.rooms_b[0],
            month=cls.this_month,
            base_rent=Decimal('6000'),
            total=Decimal('6000'),
            due_date=date(today.year, today.month, 25),
            status='paid',
        )

    def _login_owner_a(self):
        self.client.force_login(self.owner_a)
        session = self.client.session
        session['active_dormitory_id'] = str(self.dorm_a.pk)
        session.save()

    def _login_owner_b(self):
        self.client.force_login(self.owner_b)
        session = self.client.session
        session['active_dormitory_id'] = str(self.dorm_b.pk)
        session.save()

    def test_report_view_200(self):
        """ReportView ต้องตอบสนอง 200 สำหรับ owner."""
        self._login_owner_a()
        resp = self.client.get('/reports/')
        self.assertEqual(resp.status_code, 200)

    def test_report_revenue_correct(self):
        """Revenue ต้องเป็นผลรวมของ paid bills ในเดือนที่ filter."""
        self._login_owner_a()
        month_str = self.this_month.strftime('%Y-%m')
        resp = self.client.get(f'/reports/?month={month_str}')
        self.assertEqual(resp.status_code, 200)

        bldg_data = resp.context['buildings_data']
        self.assertEqual(len(bldg_data), 1, "ต้องมี 1 building ใน dorm_a")

        expected_revenue = Decimal('5500') + Decimal('5200')
        actual_revenue = bldg_data[0]['revenue']
        self.assertEqual(
            Decimal(str(actual_revenue)), expected_revenue,
            f"Revenue ควรเป็น {expected_revenue} ไม่ใช่ {actual_revenue}"
        )

    def test_report_occupancy_correct(self):
        """Occupancy % ต้องคำนวณถูก: 2 occupied / 3 total = 66.7%."""
        self._login_owner_a()
        resp = self.client.get('/reports/')
        self.assertEqual(resp.status_code, 200)

        bldg_data = resp.context['buildings_data']
        item = bldg_data[0]
        self.assertEqual(item['total_rooms'], 3)
        self.assertEqual(item['occupied_rooms'], 2)
        self.assertAlmostEqual(item['occupancy_pct'], 66.7, places=1)

    def test_report_outstanding_correct(self):
        """Outstanding ต้องเป็นผลรวม overdue bills ทั้งหมด."""
        self._login_owner_a()
        resp = self.client.get('/reports/')
        self.assertEqual(resp.status_code, 200)

        bldg_data = resp.context['buildings_data']
        item = bldg_data[0]
        self.assertEqual(
            Decimal(str(item['outstanding'])), Decimal('5000'),
            "Outstanding ต้องเท่ากับ 5000 (ยอด overdue)"
        )

    def test_tenant_isolation_owner_a_does_not_see_dorm_b(self):
        """owner_a ต้องเห็นเฉพาะ buildings ของ dorm_a ไม่ใช่ dorm_b."""
        self._login_owner_a()
        resp = self.client.get('/reports/')
        self.assertEqual(resp.status_code, 200)

        building_ids = {str(item['building'].pk) for item in resp.context['buildings_data']}
        self.assertIn(str(self.bldg_a.pk), building_ids,
                      "owner_a ต้องเห็น bldg_a")
        self.assertNotIn(str(self.bldg_b.pk), building_ids,
                         "owner_a ต้องไม่เห็น bldg_b ของ dorm_b (tenant isolation)")

    def test_tenant_isolation_owner_b_does_not_see_dorm_a(self):
        """owner_b ต้องเห็นเฉพาะ buildings ของ dorm_b."""
        self._login_owner_b()
        resp = self.client.get('/reports/')
        self.assertEqual(resp.status_code, 200)

        building_ids = {str(item['building'].pk) for item in resp.context['buildings_data']}
        self.assertIn(str(self.bldg_b.pk), building_ids,
                      "owner_b ต้องเห็น bldg_b")
        self.assertNotIn(str(self.bldg_a.pk), building_ids,
                         "owner_b ต้องไม่เห็น bldg_a ของ dorm_a (tenant isolation)")

    def test_staff_cannot_access_reports(self):
        """staff ต้องไม่เข้า /reports/ ได้ — เฉพาะ owner/superadmin เท่านั้น."""
        staff = CustomUser.objects.create_user(
            'report_staff', password='pass', role='staff', dormitory=self.dorm_a
        )
        self.client.force_login(staff)
        resp = self.client.get('/reports/')
        self.assertEqual(resp.status_code, 403)

    def test_default_month_is_current_month(self):
        """Default month ต้องเป็นเดือนปัจจุบัน."""
        self._login_owner_a()
        resp = self.client.get('/reports/')
        self.assertEqual(resp.status_code, 200)
        from django.utils import timezone
        now = timezone.now()
        self.assertEqual(resp.context['default_month'], now.strftime('%Y-%m'))
        self.assertEqual(resp.context['month_filter'], now.strftime('%Y-%m'))

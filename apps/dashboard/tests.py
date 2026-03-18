from datetime import date

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
        user = CustomUser.objects.create_user(
            'dash_tenant', password='pass', role='tenant', dormitory=self.dorm_a
        )
        self.client.force_login(user)
        resp = self.client.get('/dashboard/')
        self.assertRedirects(resp, '/tenant/home/', fetch_redirect_response=False)

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

from datetime import date

from django.test import TestCase

from apps.core.models import Dormitory, CustomUser
from apps.rooms.models import Building, Floor, Room
from apps.tenants.models import TenantProfile, Lease


def _make_room(dorm, number='101'):
    b = Building.objects.create(dormitory=dorm, name=f'Building-{number}')
    f = Floor.objects.create(building=b, number=1)
    return Room.objects.create(floor=f, number=number, base_rent=5000)


def _make_tenant(username, dorm, room=None):
    user = CustomUser.objects.create_user(
        username, password='pass', role='tenant', dormitory=dorm
    )
    return TenantProfile.objects.create(user=user, room=room)


class LeaseModelTests(TestCase):
    """Lease.room, Lease.status, and Lease choices."""

    def setUp(self):
        self.dorm = Dormitory.objects.create(name='Test Dorm', address='Addr')
        self.room = _make_room(self.dorm, '101')
        self.tenant = _make_tenant('t_lease', self.dorm)

    def test_create_active_lease_with_room(self):
        lease = Lease.objects.create(
            tenant=self.tenant, room=self.room,
            status='active', start_date=date(2025, 1, 1)
        )
        self.assertEqual(lease.room, self.room)
        self.assertEqual(lease.status, 'active')

    def test_lease_status_choices(self):
        values = {c[0] for c in Lease.Status.choices}
        self.assertEqual(values, {'active', 'ended', 'pending'})

    def test_lease_str_includes_room(self):
        lease = Lease.objects.create(
            tenant=self.tenant, room=self.room,
            status='active', start_date=date(2025, 1, 1)
        )
        self.assertIn('101', str(lease))

    def test_lease_without_room_is_allowed(self):
        lease = Lease.objects.create(
            tenant=self.tenant, room=None,
            status='pending', start_date=date(2025, 2, 1)
        )
        self.assertIsNone(lease.room)


class TenantProfileActiveRoomTests(TestCase):
    """TenantProfile.active_room property."""

    def setUp(self):
        self.dorm = Dormitory.objects.create(name='AR Dorm', address='Addr')
        self.room1 = _make_room(self.dorm, '101')
        self.room2 = _make_room(self.dorm, '102')

    def test_active_room_returns_room_from_active_lease(self):
        tenant = _make_tenant('t_ar1', self.dorm, room=self.room1)
        Lease.objects.create(
            tenant=tenant, room=self.room2, status='active', start_date=date(2025, 1, 1)
        )
        self.assertEqual(tenant.active_room, self.room2)

    def test_active_room_falls_back_to_profile_room_when_no_lease(self):
        tenant = _make_tenant('t_ar2', self.dorm, room=self.room1)
        self.assertEqual(tenant.active_room, self.room1)

    def test_active_room_ignores_ended_leases(self):
        tenant = _make_tenant('t_ar3', self.dorm, room=self.room1)
        Lease.objects.create(
            tenant=tenant, room=self.room2, status='ended', start_date=date(2024, 1, 1)
        )
        # No active lease → fallback to TenantProfile.room
        self.assertEqual(tenant.active_room, self.room1)


class TenantProfileMultiUnitTests(TestCase):
    """Tenant with multiple active leases (multi-unit scenario)."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm = Dormitory.objects.create(name='Multi Dorm', address='Addr')
        cls.room_a = _make_room(cls.dorm, '201')
        cls.room_b = _make_room(cls.dorm, '202')
        cls.tenant = _make_tenant('t_multi', cls.dorm)
        Lease.objects.create(
            tenant=cls.tenant, room=cls.room_a,
            status='active', start_date=date(2025, 1, 1)
        )
        Lease.objects.create(
            tenant=cls.tenant, room=cls.room_b,
            status='active', start_date=date(2025, 2, 1)
        )

    def test_tenant_has_two_active_leases(self):
        active = cls = self.tenant.leases.filter(status='active')
        self.assertEqual(active.count(), 2)

    def test_active_room_is_most_recent_lease(self):
        # Most recent start_date = room_b (Feb)
        self.assertEqual(self.tenant.active_room, self.room_b)

    def test_dormitory_property_returns_correct_dorm(self):
        self.assertEqual(self.tenant.dormitory, self.dorm)


class DormProfilesIsolationTests(TestCase):
    """_dorm_profiles() must not leak profiles across dormitories."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm_a = Dormitory.objects.create(name='Dorm A', address='A')
        cls.dorm_b = Dormitory.objects.create(name='Dorm B', address='B')

        cls.room_a = _make_room(cls.dorm_a, '101')
        cls.room_b = _make_room(cls.dorm_b, '101')

        cls.tenant_a = _make_tenant('ta', cls.dorm_a, room=cls.room_a)
        Lease.objects.create(
            tenant=cls.tenant_a, room=cls.room_a,
            status='active', start_date=date(2025, 1, 1)
        )
        cls.tenant_b = _make_tenant('tb', cls.dorm_b, room=cls.room_b)
        Lease.objects.create(
            tenant=cls.tenant_b, room=cls.room_b,
            status='active', start_date=date(2025, 1, 1)
        )

        cls.owner_a = CustomUser.objects.create_user(
            'owner_a', password='pass', role='owner', dormitory=cls.dorm_a
        )

    def test_dorm_a_owner_sees_only_dorm_a_tenants(self):
        from apps.tenants.views import _dorm_profiles
        profiles = _dorm_profiles(self.owner_a)
        self.assertIn(self.tenant_a, profiles)
        self.assertNotIn(self.tenant_b, profiles)

    def test_dorm_a_profiles_with_explicit_dorm_b_sees_only_b(self):
        from apps.tenants.views import _dorm_profiles
        profiles = _dorm_profiles(self.owner_a, dormitory=self.dorm_b)
        self.assertNotIn(self.tenant_a, profiles)
        self.assertIn(self.tenant_b, profiles)

    def test_ended_lease_tenant_not_in_active_scope(self):
        """Tenant whose only lease is 'ended' must not appear in dorm_a profiles via Lease path."""
        from apps.tenants.views import _dorm_profiles
        ended_tenant = _make_tenant('t_ended', self.dorm_a)
        Lease.objects.create(
            tenant=ended_tenant, room=self.room_a,
            status='ended', start_date=date(2024, 1, 1)
        )
        profiles = list(_dorm_profiles(self.owner_a))
        # Must not appear via active-lease path, but can appear via legacy room FK fallback
        # because ended_tenant has no TenantProfile.room set and no active lease
        self.assertNotIn(ended_tenant, profiles)

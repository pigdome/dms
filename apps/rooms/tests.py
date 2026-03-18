from django.test import TestCase

from apps.core.models import Dormitory, CustomUser
from apps.rooms.models import Building, Floor, Room
from apps.rooms.views import _dorm_rooms


def _setup_dorm(name, prefix=''):
    dorm = Dormitory.objects.create(name=name, address=f'{name} Addr', invoice_prefix=prefix)
    building = Building.objects.create(dormitory=dorm, name=f'{name} Building')
    floor = Floor.objects.create(building=building, number=1)
    room = Room.objects.create(floor=floor, number='101', base_rent=5000)
    return dorm, room


class DormRoomsHelperTests(TestCase):
    """_dorm_rooms() tenant isolation and dormitory override."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm_a, cls.room_a = _setup_dorm('Rooms A', 'A01')
        cls.dorm_b, cls.room_b = _setup_dorm('Rooms B', 'B01')
        cls.owner_a = CustomUser.objects.create_user(
            'rooms_owner_a', password='pass', role='owner', dormitory=cls.dorm_a
        )

    def test_returns_only_own_dormitory_rooms(self):
        rooms = list(_dorm_rooms(self.owner_a))
        self.assertIn(self.room_a, rooms)
        self.assertNotIn(self.room_b, rooms)

    def test_dormitory_override_returns_other_dorm_rooms(self):
        rooms = list(_dorm_rooms(self.owner_a, dormitory=self.dorm_b))
        self.assertNotIn(self.room_a, rooms)
        self.assertIn(self.room_b, rooms)

    def test_user_with_no_dormitory_returns_empty(self):
        user_no_dorm = CustomUser.objects.create_user('rooms_nodorm', password='pass')
        rooms = list(_dorm_rooms(user_no_dorm))
        self.assertEqual(rooms, [])


class RoomStatusChoicesTests(TestCase):
    def test_all_status_choices_exist(self):
        values = {c[0] for c in Room.Status.choices}
        self.assertEqual(values, {'occupied', 'vacant', 'cleaning', 'maintenance'})


class RoomListViewTenantIsolationTests(TestCase):
    """RoomListView must not show rooms from another dormitory."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm_a, cls.room_a = _setup_dorm('View A')
        cls.dorm_b, cls.room_b = _setup_dorm('View B')
        cls.owner_a = CustomUser.objects.create_user(
            'view_owner_a', password='pass', role='owner', dormitory=cls.dorm_a
        )

    def test_room_list_view_only_shows_own_rooms(self):
        self.client.force_login(self.owner_a)
        resp = self.client.get('/rooms/')
        self.assertEqual(resp.status_code, 200)
        rooms_in_context = list(resp.context['rooms'])
        self.assertIn(self.room_a, rooms_in_context)
        self.assertNotIn(self.room_b, rooms_in_context)

    def test_room_detail_from_other_dorm_returns_404(self):
        self.client.force_login(self.owner_a)
        resp = self.client.get(f'/rooms/{self.room_b.pk}/')
        self.assertEqual(resp.status_code, 404)

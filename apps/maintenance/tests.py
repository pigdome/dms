from datetime import date

from django.test import TestCase

from apps.core.models import Dormitory, CustomUser
from apps.rooms.models import Building, Floor, Room
from apps.tenants.models import TenantProfile, Lease
from apps.maintenance.models import MaintenanceTicket, TicketStatusHistory


def _make_room(dorm, number='101'):
    b = Building.objects.create(dormitory=dorm, name=f'B-{number}')
    f = Floor.objects.create(building=b, number=1)
    return Room.objects.create(floor=f, number=number, base_rent=4000)


class TicketStatusChoicesTests(TestCase):
    def test_all_status_choices_exist(self):
        values = {c[0] for c in MaintenanceTicket.Status.choices}
        self.assertEqual(values, {'new', 'in_progress', 'waiting_parts', 'completed'})


class TicketTenantIsolationTests(TestCase):
    """Staff from dorm_a must not access tickets from dorm_b."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm_a = Dormitory.objects.create(name='Maint A', address='A')
        cls.dorm_b = Dormitory.objects.create(name='Maint B', address='B')
        cls.room_a = _make_room(cls.dorm_a, '101')
        cls.room_b = _make_room(cls.dorm_b, '101')

        cls.staff_a = CustomUser.objects.create_user(
            'maint_staff_a', password='pass', role='staff', dormitory=cls.dorm_a
        )
        from apps.core.models import StaffPermission
        StaffPermission.objects.create(
            user=cls.staff_a, dormitory=cls.dorm_a, can_manage_maintenance=True
        )
        cls.ticket_a = MaintenanceTicket.objects.create(
            room=cls.room_a, reported_by=cls.staff_a, description='Broken A'
        )
        cls.ticket_b = MaintenanceTicket.objects.create(
            room=cls.room_b, reported_by=cls.staff_a, description='Broken B'
        )

    def test_ticket_list_only_shows_own_dorm(self):
        self.client.force_login(self.staff_a)
        resp = self.client.get('/maintenance/')
        self.assertEqual(resp.status_code, 200)
        tickets = list(resp.context['tickets'])
        self.assertIn(self.ticket_a, tickets)
        self.assertNotIn(self.ticket_b, tickets)

    def test_ticket_detail_from_other_dorm_returns_404(self):
        self.client.force_login(self.staff_a)
        resp = self.client.get(f'/maintenance/{self.ticket_b.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_update_status_from_other_dorm_returns_404(self):
        self.client.force_login(self.staff_a)
        resp = self.client.post(
            f'/maintenance/{self.ticket_b.pk}/update-status/',
            {'status': 'completed', 'note': 'Done'}
        )
        self.assertEqual(resp.status_code, 404)


class TicketCreateTests(TestCase):
    """TicketCreateView creates ticket with status history entry."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm = Dormitory.objects.create(name='Create Dorm', address='Addr')
        cls.room = _make_room(cls.dorm, '201')
        cls.staff = CustomUser.objects.create_user(
            'maint_create_staff', password='pass', role='staff', dormitory=cls.dorm
        )

    def test_create_ticket_creates_history_entry(self):
        self.client.force_login(self.staff)
        resp = self.client.post('/maintenance/create/', {
            'room': self.room.pk,
            'description': 'AC not working',
            'technician': '',
        })
        self.assertEqual(resp.status_code, 302)
        ticket = MaintenanceTicket.objects.get(room=self.room)
        self.assertEqual(ticket.description, 'AC not working')
        history = TicketStatusHistory.objects.filter(ticket=ticket)
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().status, 'new')

    def test_create_ticket_from_other_dorm_room_is_rejected(self):
        other_dorm = Dormitory.objects.create(name='Other', address='Other')
        other_room = _make_room(other_dorm, '301')
        self.client.force_login(self.staff)
        resp = self.client.post('/maintenance/create/', {
            'room': other_room.pk,
            'description': 'Hack attempt',
        })
        self.assertEqual(resp.status_code, 404)


class TicketStatusUpdateTests(TestCase):
    """update_status correctly logs history and changes ticket status."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm = Dormitory.objects.create(name='Update Dorm', address='Addr')
        cls.room = _make_room(cls.dorm, '301')
        cls.staff = CustomUser.objects.create_user(
            'maint_update_staff', password='pass', role='staff', dormitory=cls.dorm
        )
        cls.ticket = MaintenanceTicket.objects.create(
            room=cls.room, reported_by=cls.staff, description='Leaking pipe'
        )

    def test_status_update_creates_history(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            f'/maintenance/{self.ticket.pk}/update-status/',
            {'status': 'in_progress', 'note': 'Assigned technician'}
        )
        self.assertRedirects(
            resp, f'/maintenance/{self.ticket.pk}/', fetch_redirect_response=False
        )
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'in_progress')
        history = TicketStatusHistory.objects.filter(ticket=self.ticket)
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().note, 'Assigned technician')


class TenantTicketCreateWithActiveLease(TestCase):
    """TenantTicketCreateView uses active_room from Lease, not TenantProfile.room."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm = Dormitory.objects.create(name='Tenant Ticket Dorm', address='Addr')
        cls.room_old = _make_room(cls.dorm, '401')
        cls.room_new = _make_room(cls.dorm, '402')

        user = CustomUser.objects.create_user(
            'tt_tenant', password='pass', role='tenant', dormitory=cls.dorm
        )
        # Legacy: profile.room points to old room
        cls.profile = TenantProfile.objects.create(user=user, room=cls.room_old)
        # Active lease points to new room
        Lease.objects.create(
            tenant=cls.profile, room=cls.room_new,
            status='active', start_date=date(2025, 1, 1)
        )
        cls.tenant_user = user

    def test_tenant_request_uses_active_lease_room(self):
        self.client.force_login(self.tenant_user)
        resp = self.client.get('/tenant/maintenance/')
        self.assertEqual(resp.status_code, 200)
        # Context should show the active lease room, not the legacy profile.room
        self.assertEqual(resp.context['room'], self.room_new)

    def test_tenant_maintenance_shows_previous_tickets(self):
        # Create some tickets for the room
        t1 = MaintenanceTicket.objects.create(room=self.room_new, reported_by=self.tenant_user, description='Old ticket')
        t2 = MaintenanceTicket.objects.create(room=self.room_new, reported_by=self.tenant_user, description='New ticket')

        self.client.force_login(self.tenant_user)
        resp = self.client.get('/tenant/maintenance/')
        self.assertEqual(resp.status_code, 200)

        tickets = list(resp.context['tickets'])
        self.assertEqual(len(tickets), 2)
        self.assertIn(t1, tickets)
        self.assertIn(t2, tickets)


# ---------------------------------------------------------------------------
# Flow 5: Maintenance Ticket Full Lifecycle Integration Tests
# ---------------------------------------------------------------------------


class MaintenanceLifecycleIntegrationTests(TestCase):
    """
    Integration tests for the complete maintenance ticket lifecycle:
    tenant submit → staff view → status transitions → tenant sees update → dashboard count.
    """

    @classmethod
    def setUpTestData(cls):
        cls.dorm = Dormitory.objects.create(name='Lifecycle Dorm', address='Addr')
        cls.room = _make_room(cls.dorm, '501')
        cls.room2 = _make_room(cls.dorm, '502')

        cls.staff = CustomUser.objects.create_user(
            'lc_staff', password='pass', role='staff', dormitory=cls.dorm
        )
        cls.owner = CustomUser.objects.create_user(
            'lc_owner', password='pass', role='owner', dormitory=cls.dorm
        )
        from apps.core.models import StaffPermission
        StaffPermission.objects.create(
            user=cls.staff, dormitory=cls.dorm, can_manage_maintenance=True
        )

        # Tenant with active lease
        cls.tenant_user = CustomUser.objects.create_user(
            'lc_tenant', password='pass', role='tenant', dormitory=cls.dorm
        )
        from apps.tenants.models import TenantProfile, Lease
        # legacy profile.room = room2 (old room)
        cls.profile = TenantProfile.objects.create(user=cls.tenant_user, room=cls.room2)
        # active lease → room (new room)
        Lease.objects.create(
            tenant=cls.profile, room=cls.room,
            status='active', start_date=date(2025, 1, 1)
        )

    def test_tenant_submit_ticket_uses_active_lease_room(self):
        """tenant POST /tenant/maintenance/ → ticket.room = ห้องจาก active lease"""
        self.client.force_login(self.tenant_user)
        resp = self.client.post('/tenant/maintenance/', {
            'description': 'AC broken in active room',
        })
        self.assertEqual(resp.status_code, 302)
        ticket = MaintenanceTicket.objects.filter(
            reported_by=self.tenant_user, description='AC broken in active room'
        ).first()
        self.assertIsNotNone(ticket)
        # ต้องใช้ห้องจาก active lease ไม่ใช่ profile.room (legacy)
        self.assertEqual(ticket.room, self.room)
        self.assertNotEqual(ticket.room, self.room2)

    def test_staff_sees_ticket_in_list(self):
        """staff GET /maintenance/ → เห็น ticket ในรายการ"""
        ticket = MaintenanceTicket.objects.create(
            room=self.room, reported_by=self.staff, description='Broken door'
        )
        self.client.force_login(self.staff)
        resp = self.client.get('/maintenance/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(ticket, list(resp.context['tickets']))

    def test_status_transitions_full_cycle(self):
        """staff อัพเดต new→in_progress→waiting_parts→completed → TicketStatusHistory มี 4 entries"""
        ticket = MaintenanceTicket.objects.create(
            room=self.room, reported_by=self.staff, description='Full cycle test'
        )
        # สร้าง initial history entry (status=new)
        TicketStatusHistory.objects.create(
            ticket=ticket, status='new', changed_by=self.staff, note='Created'
        )

        self.client.force_login(self.staff)
        for new_status in ['in_progress', 'waiting_parts', 'completed']:
            resp = self.client.post(
                f'/maintenance/{ticket.pk}/update-status/',
                {'status': new_status, 'note': f'Moving to {new_status}'}
            )
            self.assertRedirects(
                resp, f'/maintenance/{ticket.pk}/', fetch_redirect_response=False
            )

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'completed')
        history_count = TicketStatusHistory.objects.filter(ticket=ticket).count()
        self.assertEqual(history_count, 4)

    def test_tenant_sees_updated_status_in_portal(self):
        """หลัง status update, tenant GET portal เห็น ticket status ล่าสุด"""
        ticket = MaintenanceTicket.objects.create(
            room=self.room, reported_by=self.tenant_user, description='Portal status test'
        )

        # staff update status
        self.client.force_login(self.staff)
        self.client.post(
            f'/maintenance/{ticket.pk}/update-status/',
            {'status': 'in_progress', 'note': 'Started'}
        )

        # tenant เข้าดู portal
        self.client.force_login(self.tenant_user)
        resp = self.client.get('/tenant/maintenance/')
        self.assertEqual(resp.status_code, 200)

        # ต้องเห็น ticket ที่ status อัพเดตแล้ว
        tickets = list(resp.context['tickets'])
        updated = next((t for t in tickets if t.pk == ticket.pk), None)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, 'in_progress')

    def test_dashboard_pending_decreases_after_completion(self):
        """ticket completed → Dashboard pending_maintenance count ลด"""
        ticket = MaintenanceTicket.objects.create(
            room=self.room, reported_by=self.staff,
            description='Dashboard count test', status='new'
        )

        from apps.maintenance.models import MaintenanceTicket as MT
        pending_before = MT.objects.filter(
            room__floor__building__dormitory=self.dorm,
            status__in=['new', 'in_progress', 'waiting_parts'],
        ).count()

        self.client.force_login(self.staff)
        self.client.post(
            f'/maintenance/{ticket.pk}/update-status/',
            {'status': 'completed', 'note': 'Done'}
        )

        pending_after = MT.objects.filter(
            room__floor__building__dormitory=self.dorm,
            status__in=['new', 'in_progress', 'waiting_parts'],
        ).count()

        self.assertEqual(pending_after, pending_before - 1)

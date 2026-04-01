"""
Permission Enforcement Tests — Task 1.3

ทดสอบ:
1. Anonymous user → redirect to login (ทุก view ที่ต้อง login)
2. Tenant user พยายามเข้า staff/owner view → 403
3. Staff user พยายามเข้า owner-only view → 403
4. Owner user เข้า owner view → 200
5. Owner A ไม่เห็นข้อมูล owner B (tenant isolation)
"""
from django.test import TestCase

from apps.core.models import CustomUser, Dormitory, UserDormitoryRole


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

class _PermFixture:
    """สร้าง users และ dormitories ที่ใช้ร่วมกันใน permission tests."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm1 = Dormitory.objects.create(
            name='Perm Dorm 1', address='1 Test Rd', invoice_prefix='P01'
        )
        cls.dorm2 = Dormitory.objects.create(
            name='Perm Dorm 2', address='2 Test Rd', invoice_prefix='P02'
        )
        cls.owner = CustomUser.objects.create_user(
            'perm_owner', password='pass', role='owner', dormitory=cls.dorm1
        )
        cls.owner2 = CustomUser.objects.create_user(
            'perm_owner2', password='pass', role='owner', dormitory=cls.dorm2
        )
        cls.staff = CustomUser.objects.create_user(
            'perm_staff', password='pass', role='staff', dormitory=cls.dorm1
        )
        cls.tenant_user = CustomUser.objects.create_user(
            'perm_tenant', password='pass', role='tenant', dormitory=cls.dorm1
        )
        # UserDormitoryRole สำหรับ owner เพื่อให้ property_switch ทำงานได้
        UserDormitoryRole.objects.create(
            user=cls.owner, dormitory=cls.dorm1, role='owner', is_primary=True
        )
        UserDormitoryRole.objects.create(
            user=cls.owner2, dormitory=cls.dorm2, role='owner', is_primary=True
        )


# ---------------------------------------------------------------------------
# 1. Anonymous user → redirect to login
# ---------------------------------------------------------------------------

class AnonymousAccessTests(_PermFixture, TestCase):
    """Anonymous user ต้อง redirect ไป login สำหรับทุก protected view."""

    def _assert_redirects_to_login(self, url):
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (301, 302),
                      f"Expected redirect for anonymous at {url}, got {resp.status_code}")

    # core views
    def test_anonymous_audit_log_redirects(self):
        self._assert_redirects_to_login('/audit-log/')

    def test_anonymous_setup_wizard_redirects(self):
        self._assert_redirects_to_login('/setup/')

    # billing views
    def test_anonymous_billing_settings_redirects(self):
        self._assert_redirects_to_login('/billing/settings/')

    def test_anonymous_bill_list_redirects(self):
        self._assert_redirects_to_login('/billing/')

    def test_anonymous_bill_export_redirects(self):
        self._assert_redirects_to_login('/billing/export/')

    # rooms views
    def test_anonymous_room_list_redirects(self):
        self._assert_redirects_to_login('/rooms/')

    def test_anonymous_room_create_redirects(self):
        self._assert_redirects_to_login('/rooms/create/')

    def test_anonymous_meter_reading_redirects(self):
        self._assert_redirects_to_login('/rooms/meter-reading/')

    # maintenance views
    def test_anonymous_ticket_list_redirects(self):
        self._assert_redirects_to_login('/maintenance/')

    def test_anonymous_ticket_create_redirects(self):
        self._assert_redirects_to_login('/maintenance/create/')

    # notifications views
    def test_anonymous_parcel_create_redirects(self):
        self._assert_redirects_to_login('/notifications/parcels/')

    def test_anonymous_parcel_list_redirects(self):
        self._assert_redirects_to_login('/notifications/parcels/history/')

    def test_anonymous_broadcast_redirects(self):
        self._assert_redirects_to_login('/notifications/broadcast/')

    # tenant management views
    def test_anonymous_tenant_list_redirects(self):
        self._assert_redirects_to_login('/tenants/')

    def test_anonymous_tenant_create_redirects(self):
        self._assert_redirects_to_login('/tenants/add/')

    def test_anonymous_tenant_import_redirects(self):
        # single-step /tenants/import/ ถูกลบแล้ว — ใช้ /import/tenants/ แทน
        self._assert_redirects_to_login('/import/tenants/')


# ---------------------------------------------------------------------------
# 2. Tenant user พยายามเข้า staff/owner view → 403
# ---------------------------------------------------------------------------

class TenantAccessDeniedTests(_PermFixture, TestCase):
    """Tenant user ต้องได้รับ 403 เมื่อพยายามเข้า staff/owner views."""

    def setUp(self):
        self.client.force_login(self.tenant_user)

    def _assert_403(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403,
                         f"Expected 403 for tenant at {url}, got {resp.status_code}")

    # owner-only views
    def test_tenant_billing_settings_forbidden(self):
        self._assert_403('/billing/settings/')

    def test_tenant_bill_export_forbidden(self):
        self._assert_403('/billing/export/')

    def test_tenant_audit_log_forbidden(self):
        self._assert_403('/audit-log/')

    # staff views
    def test_tenant_room_list_forbidden(self):
        self._assert_403('/rooms/')

    def test_tenant_bill_list_forbidden(self):
        self._assert_403('/billing/')

    def test_tenant_ticket_list_forbidden(self):
        self._assert_403('/maintenance/')

    def test_tenant_parcel_list_forbidden(self):
        self._assert_403('/notifications/parcels/history/')

    def test_tenant_tenant_list_forbidden(self):
        self._assert_403('/tenants/')


# ---------------------------------------------------------------------------
# 3. Staff user พยายามเข้า owner-only view → 403
# ---------------------------------------------------------------------------

class StaffAccessOwnerOnlyTests(_PermFixture, TestCase):
    """Staff user ต้องได้รับ 403 เมื่อพยายามเข้า owner-only views."""

    def setUp(self):
        self.client.force_login(self.staff)

    def _assert_403(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403,
                         f"Expected 403 for staff at {url}, got {resp.status_code}")

    def test_staff_billing_settings_forbidden(self):
        """Staff ไม่ควรเข้า billing settings ได้ — เฉพาะ owner เท่านั้น."""
        self._assert_403('/billing/settings/')

    def test_staff_bill_export_forbidden(self):
        """Staff ไม่ควร export CSV billing ได้ — ข้อมูลการเงินสำคัญ."""
        self._assert_403('/billing/export/')

    def test_staff_audit_log_forbidden(self):
        """Staff ไม่ควรเข้า audit log ได้ — เฉพาะ owner/superadmin เท่านั้น."""
        self._assert_403('/audit-log/')

    def test_staff_setup_wizard_forbidden(self):
        """Staff ไม่ควรตั้งค่าหอพักได้ — เฉพาะ owner เท่านั้น."""
        self._assert_403('/setup/')


# ---------------------------------------------------------------------------
# 4. Staff user เข้า staff-allowed views → 200
# ---------------------------------------------------------------------------

class StaffAccessAllowedTests(_PermFixture, TestCase):
    """Staff user ต้องเข้า staff views ได้ปกติ (200)."""

    def setUp(self):
        self.client.force_login(self.staff)

    def test_staff_room_list_allowed(self):
        resp = self.client.get('/rooms/')
        self.assertEqual(resp.status_code, 200)

    def test_staff_ticket_list_allowed(self):
        resp = self.client.get('/maintenance/')
        self.assertEqual(resp.status_code, 200)

    def test_staff_parcel_list_allowed(self):
        resp = self.client.get('/notifications/parcels/history/')
        self.assertEqual(resp.status_code, 200)

    def test_staff_bill_list_allowed(self):
        resp = self.client.get('/billing/')
        self.assertEqual(resp.status_code, 200)

    def test_staff_tenant_list_allowed(self):
        resp = self.client.get('/tenants/')
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 5. Owner user เข้า owner view → 200
# ---------------------------------------------------------------------------

class OwnerAccessAllowedTests(_PermFixture, TestCase):
    """Owner user ต้องเข้าได้ทุก view ทั้ง owner-only และ staff views."""

    def setUp(self):
        self.client.force_login(self.owner)
        # Set session dormitory
        session = self.client.session
        session['active_dormitory_id'] = str(self.dorm1.pk)
        session.save()

    def test_owner_audit_log_allowed(self):
        resp = self.client.get('/audit-log/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_billing_settings_allowed(self):
        resp = self.client.get('/billing/settings/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_bill_export_form_allowed(self):
        resp = self.client.get('/billing/export/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_room_list_allowed(self):
        resp = self.client.get('/rooms/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_ticket_list_allowed(self):
        resp = self.client.get('/maintenance/')
        self.assertEqual(resp.status_code, 200)

    def test_owner_tenant_list_allowed(self):
        resp = self.client.get('/tenants/')
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 6. Tenant isolation — Owner A ไม่เห็นข้อมูล Owner B
# ---------------------------------------------------------------------------

class TenantIsolationTests(_PermFixture, TestCase):
    """ทดสอบว่า owner A ไม่สามารถเข้าถึงข้อมูลของ owner B ได้."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # สร้าง rooms ใน dorm1 และ dorm2 เพื่อทดสอบ isolation
        from apps.rooms.models import Building, Floor, Room
        bldg1 = Building.objects.create(name='Bldg-P1', dormitory=cls.dorm1)
        floor1 = Floor.objects.create(building=bldg1, number=1, dormitory=cls.dorm1)
        cls.room1 = Room.objects.create(
            floor=floor1, number='P101', base_rent=3000, dormitory=cls.dorm1
        )

        bldg2 = Building.objects.create(name='Bldg-P2', dormitory=cls.dorm2)
        floor2 = Floor.objects.create(building=bldg2, number=1, dormitory=cls.dorm2)
        cls.room2 = Room.objects.create(
            floor=floor2, number='P201', base_rent=4000, dormitory=cls.dorm2
        )

    def _login_as_owner1(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session['active_dormitory_id'] = str(self.dorm1.pk)
        session.save()

    def _login_as_owner2(self):
        self.client.force_login(self.owner2)
        session = self.client.session
        session['active_dormitory_id'] = str(self.dorm2.pk)
        session.save()

    def test_owner1_room_list_does_not_contain_dorm2_rooms(self):
        """Room list ของ owner1 ต้องแสดงเฉพาะห้องใน dorm1."""
        self._login_as_owner1()
        resp = self.client.get('/rooms/')
        self.assertEqual(resp.status_code, 200)
        rooms_in_response = list(resp.context['rooms'])
        room_ids = {str(r.pk) for r in rooms_in_response}
        self.assertIn(str(self.room1.pk), room_ids,
                      "Owner1 ต้องเห็นห้องของตัวเอง (dorm1)")
        self.assertNotIn(str(self.room2.pk), room_ids,
                         "Owner1 ต้องไม่เห็นห้องของ dorm2")

    def test_owner2_room_list_does_not_contain_dorm1_rooms(self):
        """Room list ของ owner2 ต้องแสดงเฉพาะห้องใน dorm2."""
        self._login_as_owner2()
        resp = self.client.get('/rooms/')
        self.assertEqual(resp.status_code, 200)
        rooms_in_response = list(resp.context['rooms'])
        room_ids = {str(r.pk) for r in rooms_in_response}
        self.assertIn(str(self.room2.pk), room_ids,
                      "Owner2 ต้องเห็นห้องของตัวเอง (dorm2)")
        self.assertNotIn(str(self.room1.pk), room_ids,
                         "Owner2 ต้องไม่เห็นห้องของ dorm1")

    def test_owner1_cannot_access_dorm2_room_detail_directly(self):
        """Owner1 ต้องไม่สามารถเข้า room detail ของ dorm2 โดยตรง (IDOR protection)."""
        self._login_as_owner1()
        resp = self.client.get(f'/rooms/{self.room2.pk}/')
        # ต้องได้ 404 (room ไม่อยู่ใน queryset ที่ scoped แล้ว) ไม่ใช่ 200
        self.assertEqual(resp.status_code, 404,
                         "Owner1 ต้องไม่สามารถเข้า room detail ของ dorm2 ได้")

    def test_owner1_ticket_list_does_not_contain_dorm2_tickets(self):
        """Maintenance ticket list ของ owner1 ต้องไม่มี ticket จาก dorm2."""
        from apps.maintenance.models import MaintenanceTicket
        # สร้าง ticket ใน dorm2
        ticket2 = MaintenanceTicket.objects.create(
            room=self.room2,
            reported_by=self.owner2,
            description='Dorm2 issue',
        )

        self._login_as_owner1()
        resp = self.client.get('/maintenance/')
        self.assertEqual(resp.status_code, 200)
        ticket_ids = {str(t.pk) for t in resp.context['tickets']}
        self.assertNotIn(str(ticket2.pk), ticket_ids,
                         "Owner1 ต้องไม่เห็น ticket ของ dorm2")

    def test_owner1_tenant_list_does_not_contain_dorm2_tenants(self):
        """Tenant list ของ owner1 ต้องไม่มีผู้เช่าจาก dorm2."""
        from apps.tenants.models import TenantProfile
        from apps.tenants.models import Lease
        # สร้าง tenant ใน dorm2
        tenant2_user = CustomUser.objects.create_user(
            'iso_tenant2', password='pass', role='tenant', dormitory=self.dorm2
        )
        profile2 = TenantProfile.objects.create(
            user=tenant2_user,
            room=self.room2,
        )
        Lease.objects.create(
            tenant=profile2,
            room=self.room2,
            start_date='2026-01-01',
            status='active',
        )

        self._login_as_owner1()
        resp = self.client.get('/tenants/')
        self.assertEqual(resp.status_code, 200)
        profile_ids = {str(p.pk) for p in resp.context['tenants']}
        self.assertNotIn(str(profile2.pk), profile_ids,
                         "Owner1 ต้องไม่เห็นผู้เช่าของ dorm2")


# ---------------------------------------------------------------------------
# 7. Building Manager role tests (Task 2.1)
# ---------------------------------------------------------------------------

class BuildingManagerRoleTests(_PermFixture, TestCase):
    """
    ทดสอบ building_manager role:
    - เข้า staff views ได้ (StaffRequiredMixin ต้องรับ building_manager)
    - เข้า owner-only views ไม่ได้ (403)
    - เห็นเฉพาะ buildings ที่ assign ผ่าน managed_buildings (BuildingManagerRequiredMixin)
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from apps.rooms.models import Building, Floor, Room

        # สร้าง building_manager user ผูกกับ dorm1
        cls.bm_user = CustomUser.objects.create_user(
            'bm_user', password='pass', role='building_manager', dormitory=cls.dorm1
        )

        # สร้าง 2 buildings ใน dorm1 — assign เฉพาะ bldg_assigned ให้ bm_user
        cls.bldg_assigned = Building.objects.create(name='Bldg-Assigned', dormitory=cls.dorm1)
        cls.bldg_other = Building.objects.create(name='Bldg-Other', dormitory=cls.dorm1)
        cls.bm_user.managed_buildings.add(cls.bldg_assigned)

        # สร้าง rooms ใน building ทั้งสองเพื่อใช้ใน isolation test
        floor_a = Floor.objects.create(building=cls.bldg_assigned, number=1, dormitory=cls.dorm1)
        cls.room_assigned = Room.objects.create(
            floor=floor_a, number='BM101', base_rent=3000, dormitory=cls.dorm1
        )
        floor_b = Floor.objects.create(building=cls.bldg_other, number=1, dormitory=cls.dorm1)
        cls.room_other = Room.objects.create(
            floor=floor_b, number='BM201', base_rent=3000, dormitory=cls.dorm1
        )

    # --- 7a. building_manager เข้า staff view → 200 ---

    def test_building_manager_room_list_allowed(self):
        """building_manager ต้องเข้า staff view เช่น /rooms/ ได้ (200)."""
        self.client.force_login(self.bm_user)
        resp = self.client.get('/rooms/')
        self.assertEqual(resp.status_code, 200,
                         "building_manager ควรเข้า staff view (/rooms/) ได้")

    def test_building_manager_ticket_list_allowed(self):
        """building_manager ต้องเข้า maintenance list ได้ (200)."""
        self.client.force_login(self.bm_user)
        resp = self.client.get('/maintenance/')
        self.assertEqual(resp.status_code, 200)

    def test_building_manager_bill_list_allowed(self):
        """building_manager ต้องเข้า billing list ได้ (200)."""
        self.client.force_login(self.bm_user)
        resp = self.client.get('/billing/')
        self.assertEqual(resp.status_code, 200)

    # --- 7b. building_manager เข้า owner-only view → 403 ---

    def test_building_manager_billing_settings_forbidden(self):
        """building_manager ต้องไม่เข้า billing settings ได้ — เฉพาะ owner เท่านั้น."""
        self.client.force_login(self.bm_user)
        resp = self.client.get('/billing/settings/')
        self.assertEqual(resp.status_code, 403,
                         "building_manager ต้องได้รับ 403 จาก owner-only view")

    def test_building_manager_audit_log_forbidden(self):
        """building_manager ต้องไม่เข้า audit log ได้."""
        self.client.force_login(self.bm_user)
        resp = self.client.get('/audit-log/')
        self.assertEqual(resp.status_code, 403)

    def test_building_manager_setup_wizard_forbidden(self):
        """building_manager ต้องไม่เข้า setup wizard ได้."""
        self.client.force_login(self.bm_user)
        resp = self.client.get('/setup/')
        self.assertEqual(resp.status_code, 403)

    # --- 7c. building_manager เห็นเฉพาะ buildings ที่ assign ---

    def test_building_manager_managed_buildings_assigned(self):
        """managed_buildings ต้องมีเฉพาะ bldg_assigned ที่ assign ให้ bm_user."""
        assigned_ids = set(
            self.bm_user.managed_buildings.values_list('pk', flat=True)
        )
        self.assertIn(self.bldg_assigned.pk, assigned_ids,
                      "bm_user ต้องเห็น bldg_assigned")
        self.assertNotIn(self.bldg_other.pk, assigned_ids,
                         "bm_user ต้องไม่เห็น bldg_other ที่ไม่ได้ assign")

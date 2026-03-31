from django.test import SimpleTestCase, TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core.models import CustomUser, Dormitory, UserDormitoryRole, ActivityLog
from config.middleware import ActiveDormitoryMiddleware


class CustomUserRoleTests(SimpleTestCase):
    def _make_user(self, role):
        user = CustomUser.__new__(CustomUser)
        user.role = role
        return user

    def test_user_role_is_owner(self):
        user = self._make_user(CustomUser.Role.OWNER)
        self.assertTrue(user.is_owner)
        self.assertFalse(user.is_staff_member)
        self.assertFalse(user.is_tenant_user)

    def test_user_role_is_staff_member(self):
        user = self._make_user(CustomUser.Role.STAFF)
        self.assertFalse(user.is_owner)
        self.assertTrue(user.is_staff_member)
        self.assertFalse(user.is_tenant_user)

    def test_user_role_is_tenant(self):
        user = self._make_user(CustomUser.Role.TENANT)
        self.assertFalse(user.is_owner)
        self.assertFalse(user.is_staff_member)
        self.assertTrue(user.is_tenant_user)


class _DormFixture:
    @classmethod
    def setUpTestData(cls):
        cls.dorm1 = Dormitory.objects.create(
            name='Dorm Alpha', address='1 Alpha Rd', invoice_prefix='A01'
        )
        cls.dorm2 = Dormitory.objects.create(
            name='Dorm Beta', address='2 Beta Rd', invoice_prefix='B01'
        )
        cls.owner = CustomUser.objects.create_user(
            'owner_test', password='pass', role='owner', dormitory=cls.dorm1
        )
        cls.staff = CustomUser.objects.create_user(
            'staff_test', password='pass', role='staff', dormitory=cls.dorm1
        )


class UserDormitoryRoleTests(_DormFixture, TestCase):

    def test_create_role(self):
        role = UserDormitoryRole.objects.create(
            user=self.owner, dormitory=self.dorm1, role='owner', is_primary=True
        )
        self.assertEqual(role.dormitory, self.dorm1)
        self.assertTrue(role.is_primary)

    def test_unique_together_prevents_duplicate(self):
        UserDormitoryRole.objects.create(user=self.owner, dormitory=self.dorm1, role='owner')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            UserDormitoryRole.objects.create(user=self.owner, dormitory=self.dorm1, role='staff')

    def test_owned_dormitories_returns_both_owner_roles(self):
        UserDormitoryRole.objects.create(user=self.owner, dormitory=self.dorm1, role='owner')
        UserDormitoryRole.objects.create(user=self.owner, dormitory=self.dorm2, role='owner')
        owned = list(self.owner.owned_dormitories)
        self.assertIn(self.dorm1, owned)
        self.assertIn(self.dorm2, owned)
        self.assertEqual(len(owned), 2)

    def test_staff_role_excluded_from_owned_dormitories(self):
        UserDormitoryRole.objects.create(user=self.staff, dormitory=self.dorm1, role='staff')
        self.assertEqual(list(self.staff.owned_dormitories), [])

    def test_str_representation(self):
        role = UserDormitoryRole.objects.create(user=self.owner, dormitory=self.dorm1, role='owner')
        self.assertIn('Dorm Alpha', str(role))
        self.assertIn('owner', str(role))


class ActiveDormitoryMiddlewareTests(_DormFixture, TestCase):

    def _request_with_session(self, user, session_dorm_id=None):
        factory = RequestFactory()
        request = factory.get('/')
        request.user = user
        mw = SessionMiddleware(lambda r: None)
        mw.process_request(request)
        request.session.save()
        if session_dorm_id is not None:
            request.session['active_dormitory_id'] = str(session_dorm_id)
            request.session.save()
        return request

    def test_falls_back_to_user_dormitory(self):
        request = self._request_with_session(self.owner)
        self.assertEqual(ActiveDormitoryMiddleware._resolve(request), self.dorm1)

    def test_uses_session_dormitory_when_user_has_role(self):
        UserDormitoryRole.objects.create(user=self.owner, dormitory=self.dorm2, role='owner')
        request = self._request_with_session(self.owner, session_dorm_id=self.dorm2.pk)
        self.assertEqual(ActiveDormitoryMiddleware._resolve(request), self.dorm2)

    def test_clears_session_when_user_has_no_role(self):
        request = self._request_with_session(self.owner, session_dorm_id=self.dorm2.pk)
        result = ActiveDormitoryMiddleware._resolve(request)
        self.assertEqual(result, self.dorm1)
        self.assertNotIn('active_dormitory_id', request.session)

    def test_unauthenticated_returns_none(self):
        from django.contrib.auth.models import AnonymousUser
        factory = RequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        self.assertIsNone(ActiveDormitoryMiddleware._resolve(request))


class PropertySwitchViewTests(_DormFixture, TestCase):

    def setUp(self):
        UserDormitoryRole.objects.create(user=self.owner, dormitory=self.dorm1, role='owner', is_primary=True)
        UserDormitoryRole.objects.create(user=self.owner, dormitory=self.dorm2, role='owner')
        self.client.force_login(self.owner)

    def test_switch_to_accessible_dormitory(self):
        resp = self.client.post('/property/switch/', {'dormitory_id': self.dorm2.pk, 'next': '/dashboard/'})
        self.assertRedirects(resp, '/dashboard/', fetch_redirect_response=False)
        self.assertEqual(self.client.session.get('active_dormitory_id'), str(self.dorm2.pk))

    def test_switch_to_inaccessible_dormitory_is_rejected(self):
        stranger = Dormitory.objects.create(name='Stranger', address='X', invoice_prefix='X01')
        self.client.post('/property/switch/', {'dormitory_id': stranger.pk})
        self.assertNotEqual(self.client.session.get('active_dormitory_id'), stranger.pk)

    def test_get_returns_405(self):
        self.assertEqual(self.client.get('/property/switch/').status_code, 405)

    def test_unauthenticated_redirects_to_login(self):
        self.client.logout()
        resp = self.client.post('/property/switch/', {'dormitory_id': self.dorm1.pk})
        self.assertRedirects(resp, '/login/?next=/property/switch/', fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# AuditMixin Tests
# ---------------------------------------------------------------------------

class _AuditFixture:
    """Common setup สำหรับ audit tests: สร้าง dormitory, owner, building, floor."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm1 = Dormitory.objects.create(
            name='Audit Dorm A', address='1 Audit Rd', invoice_prefix='AU1'
        )
        cls.dorm2 = Dormitory.objects.create(
            name='Audit Dorm B', address='2 Audit Rd', invoice_prefix='AU2'
        )
        cls.owner_a = CustomUser.objects.create_user(
            'audit_owner_a', password='pass', role='owner', dormitory=cls.dorm1
        )
        cls.owner_b = CustomUser.objects.create_user(
            'audit_owner_b', password='pass', role='owner', dormitory=cls.dorm2
        )

    def _set_thread_user(self, user):
        """Set thread-local user ให้ AuditMixin สามารถ capture user ได้."""
        from apps.core.threadlocal import set_current_user, set_current_dormitory
        set_current_user(user)
        if user and hasattr(user, 'dormitory') and user.dormitory:
            set_current_dormitory(user.dormitory)

    def _clear_thread(self):
        from apps.core.threadlocal import clear_current_user, clear_current_dormitory
        clear_current_user()
        clear_current_dormitory()


class AuditMixinRoomTests(_AuditFixture, TestCase):
    """ทดสอบ AuditMixin บน Room model (critical model)."""

    def setUp(self):
        from apps.rooms.models import Building, Floor
        self.building = Building.objects.create(name='Bldg A', dormitory=self.dorm1)
        self.floor = Floor.objects.create(building=self.building, number=1, dormitory=self.dorm1)

    def tearDown(self):
        self._clear_thread()

    def test_create_room_generates_audit_entry(self):
        """สร้าง Room ต้องสร้าง ActivityLog action=create."""
        from apps.rooms.models import Room

        self._set_thread_user(self.owner_a)
        room = Room.objects.create(
            floor=self.floor, number='101', base_rent=3000, dormitory=self.dorm1
        )

        log = ActivityLog.unscoped_objects.filter(
            model_name='Room', action='create', record_id=str(room.pk)
        ).first()

        self.assertIsNotNone(log, "ต้องมี audit log action=create")
        self.assertIsNone(log.old_value, "create ต้องไม่มี old_value")
        self.assertIsNotNone(log.new_value, "create ต้องมี new_value")
        self.assertEqual(log.user, self.owner_a)
        self.assertEqual(log.dormitory, self.dorm1)

    def test_update_room_logs_changed_fields_only(self):
        """Update Room ต้อง log เฉพาะ fields ที่เปลี่ยน old→new."""
        from apps.rooms.models import Room

        self._set_thread_user(self.owner_a)
        room = Room.objects.create(
            floor=self.floor, number='102', base_rent=3000,
            status='vacant', dormitory=self.dorm1
        )

        # เปลี่ยน status เป็น occupied
        room.status = 'occupied'
        room.save()

        log = ActivityLog.unscoped_objects.filter(
            model_name='Room', action='update', record_id=str(room.pk)
        ).first()

        self.assertIsNotNone(log, "ต้องมี audit log action=update")
        self.assertIn('status', log.old_value, "old_value ต้องมี status field")
        self.assertEqual(log.old_value['status'], 'vacant')
        self.assertEqual(log.new_value['status'], 'occupied')
        # fields ที่ไม่เปลี่ยนต้องไม่อยู่ใน old_value
        self.assertNotIn('number', log.old_value)

    def test_delete_room_logs_old_value(self):
        """Delete Room ต้อง log action=delete พร้อม old_value."""
        from apps.rooms.models import Room

        self._set_thread_user(self.owner_a)
        room = Room.objects.create(
            floor=self.floor, number='103', base_rent=4000,
            status='vacant', dormitory=self.dorm1
        )
        room_pk = str(room.pk)

        room.delete()

        log = ActivityLog.unscoped_objects.filter(
            model_name='Room', action='delete', record_id=room_pk
        ).first()

        self.assertIsNotNone(log, "ต้องมี audit log action=delete")
        self.assertIsNotNone(log.old_value, "delete ต้องมี old_value")
        self.assertIsNone(log.new_value, "delete ต้องไม่มี new_value")

    def test_no_audit_log_when_no_real_change(self):
        """Save โดยไม่เปลี่ยนค่าใด ไม่ควรสร้าง update log."""
        from apps.rooms.models import Room

        self._set_thread_user(self.owner_a)
        room = Room.objects.create(
            floor=self.floor, number='104', base_rent=3500,
            status='vacant', dormitory=self.dorm1
        )

        # Count logs ก่อน
        before_count = ActivityLog.unscoped_objects.filter(
            model_name='Room', action='update', record_id=str(room.pk)
        ).count()

        # Save โดยไม่เปลี่ยนค่า
        room.save()

        after_count = ActivityLog.unscoped_objects.filter(
            model_name='Room', action='update', record_id=str(room.pk)
        ).count()

        self.assertEqual(before_count, after_count, "ไม่ควรสร้าง update log ถ้าไม่มีการเปลี่ยนแปลง")


class AuditLogTenantIsolationTests(_AuditFixture, TestCase):
    """ทดสอบ tenant isolation: Owner A ต้องไม่เห็น log ของ Owner B."""

    def setUp(self):
        from apps.rooms.models import Building, Floor, Room

        # สร้าง rooms ใน dorm1 และ dorm2
        bldg_a = Building.objects.create(name='Bldg A', dormitory=self.dorm1)
        floor_a = Floor.objects.create(building=bldg_a, number=1, dormitory=self.dorm1)

        bldg_b = Building.objects.create(name='Bldg B', dormitory=self.dorm2)
        floor_b = Floor.objects.create(building=bldg_b, number=1, dormitory=self.dorm2)

        from apps.core.threadlocal import set_current_user, set_current_dormitory, clear_current_user, clear_current_dormitory

        # สร้าง room ใน dorm1 (owner_a)
        set_current_user(self.owner_a)
        set_current_dormitory(self.dorm1)
        self.room_a = Room.objects.create(
            floor=floor_a, number='A01', base_rent=3000, dormitory=self.dorm1
        )
        clear_current_user()
        clear_current_dormitory()

        # สร้าง room ใน dorm2 (owner_b)
        set_current_user(self.owner_b)
        set_current_dormitory(self.dorm2)
        self.room_b = Room.objects.create(
            floor=floor_b, number='B01', base_rent=4000, dormitory=self.dorm2
        )
        clear_current_user()
        clear_current_dormitory()

    def test_owner_a_cannot_see_dorm_b_logs_via_view(self):
        """Owner A เข้า /audit-log/ ต้องไม่เห็น log ของ dorm2."""
        from django.contrib.sessions.middleware import SessionMiddleware

        self.client.force_login(self.owner_a)

        # Set session dormitory ให้ owner_a ใช้ dorm1
        session = self.client.session
        session['active_dormitory_id'] = str(self.dorm1.pk)
        session.save()

        resp = self.client.get('/audit-log/')
        self.assertEqual(resp.status_code, 200)

        # ตรวจสอบว่า log ที่แสดงทั้งหมดเป็นของ dorm1 เท่านั้น
        # page_obj.object_list เป็น list (หลังผ่าน paginator) ต้องใช้ set comprehension
        page_logs = list(resp.context['page_obj'].object_list)
        wrong_dorms = {
            str(log.dormitory_id)
            for log in page_logs
            if log.dormitory_id != self.dorm1.pk
        }
        self.assertFalse(
            wrong_dorms,
            f"พบ log จาก dormitory อื่น: {wrong_dorms} — ต้องเห็นเฉพาะ dorm1"
        )

    def test_audit_log_correctly_scoped_to_dormitory(self):
        """ActivityLog ที่สร้างจาก Room ต้องมี dormitory_id ถูกต้อง."""
        log_for_room_a = ActivityLog.unscoped_objects.filter(
            model_name='Room', action='create', record_id=str(self.room_a.pk)
        ).first()
        log_for_room_b = ActivityLog.unscoped_objects.filter(
            model_name='Room', action='create', record_id=str(self.room_b.pk)
        ).first()

        self.assertIsNotNone(log_for_room_a)
        self.assertIsNotNone(log_for_room_b)
        self.assertEqual(log_for_room_a.dormitory_id, self.dorm1.pk)
        self.assertEqual(log_for_room_b.dormitory_id, self.dorm2.pk)


class AuditLogViewAccessTests(_AuditFixture, TestCase):
    """ทดสอบ access control ของ /audit-log/ view."""

    def test_owner_can_access_audit_log(self):
        """Owner ต้องเข้า /audit-log/ ได้."""
        self.client.force_login(self.owner_a)
        resp = self.client.get('/audit-log/')
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirects_to_login(self):
        """ไม่ login ต้อง redirect ไป login."""
        resp = self.client.get('/audit-log/')
        self.assertRedirects(
            resp, '/login/?next=/audit-log/', fetch_redirect_response=False
        )

    def test_tenant_user_redirected_to_dashboard(self):
        """Tenant role ต้องได้รับ 403 เมื่อพยายามเข้า /audit-log/ (OwnerRequiredMixin)."""
        tenant_user = CustomUser.objects.create_user(
            'audit_tenant', password='pass', role='tenant', dormitory=self.dorm1
        )
        self.client.force_login(tenant_user)
        resp = self.client.get('/audit-log/')
        # OwnerRequiredMixin คืน 403 PermissionDenied — ไม่ redirect
        self.assertEqual(resp.status_code, 403)

    def test_staff_user_redirected_from_audit_log(self):
        """Staff role ต้องได้รับ 403 เมื่อพยายามเข้า /audit-log/ (OwnerRequiredMixin)."""
        staff_user = CustomUser.objects.create_user(
            'audit_staff', password='pass', role='staff', dormitory=self.dorm1
        )
        self.client.force_login(staff_user)
        resp = self.client.get('/audit-log/')
        # OwnerRequiredMixin คืน 403 PermissionDenied — ไม่ redirect
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Data Import Wizard Tests
# ---------------------------------------------------------------------------

import io
import openpyxl


def _make_rooms_xlsx(rows, headers=None):
    """
    Helper สร้าง .xlsx bytes สำหรับ import rooms
    rows: list of tuples (building_name, floor_number, room_number, room_type, base_rent, status)
    """
    if headers is None:
        headers = ['building_name', 'floor_number', 'room_number', 'room_type', 'base_rent', 'status']
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _make_tenants_xlsx(rows, headers=None):
    """
    Helper สร้าง .xlsx bytes สำหรับ import tenants
    rows: list of tuples (room_number, building_name, first_name, last_name, phone, email, line_id, start_date)
    """
    if headers is None:
        headers = ['room_number', 'building_name', 'first_name', 'last_name', 'phone', 'email', 'line_id', 'start_date']
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class _ImportFixture:
    """Common fixture สำหรับ import tests: dorm + owner + building + floor."""

    @classmethod
    def setUpTestData(cls):
        cls.dorm = Dormitory.objects.create(
            name='Import Dorm', address='1 Import Rd', invoice_prefix='IMP'
        )
        cls.dorm2 = Dormitory.objects.create(
            name='Other Dorm', address='2 Other Rd', invoice_prefix='OTH'
        )
        cls.owner = CustomUser.objects.create_user(
            'import_owner', password='pass', role='owner', dormitory=cls.dorm
        )
        cls.owner2 = CustomUser.objects.create_user(
            'import_owner2', password='pass', role='owner', dormitory=cls.dorm2
        )
        # สร้าง UserDormitoryRole เพื่อให้ middleware resolve dormitory ได้
        UserDormitoryRole.objects.create(
            user=cls.owner, dormitory=cls.dorm, role='owner', is_primary=True
        )
        UserDormitoryRole.objects.create(
            user=cls.owner2, dormitory=cls.dorm2, role='owner', is_primary=True
        )


class ImportRoomsViewTests(_ImportFixture, TestCase):
    """ทดสอบ Import Rooms view."""

    def setUp(self):
        self.client.force_login(self.owner)
        # ตั้ง session dormitory
        session = self.client.session
        session['active_dormitory_id'] = str(self.dorm.pk)
        session.save()

    # --- GET ---

    def test_get_returns_200(self):
        """GET /import/rooms/ ต้อง return 200."""
        resp = self.client.get('/import/rooms/')
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirects_to_login(self):
        """ไม่ login ต้อง redirect ไป login."""
        self.client.logout()
        resp = self.client.get('/import/rooms/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_staff_gets_403(self):
        """Staff role ต้องได้ 403."""
        staff = CustomUser.objects.create_user('imp_staff', password='pass', role='staff', dormitory=self.dorm)
        self.client.force_login(staff)
        resp = self.client.get('/import/rooms/')
        self.assertEqual(resp.status_code, 403)

    # --- Download template ---

    def test_download_template_returns_xlsx(self):
        """POST action=download ต้องส่งไฟล์ .xlsx กลับ."""
        resp = self.client.post('/import/rooms/', {'action': 'download'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        self.assertIn('rooms_import_template.xlsx', resp['Content-Disposition'])

    # --- Upload + validate ---

    def test_upload_valid_excel_shows_preview(self):
        """Upload valid .xlsx ต้องแสดง preview rows ใน response."""
        xlsx_bytes = _make_rooms_xlsx([
            ('Building A', 1, '101', 'Standard', 5000, 'vacant'),
            ('Building A', 1, '102', 'Standard', 5000, 'vacant'),
        ])
        resp = self.client.post(
            '/import/rooms/',
            {'action': 'upload', 'excel_file': io.BytesIO(xlsx_bytes.read())},
            format='multipart',
        )
        # xlsx_bytes เป็น BytesIO — ต้องส่งเป็น InMemoryUploadedFile
        # ทดสอบผ่าน SimpleUploadedFile แทน
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes.seek(0)
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.context.get('preview_rows'))
        self.assertEqual(len(resp.context['preview_rows']), 2)

    def test_upload_stores_preview_in_session(self):
        """หลัง upload สำเร็จ ต้องมี import_rooms_preview ใน session."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_rooms_xlsx([('Building A', 1, '101', 'Standard', 5000, 'vacant')])
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        self.assertIn('import_rooms_preview', self.client.session)

    def test_upload_missing_column_shows_error(self):
        """ถ้า header ไม่ครบ ต้องแสดง error."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        # ไม่มี column 'status'
        xlsx_bytes = _make_rooms_xlsx(
            [('Building A', 1, '101', 'Standard', 5000)],
            headers=['building_name', 'floor_number', 'room_number', 'room_type', 'base_rent']
        )
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.context.get('errors'))
        self.assertIsNone(resp.context.get('preview_rows'))

    def test_upload_invalid_status_shows_error(self):
        """status ที่ไม่ valid ต้องแสดง error พร้อม row number."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_rooms_xlsx([('Building A', 1, '101', 'Standard', 5000, 'unknown_status')])
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        errors = resp.context.get('errors', [])
        self.assertTrue(len(errors) > 0)
        # error ต้องระบุ row number
        self.assertTrue(any('Row 2' in e for e in errors))

    def test_upload_duplicate_room_in_file_shows_error(self):
        """duplicate entry ภายในไฟล์เดียวกัน ต้องแสดง error."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_rooms_xlsx([
            ('Building A', 1, '101', 'Standard', 5000, 'vacant'),
            ('Building A', 1, '101', 'Standard', 5000, 'vacant'),  # ซ้ำ
        ])
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        errors = resp.context.get('errors', [])
        self.assertTrue(len(errors) > 0)

    def test_upload_room_already_in_db_shows_error(self):
        """ห้องที่มีอยู่แล้วใน DB ต้องแสดง error (ไม่ซ้ำ)."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.rooms.models import Building, Floor, Room
        # สร้างห้องก่อน
        bldg = Building.objects.create(name='Building A', dormitory=self.dorm)
        floor = Floor.objects.create(building=bldg, number=1, dormitory=self.dorm)
        Room.objects.create(floor=floor, number='101', dormitory=self.dorm)

        xlsx_bytes = _make_rooms_xlsx([('Building A', 1, '101', 'Standard', 5000, 'vacant')])
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        errors = resp.context.get('errors', [])
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any('already exists' in e for e in errors))

    def test_upload_invalid_floor_number_shows_error(self):
        """floor_number ที่ไม่ใช่ตัวเลข ต้องแสดง error."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_rooms_xlsx([('Building A', 'ABC', '101', 'Standard', 5000, 'vacant')])
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        errors = resp.context.get('errors', [])
        self.assertTrue(len(errors) > 0)

    # --- Confirm import ---

    def test_confirm_creates_rooms(self):
        """POST action=confirm ต้องสร้าง rooms ใน DB จาก preview session."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.rooms.models import Room

        # Step 1: upload ก่อน
        xlsx_bytes = _make_rooms_xlsx([
            ('Building B', 2, '201', 'Standard', 6000, 'vacant'),
            ('Building B', 2, '202', 'Deluxe', 7000, 'vacant'),
        ])
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})

        # Step 2: confirm
        before_count = Room.unscoped_objects.filter(dormitory=self.dorm).count()
        resp = self.client.post('/import/rooms/', {'action': 'confirm'})

        # ต้อง redirect ไป rooms:list
        self.assertEqual(resp.status_code, 302)
        after_count = Room.unscoped_objects.filter(dormitory=self.dorm).count()
        self.assertEqual(after_count - before_count, 2)

    def test_confirm_clears_session_preview(self):
        """หลัง confirm สำเร็จ session ต้องไม่มี import_rooms_preview แล้ว."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_rooms_xlsx([('Building C', 3, '301', 'Standard', 5000, 'vacant')])
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        self.client.post('/import/rooms/', {'action': 'confirm'})
        self.assertNotIn('import_rooms_preview', self.client.session)

    def test_confirm_without_preview_redirects(self):
        """POST action=confirm โดยไม่มี session preview ต้อง redirect กลับ."""
        resp = self.client.post('/import/rooms/', {'action': 'confirm'})
        self.assertEqual(resp.status_code, 302)

    # --- Tenant isolation ---

    def test_tenant_isolation_rooms_not_cross_dormitory(self):
        """Import rooms ของ owner ต้องอยู่ใน dormitory ของตัวเองเท่านั้น ไม่ข้าม dormitory."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.rooms.models import Room

        xlsx_bytes = _make_rooms_xlsx([('Building D', 1, '101', 'Standard', 5000, 'vacant')])
        f = SimpleUploadedFile('rooms.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post('/import/rooms/', {'action': 'upload', 'excel_file': f})
        self.client.post('/import/rooms/', {'action': 'confirm'})

        # Room ต้องไม่ปรากฏใน dorm2
        self.assertFalse(
            Room.unscoped_objects.filter(dormitory=self.dorm2, number='101').exists()
        )
        # Room ต้องอยู่ใน dorm1 เท่านั้น
        self.assertTrue(
            Room.unscoped_objects.filter(dormitory=self.dorm, number='101').exists()
        )


class ImportTenantsViewTests(_ImportFixture, TestCase):
    """ทดสอบ Import Tenants view."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # สร้าง building + floor + room สำหรับทดสอบ import tenant
        from apps.rooms.models import Building, Floor, Room
        cls.building = Building.objects.create(name='Building A', dormitory=cls.dorm)
        cls.floor = Floor.objects.create(building=cls.building, number=1, dormitory=cls.dorm)
        cls.room = Room.objects.create(
            floor=cls.floor, number='101', dormitory=cls.dorm, status='vacant'
        )
        # สร้าง room ใน dorm2 เพื่อทดสอบ isolation
        cls.building2 = Building.objects.create(name='Building X', dormitory=cls.dorm2)
        cls.floor2 = Floor.objects.create(building=cls.building2, number=1, dormitory=cls.dorm2)
        cls.room2 = Room.objects.create(
            floor=cls.floor2, number='101', dormitory=cls.dorm2, status='vacant'
        )

    def setUp(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session['active_dormitory_id'] = str(self.dorm.pk)
        session.save()

    def test_get_returns_200(self):
        """GET /import/tenants/ ต้อง return 200."""
        resp = self.client.get('/import/tenants/')
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirects_to_login(self):
        """ไม่ login ต้อง redirect ไป login."""
        self.client.logout()
        resp = self.client.get('/import/tenants/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_download_template_returns_xlsx(self):
        """POST action=download ต้องส่งไฟล์ .xlsx กลับ."""
        resp = self.client.post('/import/tenants/', {'action': 'download'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        self.assertIn('tenants_import_template.xlsx', resp['Content-Disposition'])

    def test_upload_valid_excel_shows_preview(self):
        """Upload .xlsx ที่ valid ต้องแสดง preview."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_tenants_xlsx([
            ('101', 'Building A', 'สมชาย', 'ใจดี', '0891234567', 'somchai@test.com', '@line1', '2026-01-01'),
        ])
        f = SimpleUploadedFile('tenants.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/tenants/', {'action': 'upload', 'excel_file': f})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.context.get('preview_rows'))
        self.assertEqual(len(resp.context['preview_rows']), 1)

    def test_upload_invalid_date_format_shows_error(self):
        """start_date ที่ format ผิด ต้องแสดง error พร้อม row number."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_tenants_xlsx([
            ('101', 'Building A', 'สมชาย', 'ใจดี', '0891234567', 'somchai2@test.com', '', 'not-a-date'),
        ])
        f = SimpleUploadedFile('tenants.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/tenants/', {'action': 'upload', 'excel_file': f})
        errors = resp.context.get('errors', [])
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any('Row 2' in e for e in errors))

    def test_upload_room_not_in_dormitory_shows_error(self):
        """room ที่ไม่มีใน dormitory ต้องแสดง error."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_tenants_xlsx([
            ('999', 'Building A', 'สมชาย', 'ใจดี', '', 'somchai3@test.com', '', '2026-01-01'),
        ])
        f = SimpleUploadedFile('tenants.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/tenants/', {'action': 'upload', 'excel_file': f})
        errors = resp.context.get('errors', [])
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any('not found' in e for e in errors))

    def test_upload_missing_columns_shows_error(self):
        """ถ้า header ไม่ครบ ต้องแสดง error."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        xlsx_bytes = _make_tenants_xlsx(
            [('101', 'Building A', 'สมชาย', 'ใจดี')],
            headers=['room_number', 'building_name', 'first_name', 'last_name']
        )
        f = SimpleUploadedFile('tenants.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp = self.client.post('/import/tenants/', {'action': 'upload', 'excel_file': f})
        errors = resp.context.get('errors', [])
        self.assertTrue(len(errors) > 0)

    def test_confirm_creates_user_and_profile_and_lease(self):
        """POST action=confirm ต้องสร้าง CustomUser + TenantProfile + Lease."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.core.models import CustomUser
        from apps.tenants.models import TenantProfile, Lease

        xlsx_bytes = _make_tenants_xlsx([
            ('101', 'Building A', 'สมหญิง', 'ดีใจ', '0891111111', 'somying@test.com', '@line2', '2026-03-01'),
        ])
        f = SimpleUploadedFile('tenants.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post('/import/tenants/', {'action': 'upload', 'excel_file': f})
        resp = self.client.post('/import/tenants/', {'action': 'confirm'})

        self.assertEqual(resp.status_code, 302)

        # ตรวจ user สร้างแล้ว
        user = CustomUser.objects.filter(first_name='สมหญิง', last_name='ดีใจ').first()
        self.assertIsNotNone(user, 'ต้องสร้าง CustomUser สำหรับผู้เช่า')
        self.assertEqual(user.role, CustomUser.Role.TENANT)

        # ตรวจ TenantProfile
        profile = TenantProfile.unscoped_objects.filter(user=user).first()
        self.assertIsNotNone(profile, 'ต้องสร้าง TenantProfile')
        self.assertEqual(profile.dormitory, self.dorm)

        # ตรวจ Lease
        lease = Lease.unscoped_objects.filter(tenant=profile).first()
        self.assertIsNotNone(lease, 'ต้องสร้าง Lease')
        self.assertEqual(str(lease.start_date), '2026-03-01')
        self.assertEqual(lease.status, Lease.Status.ACTIVE)

    def test_confirm_updates_room_status_to_occupied(self):
        """หลัง import tenant สำเร็จ สถานะห้องต้องเป็น occupied."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.rooms.models import Room

        xlsx_bytes = _make_tenants_xlsx([
            ('101', 'Building A', 'ทดสอบ', 'ห้อง', '', 'testroom@test.com', '', '2026-03-01'),
        ])
        f = SimpleUploadedFile('tenants.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.client.post('/import/tenants/', {'action': 'upload', 'excel_file': f})
        self.client.post('/import/tenants/', {'action': 'confirm'})

        self.room.refresh_from_db()
        self.assertEqual(self.room.status, Room.Status.OCCUPIED)

    def test_tenant_isolation_cannot_import_to_other_dormitory(self):
        """
        Owner ของ dorm1 ต้องไม่สามารถ import tenant เข้า dorm2 ได้
        ห้อง 101 ใน dorm2 ต้องไม่มี tenant ที่สร้างจาก dorm1 session
        """
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.tenants.models import TenantProfile

        # Upload โดยใช้ session ของ dorm1 แต่ระบุ room ที่มีอยู่ใน dorm1 เท่านั้น
        # เพราะ parser จะ query เฉพาะ dorm ของ active session
        # dorm2/room2 จะ "not found" สำหรับ owner ของ dorm1
        xlsx_bytes = _make_tenants_xlsx([
            ('101', 'Building X', 'ผิดDorm', 'คนนี้', '', 'wrongdorm@test.com', '', '2026-01-01'),
        ])
        f = SimpleUploadedFile('tenants.xlsx', xlsx_bytes.read(),
                               content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        # Session ของ dorm1 — Building X ไม่มีใน dorm1
        resp = self.client.post('/import/tenants/', {'action': 'upload', 'excel_file': f})
        errors = resp.context.get('errors', [])
        # ต้องมี error เพราะ Building X ไม่ได้อยู่ใน dorm1
        self.assertTrue(len(errors) > 0, 'ต้องมี error ถ้า room ไม่ได้อยู่ใน dormitory นี้')

        # ตรวจว่าไม่มี TenantProfile ถูกสร้างสำหรับ dorm2
        self.assertFalse(
            TenantProfile.unscoped_objects.filter(dormitory=self.dorm2, user__first_name='ผิดDorm').exists()
        )

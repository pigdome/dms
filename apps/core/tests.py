from django.test import SimpleTestCase, TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core.models import CustomUser, Dormitory, UserDormitoryRole
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
